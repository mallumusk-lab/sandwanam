"""Accounts (the legacy `role` table), sessions and login throttling."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from . import Db

PUBLIC_COLUMNS = (
    "username, role, display_name, legal_name, logo, address, phone, email, permissions, "
    "account_type, branch_prefix, is_active, must_change_password, password_changed_at, created_at"
)
EDITABLE_SETTINGS = ("display_name", "legal_name", "logo", "address", "phone", "email", "permissions")


class UsersRepo:
    def __init__(self, db: Db):
        self.db = db

    async def get(self, username: str) -> dict | None:
        return await self.db.fetchrow(
            f"SELECT password, {PUBLIC_COLUMNS} FROM role WHERE lower(username) = lower($1)", username
        )

    async def list_accounts(self) -> list[dict]:
        return await self.db.fetch(
            f"""
            SELECT {PUBLIC_COLUMNS}, (password IS NOT NULL) AS has_password
            FROM role ORDER BY CASE account_type WHEN 'superadmin' THEN 0 WHEN 'hq' THEN 1 ELSE 2 END, username
            """
        )

    async def branches(self) -> list[dict]:
        return await self.db.fetch(
            """
            SELECT username, display_name, legal_name, logo, address, phone, email, branch_prefix, account_type
            FROM role WHERE branch_prefix IS NOT NULL
            ORDER BY CASE account_type WHEN 'hq' THEN 0 ELSE 1 END, display_name
            """
        )

    async def branch(self, prefix: str) -> dict | None:
        return await self.db.fetchrow(
            """
            SELECT username, display_name, legal_name, logo, address, phone, email, branch_prefix, account_type
            FROM role WHERE branch_prefix = $1
            """,
            prefix,
        )

    async def branch_prefixes(self) -> set[str]:
        rows = await self.db.fetch("SELECT branch_prefix FROM role WHERE branch_prefix IS NOT NULL")
        return {row["branch_prefix"] for row in rows}

    async def create(
        self,
        *,
        username: str,
        password_hash: str,
        account_type: str,
        branch_prefix: str | None,
        display_name: str,
        legal_name: str | None,
        address: str | None,
        phone: str | None,
        email: str | None,
        logo: str | None,
        permissions: str,
    ) -> None:
        legacy_role = {"superadmin": "SuperAdmin", "hq": "Admin"}.get(account_type, username[:20])
        await self.db.execute(
            """
            INSERT INTO role (username, password, role, account_type, branch_prefix, display_name, legal_name,
                              address, phone, email, logo, permissions, is_active, must_change_password)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, TRUE, TRUE)
            """,
            username, password_hash, legacy_role, account_type, branch_prefix, display_name, legal_name,
            address, phone, email, logo, permissions,
        )

    async def update_settings(self, username: str, fields: dict[str, Any]) -> None:
        columns = [name for name in EDITABLE_SETTINGS if name in fields]
        if not columns:
            return
        assignments = ", ".join(f"{name} = ${index}" for index, name in enumerate(columns, start=2))
        await self.db.execute(
            f"UPDATE role SET {assignments} WHERE username = $1", username, *(fields[name] for name in columns)
        )

    async def set_password(self, username: str, password_hash: str, *, must_change: bool) -> None:
        await self.db.execute(
            """
            UPDATE role SET password = $2, must_change_password = $3, password_changed_at = NOW()
            WHERE username = $1
            """,
            username, password_hash, must_change,
        )

    async def upgrade_hash(self, username: str, password_hash: str) -> None:
        await self.db.execute("UPDATE role SET password = $2 WHERE username = $1", username, password_hash)

    async def set_active(self, username: str, active: bool) -> None:
        await self.db.execute("UPDATE role SET is_active = $2 WHERE username = $1", username, active)

    async def delete(self, username: str) -> None:
        await self.db.execute("DELETE FROM role WHERE username = $1", username)

    async def customer_count(self, prefix: str) -> int:
        return await self.db.fetchval("SELECT COUNT(*) FROM customers WHERE branch_prefix = $1", prefix)

    async def ensure_counter(self, prefix: str) -> None:
        await self.db.execute(
            "INSERT INTO branch_counters (branch_prefix, next_customer_no, next_receipt_no) VALUES ($1, 1, 1) ON CONFLICT DO NOTHING",
            prefix,
        )


class SessionsRepo:
    def __init__(self, db: Db):
        self.db = db

    async def create(
        self, token_hash: bytes, username: str, now: datetime, expires_at: datetime, ip: str, user_agent: str
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO sessions (token_hash, username, created_at, last_seen_at, expires_at, ip, user_agent)
            VALUES ($1, $2, $3, $3, $4, $5, $6)
            """,
            token_hash, username, now, expires_at, ip, user_agent[:255],
        )

    async def get(self, token_hash: bytes) -> dict | None:
        return await self.db.fetchrow(
            f"""
            SELECT s.expires_at, s.last_seen_at, r.password, {", ".join("r." + c.strip() for c in PUBLIC_COLUMNS.split(","))}
            FROM sessions s JOIN role r ON r.username = s.username
            WHERE s.token_hash = $1
            """,
            token_hash,
        )

    async def touch(self, token_hash: bytes, now: datetime) -> None:
        await self.db.execute("UPDATE sessions SET last_seen_at = $2 WHERE token_hash = $1", token_hash, now)

    async def delete(self, token_hash: bytes) -> None:
        await self.db.execute("DELETE FROM sessions WHERE token_hash = $1", token_hash)

    async def delete_for_user(self, username: str, keep: bytes | None = None) -> None:
        await self.db.execute(
            "DELETE FROM sessions WHERE username = $1 AND ($2::bytea IS NULL OR token_hash <> $2)", username, keep
        )

    async def purge_expired(self, now: datetime, idle_cutoff: datetime) -> None:
        await self.db.execute(
            "DELETE FROM sessions WHERE expires_at <= $1 OR last_seen_at <= $2", now, idle_cutoff
        )


class ThrottleRepo:
    def __init__(self, db: Db):
        self.db = db

    async def get(self, username: str, key: str) -> dict | None:
        return await self.db.fetchrow(
            "SELECT failures, locked_until, updated_at FROM login_throttle WHERE username = lower($1) AND ip = $2",
            username, key,
        )

    async def purge(self, stale_before: datetime, now: datetime, trusted_before: datetime) -> None:
        await self.db.execute(
            """
            DELETE FROM login_throttle
            WHERE (ip NOT LIKE 'trusted:%' AND updated_at < $1 AND (locked_until IS NULL OR locked_until < $2))
               OR (ip LIKE 'trusted:%' AND updated_at < $3)
            """,
            stale_before, now, trusted_before,
        )

    async def lock_row(self, username: str, key: str, now: datetime) -> dict:
        """Create the counter if needed and lock it until the transaction ends, so
        concurrent sign-in attempts for the same key are counted one at a time."""
        await self.db.execute(
            """
            INSERT INTO login_throttle (username, ip, failures, locked_until, updated_at)
            VALUES (lower($1), $2, 0, NULL, $3) ON CONFLICT (username, ip) DO NOTHING
            """,
            username, key, now,
        )
        return await self.db.fetchrow(
            "SELECT failures, locked_until, updated_at FROM login_throttle WHERE username = lower($1) AND ip = $2 FOR UPDATE",
            username, key,
        )

    async def save(self, username: str, ip: str, failures: int, locked_until: datetime | None, now: datetime) -> None:
        await self.db.execute(
            """
            INSERT INTO login_throttle (username, ip, failures, locked_until, updated_at)
            VALUES (lower($1), $2, $3, $4, $5)
            ON CONFLICT (username, ip) DO UPDATE
                SET failures = EXCLUDED.failures, locked_until = EXCLUDED.locked_until, updated_at = EXCLUDED.updated_at
            """,
            username, ip, failures, locked_until, now,
        )

    async def clear(self, username: str, ip: str) -> None:
        await self.db.execute("DELETE FROM login_throttle WHERE username = lower($1) AND ip = $2", username, ip)

    async def clear_user(self, username: str) -> None:
        await self.db.execute("DELETE FROM login_throttle WHERE username = lower($1)", username)
