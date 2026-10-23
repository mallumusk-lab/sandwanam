"""Branch cash ledger (the drawer book): categories, entry rules, day totals and retention.

Independent of loans: every amount is entered by hand and nothing here reads the loan
ledger. A day opens with the drawer counted against the amount carried forward from the
last closed day, records cash in and out (voided lines do not count), and closes with
the drawer counted against the expected amount. Totals are always worked out here, on
the server.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Mapping

from .money import MAX_AMOUNT, ZERO, AmountError, money, parse_amount, to_decimal

IN, OUT, ANY = "in", "out", "any"
DIRECTIONS = (IN, OUT)
OTHER = "other"
RETENTION_DAYS = 14  # today and the 13 days before it
MAX_DESCRIPTION = 255
MAX_REFERENCE = 40
MIN_REASON, MAX_REASON = 3, 255


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    direction: str  # IN, OUT or ANY


CATEGORIES = (
    Category("loan_collection", "Loan collection", IN),
    Category("from_head_office", "Cash from head office", IN),
    Category("other_income", "Other income", IN),
    Category("loan_disbursement", "Loan disbursement", OUT),
    Category("bill_payment", "Bill payment", OUT),
    Category("donation", "Donation", OUT),
    Category("expense", "Expense", OUT),
    Category("to_head_office", "Cash to head office / bank", OUT),
    Category(OTHER, "Other (type a description)", ANY),
)
_BY_KEY = {c.key: c for c in CATEGORIES}


class CashError(ValueError):
    def __init__(self, field: str, message: str, code: str):
        super().__init__(message)
        self.field = field
        self.message = message
        self.code = code


def label(key: str) -> str:
    category = _BY_KEY.get(key)
    return category.label if category else key


def _text(value: str | None) -> str | None:
    return " ".join((value or "").split()) or None


@dataclass(frozen=True)
class NewEntry:
    direction: str
    category: str
    description: str | None
    reference: str | None
    amount: Decimal


def validate_entry(direction: str, category: str, description: str | None, reference: str | None,
                   amount: object) -> NewEntry:
    if direction not in DIRECTIONS:
        raise CashError("direction", "Choose cash in or cash out.", "invalid_direction")
    chosen = _BY_KEY.get(category)
    if chosen is None:
        raise CashError("category", "Choose a category from the list.", "invalid_category")
    if chosen.direction != ANY and chosen.direction != direction:
        raise CashError("category", f"{chosen.label} is cash {chosen.direction}, not cash {direction}.",
                        "category_direction")
    text = _text(description)
    if text is not None and len(text) > MAX_DESCRIPTION:
        raise CashError("description", f"The description can have at most {MAX_DESCRIPTION} characters.",
                        "invalid_description")
    if chosen.key == OTHER and text is None:
        raise CashError("description", "Type a description for this entry.", "description_required")
    ref = _text(reference)
    if ref is not None and len(ref) > MAX_REFERENCE:
        raise CashError("reference", f"The reference can have at most {MAX_REFERENCE} characters.",
                        "invalid_reference")
    try:
        value = parse_amount(amount, field="Amount")
    except AmountError as exc:
        raise CashError("amount", str(exc), "invalid_amount") from exc
    return NewEntry(direction, chosen.key, text, ref, value)


def counted(value: object, *, field: str, name: str) -> Decimal:
    """A drawer count: zero or more, at most 2 decimal places. `name` is shown in messages."""
    try:
        return parse_amount(value, field=name, allow_zero=True)
    except AmountError as exc:
        raise CashError(field, str(exc), "invalid_amount") from exc


def shown_amount(value: object, *, field: str) -> Decimal:
    """A figure the client was shown and sends back for comparison (may be below zero)."""
    try:
        amount = to_decimal(value)
    except AmountError as exc:
        raise CashError(field, "The expected cash amount is not a number.", "invalid_amount") from exc
    if abs(amount) > MAX_AMOUNT:
        raise CashError(field, "The expected cash amount is too large.", "invalid_amount")
    return money(amount)


def void_reason(value: str | None) -> str:
    text = _text(value)
    if text is None or len(text) < MIN_REASON:
        raise CashError("reason", f"Give a reason of at least {MIN_REASON} characters.", "invalid_reason")
    if len(text) > MAX_REASON:
        raise CashError("reason", f"The reason can have at most {MAX_REASON} characters.", "invalid_reason")
    return text


@dataclass(frozen=True)
class Totals:
    cash_in: Decimal
    cash_out: Decimal
    expected: Decimal  # opening counted + cash in - cash out
    opening_difference: Decimal  # opening counted - carried forward; negative is a shortage


def is_voided(entry: Mapping) -> bool:
    return entry.get("voided_at") is not None


def day_totals(carried: object, opening: object, entries: Iterable[Mapping]) -> Totals:
    """Totals of one day. Entries are mappings with direction, amount and voided_at."""
    cash_in = cash_out = ZERO
    for entry in entries:
        if is_voided(entry):
            continue
        if entry["direction"] == IN:
            cash_in += money(entry["amount"])
        elif entry["direction"] == OUT:
            cash_out += money(entry["amount"])
    opening_counted = money(opening)
    return Totals(cash_in, cash_out, opening_counted + cash_in - cash_out, opening_counted - money(carried))


def closing_difference(expected: object, counted_: object) -> Decimal:
    """Counted minus expected: negative is a shortage, positive an excess."""
    return money(counted_) - money(expected)


def cutoff(today: date) -> date:
    """The oldest day kept: days before it are deleted (each branch's latest day excepted)."""
    return today - timedelta(days=RETENTION_DAYS - 1)
