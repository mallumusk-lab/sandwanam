"""Backup file format (version 2).

{
  "format_version": 2,
  "created_at": "...",
  "tables": {"customers": {"columns": [...], "rows": [[...], ...]}, ...}
}

Only business data is included. Credentials, sessions, throttling state, audit logs
and stored snapshots are never exported or restored. Every value is coerced from the
declared column type, and unknown tables or columns are rejected, so a crafted file
cannot inject SQL identifiers.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .dates import as_aware, parse_timestamp

FORMAT_VERSION = 2
MAX_ROWS_PER_TABLE = 500_000

# Restore order matters (foreign keys): parents first.
TABLES: dict[str, tuple[tuple[str, str], ...]] = {
    "branches": (
        ("username", "text"), ("display_name", "text"), ("address", "text"), ("phone", "text"),
        ("email", "text"), ("logo", "text"), ("permissions", "text"), ("branch_prefix", "text"),
        ("account_type", "text"),
    ),
    "branch_counters": (("branch_prefix", "text"), ("next_customer_no", "int")),
    "customers": (
        ("customerid", "int"), ("customername", "text"), ("phone", "text"), ("address", "text"),
        ("loanstatus", "text"), ("role", "text"), ("user_id", "text"), ("branch_prefix", "text"),
        ("last_loan_no", "int"), ("created_at", "timestamptz"),
    ),
    "loan_data": (
        ("loanid", "int"), ("customerid", "int"), ("loanstatus", "text"), ("particulars", "text"),
        ("particulars_qty", "text"), ("loan_number", "text"), ("number_of_items", "text"),
        ("weight", "decimal"), ("net_weight", "decimal"), ("principle_amount", "decimal"),
        ("interest", "decimal"), ("tenure", "int"), ("deduction", "decimal"), ("role", "text"),
        ("date", "timestamptz"), ("loantype", "text"), ("refreshprincipleamount", "decimal"),
        ("refreshinterest", "decimal"), ("follow_up_date", "date"), ("closed_at", "timestamptz"),
        ("items", "json"), ("created_by", "text"),
    ),
    "statement": (
        ("statementid", "int"), ("loanid", "int"), ("loan_number", "text"), ("amountpaid", "decimal"),
        ("date", "timestamptz"), ("currentprincipal", "decimal"), ("currentinterest", "decimal"),
        ("principlebalance", "decimal"), ("interestbalance", "decimal"), ("transactiontype", "text"),
        ("accrued_days", "int"), ("writeoff_principal", "decimal"), ("writeoff_interest", "decimal"),
        ("client_request_id", "text"), ("created_by", "text"), ("created_at", "timestamptz"),
    ),
    "app_settings": (("key", "text"), ("value", "json"), ("updated_at", "timestamptz"), ("updated_by", "text")),
}
REQUIRED_TABLES = ("customers", "loan_data", "statement")


class BackupFormatError(ValueError):
    pass


def columns(table: str) -> list[str]:
    return [name for name, _ in TABLES[table]]


def _encode_value(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind == "decimal":
        return str(value)
    if kind == "timestamptz":
        return as_aware(value).isoformat()
    if kind == "date":
        return value.isoformat()
    if kind == "json":
        return json.loads(value) if isinstance(value, str) else value
    return value


def _decode_value(value: Any, kind: str, where: str) -> Any:
    if value is None:
        return None
    try:
        if kind == "text":
            if not isinstance(value, str):
                raise TypeError
            return value
        if kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError
            return value
        if kind == "decimal":
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise TypeError
            result = Decimal(str(value))
            if not result.is_finite():
                raise TypeError
            return result
        if kind == "timestamptz":
            return parse_timestamp(value)
        if kind == "date":
            return date.fromisoformat(value)
        if kind == "json":
            return json.dumps(value)
    except (TypeError, ValueError, InvalidOperation, AttributeError) as exc:
        raise BackupFormatError(f"Invalid {kind} value in {where}.") from exc
    raise BackupFormatError(f"Unsupported column type in {where}.")


def encode(rows_by_table: Mapping[str, list[Mapping[str, Any]]], created_at: datetime) -> dict:
    tables: dict[str, dict] = {}
    for table, spec in TABLES.items():
        rows = rows_by_table.get(table, [])
        tables[table] = {
            "columns": [name for name, _ in spec],
            "rows": [[_encode_value(row.get(name), kind) for name, kind in spec] for row in rows],
        }
    return {"format_version": FORMAT_VERSION, "created_at": as_aware(created_at).isoformat(), "tables": tables}


def decode(payload: Any) -> dict[str, list[tuple]]:
    """Validate a backup and return rows per table, in `columns(table)` order."""
    if not isinstance(payload, dict):
        raise BackupFormatError("The backup file is not a JSON object.")
    if payload.get("format_version") != FORMAT_VERSION:
        raise BackupFormatError(
            "This backup was not created by this version of the application and cannot be restored."
        )
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise BackupFormatError("The backup has no tables.")
    unknown = sorted(set(tables) - set(TABLES))
    if unknown:
        raise BackupFormatError(f"Unknown tables in backup: {', '.join(unknown)}.")
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    if missing:
        raise BackupFormatError(f"The backup is missing: {', '.join(missing)}.")
    result: dict[str, list[tuple]] = {}
    for table, spec in TABLES.items():
        block = tables.get(table)
        if block is None:
            result[table] = []
            continue
        if not isinstance(block, dict) or block.get("columns") != [name for name, _ in spec]:
            raise BackupFormatError(f"The columns of '{table}' do not match this application's schema.")
        rows = block.get("rows")
        if not isinstance(rows, list) or len(rows) > MAX_ROWS_PER_TABLE:
            raise BackupFormatError(f"The rows of '{table}' are invalid.")
        decoded = []
        for index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(spec):
                raise BackupFormatError(f"Row {index + 1} of '{table}' has the wrong number of values.")
            decoded.append(
                tuple(
                    _decode_value(value, kind, f"{table}.{name} row {index + 1}")
                    for value, (name, kind) in zip(row, spec)
                )
            )
        result[table] = decoded
    return result
