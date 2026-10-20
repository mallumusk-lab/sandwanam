"""The loan ledger as pure functions.

Every operation takes the loan terms and the current position (the balances recorded on
the latest ledger entry) and returns the entries to append. Nothing here touches the
database, so the same code serves live postings, display quotes and history imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from .interest import (
    CLOSING_MINIMUM_DAYS,
    COMPOUNDING_INTERVAL_DAYS,
    PeriodEnd,
    accrual_days,
    closing_days,
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
    """Balances after the latest ledger entry."""

    as_of: date
    principal: Decimal
    interest: Decimal
    compoundings: int = 0


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
    loan_age_days: int = CLOSING_MINIMUM_DAYS  # inclusive age on as_of

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
    )


def opening_entry(terms: LoanTerms, principal: Decimal) -> Entry:
    return Entry(NEW_LOAN, terms.start_date, ZERO, ZERO, ZERO, money(principal), ZERO, 0)


def anniversary(terms: LoanTerms, number: int) -> date:
    """Compounding dates are anchored to the loan date: start + 365·k."""
    return terms.start_date + timedelta(days=COMPOUNDING_INTERVAL_DAYS * number)


def due_compoundings(terms: LoanTerms, position: Position, as_of: date) -> tuple[list[Entry], Position]:
    """Compounding entries due on or before `as_of`, and the position after them.

    If a past anniversary was never applied and later entries already exist (legacy
    data), the compounding is dated on the latest entry so the ledger stays in order.
    """
    entries: list[Entry] = []
    current = position
    while True:
        due = anniversary(terms, current.compoundings + 1)
        if due > as_of:
            break
        on = max(due, current.as_of)
        days = accrual_days(current.as_of, on, PeriodEnd.COMPOUNDING)
        interest = money(current.interest + interest_for(current.principal, terms.rate, days))
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


def quote(
    terms: LoanTerms,
    position: Position,
    as_of: date,
    *,
    closing: bool = False,
    prior_days_charged: int = 0,
) -> Quote:
    if as_of < position.as_of:
        raise LedgerError(
            "backdated",
            "This date is before the loan's latest entry. Entries must be recorded in order.",
        )
    compoundings, current = due_compoundings(terms, position, as_of)
    if current.interest < 0:
        # A negative interest balance (earlier system) is a credit: it reduces what is owed.
        current = Position(current.as_of, current.principal + current.interest, ZERO, current.compoundings)
    days = accrual_days(current.as_of, as_of, PeriodEnd.CUSTOMER)
    age = (as_of - terms.start_date).days + 1
    if closing:
        days = closing_days(days, prior_days_charged + sum(c.accrued_days for c in compoundings), age)
    interest = money(current.interest + interest_for(current.principal, terms.rate, days))
    return Quote(
        as_of=as_of,
        compoundings=tuple(compoundings),
        position=current,
        period_days=days,
        principal=money(current.principal),
        interest=interest,
        loan_age_days=age,
    )


def collect(q: Quote, amount: object) -> Entry:
    """Record a payment. Interest is settled first, the rest reduces principal."""
    paid = parse_amount(amount, field="Collection amount")
    if paid >= q.total:
        raise LedgerError(
            "settle_with_close",
            f"₹{paid} would settle the whole amount due (₹{q.total}). Use 'Close loan' to settle in full, "
            "so the closing rules apply and the pledged items are released.",
        )
    if q.loan_age_days < CLOSING_MINIMUM_DAYS and paid > q.interest:
        raise LedgerError(
            "early_principal",
            f"In a loan's first {CLOSING_MINIMUM_DAYS} days a payment can cover interest only (₹{q.interest} now). "
            "To repay principal, close the loan; the 7-day minimum applies.",
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
    """Disburse additional principal. Interest accrued so far stays owed."""
    added = parse_amount(amount, field="Additional principal")
    return Entry(
        kind=TOP_UP,
        on=q.as_of,
        amount_paid=ZERO,
        current_principal=added,
        current_interest=ZERO,
        principal_balance=q.principal + added,
        interest_balance=q.interest,
        accrued_days=q.period_days,
    )


def close(q: Quote, amount_received: object, *, write_off_remaining: bool) -> list[Entry]:
    """Settle a loan. `q` must be a closing quote (7-day minimum applied).

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


@dataclass(frozen=True)
class ImportEvent:
    on: date
    kind: str  # COLLECTION or TOP_UP
    amount: Decimal


def simulate(terms: LoanTerms, principal: Decimal, events: Sequence[ImportEvent], today: date) -> list[Entry]:
    """Replay a loan's history (used by history import preview and commit alike)."""
    if terms.start_date > today:
        raise LedgerError("future_date", "The loan date cannot be in the future.")
    entries = [opening_entry(terms, principal)]
    position = Position(terms.start_date, money(principal), ZERO, 0)
    for event in sorted(events, key=lambda e: e.on):
        if event.on < terms.start_date:
            raise LedgerError("backdated", f"An entry on {event.on} is before the loan date.")
        if event.on > today:
            raise LedgerError("future_date", f"An entry on {event.on} is in the future.")
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
    trailing, _ = due_compoundings(terms, position, today)
    entries.extend(trailing)
    return entries
