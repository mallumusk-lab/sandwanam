"""Business-date handling.

The business runs on Indian Standard Time. India has no daylight saving, so a fixed
+05:30 offset is exact and needs no tz database (which Windows Python lacks).

Rules:
- Timestamps are stored as timezone-aware UTC (`timestamptz`).
- Every "which day is this?" question is answered in IST.
- Naive datetimes are treated as UTC (that is what asyncpg and the legacy code wrote).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")
_NOON = time(12, 0)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(value: datetime) -> datetime:
    """Return an aware datetime; naive values are interpreted as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def to_ist(value: datetime) -> datetime:
    return as_aware(value).astimezone(IST)


def business_date(value: datetime | date | str | None = None) -> date:
    """The IST calendar date of a timestamp (today when omitted)."""
    if value is None:
        return to_ist(now_utc()).date()
    if isinstance(value, str):
        value = parse_timestamp(value)
    if isinstance(value, datetime):
        return to_ist(value).date()
    if isinstance(value, date):
        return value
    raise TypeError(f"Unsupported date value: {type(value).__name__}")


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp (accepts a trailing 'Z')."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return as_aware(datetime.fromisoformat(text))


def parse_business_date(value: str) -> date:
    """Strictly parse YYYY-MM-DD."""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (AttributeError, ValueError) as exc:
        raise ValueError("Dates must use the format YYYY-MM-DD.") from exc


def business_datetime(day: date, now: datetime | None = None) -> datetime:
    """The UTC timestamp to store for an event on an IST business day.

    Today's events get the real current time. Past days get IST noon so the stored
    instant can never drift across a day boundary in any timezone report.
    """
    current = as_aware(now) if now else now_utc()
    if day == business_date(current):
        return current.astimezone(timezone.utc)
    return datetime.combine(day, _NOON, tzinfo=IST).astimezone(timezone.utc)


def add_months(day: date, months: int) -> date:
    """Same day-of-month `months` later, clamped to the month's last day (31 Jan + 1 → 28/29 Feb)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    return date(year, month, min(day.day, (next_month - timedelta(days=1)).day))


def ist_day_bounds_utc(start: date, end: date) -> tuple[datetime, datetime]:
    """Half-open UTC range [start 00:00 IST, end+1 00:00 IST) for SQL range filters."""
    if end < start:
        raise ValueError("The end date must be on or after the start date.")
    lower = datetime.combine(start, time(0, 0), tzinfo=IST).astimezone(timezone.utc)
    upper = datetime.combine(end + timedelta(days=1), time(0, 0), tzinfo=IST).astimezone(timezone.utc)
    return lower, upper
