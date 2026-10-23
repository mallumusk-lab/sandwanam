"""The backup email: an AES-256 ZIP holding a fresh backup, sent to one address chosen by a
SuperAdmin, every night (`send_nightly`) and on request (`send_now`, "Email backup now").
Nothing is stored: the backup is built in memory for each email.

The mail server and the ZIP password are server settings (environment variables), so
this module only receives a ready mailer object (`app.infra.mailer.BackupMailer`, or a
fake in tests) and the list of what is missing. The address and the last results are
kept in app_settings under keys that backups never export or restore.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .. import logs
from ..domain import backup_codec, dates, validation
from ..errors import Forbidden, Invalid, ServiceUnavailable, TooManyRequests
from . import backup_service
from .context import Actor

SETTINGS_KEY = "backup_email"
STATUS_KEY = "backup_email_status"
# The last result of each kind of send. An older "test" half is ignored when read and dropped on the next save.
STATUS_HALVES = ("nightly", "manual")
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
SEND_NOW_INTERVAL = timedelta(minutes=10)
SYSTEM_USER = "system"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

README = """Gold Loan Desk backup
=====================

This ZIP file is protected with a password. The password is not in this email: ask the
person who set up the server (it is the BACKUP_ZIP_PASSWORD setting).

What is inside
  backup_<date>_<time>IST.json  the full backup of customers, loans, ledger entries and
                                the cash ledger.

To import it (if anything goes wrong)
  Sign in as SuperAdmin and open Backups. Under "Import backup", choose this ZIP file as
  it is, type the ZIP password and press Check. Read the summary, press Import and type
  RESTORE. The .json inside the ZIP can be chosen instead (no password is needed then).
  Restoring replaces all data: keep your own copy of the current data first.

To open it yourself
  Windows: install 7-Zip (7-zip.org), right-click the ZIP, choose 7-Zip > Extract Here,
           and type the password. WinZip also works. The built-in Windows "Extract all"
           cannot open AES-encrypted ZIP files.
  Mac:     use Keka or The Unarchiver and type the password.

Keep this file somewhere safe: it contains customer names, phone numbers and loans.
"""


def _require_backup_access(actor: Actor) -> None:
    if not actor.is_head_office:
        raise Forbidden("Backups contain every branch's data and are limited to head office.")


def _stamp(value: datetime | None) -> str | None:
    return None if value is None else dates.as_aware(value).isoformat()


def taken_label(at: datetime) -> str:
    """20 Oct 2025, 11:30 (IST)."""
    ist = dates.to_ist(at)
    return f"{ist.day} {_MONTHS[ist.month - 1]} {ist.year}, {ist:%H:%M}"


async def _config(repos) -> dict:
    row = await repos.settings.get(SETTINGS_KEY)
    value = row["value"] if row and isinstance(row.get("value"), dict) else {}
    recipient = value.get("recipient") if isinstance(value.get("recipient"), str) else None
    return {"recipient": recipient, "enabled": bool(value.get("enabled")) and recipient is not None}


async def _status(repos) -> dict:
    row = await repos.settings.get(STATUS_KEY)
    value = row["value"] if row and isinstance(row.get("value"), dict) else {}
    return {half: value.get(half) if isinstance(value.get(half), dict) else None for half in STATUS_HALVES}


async def _save_status(repos, half: str, entry: dict) -> None:
    """Each half is written on its own, so "Email backup now" never hides last night's result."""
    status = await _status(repos)
    status[half] = entry
    await repos.settings.put(STATUS_KEY, status, SYSTEM_USER)


async def _view(repos, missing: tuple[str, ...]) -> dict:
    config = await _config(repos)
    return {"configured": not missing, "missing": list(missing), **config, "status": await _status(repos)}


async def email_settings(repos, actor: Actor, *, missing: tuple[str, ...]) -> dict:
    _require_backup_access(actor)
    return await _view(repos, missing)


async def set_email_settings(repos, actor: Actor, *, recipient: str | None, enabled: bool,
                             missing: tuple[str, ...]) -> dict:
    actor.require_superadmin()
    address = None
    if recipient is not None and recipient.strip():
        try:
            address = validation.email_recipient(recipient)
        except validation.ValidationError as exc:
            raise Invalid(exc.message, code="invalid_email", details={"field": exc.field}) from exc
    if enabled and address is None:
        raise Invalid("Add the address that should receive the backups before turning the email on.",
                      code="email_no_recipient", details={"field": "recipient"})
    await repos.settings.put(SETTINGS_KEY, {"recipient": address, "enabled": bool(enabled)}, actor.username)
    await repos.audit.log(username=actor.username, action="SET_BACKUP_EMAIL", entity_type="SETTING",
                          entity_id=SETTINGS_KEY,
                          details=f"Nightly backup email {'on' if enabled else 'off'}; address {address or 'none'}")
    return await _view(repos, missing)


def _public_message(exc: Exception) -> str:
    message = getattr(exc, "public_message", None)
    return message if isinstance(message, str) else "The email could not be sent."


def _entry(now: datetime, result: str, ok: bool, message: str, size_bytes: int | None = None, **extra) -> dict:
    return {"at": _stamp(now), "ok": ok, "result": result, "message": message, "size_bytes": size_bytes, **extra}


def _attached_text(label: str, when: str, size_bytes: int) -> str:
    return (f"The Gold Loan Desk {label} taken {when} IST is attached as a password-protected ZIP "
            f"({size_bytes:,} bytes).\n\nOpen it with 7-Zip or WinZip and the backup password, or import the ZIP "
            "as it is on the Backups page. README.txt inside explains how.\n")


def _too_large_text(label: str, when: str) -> str:
    return (f"The Gold Loan Desk {label} taken {when} IST is larger than "
            f"{MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB, so it is not attached.\n\n"
            "Nothing is stored in the app. Ask whoever manages the hosting to keep the database provider's own "
            "backups switched on and to take a copy from there.\n")


def _audit_details(prefix: str, entry: dict) -> str:
    sha = f" sha256 {entry['sha256']}" if entry.get("sha256") else ""
    return f"{prefix}: {entry['result']}. {entry['message']}{sha}"


async def _email_backup(repos, mailer, *, recipient: str, now: datetime, created_by: str, kind: str,
                        label: str) -> dict:
    """Build a backup in memory, ZIP it and send it. Raises on failure; returns the status entry."""
    raw, digest = await backup_service.backup_bytes(repos, now, created_by=created_by, kind=kind)
    stamp, when = backup_codec.file_stamp(now), taken_label(now)
    archive = mailer.encrypt_zip([(f"backup_{stamp}.json", raw), ("README.txt", README.encode("utf-8"))],
                                 modified=dates.to_ist(now).replace(tzinfo=None))
    subject = f"Gold Loan Desk {label} · taken {when} IST"
    if len(archive) > MAX_ATTACHMENT_BYTES:
        await mailer.send(to=recipient, subject=subject, text=_too_large_text(label, when))
        return _entry(now, "too_large", False, "The backup was too large to attach; a notice was emailed instead.",
                      len(archive), sha256=digest)
    await mailer.send(to=recipient, subject=subject, text=_attached_text(label, when, len(archive)),
                      attachment=(f"backup_{stamp}.zip", archive))
    return _entry(now, "sent", True, "Backup emailed.", len(archive), sha256=digest)


async def send_now(repos, actor: Actor, mailer, *, missing: tuple[str, ...], now: datetime) -> dict:
    """"Email backup now": the same ZIP as the nightly email, sent at once. Head office; 1 per 10 minutes."""
    _require_backup_access(actor)
    if mailer is None:
        raise ServiceUnavailable("Email is not set up on the server yet. Missing: " + ", ".join(missing) + ".",
                                 code="email_not_configured")
    config = await _config(repos)
    if config["recipient"] is None:
        raise Invalid("Add the address that should receive the backups first.", code="email_no_recipient",
                      details={"field": "recipient"})
    last = (await _status(repos))["manual"]
    if last and isinstance(last.get("at"), str):
        try:
            last_at = dates.parse_timestamp(last["at"])
        except ValueError:
            last_at = None
        if last_at is not None and now - last_at < SEND_NOW_INTERVAL:
            raise TooManyRequests("A backup was emailed a few minutes ago. Wait 10 minutes before sending another.",
                                  code="email_backup_too_soon")
    try:
        entry = await _email_backup(repos, mailer, recipient=config["recipient"], now=now, created_by=actor.username,
                                    kind="manual", label="backup")
    except Exception as exc:  # report the failure on screen; the reason never contains secrets
        logs.warning("backup_email_now_failed", exc_type=type(exc).__name__)
        entry = _entry(now, "failed", False, _public_message(exc))
    entry["by"] = actor.username
    await _save_status(repos, "manual", entry)
    await repos.audit.log(username=actor.username, action="EMAIL_BACKUP_NOW", entity_type="BACKUP",
                          entity_id=f"backup_{backup_codec.file_stamp(now)}",
                          details=_audit_details("Email backup now", entry))
    return await _view(repos, missing)


async def _finish(repos, now: datetime, entry: dict) -> str:
    try:
        await _save_status(repos, "nightly", entry)
        await repos.audit.log(username=SYSTEM_USER, action="EMAIL_BACKUP", entity_type="BACKUP",
                              entity_id=f"backup_{backup_codec.file_stamp(now)}",
                              details=_audit_details("Nightly backup email", entry))
    except Exception:  # the result is still returned and logged
        logs.error("backup_email_status_failed", result=entry["result"], exc_info=True)
    logs.info("backup_email", result=entry["result"], size_bytes=entry.get("size_bytes"))
    return entry["result"]


async def send_nightly(repos, mailer, *, now: datetime, missing: tuple[str, ...] = ()) -> str:
    """Build tonight's backup in memory and email it. Never raises; returns the result name."""
    try:
        config = await _config(repos)
        if not config["enabled"]:
            return await _finish(repos, now, _entry(now, "skipped_disabled", False, "The backup email is turned off."))
        if mailer is None:
            reason = "Email is not set up on the server. Missing: " + (", ".join(missing) or "mail settings") + "."
            return await _finish(repos, now, _entry(now, "skipped_not_configured", False, reason))
        last = (await _status(repos))["nightly"]
        if last and last.get("result") == "sent" and isinstance(last.get("at"), str):
            try:
                already = dates.business_date(last["at"]) == dates.business_date(now)
            except ValueError:
                already = False
            if already:
                logs.info("backup_email", result="already_sent_today")
                await repos.audit.log(username=SYSTEM_USER, action="EMAIL_BACKUP", entity_type="BACKUP",
                                      entity_id=f"backup_{backup_codec.file_stamp(now)}",
                                      details="Nightly backup email: already_sent_today.")
                return "already_sent_today"
        entry = await _email_backup(repos, mailer, recipient=config["recipient"], now=now, created_by=SYSTEM_USER,
                                    kind="scheduled", label="nightly backup")
        return await _finish(repos, now, entry)
    except Exception as exc:  # email trouble must never fail the nightly job
        logs.error("backup_email_failed", exc_type=type(exc).__name__)
        return await _finish(repos, now, _entry(now, "failed", False, _public_message(exc)))
