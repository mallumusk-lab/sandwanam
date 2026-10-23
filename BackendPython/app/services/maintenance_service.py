"""Daily job (Vercel Cron at 00:00 IST) and the audit log view."""
from __future__ import annotations

from datetime import datetime, timedelta

from .. import logs
from ..domain import dates
from ..security import throttle
from ..security.sessions import DEFAULT_POLICY
from . import backup_email_service, cash_service, loans_service, serialize
from .context import Actor


async def run_daily(repos, now: datetime, mailer=None, *, mail_missing: tuple[str, ...] = ()) -> dict:
    """Compounding, the cash ledger (auto-close and 14-day purge), session and throttle
    purges, then the nightly backup email (built in memory; nothing is stored). Neither a
    cash ledger failure nor an email failure fails the job. `mailer` is None when email is
    not set up on the server."""
    today = dates.business_date(now)
    rows = await repos.loans.open_with_position(None)
    due = [row["loan_number"] for row in rows if loans_service.due_for_compounding(row, today)]
    applied, failed = 0, []
    for loan_number in due:
        try:
            applied += await loans_service.apply_due_compounding(repos, loan_number, now)
        except Exception:  # one bad loan must not stop the rest; it is retried tomorrow
            failed.append(loan_number)
            logs.error("compounding_failed", loan_number=loan_number, exc_info=True)
    try:
        cash = await cash_service.auto_close_and_purge(repos, now)
    except Exception:  # the drawer book is independent of loans; retried tomorrow
        cash = {"cash_days_closed": None, "cash_days_purged": None}
        logs.error("cash_ledger_failed", exc_info=True)
    await repos.sessions.purge_expired(now, now - DEFAULT_POLICY.idle)
    await repos.throttle.purge(now - timedelta(days=1), now, now - throttle.TRUST_PERIOD)
    result = {"loans_checked": len(rows), "compoundings": applied, "failed": failed, **cash}
    result["backup_email"] = await backup_email_service.send_nightly(repos, mailer, now=now, missing=mail_missing)
    logs.info("daily_job", **result)
    return result


async def audit_page(repos, actor: Actor, term: str | None, page: int, page_size: int) -> dict:
    actor.require_head_office()
    size = max(1, min(page_size, 100))
    current = max(1, page)
    cleaned = " ".join((term or "").split())[:60] or None
    rows, total = await repos.audit.page(cleaned, size, (current - 1) * size)
    return {
        "items": [
            {"id": r["log_id"], "at": serialize.stamp(r["timestamp"]), "username": r["username"], "action": r["action"],
             "entity_type": r["entity_type"], "entity_id": r["entity_id"], "details": r["details"], "ip": r.get("ip")}
            for r in rows
        ],
        "total": total,
        "page": current,
        "page_size": size,
    }
