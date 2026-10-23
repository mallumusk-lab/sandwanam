"""Backups are never stored in the app: the nightly job (and "Email backup now") build one
in memory and email it as a password-protected ZIP (backup_email_service). Supabase's own
backups / PITR remain the disaster-recovery layer.

Import backup takes a file back: the emailed ZIP (decrypted by the router's `unzip`
helper from app.infra, so this module never imports infra), the `.json` inside it, or a
`.json.gz`. A file can be checked (dry run) before it is restored. A restore replaces all
business data and keeps no copy of the old data; the page asks the user to keep their own.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import datetime
from typing import Callable

from ..domain import backup_codec, validation
from ..errors import Forbidden, Invalid
from .context import Actor

RESTORE_CONFIRMATION = "RESTORE"
# Opens an emailed backup ZIP: (zip bytes, password, limit=…) -> the backup JSON bytes.
Unzip = Callable[..., bytes]


def _require_backup_access(actor: Actor) -> None:
    if not actor.is_head_office:
        raise Forbidden("Backups contain every branch's data and are limited to head office.")


async def export_document(repos, now: datetime, *, created_by: str | None = None, kind: str | None = None) -> dict:
    return backup_codec.encode(await repos.backups.export_rows(), now, created_by=created_by, kind=kind)


async def backup_bytes(repos, now: datetime, *, created_by: str, kind: str) -> tuple[bytes, str]:
    """A fresh backup as canonical JSON (what goes in the emailed ZIP) and its sha256."""
    raw = backup_codec.canonical(await export_document(repos, now, created_by=created_by, kind=kind))
    return raw, hashlib.sha256(raw).hexdigest()


def _with_safe_logo(row: tuple, index: int) -> tuple:
    """Logos from a file get the same checks as uploads; anything else is dropped."""
    try:
        logo = validation.logo_data_url(row[index])
    except validation.ValidationError:
        logo = None
    return row[:index] + (logo,) + row[index + 1:]


def _decoded(packed: str) -> bytes:
    try:
        return base64.b64decode(packed, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise backup_codec.BackupFormatError("The uploaded file could not be read.") from exc


def _source(*, document: object | None, packed: str | None, zipped: str | None, zip_password: str | None,
            unzip: Unzip | None) -> object:
    """The backup document from exactly one of: an uploaded object, a gzip or a ZIP (base64)."""
    if sum(value is not None for value in (document, packed, zipped)) != 1:
        raise Invalid("Choose one backup file.", code="invalid_restore")
    if zip_password is not None and zipped is None:
        raise Invalid("A ZIP password is only needed for a ZIP file.", code="invalid_restore")
    try:
        if zipped is not None:
            if not zip_password:
                raise Invalid("Enter the ZIP password.", code="zip_password", details={"field": "zip_password"})
            if unzip is None:
                raise Invalid("ZIP files can't be opened here. Upload the .json file from inside the ZIP.",
                              code="invalid_backup")
            raw = unzip(_decoded(zipped), zip_password, limit=backup_codec.MAX_UPLOAD_BYTES)
            return backup_codec.loads(raw, limit=backup_codec.MAX_UPLOAD_BYTES)
        if packed is not None:
            return backup_codec.loads(_decoded(packed), limit=backup_codec.MAX_UPLOAD_BYTES)
    except backup_codec.BackupFormatError as exc:
        raise Invalid(str(exc), code="invalid_backup") from exc
    return document


async def check(repos, actor: Actor, *, document: object | None = None, packed: str | None = None,
                zipped: str | None = None, zip_password: str | None = None, unzip: Unzip | None = None) -> dict:
    """Dry run of a restore: what the file holds and whether it can be restored here."""
    _require_backup_access(actor)
    payload = _source(document=document, packed=packed, zipped=zipped, zip_password=zip_password, unzip=unzip)
    try:
        report = backup_codec.inspect(payload)
    except backup_codec.BackupFormatError as exc:
        raise Invalid(str(exc), code="invalid_backup") from exc
    missing = await repos.backups.missing_branches(set(report.pop("required_branches")))
    return {**report, "missing_branches": missing, "restorable": not missing}


async def restore(repos, actor: Actor, *, document: object | None = None, packed: str | None = None,
                  zipped: str | None = None, zip_password: str | None = None, unzip: Unzip | None = None,
                  confirmation: str, now: datetime, context: dict | None = None) -> dict:
    """Replace all business data with the file's. Nothing else is saved first (by decision)."""
    actor.require_superadmin()
    if confirmation != RESTORE_CONFIRMATION:
        raise Invalid(f"Type {RESTORE_CONFIRMATION} to confirm the restore.", code="confirmation_required")
    payload = _source(document=document, packed=packed, zipped=zipped, zip_password=zip_password, unzip=unzip)
    try:
        tables = backup_codec.decode(payload)
    except backup_codec.BackupFormatError as exc:
        raise Invalid(str(exc), code="invalid_backup") from exc

    logo_index = backup_codec.columns("branches").index("logo")
    tables["branches"] = [_with_safe_logo(row, logo_index) for row in tables["branches"]]
    missing = await repos.backups.missing_branches(backup_codec.required_branches(tables))
    if missing:
        raise Invalid("The backup refers to branches that do not exist here: " + ", ".join(missing) + ".",
                      code="unknown_branches")

    context = context or {}
    source = "zip" if zipped is not None else "upload"
    taken = payload.get("created_at") if isinstance(payload, dict) else None
    taken = taken[:40] if isinstance(taken, str) else None
    async with repos.transaction():
        await repos.backups.replace_business_data(tables)
        await repos.audit.log(
            username=actor.username, action="RESTORE_BACKUP", entity_type="BACKUP", entity_id=source,
            details=(f"Restored {len(tables['customers'])} customers, {len(tables['loan_data'])} loans, "
                     f"{len(tables['statement'])} ledger entries from a backup taken "
                     f"{taken or 'at an unknown time'}"),
            ip=context.get("ip"), request_id=context.get("request_id"),
        )
    return {
        "customers": len(tables["customers"]),
        "loans": len(tables["loan_data"]),
        "entries": len(tables["statement"]),
        "taken_at": taken,
    }
