"""Reporting definitions shared by summaries, drill-downs and exports.

Metric definitions (all amounts from the ledger, all periods in IST business days):
- disbursed            new-loan principal + top-ups (`disbursement.currentPrincipal`,
                       legacy `modify.amountPaid`) dated in the period
- interest_collected   Σ currentInterest of collections
- principal_collected  Σ −currentPrincipal of collections
- total_collected      Σ amountPaid of collections
- compounded           Σ currentPrincipal of compounding entries
- written_off          new write-offs: writeoff_principal + writeoff_interest;
                       legacy write-offs (no split recorded): principleBalance on the row
- closures             loans whose closed_at falls in the period
- gold_pledged         net weight of loans created in the period
- gold_released        net weight of loans closed in the period

Follow-ups and overdue loans (approved 2026-10):
- an open loan is overdue when today is after loan date + 365 days (its due date)
- an open loan is due a follow-up on the date staff set, else on loan date + 364 days;
  the automatic date is computed, never stored, so no data is backfilled
- the dashboard lists a follow-up from 10 days before its date until it is done (changed 2026-10-23);
  `follow_up_days` is the follow-up date minus today (negative once it has passed)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Sequence

from .dates import parse_business_date

PERIOD_METRICS = (
    "disbursed",
    "new_loans",
    "new_customers",
    "interest_collected",
    "principal_collected",
    "total_collected",
    "compounded",
    "written_off",
    "closures",
    "gold_pledged",
    "gold_released",
)
MAX_RANGE_DAYS = 5 * 366
AGING_BUCKETS: tuple[tuple[int, int | None, str], ...] = (
    (0, 30, "0–30 days"),
    (31, 60, "31–60 days"),
    (61, 90, "61–90 days"),
    (91, None, "Over 90 days"),
)
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
FOLLOW_UP_AFTER_DAYS = 364
OVERDUE_AFTER_DAYS = 365
FOLLOW_UP_NOTICE_DAYS = 10


class PeriodError(ValueError):
    pass


def resolve_period(start: str | None, end: str | None, today: date) -> tuple[date, date]:
    try:
        start_day = parse_business_date(start) if start else today
        end_day = parse_business_date(end) if end else today
    except ValueError as exc:
        raise PeriodError(str(exc)) from exc
    if end_day < start_day:
        raise PeriodError("The end date must be on or after the start date.")
    if end_day > today:
        raise PeriodError("The period cannot extend into the future.")
    if (end_day - start_day).days > MAX_RANGE_DAYS:
        raise PeriodError("Choose a period of at most five years.")
    return start_day, end_day


def aging_bucket(days_since_payment: int) -> str:
    for low, high, label in AGING_BUCKETS:
        if days_since_payment >= low and (high is None or days_since_payment <= high):
            return label
    return AGING_BUCKETS[0][2]


def default_follow_up(loan_date: date) -> date:
    return loan_date + timedelta(days=FOLLOW_UP_AFTER_DAYS)


def overdue_from(loan_date: date) -> date:
    """The due date: a loan is overdue on any day after it."""
    return loan_date + timedelta(days=OVERDUE_AFTER_DAYS)


def effective_follow_up(stored: date | None, loan_date: date | None, is_open: bool) -> date | None:
    """The follow-up date to act on: the stored one wins; open loans otherwise get the default."""
    if not is_open:
        return None
    if stored is not None:
        return stored
    return default_follow_up(loan_date) if loan_date is not None else None


def month_starts(today: date, count: int = 6) -> list[date]:
    """First days of the last `count` months, oldest first, including the current one."""
    months: list[date] = []
    cursor = today.replace(day=1)
    for _ in range(count):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(months))


def csv_cell(value: object) -> str:
    """Quote a value for CSV and neutralise spreadsheet formula injection."""
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        text = "'" + text
    if any(ch in text for ch in (",", '"', "\n", "\r")) or text != text.strip():
        text = '"' + text.replace('"', '""') + '"'
    return text


def to_csv(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = [",".join(csv_cell(h) for h in headers)]
    lines.extend(",".join(csv_cell(v) for v in row) for row in rows)
    return "\r\n".join(lines) + "\r\n"
