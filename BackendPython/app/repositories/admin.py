"""Audit log, settings and backups."""
from __future__ import annotations

import json
from typing import Any

from ..domain import backup_codec
from . import Db, like_pattern

_BRANCH_EXPORT = (
    "SELECT username, display_name, address, phone, email, logo, permissions, branch_prefix, account_type "
    "FROM role WHERE account_type <> 'superadmin' ORDER BY username"
)
_TABLE_ORDER_BY = {
    "branch_counters": "branch_prefix",
    "customers": "customerid",
    "loan_data": "loanid",
    "statement": "statementid",
    "app_settings": "key",
    "cash_days": "id",
    "cash_entries": "id",
}
# Restore order: parents first (cash_entries.day_id references cash_days; cash_days.branch_prefix
# references role, which a restore never touches).
_REPLACED_TABLES = ("customers", "loan_data", "statement", "cash_days", "cash_entries")
_SERIALS = (("customers", "customerid"), ("loan_data", "loanid"), ("statement", "statementid"),
            ("cash_days", "id"), ("cash_entries", "id"))

# Constraints added NOT VALID by migrations 002/003: legacy rows may not satisfy them until
# 004 validates them. A restore re-inserts every row, so they are dropped for the copy and
# recreated NOT VALID afterwards (same definitions as the migrations; same transaction).
_RELAXED_CONSTRAINTS = (
    ("loan_data", "loan_data_values_check",
     "CHECK (principle_amount > 0 AND COALESCE(weight, 0) >= 0 AND COALESCE(net_weight, 0) >= 0 "
     "AND COALESCE(deduction, 0) >= 0 AND loantype IN ('open', 'closed')) NOT VALID"),
    ("loan_data", "loan_data_customerid_fkey",
     "FOREIGN KEY (customerid) REFERENCES customers(customerid) ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID"),
    ("statement", "statement_loanid_fkey",
     "FOREIGN KEY (loanid) REFERENCES loan_data(loanid) ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID"),
    ("statement", "statement_loan_number_fkey",
     "FOREIGN KEY (loan_number) REFERENCES loan_data(loan_number) ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID"),
)


class AuditRepo:
    def __init__(self, db: Db):
        self.db = db

    async def log(
        self,
        *,
        username: str,
        action: str,
        entity_type: str,
        entity_id: str,
        details: str,
        ip: str | None = None,
        request_id: str | None = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO audit_logs (username, action, entity_type, entity_id, details, ip, request_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            username, action, entity_type, entity_id, details[:2000], ip, request_id,
        )

    async def page(self, term: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
        rows = await self.db.fetch(
            """
            SELECT log_id, username, action, entity_type, entity_id, details, timestamp, ip,
                   COUNT(*) OVER () AS total
            FROM audit_logs
            WHERE $1::text IS NULL OR username ILIKE $1 OR action ILIKE $1 OR entity_id ILIKE $1
            ORDER BY timestamp DESC, log_id DESC
            LIMIT $2 OFFSET $3
            """,
            like_pattern(term) if term else None, limit, offset,
        )
        total = rows[0]["total"] if rows else 0
        for row in rows:
            row.pop("total", None)
        return rows, total


class SettingsRepo:
    def __init__(self, db: Db):
        self.db = db

    async def get(self, key: str) -> dict | None:
        row = await self.db.fetchrow("SELECT value, updated_at, updated_by FROM app_settings WHERE key = $1", key)
        if row is None:
            return None
        value = row["value"]
        return {"value": json.loads(value) if isinstance(value, str) else value,
                "updated_at": row["updated_at"], "updated_by": row["updated_by"]}

    async def put(self, key: str, value: Any, updated_by: str) -> None:
        await self.db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES ($1, $2::jsonb, NOW(), $3)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW(), updated_by = EXCLUDED.updated_by
            """,
            key, json.dumps(value), updated_by,
        )


class BackupsRepo:
    def __init__(self, db: Db):
        self.db = db

    async def export_rows(self) -> dict[str, list[dict]]:
        rows: dict[str, list[dict]] = {"branches": await self.db.fetch(_BRANCH_EXPORT)}
        for table, order_by in _TABLE_ORDER_BY.items():
            columns = ", ".join(backup_codec.columns(table))
            rows[table] = await self.db.fetch(f"SELECT {columns} FROM {table} ORDER BY {order_by}")
        return rows

    async def missing_branches(self, prefixes: set[str]) -> list[str]:
        known = {r["branch_prefix"] for r in await self.db.fetch("SELECT branch_prefix FROM role WHERE branch_prefix IS NOT NULL")}
        return sorted(prefixes - known)

    async def replace_business_data(self, tables: dict[str, list[tuple]]) -> None:
        """Replace customers, loans, ledger and the cash ledger. Must run inside a transaction.

        Table and column names come from backup_codec's fixed schema, never from the file.
        """
        for table, name, _ in _RELAXED_CONSTRAINTS:
            await self.db.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        await self.db.execute("TRUNCATE cash_entries, cash_days, statement, loan_data, customers RESTART IDENTITY")
        for table in _REPLACED_TABLES:
            columns = backup_codec.columns(table)
            placeholders = ", ".join(
                f"${i}::jsonb" if name == "items" else f"${i}" for i, name in enumerate(columns, start=1)
            )
            await self.db.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", tables.get(table, [])
            )
        for table, name, definition in _RELAXED_CONSTRAINTS:
            await self.db.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} {definition}")
        for table, column in _SERIALS:
            await self.db.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
                f"COALESCE((SELECT MAX({column}) FROM {table}), 0) + 1, false)"
            )
        branch_columns = backup_codec.columns("branches")
        for row in tables.get("branches", []):
            record = dict(zip(branch_columns, row))
            # Letterhead details only: feature permissions are never re-granted by a restore.
            await self.db.execute(
                """
                UPDATE role SET display_name = $2, address = $3, phone = $4, email = $5, logo = $6
                WHERE username = $1 AND branch_prefix = $7
                """,
                record["username"], record["display_name"], record["address"], record["phone"], record["email"],
                record["logo"], record["branch_prefix"],
            )
        await self.db.executemany(
            """
            INSERT INTO branch_counters (branch_prefix, next_customer_no, next_receipt_no) VALUES ($1, $2, $3)
            ON CONFLICT (branch_prefix) DO UPDATE SET next_customer_no = EXCLUDED.next_customer_no, next_receipt_no = EXCLUDED.next_receipt_no
            """,
            tables.get("branch_counters", []),
        )
        await self.db.executemany(
            """
            INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES ($1, $2::jsonb, $3, $4)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at,
                                            updated_by = EXCLUDED.updated_by
            """,
            tables.get("app_settings", []),
        )
