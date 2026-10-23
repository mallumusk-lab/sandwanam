"""Backup file format (version 3; version 2 files are still read).

{
  "format_version": 3,
  "app": "gold-loan-desk",
  "schema": "<16 hex: fingerprint of TABLES>",
  "created_at": "...", "created_by": "...", "kind": "scheduled | manual",
  "manifest": {"tables": {"customers": {"rows": 12, "sha256": "..."}, ...}},
  "tables": {"customers": {"columns": [...], "rows": [[...], ...]}, ...},
  "checksum": "<sha256 of the canonical document without this key>"
}

Files are canonical JSON (sorted keys, no spaces, ASCII only, no NaN) and travel gzipped
(`.json.gz`); plain `.json` is accepted too. Version 2 files have no app, schema,
manifest or checksum.

Only business data is included. Credentials, sessions, throttling state, audit logs
and this server's own settings (LOCAL_SETTINGS) are never exported or restored. Every value is coerced from the declared column type, and unknown tables or
columns are rejected, so a crafted file cannot inject SQL identifiers.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import zlib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .dates import as_aware, parse_timestamp, to_ist

FORMAT_VERSION = 3
READABLE_VERSIONS = (2, 3)
APP_NAME = "gold-loan-desk"
MAX_ROWS_PER_TABLE = 500_000
MAX_UPLOAD_BYTES = 48 * 1024 * 1024  # decompressed size of a file sent from the browser
# Document kinds: "scheduled" is the nightly email, "manual" is "Email backup now".
KINDS = ("scheduled", "manual")
# Kinds written by earlier versions (before backups were email-only); such files still import.
OLDER_KINDS = ("pre_restore", "export")
# Settings that belong to this server (where backups are emailed), not to the business data.
LOCAL_SETTINGS = frozenset({"backup_email", "backup_email_status"})

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
    # Branch cash ledger (migration 005), independent of loans.
    "cash_days": (
        ("id", "int"), ("branch_prefix", "text"), ("day", "date"), ("carried_forward", "decimal"),
        ("opening_counted", "decimal"), ("opened_by", "text"), ("opened_at", "timestamptz"),
        ("client_request_id", "text"), ("closing_expected", "decimal"), ("closing_counted", "decimal"),
        ("closed_by", "text"), ("closed_at", "timestamptz"), ("closed_automatically", "bool"),
    ),
    "cash_entries": (
        ("id", "int"), ("day_id", "int"), ("direction", "text"), ("category", "text"), ("description", "text"),
        ("reference", "text"), ("amount", "decimal"), ("client_request_id", "text"), ("created_by", "text"),
        ("created_at", "timestamptz"), ("voided_at", "timestamptz"), ("voided_by", "text"),
        ("void_reason", "text"),
    ),
}
REQUIRED_TABLES = ("customers", "loan_data", "statement")
_GZIP_MAGIC = b"\x1f\x8b"
_BOM = b"\xef\xbb\xbf"


class BackupFormatError(ValueError):
    pass


def columns(table: str) -> list[str]:
    return [name for name, _ in TABLES[table]]


def canonical(value: Any) -> bytes:
    """The one serialisation used for files and checksums."""
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


SCHEMA = _sha256(canonical({table: [list(c) for c in spec] for table, spec in TABLES.items()}))[:16]


# ── bytes ↔ document ────────────────────────────────────────────────────────────

def pack(raw: bytes) -> bytes:
    """Gzip with a fixed header (mtime 0), so the same document always gives the same bytes."""
    return gzip.compress(raw, compresslevel=6, mtime=0)


def unpack(blob: bytes, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    """Gunzip one member, refusing anything larger than `limit` once decompressed."""
    inflater = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    out = bytearray()
    data = bytes(blob)
    try:
        while not inflater.eof:
            chunk = inflater.decompress(data, limit + 1 - len(out))
            out += chunk
            if len(out) > limit:
                raise BackupFormatError(f"The backup is larger than {limit // (1024 * 1024)} MB when unpacked.")
            data = inflater.unconsumed_tail
            if not chunk and not data:
                break
    except zlib.error as exc:
        raise BackupFormatError("The compressed backup file is damaged.") from exc
    if not inflater.eof:
        raise BackupFormatError("The compressed backup file is incomplete.")
    if inflater.unused_data:
        raise BackupFormatError("The compressed backup file has extra data after the end.")
    return bytes(out)


def _reject_constant(name: str) -> Any:
    raise BackupFormatError(f"The backup contains an invalid number ({name}).")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise BackupFormatError(f"The backup repeats the key '{key[:40]}'.")
        result[key] = value
    return result


def loads(data: bytes, *, limit: int = MAX_UPLOAD_BYTES) -> Any:
    """Parse a backup file: gzip or plain JSON, strict UTF-8, no NaN, no repeated keys."""
    data = bytes(data)
    if data.startswith(_GZIP_MAGIC):
        data = unpack(data, limit)
    elif len(data) > limit:
        raise BackupFormatError(f"The backup is larger than {limit // (1024 * 1024)} MB.")
    if data.startswith(_BOM):
        data = data[len(_BOM):]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BackupFormatError("The backup file is not valid UTF-8 text.") from exc
    try:
        return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise BackupFormatError("The backup file is nested too deeply.") from exc
    except json.JSONDecodeError as exc:
        raise BackupFormatError("The backup file is not valid JSON.") from exc


def file_stamp(at: datetime) -> str:
    """IST stamp used in backup file names: 2025-10-20_1130IST."""
    return to_ist(at).strftime("%Y-%m-%d_%H%M") + "IST"


# ── encode ──────────────────────────────────────────────────────────────────────

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


def _is_local_setting(row: Mapping[str, Any]) -> bool:
    return row.get("key") in LOCAL_SETTINGS


def encode(rows_by_table: Mapping[str, list[Mapping[str, Any]]], created_at: datetime, *,
           created_by: str | None = None, kind: str | None = None) -> dict:
    if kind is not None and kind not in KINDS:
        raise ValueError(f"Unknown backup kind: {kind}")
    tables: dict[str, dict] = {}
    for table, spec in TABLES.items():
        rows = rows_by_table.get(table, [])
        if table == "app_settings":
            rows = [row for row in rows if not _is_local_setting(row)]
        tables[table] = {
            "columns": [name for name, _ in spec],
            "rows": [[_encode_value(row.get(name), kind_) for name, kind_ in spec] for row in rows],
        }
    document = {
        "format_version": FORMAT_VERSION,
        "app": APP_NAME,
        "schema": SCHEMA,
        "created_at": as_aware(created_at).isoformat(),
        "created_by": created_by,
        "kind": kind,
        "manifest": {"tables": {t: {"rows": len(b["rows"]), "sha256": _sha256(canonical(b))} for t, b in tables.items()}},
        "tables": tables,
    }
    document["checksum"] = _sha256(canonical(document))
    return document


# ── decode ──────────────────────────────────────────────────────────────────────

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
        if kind == "bool":
            if not isinstance(value, bool):
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
            return json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, InvalidOperation, AttributeError) as exc:
        raise BackupFormatError(f"Invalid {kind} value in {where}.") from exc
    raise BackupFormatError(f"Unsupported column type in {where}.")


def _digest(value: Any) -> str:
    try:
        return _sha256(canonical(value))
    except (ValueError, TypeError, RecursionError) as exc:
        raise BackupFormatError("The backup contains values that are not valid JSON.") from exc


def _check_v3(payload: dict, tables: dict) -> None:
    if payload.get("app") != APP_NAME:
        raise BackupFormatError("This file is not a Gold Loan Desk backup.")
    if payload.get("schema") != SCHEMA:
        raise BackupFormatError("This backup was made for a different database layout and cannot be restored.")
    if payload.get("kind") is not None and payload.get("kind") not in KINDS + OLDER_KINDS:
        raise BackupFormatError("The backup has an unknown kind.")
    manifest = payload.get("manifest")
    listed = manifest.get("tables") if isinstance(manifest, dict) else None
    if not isinstance(listed, dict) or set(listed) != set(tables):
        raise BackupFormatError("The backup's table list does not match its contents.")
    for table, block in tables.items():
        entry = listed[table]
        rows = block.get("rows") if isinstance(block, dict) else None
        if (not isinstance(entry, dict) or not isinstance(rows, list) or entry.get("rows") != len(rows)
                or entry.get("sha256") != _digest(block)):
            raise BackupFormatError(f"The '{table}' data in this backup has been changed or damaged.")
    checksum = payload.get("checksum")
    body = {key: value for key, value in payload.items() if key != "checksum"}
    if not isinstance(checksum, str) or checksum != _digest(body):
        raise BackupFormatError("The backup file has been changed or damaged (checksum does not match).")


_UNIQUE_KEYS = (
    # table, column (or columns), transform, message
    ("customers", "customerid", None, "Customer record {} appears more than once in the backup."),
    ("customers", "phone", None, "The phone number {} belongs to more than one customer in the backup."),
    ("customers", "user_id", str.upper, "Customer ID {} appears more than once in the backup."),
    ("loan_data", "loanid", None, "Loan record {} appears more than once in the backup."),
    ("loan_data", "loan_number", None, "Loan {} appears more than once in the backup."),
    ("statement", "statementid", None, "Ledger entry {} appears more than once in the backup."),
    ("statement", "client_request_id", None, "Ledger request {} appears more than once in the backup."),
    ("cash_days", "id", None, "Cash day record {} appears more than once in the backup."),
    ("cash_days", ("branch_prefix", "day"), None, "The cash day {} appears more than once in the backup."),
    ("cash_entries", "id", None, "Cash entry {} appears more than once in the backup."),
    ("cash_entries", "client_request_id", None, "Cash entry request {} appears more than once in the backup."),
)


def _check_unique(result: dict[str, list[tuple]]) -> None:
    for table, column, transform, message in _UNIQUE_KEYS:
        names = column if isinstance(column, tuple) else (column,)
        indexes = [columns(table).index(name) for name in names]
        seen: set = set()
        for row in result[table]:
            values = tuple(row[i] for i in indexes)
            if any(value is None for value in values):
                continue
            key = tuple(transform(value) for value in values) if transform else values
            if key in seen:
                shown = " ".join(v.isoformat() if isinstance(v, date) else str(v) for v in values)
                raise BackupFormatError(message.replace("{}", shown[:64]))
            seen.add(key)
    day_id_at, entry_id_at = columns("cash_days").index("id"), columns("cash_entries").index("id")
    day_ids = {row[day_id_at] for row in result["cash_days"]}
    day_at = columns("cash_entries").index("day_id")
    for row in result["cash_entries"]:  # restored in one transaction; a dangling entry would fail it
        if row[day_at] not in day_ids:
            raise BackupFormatError(
                f"Cash entry {str(row[entry_id_at])[:64]} belongs to a cash day that is not in the backup.")
    spec = columns("statement")
    number_at, kind_at = spec.index("loan_number"), spec.index("transactiontype")
    opened: set = set()
    for row in result["statement"]:
        if row[kind_at] == "newLoan":
            if row[number_at] in opened:
                raise BackupFormatError(f"Loan {str(row[number_at])[:64]} has more than one opening entry in the backup.")
            opened.add(row[number_at])


def _decode(payload: Any) -> tuple[dict[str, list[tuple]], bool]:
    if not isinstance(payload, dict):
        raise BackupFormatError("The backup file is not a JSON object.")
    version = payload.get("format_version")
    if isinstance(version, bool) or not isinstance(version, int) or version not in READABLE_VERSIONS:
        raise BackupFormatError(
            "This backup was not created by this version of the application and cannot be restored."
        )
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise BackupFormatError("The backup has no tables.")
    unknown = sorted(set(tables) - set(TABLES))
    if unknown:
        raise BackupFormatError(f"Unknown tables in backup: {', '.join(str(t)[:40] for t in unknown)}.")
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    if missing:
        raise BackupFormatError(f"The backup is missing: {', '.join(missing)}.")
    if version == 3:
        _check_v3(payload, tables)
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
    result["app_settings"] = [row for row in result["app_settings"] if row[0] not in LOCAL_SETTINGS]
    _check_unique(result)
    return result, version == 3


def decode(payload: Any) -> dict[str, list[tuple]]:
    """Validate a backup and return rows per table, in `columns(table)` order."""
    return _decode(payload)[0]


def _prefixes(tables: Mapping[str, list[tuple]], names: tuple[str, ...]) -> set[str]:
    found: set[str] = set()
    for table in names:
        at = columns(table).index("branch_prefix")
        found.update(row[at] for row in tables.get(table, ()) if row[at])
    return found


def branch_prefixes(tables: Mapping[str, list[tuple]]) -> set[str]:
    """Branches holding business data (customers, cash days): the "Branches in the file" list.
    Counters are left out, because every sign-in, the head office's too, has one."""
    return _prefixes(tables, ("customers", "cash_days"))


def required_branches(tables: Mapping[str, list[tuple]]) -> set[str]:
    """Branches the rows depend on (customers, cash days and branch counters); each must exist
    before a restore, because each of these rows references the branch."""
    return _prefixes(tables, ("customers", "cash_days", "branch_counters"))


def inspect(payload: Any) -> dict:
    """Dry run: validate exactly as a restore would and describe what the file holds.

    Raises BackupFormatError when the file cannot be restored. Loose ends that a restore
    keeps as they are (a loan without its customer, say) are reported as warnings.
    """
    tables, verified = _decode(payload)
    customer_cols, loan_cols, entry_cols = columns("customers"), columns("loan_data"), columns("statement")
    prefix_at = customer_cols.index("branch_prefix")
    customer_ids = {row[customer_cols.index("customerid")] for row in tables["customers"]}
    loan_numbers = {row[loan_cols.index("loan_number")] for row in tables["loan_data"]}
    warnings: list[str] = []
    no_branch = sum(1 for row in tables["customers"] if not row[prefix_at])
    if no_branch:
        warnings.append(f"{no_branch} customer(s) have no branch.")
    loan_customer_at = loan_cols.index("customerid")
    orphan_loans = sum(1 for row in tables["loan_data"] if row[loan_customer_at] not in customer_ids)
    if orphan_loans:
        warnings.append(f"{orphan_loans} loan(s) belong to a customer that is not in the backup.")
    entry_loan_at = entry_cols.index("loan_number")
    orphan_entries = sum(1 for row in tables["statement"] if row[entry_loan_at] not in loan_numbers)
    if orphan_entries:
        warnings.append(f"{orphan_entries} ledger entr{'y' if orphan_entries == 1 else 'ies'} "
                        "belong to a loan that is not in the backup.")
    kind_at = entry_cols.index("transactiontype")
    opened = {row[entry_loan_at] for row in tables["statement"] if row[kind_at] == "newLoan"}
    without_opening = len(loan_numbers - opened)
    if without_opening:
        warnings.append(f"{without_opening} loan(s) have no opening ledger entry.")
    if not verified:
        warnings.append("This is an older backup file without a checksum, so damage cannot be ruled out.")
    created_by, kind = payload.get("created_by"), payload.get("kind")
    return {
        "format_version": payload["format_version"],
        "created_at": payload.get("created_at") if isinstance(payload.get("created_at"), str) else None,
        "created_by": created_by if isinstance(created_by, str) else None,
        "kind": kind if isinstance(kind, str) else None,
        "checksum": "verified" if verified else "absent",
        "counts": {
            "branches": len(tables["branches"]),
            "customers": len(tables["customers"]),
            "loans": len(tables["loan_data"]),
            "entries": len(tables["statement"]),
            "settings": len(tables["app_settings"]),
        },
        "branch_prefixes": sorted(branch_prefixes(tables)),
        "required_branches": sorted(required_branches(tables)),
        "warnings": warnings,
    }
