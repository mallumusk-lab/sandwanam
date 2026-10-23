"""Interest rules (business decisions recorded 2026-10-20).

- Rates are annual (% p.a.): interest = principal × rate × days ÷ 36500.
- A period that ends in a customer-facing event (collection, top-up, closure, imported
  entry) is counted inclusively: (end − start) + 1 days. A day that ends one period and
  starts the next is therefore charged in both; this is the agreed rule.
- A period that ends in an annual compounding entry counts exact days (no +1).
- The first 7 days (inclusive) are charged as 7 days' interest on the highest principal
  reached in them, when the loan closes in those days or at the first event after day 7
  (see app/domain/ledger.py). `closing_days` is the earlier minimum-days rule, kept for
  reference; the ledger no longer uses it.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from .money import ZERO

DEFAULT_RATE = Decimal("18.00")
DAYS_PER_YEAR = Decimal(36500)
COMPOUNDING_INTERVAL_DAYS = 365
CLOSING_MINIMUM_DAYS = 7


class PeriodEnd(str, Enum):
    CUSTOMER = "customer"
    COMPOUNDING = "compounding"


def effective_rate(rate: Decimal | None) -> Decimal:
    return DEFAULT_RATE if rate is None else rate


def accrual_days(start: date, end: date, period_end: PeriodEnd) -> int:
    if end < start:
        raise ValueError("An entry cannot be dated before the previous ledger entry.")
    days = (end - start).days
    return days + 1 if period_end is PeriodEnd.CUSTOMER else days


def interest_for(principal: Decimal, rate: Decimal, days: int) -> Decimal:
    """Unrounded simple interest. A non-positive principal accrues nothing."""
    if days <= 0 or principal <= 0:
        return ZERO
    return principal * rate * Decimal(days) / DAYS_PER_YEAR


def closing_days(period_days: int, prior_days_charged: int, loan_age_days: int) -> int:
    """Days to charge for the closing period, applying the 7-day minimum.

    `loan_age_days` is the inclusive age of the loan on the closing day.
    """
    if loan_age_days >= CLOSING_MINIMUM_DAYS:
        return period_days
    return max(period_days, CLOSING_MINIMUM_DAYS - prior_days_charged)
