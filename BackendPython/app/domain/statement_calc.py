"""How each ledger row's interest was worked out ("Show calculation" on the statement).

Everything is derived from the values stored on the rows: the previous row's balances, the
row's accrued days, amounts and resulting balances. Nothing is recalculated from today's
rules, so a row always explains what was actually recorded. Rows from the earlier system
(created_at NULL) are not explained. A self-check reproduces each row's interest from the
stored figures; when it cannot, the row is shown "as recorded". `explain` never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .dates import business_date
from .interest import CLOSING_MINIMUM_DAYS, interest_for
from .ledger import COLLECTION, COMPOUNDING, NEW_LOAN, TOP_UP, WRITE_OFF, LoanTerms, first_week_end
from .money import ZERO, money

METHODS = (
    "opening", "first_week", "first_week_settlement", "inclusive", "compounding", "writeoff", "legacy", "as_recorded",
)
LEGACY_NOTE = "Earlier system — not recalculated"
AS_RECORDED_NOTE = "Shown as recorded; these figures could not be worked out again from the stored entries."


@dataclass(frozen=True)
class Calculation:
    method: str
    interest_paid: Decimal
    principal_paid: Decimal
    principal_balance: Decimal
    interest_balance: Decimal
    period_from: date | None = None
    period_to: date | None = None
    days: int | None = None
    principal_charged: Decimal | None = None
    rate: Decimal | None = None
    interest_accrued: Decimal | None = None
    peak_principal: Decimal | None = None  # first-week settlement only
    first_week_days: int | None = None
    extra_days: int | None = None
    extra_principal: Decimal | None = None
    note: str | None = None


def explain(terms: LoanTerms, rows: list[dict], *, opening: object = None) -> list[Calculation]:
    """One Calculation per row, in the order given (oldest first). `opening` is the loan's
    opening principal, used for the first-week peak when no opening row exists."""
    end = first_week_end(terms)
    peak = money(opening) if opening is not None else None
    window_paid = ZERO
    previous: dict | None = None
    result: list[Calculation] = []
    for row in rows:
        try:
            calc = _explain_row(terms, end, row, previous, peak, window_paid)
        except Exception:  # never let one odd row break the statement
            calc = _as_recorded(row)
        result.append(calc)
        try:
            if business_date(row["date"]) <= end:
                if row.get("principlebalance") is not None:
                    balance = money(row["principlebalance"])
                    peak = balance if peak is None else max(peak, balance)
                if row.get("transactiontype") == COLLECTION:
                    window_paid += money(row.get("currentinterest") or 0)
        except Exception:
            pass
        previous = row
    return result


def _num(value: object) -> Decimal:
    return money(value if value is not None else 0)


def _base(row: dict) -> dict:
    kind = row.get("transactiontype")
    principal_change = _num(row.get("currentprincipal"))
    legacy_writeoff = kind == WRITE_OFF and row.get("writeoff_principal") is None
    return {
        "interest_paid": _num(row.get("currentinterest")) if kind == COLLECTION else ZERO,
        "principal_paid": -principal_change if kind == COLLECTION and principal_change < 0 else ZERO,
        "principal_balance": ZERO if legacy_writeoff else _num(row.get("principlebalance")),
        "interest_balance": _num(row.get("interestbalance")),
    }


def _safe_base(row: dict) -> dict:
    try:
        return _base(row)
    except Exception:
        return {"interest_paid": ZERO, "principal_paid": ZERO, "principal_balance": ZERO, "interest_balance": ZERO}


def _as_recorded(row: dict) -> Calculation:
    return Calculation("as_recorded", note=AS_RECORDED_NOTE, **_safe_base(row))


def _rupees(value: Decimal) -> str:
    return f"₹{money(value)}"


def _pct(rate: Decimal) -> str:
    return format(rate.normalize(), "f")


def _day(value: date) -> str:
    return f"{value.day} {value:%b %Y}"


def _formula(principal: Decimal, rate: Decimal, days: int) -> str:
    return (f"{_rupees(principal)} × {_pct(rate)}% × {days} ÷ 365 = "
            f"{_rupees(interest_for(principal, rate, days))}")


def _explain_row(terms: LoanTerms, end: date, row: dict, previous: dict | None, peak: Decimal | None,
                 window_paid: Decimal) -> Calculation:
    base = _base(row)
    kind = row.get("transactiontype")
    if "created_at" in row and row.get("created_at") is None:
        return Calculation("legacy", note=LEGACY_NOTE, **base)
    if kind == NEW_LOAN:
        return Calculation("opening", rate=terms.rate,
                           note=f"Loan opened with principal {_rupees(base['principal_balance'])} "
                                f"at {_pct(terms.rate)}% a year.", **base)
    days = row.get("accrued_days")
    if previous is None or days is None or kind not in (COLLECTION, TOP_UP, COMPOUNDING, WRITE_OFF):
        return _as_recorded(row)

    on = business_date(row["date"])
    prev_on = business_date(previous["date"])
    p0, i0 = _num(previous.get("principlebalance")), _num(previous.get("interestbalance"))
    if kind == COMPOUNDING:
        p_base, i_base = p0, i0
    elif i0 < 0:  # a legacy interest credit reduces principal before a customer event (ledger.quote)
        p_base, i_base = p0 + i0, ZERO
    else:
        p_base, i_base = p0, i0
    change = _num(row.get("currentprincipal"))
    p_after, i_after = _num(row.get("principlebalance")), _num(row.get("interestbalance"))

    # Interest accrued by this row, and a check that the stored balances follow from it.
    if kind == COLLECTION:
        accrued = i_after + base["interest_paid"] - i_base
        consistent = p_after == p_base + change
    elif kind == TOP_UP:
        accrued = i_after - i_base
        consistent = p_after == p_base + change
    elif kind == COMPOUNDING:
        accrued = change - i_base
        consistent = p_after == p_base + change and i_after == ZERO
    else:  # write-off: the remaining balances, carrying the accrual when no cash was received
        w_principal, w_interest = _num(row.get("writeoff_principal")), _num(row.get("writeoff_interest"))
        accrued = w_interest - i_base
        consistent = (row.get("writeoff_principal") is not None and p_after == ZERO and i_after == ZERO
                      and w_principal == max(p_base, ZERO))
    if not consistent:
        return _as_recorded(row)

    rate = terms.rate
    common = dict(base, rate=rate, interest_accrued=accrued)
    unsettled = prev_on <= end
    if days == 0:
        if accrued != ZERO:
            return _as_recorded(row)
        if kind == WRITE_OFF:
            return Calculation("writeoff", days=0, note=_writeoff_note(row), **common)
        if unsettled and on <= end and kind in (COLLECTION, TOP_UP):
            if kind == COLLECTION:
                text = f"payment reduces principal by {_rupees(-change)}"
            else:
                text = f"{_rupees(change)} added to principal"
            return Calculation(
                "first_week", days=0,
                note=f"First {CLOSING_MINIMUM_DAYS} days: no daily interest; {text}. {CLOSING_MINIMUM_DAYS} days' "
                     f"interest on the highest principal is charged at closing or on day {CLOSING_MINIMUM_DAYS + 1}.",
                **common,
            )
        if kind == COMPOUNDING:
            return Calculation("compounding", period_from=prev_on, period_to=on, days=0, principal_charged=p_base,
                               note=f"Yearly compounding on the latest entry date: {_rupees(change)} of interest "
                                    "added to principal.", **common)
        return _as_recorded(row)

    had_window_events = (
        previous is not None
        and previous.get("transactiontype") != NEW_LOAN
        and business_date(previous["date"]) <= end
    )
    needs_split = had_window_events or (peak is not None and peak != p_base) or window_paid > ZERO or i0 > ZERO
    if unsettled and peak is not None and days >= CLOSING_MINIMUM_DAYS:
        extra = days - CLOSING_MINIMUM_DAYS
        if on > end:
            expected_extra = (on - end).days - (1 if kind == COMPOUNDING else 0)
        else:
            expected_extra = 0
        if extra == expected_extra and (extra == 0 or needs_split):
            charged = window_paid + max(i0, ZERO)
            week = interest_for(peak, rate, CLOSING_MINIMUM_DAYS)
            raw = max(ZERO, week - charged) + interest_for(p_base, rate, extra)
            if money(i_base + raw) - i_base == accrued:
                parts = [f"First {CLOSING_MINIMUM_DAYS} days on the highest principal: "
                         f"{_formula(peak, rate, CLOSING_MINIMUM_DAYS)}"]
                if charged > 0:
                    parts.append(f"less {_rupees(charged)} already charged in those days")
                if extra:
                    parts.append(f"plus {extra} day{'s' if extra != 1 else ''} after day {CLOSING_MINIMUM_DAYS}: "
                                 f"{_formula(p_base, rate, extra)}")
                note = "; ".join(parts) + f". Interest {_rupees(accrued)}, rounded once."
                if kind == COMPOUNDING:
                    note += " Added to principal (yearly compounding)."
                if kind == WRITE_OFF:
                    note += " " + _writeoff_note(row)
                return Calculation(
                    "writeoff" if kind == WRITE_OFF else "first_week_settlement",
                    period_from=terms.start_date, period_to=max(on, end), days=days, peak_principal=peak,
                    first_week_days=CLOSING_MINIMUM_DAYS, extra_days=extra, extra_principal=p_base if extra else None,
                    note=note, **common,
                )

    if money(i_base + interest_for(p_base, rate, days)) - i_base != accrued:
        return _as_recorded(row)
    span = f"{days} day{'s' if days != 1 else ''} ({_day(prev_on)} to {_day(on)}"
    if kind == COMPOUNDING:
        note = f"Yearly compounding, {span}, exact days): {_formula(p_base, rate, days)}"
        if i_base > 0:
            note += f", plus {_rupees(i_base)} interest owed"
        method, note = "compounding", note + "; added to principal."
    else:
        method = "writeoff" if kind == WRITE_OFF else "inclusive"
        note = f"{span}, both days counted): {_formula(p_base, rate, days)}."
        if kind == WRITE_OFF:
            note += " " + _writeoff_note(row)
    return Calculation(method, period_from=prev_on, period_to=on, days=days, principal_charged=p_base,
                       note=note, **common)


def _writeoff_note(row: dict) -> str:
    return (f"Written off: principal {_rupees(_num(row.get('writeoff_principal')))}, "
            f"interest {_rupees(_num(row.get('writeoff_interest')))}.")
