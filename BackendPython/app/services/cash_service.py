"""Branch cash ledger (the drawer book). Independent of loans: every amount is entered by
hand, and nothing here is shown on the dashboard, reports or any other screen.

A branch has at most one day per IST business day:
  1. start: the drawer is counted against the amount carried forward (the latest closed
     day's counted closing, 0.00 for the first day ever); any day left open before
     today is closed automatically first,
  2. entries (cash in or out) are added to today's open day only; mistakes are voided
     with a reason and stop counting,
  3. close: the drawer is counted against the expected amount worked out here; the day
     is then locked. Head office may reopen it while it is today's and the latest day.
Head office works on one branch at a time (there is no combined drawer). Every write
locks the day row, is audited, and returns the fresh overview. Days older than 14 days
are deleted by the daily job, except each branch's latest day.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..domain import cash, dates
from ..domain.money import ZERO, fmt, money
from ..errors import Conflict, Invalid, NotFound
from . import serialize
from .context import Actor, ensure_visible, resolve_scope

FEATURE = "cashbook"
MAX_SUGGESTIONS = 20


def _invalid(exc: cash.CashError) -> Invalid:
    return Invalid(exc.message, code=exc.code, details={"field": exc.field})


async def _branch(repos, actor: Actor, requested: str | None) -> str:
    actor.require(FEATURE)
    scope = resolve_scope(actor, requested, await repos.users.branch_prefixes())
    if scope.branch is None:
        raise Invalid("Choose a branch to see its cash ledger.", code="branch_required")
    return scope.branch


async def _locked_day(repos, actor: Actor, day_id: int) -> dict:
    day = await repos.cash.day_for_update(day_id)
    if day is None:
        raise NotFound("Cash day was not found.")
    ensure_visible(actor, day["branch_prefix"], "Cash day")
    return day


def _is_closed(day: dict) -> bool:
    return day.get("closed_at") is not None


def _totals(day: dict, entries: list[dict]) -> cash.Totals:
    return cash.day_totals(day["carried_forward"], day["opening_counted"], entries)


def _entry_view(row: dict) -> dict:
    return {
        "id": row["id"],
        "at": serialize.stamp(row["created_at"]),
        "direction": row["direction"],
        "category": row["category"],
        "category_label": cash.label(row["category"]),
        "description": row.get("description"),
        "reference": row.get("reference"),
        "amount": fmt(row["amount"]),
        "recorded_by": row.get("created_by"),
        "voided": cash.is_voided(row),
        "voided_at": serialize.stamp(row.get("voided_at")),
        "voided_by": row.get("voided_by"),
        "void_reason": row.get("void_reason"),
    }


def _day_view(row: dict, entries: list[dict]) -> dict:
    totals = _totals(row, entries)
    closed = _is_closed(row)
    return {
        "id": row["id"],
        "day": serialize.day(row["day"]),
        "status": "closed" if closed else "open",
        "carried_forward": fmt(row["carried_forward"]),
        "opening_counted": fmt(row["opening_counted"]),
        "opening_difference": fmt(totals.opening_difference),
        "cash_in": fmt(totals.cash_in),
        "cash_out": fmt(totals.cash_out),
        "expected": fmt(totals.expected),
        "closing_counted": serialize.money(row.get("closing_counted")) if closed else None,
        "closing_difference": (fmt(cash.closing_difference(row["closing_expected"], row["closing_counted"]))
                               if closed else None),
        "closed_automatically": bool(row.get("closed_automatically")),
        "opened_by": row.get("opened_by"),
        "opened_at": serialize.stamp(row.get("opened_at")),
        "closed_by": row.get("closed_by") if closed else None,
        "closed_at": serialize.stamp(row.get("closed_at")) if closed else None,
        "entries": [_entry_view(e) for e in entries],
    }


async def _expected(repos, day: dict) -> cash.Totals:
    return _totals(day, await repos.cash.entries_for_days([day["id"]]))


async def _carry_forward(repos, branch: str, today) -> tuple:
    """(amount, day) carried into `today`: the latest earlier day's counted closing. A day
    still open (the daily job has not closed it yet) carries what an automatic close
    will store: its expected amount."""
    previous = await repos.cash.latest_day(branch, today)
    if previous is None:
        return ZERO, None
    if _is_closed(previous):
        return money(previous["closing_counted"]), previous["day"]
    return (await _expected(repos, previous)).expected, previous["day"]


async def _overview(repos, actor: Actor, branch: str, now: datetime) -> dict:
    today = dates.business_date(now)
    since = cash.cutoff(today)
    days = await repos.cash.days_since(branch, since)  # newest first
    by_day: dict[int, list[dict]] = defaultdict(list)
    for entry in await repos.cash.entries_for_days([d["id"] for d in days]):
        by_day[entry["day_id"]].append(entry)
    today_row = next((d for d in days if dates.business_date(d["day"]) == today), None)
    carried, from_day = await _carry_forward(repos, branch, today)
    named = await repos.users.branch(branch)
    latest = await repos.cash.latest_day(branch)
    return {
        "branch": branch,
        "branch_name": (named or {}).get("display_name") or branch,
        "today": today.isoformat(),
        "carry_forward": {"amount": fmt(carried), "from_day": serialize.day(from_day)},
        "today_day": _day_view(today_row, by_day[today_row["id"]]) if today_row else None,
        "history": [_day_view(d, by_day[d["id"]]) for d in days if dates.business_date(d["day"]) < today],
        "categories": [{"key": c.key, "label": c.label, "direction": c.direction} for c in cash.CATEGORIES],
        "suggestions": await repos.cash.recent_custom_descriptions(branch, since, MAX_SUGGESTIONS),
        "can_reopen": bool(
            actor.account_type == "hq" and today_row is not None and _is_closed(today_row)
            and latest is not None and latest["id"] == today_row["id"]
        ),
    }


async def _audit(repos, username: str, action: str, entity_id: str, details: str, context: dict | None) -> None:
    context = context or {}
    await repos.audit.log(username=username, action=action, entity_type="CASH", entity_id=entity_id, details=details,
                          ip=context.get("ip"), request_id=context.get("request_id"))


def _day_label(day: dict) -> str:
    return f"{day['branch_prefix']} {serialize.day(day['day'])}"


async def _auto_close(repos, day_id: int, today, now: datetime, context: dict | None = None) -> bool:
    """Close a day left open before today: nobody counted it, so counted = expected."""
    day = await repos.cash.day_for_update(day_id)
    if day is None or _is_closed(day) or dates.business_date(day["day"]) >= today:
        return False
    expected = (await _expected(repos, day)).expected
    await repos.cash.close_day(day["id"], expected=expected, counted=expected, closed_by="system", at=now,
                               automatically=True)
    await _audit(repos, "system", "CASH_CLOSE_DAY", _day_label(day),
                 f"Closed automatically (not counted): expected {expected}", context)
    return True


async def overview(repos, actor: Actor, branch: str | None, now: datetime) -> dict:
    prefix = await _branch(repos, actor, branch)
    return await _overview(repos, actor, prefix, now)


async def start_day(repos, actor: Actor, *, branch: str | None, opening_counted: str, request_id: str,
                    now: datetime, context: dict | None = None) -> dict:
    prefix = await _branch(repos, actor, branch)
    try:
        counted = cash.counted(opening_counted, field="opening_counted", name="Cash in hand")
    except cash.CashError as exc:
        raise _invalid(exc) from exc
    today = dates.business_date(now)
    async with repos.transaction():
        for stale in await repos.cash.open_days_before(today, prefix):
            await _auto_close(repos, stale["id"], today, now, context)
        existing = (await repos.cash.days_since(prefix, today))[:1]
        if existing:
            if request_id and existing[0].get("client_request_id") == request_id:
                return await _overview(repos, actor, prefix, now)  # the same request again
            raise Conflict("Today's cash day has already been started.", code="day_already_started")
        carried, _ = await _carry_forward(repos, prefix, today)
        day_id = await repos.cash.create_day(branch=prefix, day=today, carried_forward=carried,
                                             opening_counted=counted, opened_by=actor.username, opened_at=now,
                                             request_id=request_id)
        if day_id is None:  # started at the same moment by someone else
            raise Conflict("Today's cash day has already been started.", code="day_already_started")
        await _audit(repos, actor.username, "CASH_START_DAY", f"{prefix} {today.isoformat()}",
                     f"Carried forward {carried}, counted {counted}, difference {counted - carried}", context)
    return await _overview(repos, actor, prefix, now)


def _require_today_open(day: dict, today) -> None:
    if _is_closed(day):
        raise Invalid("This day is closed. Ask head office to reopen it if it needs a change.", code="day_closed")
    if dates.business_date(day["day"]) != today:
        raise Invalid("Only today's cash day can be changed. Start today's day first.", code="no_open_day")


async def add_entry(repos, actor: Actor, day_id: int, *, direction: str, category: str, description: str | None,
                    reference: str | None, amount: str, request_id: str, now: datetime,
                    context: dict | None = None) -> dict:
    actor.require(FEATURE)
    try:
        entry = cash.validate_entry(direction, category, description, reference, amount)
    except cash.CashError as exc:
        raise _invalid(exc) from exc
    today = dates.business_date(now)
    async with repos.transaction():
        day = await _locked_day(repos, actor, day_id)
        prior = await repos.cash.entry_by_request_id(request_id)
        if prior is not None:
            if prior["day_id"] != day["id"]:
                raise Conflict("This request id was already used for another entry.", code="request_id_reused")
            return await _overview(repos, actor, day["branch_prefix"], now)  # the same request again
        _require_today_open(day, today)
        entry_id = await repos.cash.add_entry(
            day_id=day["id"], direction=entry.direction, category=entry.category, description=entry.description,
            reference=entry.reference, amount=entry.amount, request_id=request_id, created_by=actor.username,
            created_at=now,
        )
        if entry_id is None:
            raise Conflict("This request id was already used for another entry.", code="request_id_reused")
        await _audit(repos, actor.username, "CASH_ENTRY", str(entry_id),
                     f"{_day_label(day)}: cash {entry.direction} {entry.amount} ({cash.label(entry.category)})"
                     + (f" {entry.description}" if entry.description else ""), context)
    return await _overview(repos, actor, day["branch_prefix"], now)


async def void_entry(repos, actor: Actor, entry_id: int, *, reason: str, now: datetime,
                     context: dict | None = None) -> dict:
    actor.require(FEATURE)
    try:
        why = cash.void_reason(reason)
    except cash.CashError as exc:
        raise _invalid(exc) from exc
    async with repos.transaction():
        entry = await repos.cash.entry(entry_id)
        if entry is None:
            raise NotFound("Cash entry was not found.")
        ensure_visible(actor, entry["branch_prefix"], "Cash entry")
        day = await _locked_day(repos, actor, entry["day_id"])
        _require_today_open(day, dates.business_date(now))
        if not await repos.cash.void_entry(entry["id"], voided_by=actor.username, reason=why, at=now):
            raise Conflict("This entry has already been voided.", code="entry_voided")
        await _audit(repos, actor.username, "CASH_VOID", str(entry["id"]),
                     f"{_day_label(day)}: voided cash {entry['direction']} {fmt(entry['amount'])}: {why}", context)
    return await _overview(repos, actor, day["branch_prefix"], now)


async def close_day(repos, actor: Actor, day_id: int, *, closing_counted: str, expected_total: str, now: datetime,
                    context: dict | None = None) -> dict:
    actor.require(FEATURE)
    try:
        counted = cash.counted(closing_counted, field="closing_counted", name="Cash in hand")
        shown = cash.shown_amount(expected_total, field="expected_total")
    except cash.CashError as exc:
        raise _invalid(exc) from exc
    async with repos.transaction():
        day = await _locked_day(repos, actor, day_id)
        _require_today_open(day, dates.business_date(now))
        expected = (await _expected(repos, day)).expected
        if shown != expected:
            raise Conflict("The expected cash has changed since it was shown. Check the new amount and try again.",
                           code="cash_changed", details={"expected": fmt(expected)})
        await repos.cash.close_day(day["id"], expected=expected, counted=counted, closed_by=actor.username, at=now,
                                   automatically=False)
        await _audit(repos, actor.username, "CASH_CLOSE_DAY", _day_label(day),
                     f"Expected {expected}, counted {counted}, difference "
                     f"{cash.closing_difference(expected, counted)}", context)
    return await _overview(repos, actor, day["branch_prefix"], now)


async def reopen_day(repos, actor: Actor, day_id: int, *, now: datetime, context: dict | None = None) -> dict:
    actor.require(FEATURE)
    actor.require_head_office()
    async with repos.transaction():
        day = await _locked_day(repos, actor, day_id)
        if not _is_closed(day):
            raise Invalid("This day is already open.", code="day_open")
        latest = await repos.cash.latest_day(day["branch_prefix"])
        if dates.business_date(day["day"]) != dates.business_date(now) or latest is None or latest["id"] != day["id"]:
            raise Invalid("Only today's day can be reopened, while it is the branch's latest day.",
                          code="reopen_not_allowed")
        await repos.cash.reopen_day(day["id"])
        await _audit(repos, actor.username, "CASH_REOPEN_DAY", _day_label(day),
                     f"Reopened; it was closed by {day.get('closed_by')} with {fmt(day.get('closing_counted'))} counted",
                     context)
    return await _overview(repos, actor, day["branch_prefix"], now)


async def auto_close_and_purge(repos, now: datetime) -> dict:
    """Daily job: close days left open before today, then delete days past the 14-day window."""
    today = dates.business_date(now)
    closed = 0
    async with repos.transaction():
        for stale in await repos.cash.open_days_before(today):
            closed += await _auto_close(repos, stale["id"], today, now)
        purged = await repos.cash.purge(cash.cutoff(today))
    return {"cash_days_closed": closed, "cash_days_purged": int(purged or 0)}
