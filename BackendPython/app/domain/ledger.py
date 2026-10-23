"""The loan ledger as pure functions.

Every operation takes the loan terms and the current position (the balances recorded on
the latest ledger entry) and returns the entries to append. Nothing here touches the
database, so the same code serves live postings, display quotes and history imports.

First 7 days (W = loan date + 6, approved 2026-10): no daily interest is recorded in days
1-7. A payment then reduces principal by its full amount and a top-up adds principal; the
highest principal reached in those days is the window peak. Days 1-7 are charged as 7 days'
interest on the peak, either when the loan closes inside the window or by the first event
after day 7 (payment, top-up, closing or compounding), which also charges the days after
day 7 on the current principal, rounded once. Inclusive counting resumes from that entry.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from .interest import (
    CLOSING_MINIMUM_DAYS,
    COMPOUNDING_INTERVAL_DAYS,
    PeriodEnd,
    accrual_days,
    effective_rate,
    interest_for,
)
from .money import ZERO, money, parse_amount


class LedgerError(ValueError):
    """A ledger operation that violates a business rule."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


NEW_LOAN = "newLoan"
COLLECTION = "addColl"
TOP_UP = "disbursement"
COMPOUNDING = "compounding"
WRITE_OFF = "writeoff"
LEGACY_TOP_UP = "modify"
TRANSACTION_TYPES = (NEW_LOAN, COLLECTION, TOP_UP, COMPOUNDING, WRITE_OFF, LEGACY_TOP_UP)


@dataclass(frozen=True)
class LoanTerms:
    start_date: date
    rate: Decimal

    @classmethod
    def of(cls, start_date: date, rate: Decimal | None) -> "LoanTerms":
        return cls(start_date=start_date, rate=effective_rate(rate))


@dataclass(frozen=True)
class Position:
    """Balances after the latest ledger entry.

    `window_peak` (highest principal recorded so far; None = the current principal) and
    `window_interest_paid` (interest collected by earlier entries) only matter while the
    position is still in the first 7 days, when every entry so far lies in those days.
    Only entries posted under the earlier rule have window interest.
    """

    as_of: date
    principal: Decimal
    interest: Decimal
    compoundings: int = 0
    window_peak: Decimal | None = None
    window_interest_paid: Decimal = ZERO


@dataclass(frozen=True)
class Entry:
    kind: str
    on: date
    amount_paid: Decimal
    current_principal: Decimal
    current_interest: Decimal
    principal_balance: Decimal
    interest_balance: Decimal
    accrued_days: int
    writeoff_principal: Decimal | None = None
    writeoff_interest: Decimal | None = None


@dataclass(frozen=True)
class Quote:
    """What the customer owes on `as_of`, after any compounding that has fallen due."""

    as_of: date
    compoundings: tuple[Entry, ...]
    position: Position
    period_days: int
    principal: Decimal
    interest: Decimal
    first_week: bool = False  # as_of is in days 1-7 and the first-week charge is not yet settled
    window_peak: Decimal | None = None  # set while the quote includes the first-week charge
    first_week_interest: Decimal | None = None  # 7 days on the peak; set when first_week

    @property
    def total(self) -> Decimal:
        return self.principal + self.interest


@dataclass(frozen=True)
class HistoryRow:
    on: date
    kind: str
    accrued_days: int | None


def advance(position: Position, entry: Entry) -> Position:
    return Position(
        as_of=entry.on,
        principal=entry.principal_balance,
        interest=entry.interest_balance,
        compoundings=position.compoundings + (1 if entry.kind == COMPOUNDING else 0),
        window_peak=max(window_peak(position), entry.principal_balance),
        window_interest_paid=position.window_interest_paid + (entry.current_interest if entry.kind == COLLECTION else ZERO),
    )


def first_week_end(terms: LoanTerms) -> date:
    """Day 7 of the loan (W), the last day covered by the first-week charge."""
    return terms.start_date + timedelta(days=CLOSING_MINIMUM_DAYS - 1)


def first_week_open(terms: LoanTerms, position: Position) -> bool:
    """True until the first-week charge is settled, i.e. while no entry is dated after day 7."""
    return position.as_of <= first_week_end(terms)


def window_peak(position: Position) -> Decimal:
    if position.window_peak is None:
        return position.principal
    return max(position.window_peak, position.principal)


def _first_week_due(terms: LoanTerms, position: Position, days: int = CLOSING_MINIMUM_DAYS) -> Decimal:
    """Unrounded first-week interest still to charge: `days` on the peak, less interest already
    charged in the window (paid, or owed on the position), so loans begun under the earlier
    rule are never charged twice."""
    charged = position.window_interest_paid + max(position.interest, ZERO)
    return max(ZERO, interest_for(window_peak(position), terms.rate, days) - charged)


def opening_entry(terms: LoanTerms, principal: Decimal) -> Entry:
    return Entry(NEW_LOAN, terms.start_date, ZERO, ZERO, ZERO, money(principal), ZERO, 0)


def anniversary(terms: LoanTerms, number: int) -> date:
    """Compounding dates are anchored to the loan date: start + 365·k."""
    return terms.start_date + timedelta(days=COMPOUNDING_INTERVAL_DAYS * number)


def due_compoundings(terms: LoanTerms, position: Position, as_of: date) -> tuple[list[Entry], Position]:
    """Compounding entries due on or before `as_of`, and the position after them.

    If a past anniversary was never applied and later entries already exist (legacy
    data), the compounding is dated on the latest entry so the ledger stays in order.
    A compounding that ends the first week settles the 7 days on the peak plus the exact
    days after day 7, rounded once.
    """
    entries: list[Entry] = []
    current = position
    while True:
        due = anniversary(terms, current.compoundings + 1)
        if due > as_of:
            break
        on = max(due, current.as_of)
        if first_week_open(terms, current):
            extra = (on - first_week_end(terms)).days - 1
            days = CLOSING_MINIMUM_DAYS + extra
            accrued = _first_week_due(terms, current) + interest_for(current.principal, terms.rate, extra)
        else:
            days = accrual_days(current.as_of, on, PeriodEnd.COMPOUNDING)
            accrued = interest_for(current.principal, terms.rate, days)
        interest = money(current.interest + accrued)
        principal = money(current.principal + interest)
        entry = Entry(COMPOUNDING, on, ZERO, interest, ZERO, principal, ZERO, days)
        entries.append(entry)
        current = advance(current, entry)
    return entries, current


def days_already_charged(rows: Iterable[HistoryRow]) -> int:
    """Interest days charged so far. Legacy rows (no accrued_days) count exact days."""
    total = 0
    previous: date | None = None
    for row in sorted(rows, key=lambda r: r.on):
        if row.kind == NEW_LOAN:
            previous = row.on
            continue
        if row.accrued_days is not None:
            total += row.accrued_days
        elif previous is not None:
            total += max(0, (row.on - previous).days)
        previous = row.on
    return total


def quote(terms: LoanTerms, position: Position, as_of: date, *, closing: bool = False) -> Quote:
    """What is owed on `as_of`. A closing quote inside the first 7 days charges 7 days on the
    window peak; a display quote there shows the peak's interest for the days so far."""
    if as_of < position.as_of:
        raise LedgerError(
            "backdated",
            "This date is before the loan's latest entry. Entries must be recorded in order.",
        )
    compoundings, current = due_compoundings(terms, position, as_of)
    if current.interest < 0:
        # A negative interest balance (earlier system) is a credit: it reduces what is owed.
        current = replace(current, principal=current.principal + current.interest, interest=ZERO)
    peak: Decimal | None = None
    first_week = False
    if not first_week_open(terms, current):
        days = accrual_days(current.as_of, as_of, PeriodEnd.CUSTOMER)
        accrued = interest_for(current.principal, terms.rate, days)
    else:
        peak = money(window_peak(current))
        end = first_week_end(terms)
        if as_of > end:  # the first event after day 7 settles the first week
            extra = (as_of - end).days
            days = CLOSING_MINIMUM_DAYS + extra
            accrued = _first_week_due(terms, current) + interest_for(current.principal, terms.rate, extra)
        else:
            first_week = True
            days = CLOSING_MINIMUM_DAYS if closing else (as_of - terms.start_date).days + 1
            accrued = _first_week_due(terms, current, days)
    return Quote(
        as_of=as_of,
        compoundings=tuple(compoundings),
        position=current,
        period_days=days,
        principal=money(current.principal),
        interest=money(current.interest + accrued),
        first_week=first_week,
        window_peak=peak,
        first_week_interest=money(interest_for(peak, terms.rate, CLOSING_MINIMUM_DAYS)) if first_week else None,
    )


def collect(q: Quote, amount: object) -> Entry:
    """Record a payment. Interest is settled first, the rest reduces principal. In the first
    7 days the whole payment reduces principal and no interest accrues."""
    paid = parse_amount(amount, field="Collection amount")
    if q.first_week:
        if paid >= q.principal:
            raise LedgerError(
                "first_week_clears_principal",
                f"In the first {CLOSING_MINIMUM_DAYS} days a payment goes to principal. "
                f"₹{paid} would clear the principal; use Close loan to settle.",
            )
        return Entry(
            kind=COLLECTION,
            on=q.as_of,
            amount_paid=paid,
            current_principal=-paid,
            current_interest=ZERO,
            principal_balance=q.principal - paid,
            interest_balance=money(q.position.interest),
            accrued_days=0,
        )
    if paid >= q.total:
        raise LedgerError(
            "settle_with_close",
            f"₹{paid} would settle the whole amount due (₹{q.total}). Use 'Close loan' to settle in full, "
            "so the closing rules apply and the pledged items are released.",
        )
    return _payment(q, paid)


def _payment(q: Quote, paid: Decimal) -> Entry:
    # A legacy negative interest balance is a credit: it never makes "interest paid" negative.
    interest_paid = max(ZERO, min(paid, q.interest))
    principal_paid = paid - interest_paid
    return Entry(
        kind=COLLECTION,
        on=q.as_of,
        amount_paid=paid,
        current_principal=-principal_paid if principal_paid else ZERO,
        current_interest=interest_paid,
        principal_balance=q.principal - principal_paid,
        interest_balance=q.interest - interest_paid,
        accrued_days=q.period_days,
    )


def top_up(q: Quote, amount: object) -> Entry:
    """Disburse additional principal. Interest accrued so far stays owed. In the first 7 days
    nothing accrues; the new principal can raise the window peak."""
    added = parse_amount(amount, field="Additional principal")
    return Entry(
        kind=TOP_UP,
        on=q.as_of,
        amount_paid=ZERO,
        current_principal=added,
        current_interest=ZERO,
        principal_balance=q.principal + added,
        interest_balance=money(q.position.interest) if q.first_week else q.interest,
        accrued_days=0 if q.first_week else q.period_days,
    )


def close(q: Quote, amount_received: object, *, write_off_remaining: bool) -> list[Entry]:
    """Settle a loan. `q` must be a closing quote (first-week charge applied).

    Records the cash actually received, then writes off anything left over (only when
    explicitly confirmed). Accrual happens once for the whole closing event. A loan with
    nothing owed closes without any ledger entry.
    """
    received = parse_amount(amount_received, field="Amount received", allow_zero=True)
    if received > q.total:
        raise LedgerError("overpayment", f"The amount received exceeds the closing amount of ₹{q.total}.")
    entries: list[Entry] = []
    principal_left, interest_left, writeoff_days = q.principal, q.interest, q.period_days
    if received > 0:
        payment = _payment(q, received)
        entries.append(payment)
        principal_left, interest_left, writeoff_days = payment.principal_balance, payment.interest_balance, 0
    remaining = principal_left + interest_left
    if remaining > 0:
        if not write_off_remaining:
            raise LedgerError(
                "writeoff_not_confirmed",
                f"₹{remaining} would remain unpaid. Confirm the write-off to close the loan.",
            )
        entries.append(
            Entry(
                kind=WRITE_OFF,
                on=q.as_of,
                amount_paid=ZERO,
                current_principal=ZERO,
                current_interest=ZERO,
                principal_balance=ZERO,
                interest_balance=ZERO,
                accrued_days=writeoff_days,
                writeoff_principal=max(principal_left, ZERO),
                writeoff_interest=max(interest_left, ZERO),
            )
        )
    return entries


CLOSING = "close"  # history-import event only: stored as the addColl/writeoff rows of a live close


@dataclass(frozen=True)
class ImportEvent:
    on: date
    kind: str  # COLLECTION, TOP_UP or CLOSING
    amount: Decimal  # for CLOSING: the amount received (may be zero)
    write_off_remaining: bool = False  # CLOSING only: confirms writing off what the amount leaves unpaid


def simulate(terms: LoanTerms, principal: Decimal, events: Sequence[ImportEvent], today: date) -> list[Entry]:
    """Replay a loan's history (used by history import preview and commit alike). The
    first-7-days rule applies exactly as for live entries; `advance` tracks the peak.
    A closing event uses the live closing quote and `close`, must come last, and stops the
    replay: a closed loan gets no compounding afterwards."""
    if terms.start_date > today:
        raise LedgerError("future_date", "The loan date cannot be in the future.")
    entries = [opening_entry(terms, principal)]
    position = Position(terms.start_date, money(principal), ZERO, 0)
    closed = False
    for event in sorted(events, key=lambda e: e.on):
        if event.on < terms.start_date:
            raise LedgerError("backdated", f"An entry on {event.on} is before the loan date.")
        if event.on > today:
            raise LedgerError("future_date", f"An entry on {event.on} is in the future.")
        if closed:
            if event.kind == CLOSING:
                raise LedgerError("close_twice", "A loan can be closed only once.")
            raise LedgerError("close_not_last", "The loan closing must be the last entry.")
        if event.kind == CLOSING:
            q = quote(terms, position, event.on, closing=True)
            entries.extend(q.compoundings)
            entries.extend(close(q, event.amount, write_off_remaining=event.write_off_remaining))
            closed = True
            continue
        q = quote(terms, position, event.on)
        entries.extend(q.compoundings)
        if event.kind == COLLECTION:
            entry = collect(q, event.amount)
        elif event.kind == TOP_UP:
            entry = top_up(q, event.amount)
        else:
            raise LedgerError("invalid_type", f"Unsupported entry type '{event.kind}'.")
        entries.append(entry)
        position = advance(q.position, entry)
    if not closed:
        trailing, _ = due_compoundings(terms, position, today)
        entries.extend(trailing)
    return entries
