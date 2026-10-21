"""Backups that work on serverless hosting: snapshots are stored in the database
(compressed), downloads are streamed from memory. Supabase's own backups / PITR remain
the disaster-recovery layer; these snapshots protect against mistakes and bad restores.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timedelta

from ..domain import backup_codec, validation
from ..errors import Forbidden, Invalid, NotFound, TooManyRequests
from . import serialize
from .context import Actor

KEEP_SNAPSHOTS = {"scheduled": 14, "manual": 5, "pre_restore": 10}
MANUAL_SNAPSHOT_INTERVAL = timedelta(minutes=10)
RESTORE_CONFIRMATION = "RESTORE"


def _require_backup_access(actor: Actor) -> None:
    if not actor.is_head_office:
        raise Forbidden("Backups contain every branch's data and are limited to head office.")


async def export_document(repos, now: datetime) -> dict:
    return backup_codec.encode(await repos.backups.export_rows(), now)


def _pack(document: dict) -> tuple[bytes, str]:
    raw = json.dumps(document, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, compresslevel=6), hashlib.sha256(raw).hexdigest()


async def export_json(repos, actor: Actor, now: datetime) -> bytes:
    _require_backup_access(actor)
    document = await export_document(repos, now)
    await repos.audit.log(username=actor.username, action="EXPORT_BACKUP", entity_type="BACKUP", entity_id="live",
                          details="Downloaded a live backup")
    return json.dumps(document, separators=(",", ":")).encode("utf-8")


async def create_snapshot(repos, *, created_by: str, kind: str, now: datetime) -> dict:
    payload, digest = _pack(await export_document(repos, now))
    snapshot_id = await repos.backups.create_snapshot(kind=kind, created_by=created_by, payload=payload, sha256=digest)
    await repos.backups.prune_snapshots(kind, KEEP_SNAPSHOTS[kind])
    return {"id": snapshot_id, "size_bytes": len(payload), "sha256": digest}


async def manual_snapshot(repos, actor: Actor, now: datetime) -> dict:
    _require_backup_access(actor)
    latest = await repos.backups.latest_snapshot_at("manual")
    if latest is not None and now - latest < MANUAL_SNAPSHOT_INTERVAL:
        raise TooManyRequests("A snapshot was saved a few minutes ago. Wait 10 minutes between manual snapshots.",
                              code="snapshot_too_soon")
    result = await create_snapshot(repos, created_by=actor.username, kind="manual", now=now)
    await repos.audit.log(username=actor.username, action="CREATE_SNAPSHOT", entity_type="BACKUP",
                          entity_id=str(result["id"]), details="Manual snapshot")
    return result


async def list_snapshots(repos, actor: Actor) -> list[dict]:
    _require_backup_access(actor)
    return [
        {"id": r["id"], "created_at": serialize.stamp(r["created_at"]), "created_by": r["created_by"],
         "kind": r["kind"], "size_bytes": r["size_bytes"]}
        for r in await repos.backups.snapshots()
    ]


async def _load_snapshot(repos, snapshot_id: int) -> tuple[dict, bytes]:
    row = await repos.backups.snapshot(snapshot_id)
    if row is None:
        raise NotFound("Snapshot was not found.")
    raw = gzip.decompress(row["payload"])
    if hashlib.sha256(raw).hexdigest() != row["sha256"].strip():
        raise Invalid("This snapshot is damaged and cannot be used.", code="snapshot_corrupt")
    return row, raw


async def snapshot_json(repos, actor: Actor, snapshot_id: int) -> tuple[str, bytes]:
    _require_backup_access(actor)
    row, raw = await _load_snapshot(repos, snapshot_id)
    stamp = serialize.stamp(row["created_at"]).replace(":", "").replace("+", "_")[:15]
    await repos.audit.log(username=actor.username, action="DOWNLOAD_SNAPSHOT", entity_type="BACKUP",
                          entity_id=str(snapshot_id), details="Downloaded snapshot")
    return f"backup_{stamp}.json", raw


def _with_safe_logo(row: tuple, index: int) -> tuple:
    """Logos from a file get the same checks as uploads; anything else is dropped."""
    try:
        logo = validation.logo_data_url(row[index])
    except validation.ValidationError:
        logo = None
    return row[:index] + (logo,) + row[index + 1:]


async def restore(repos, actor: Actor, *, document: object | None, snapshot_id: int | None, confirmation: str,
                  now: datetime, context: dict | None = None) -> dict:
    actor.require_superadmin()
    if confirmation != RESTORE_CONFIRMATION:
        raise Invalid(f"Type {RESTORE_CONFIRMATION} to confirm the restore.", code="confirmation_required")
    if (document is None) == (snapshot_id is None):
        raise Invalid("Provide either a backup file or a snapshot.", code="invalid_restore")
    if snapshot_id is not None:
        _, raw = await _load_snapshot(repos, snapshot_id)
        document = json.loads(raw)
    try:
        tables = backup_codec.decode(document)
    except backup_codec.BackupFormatError as exc:
        raise Invalid(str(exc), code="invalid_backup") from exc

    logo_index = backup_codec.columns("branches").index("logo")
    tables["branches"] = [_with_safe_logo(row, logo_index) for row in tables["branches"]]
    prefix_index = backup_codec.columns("customers").index("branch_prefix")
    missing = await repos.backups.missing_branches({row[prefix_index] for row in tables["customers"]})
    if missing:
        raise Invalid("The backup refers to branches that do not exist here: " + ", ".join(missing) + ".",
                      code="unknown_branches")

    context = context or {}
    async with repos.transaction():
        safety = await create_snapshot(repos, created_by=actor.username, kind="pre_restore", now=now)
        await repos.backups.replace_business_data(tables)
        await repos.audit.log(
            username=actor.username, action="RESTORE_BACKUP", entity_type="BACKUP",
            entity_id=str(snapshot_id) if snapshot_id else "upload",
            details=(f"Restored {len(tables['customers'])} customers, {len(tables['loan_data'])} loans, "
                     f"{len(tables['statement'])} ledger entries; previous data saved as snapshot {safety['id']}"),
            ip=context.get("ip"), request_id=context.get("request_id"),
        )
    return {
        "customers": len(tables["customers"]),
        "loans": len(tables["loan_data"]),
        "entries": len(tables["statement"]),
        "safety_snapshot_id": safety["id"],
    }
