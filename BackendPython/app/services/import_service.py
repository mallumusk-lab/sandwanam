"""History import: enter a loan that started before this system, with its past entries.

Preview is a pure simulation (no database writes). Commit replays the same simulation
inside one transaction, so what was previewed is exactly what gets stored. A loan that was
already settled ends with a close entry: it is closed with the live closing rules (first-7-days
minimum, write-off only when confirmed) on that date, exactly as if closed live that day.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Sequence

from ..domain import dates, ledger, particulars, validation
from ..domain.ledger import ImportEvent, LoanTerms
from ..domain.money import ZERO, AmountError, parse_amount
from ..errors import Conflict, Invalid, NotFound
from . import serialize
from .context import Actor, ensure_visible
from .customers_service import NewCustomer
from .customers_service import create as create_customer
from .loans_service import CLOSING_PAIR_GAP, stamps_for

MAX_EVENTS = 500


@dataclass(frozen=True)
class HistoryLoan:
    items: Sequence[dict]
    gross_weight: str
    deduction: str
    principal: str
    rate: str
    tenure_months: int
    loan_date: date


@dataclass(frozen=True)
class HistoryEntry:
    on: date
    kind: str
    amount: str  # for a close: the amount received (may be zero)
    write_off_remaining: bool = False  # close only


@dataclass(frozen=True)
class Validated:
    items: list
    gross: Decimal
    deduction: Decimal
    net: Decimal
    principal: Decimal
    rate: Decimal
    tenure: int
    events: list[ImportEvent]


def _validate(loan: HistoryLoan, entries: Sequence[HistoryEntry]) -> Validated:
    try:
        items = particulars.validate(list(loan.items))
        gross, deduction, net = validation.weights(loan.gross_weight, loan.deduction)
        principal = parse_amount(loan.principal, field="Loan amount")
        rate = validation.rate(loan.rate)
        tenure = validation.tenure(loan.tenure_months)
        if len(entries) > MAX_EVENTS:
            raise Invalid(f"A history import can have at most {MAX_EVENTS} entries.", code="too_many_entries")
        events = []
        for index, entry in enumerate(entries, start=1):
            if entry.kind not in (ledger.COLLECTION, ledger.TOP_UP, ledger.COMPOUNDING, ledger.CLOSING):
                raise Invalid(f"Entry {index} has an unknown type.", code="invalid_entry")
            closing = entry.kind == ledger.CLOSING
            compounding = entry.kind == ledger.COMPOUNDING
            amount = parse_amount(entry.amount, field=f"Entry {index} amount", allow_zero=closing or compounding)
            events.append(ImportEvent(entry.on, entry.kind, amount, closing and bool(entry.write_off_remaining)))
        _check_close_is_last(events)
    except (particulars.ItemsError, validation.ValidationError, AmountError) as exc:
        raise Invalid(str(exc), code="invalid_import", details={"field": getattr(exc, "field", "loan")}) from exc
    return Validated(items, gross, deduction, net, principal, rate, tenure, events)


def _check_close_is_last(events: Sequence[ImportEvent]) -> None:
    closes = [i for i, e in enumerate(events) if e.kind == ledger.CLOSING]
    if len(closes) > 1:
        raise Invalid("A loan can be closed only once. Remove the extra close entry.", code="close_twice")
    if closes:
        close = events[closes[0]]
        if closes[0] != len(events) - 1 or any(e.on > close.on for e in events):
            raise Invalid("The loan closing must be the last entry. Remove or move the entries after it.",
                          code="close_not_last")


def _closing(v: Validated) -> ImportEvent | None:
    return next((e for e in v.events if e.kind == ledger.CLOSING), None)


def _stamps(simulated: Sequence[ledger.Entry], closing: ImportEvent | None, now: datetime) -> list[datetime]:
    """Storage stamps for the imported rows. Past entries on one day sit 1 µs apart at IST noon,
    so the close's own rows (its payment, if any, and its write-off) start more than
    CLOSING_PAIR_GAP after the entry before them: a same-day earlier payment must not look like
    the closing payment on its receipt (receipts_service.for_statement)."""
    at_values = stamps_for(simulated, None, now)
    if closing is None:
        return at_values
    own = (1 if closing.amount > ZERO else 0) + (1 if simulated[-1].kind == ledger.WRITE_OFF else 0)
    first = len(simulated) - own
    if own == 0 or first < 1 or at_values[first] - at_values[first - 1] > CLOSING_PAIR_GAP:
        return at_values
    step = timedelta(microseconds=1)
    start = at_values[first - 1] + CLOSING_PAIR_GAP + step
    return at_values[:first] + [start + step * i for i in range(own)]


def _simulate(v: Validated, loan_date: date, today: date) -> list[ledger.Entry]:
    try:
        return ledger.simulate(LoanTerms.of(loan_date, v.rate), v.principal, v.events, today)
    except ledger.LedgerError as exc:
        raise Invalid(exc.message, code=exc.code) from exc


def _entry_view(entry: ledger.Entry, index: int) -> dict:
    return {
        "index": index,
        "kind": entry.kind,
        "date": entry.on.isoformat(),
        "amount_paid": serialize.money(entry.amount_paid),
        "principal_change": serialize.money(entry.current_principal),
        "interest_paid": serialize.money(entry.current_interest),
        "principal_balance": serialize.money(entry.principal_balance),
        "interest_balance": serialize.money(entry.interest_balance),
        "accrued_days": entry.accrued_days,
        "writeoff_principal": serialize.money(entry.writeoff_principal),  # None except on a write-off row
        "writeoff_interest": serialize.money(entry.writeoff_interest),
    }


async def preview(actor: Actor, loan: HistoryLoan, entries: Sequence[HistoryEntry], now: datetime) -> dict:
    actor.require("history")
    validated = _validate(loan, entries)
    closing = _closing(validated)
    if closing is not None and not closing.write_off_remaining:
        # Show the rows as if the write-off were confirmed, so the remainder can be offered for
        # confirmation; commit still refuses it until write_off_remaining is set.
        validated = replace(validated, events=[replace(e, write_off_remaining=True) if e is closing else e
                                               for e in validated.events])
    simulated = _simulate(validated, loan.loan_date, dates.business_date(now))
    final = simulated[-1]
    written_off = [e for e in simulated if e.kind == ledger.WRITE_OFF]
    remaining = sum(((e.writeoff_principal or ZERO) + (e.writeoff_interest or ZERO) for e in written_off), ZERO)
    return {
        "entries": [_entry_view(e, i) for i, e in enumerate(simulated)],
        "principal_balance": serialize.money(final.principal_balance),
        "interest_balance": serialize.money(final.interest_balance),
        "closes_on": closing.on.isoformat() if closing is not None else None,
        "remaining_after_close": serialize.money(remaining) if written_off else None,
    }


async def _replay(repos, actor: Actor, request_id: str) -> dict | None:
    prior = await repos.statements.by_request_id(request_id)
    if prior is None:
        return None
    loan = await repos.loans.get(prior["loan_number"])
    if loan is None:
        raise Conflict("This request id was already used.", code="request_id_reused")
    ensure_visible(actor, loan.get("branch_prefix"), "Import")
    return {"loan_number": loan["loan_number"], "customer_id": loan["customerid"], "replayed": True}


async def commit(
    repos,
    actor: Actor,
    *,
    customer_id: int | None,
    new_customer: NewCustomer | None,
    loan: HistoryLoan,
    entries: Sequence[HistoryEntry],
    request_id: str,
    now: datetime,
    expected: dict | None = None,
    context: dict | None = None,
) -> dict:
    actor.require("history")
    if (customer_id is None) == (new_customer is None):
        raise Invalid("Choose an existing customer or enter a new one.", code="invalid_import", details={"field": "customer"})
    validated = _validate(loan, entries)
    replay = await _replay(repos, actor, request_id)
    if replay is not None:
        return replay
    simulated = _simulate(validated, loan.loan_date, dates.business_date(now))
    final = simulated[-1]
    if expected is not None and (
        serialize.money(final.principal_balance) != expected.get("principal_balance")
        or serialize.money(final.interest_balance) != expected.get("interest_balance")
    ):
        raise Conflict(
            "The calculated balances changed since the preview (for example, a new day started). Preview again.",
            code="preview_outdated",
        )

    async with repos.transaction():
        if new_customer is not None:
            if not actor.can("newcustomer"):
                raise Invalid("Your branch cannot add customers; choose an existing customer.", code="invalid_import")
            created = await create_customer(repos, actor, new_customer, context)
            customer_id = created["id"]
        customer = await repos.customers.lock(customer_id)
        if customer is None:
            raise NotFound("Customer was not found.")
        ensure_visible(actor, customer["branch_prefix"], "Customer")
        replay = await _replay(repos, actor, request_id)  # a concurrent retry may have finished meanwhile
        if replay is not None:
            return replay

        for _ in range(25):
            number = await repos.customers.next_loan_number(customer["customerid"])
            loan_number = f"{customer['user_id']}L{number}"
            if not await repos.loans.exists(loan_number):
                break
        else:
            raise Conflict("Could not allocate a loan number. Try again.", code="loan_number_unavailable")

        closing = _closing(validated)
        at_values = _stamps(simulated, closing, now)
        row = await repos.loans.insert(
            customer_id=customer["customerid"], loan_number=loan_number,
            items_json=json.dumps([i.as_dict() for i in validated.items]),
            particulars=particulars.to_display(validated.items),
            number_of_items=particulars.total_quantity(validated.items),
            weight=validated.gross, deduction=validated.deduction, net_weight=validated.net,
            principal=validated.principal, rate=validated.rate, tenure=validated.tenure,
            branch=customer["branch_prefix"], loan_date=at_values[0], created_by=actor.username,
        )
        branch = customer["branch_prefix"]
        for index, (entry, at) in enumerate(zip(simulated, at_values)):
            receipt_no = None
            if entry.kind in (ledger.COLLECTION, "disbursement", "modify"):
                for _ in range(25):
                    receipt_no = await repos.statements.next_receipt_number(branch)
                    if receipt_no is None:
                        await repos.users.ensure_counter(branch)
                        continue
                    break
            elif entry.kind == ledger.WRITE_OFF:
                previous = simulated[index - 1] if index > 0 else None
                paired = (
                    previous is not None
                    and previous.kind == ledger.COLLECTION
                    and dates.as_aware(at) - dates.as_aware(at_values[index - 1]) <= CLOSING_PAIR_GAP
                )
                if not paired:
                    for _ in range(25):
                        receipt_no = await repos.statements.next_receipt_number(branch)
                        if receipt_no is None:
                            await repos.users.ensure_counter(branch)
                            continue
                        break
            await repos.statements.insert(
                loan_id=row["loanid"], loan_number=loan_number, kind=entry.kind, at=at,
                amount_paid=entry.amount_paid, current_principal=entry.current_principal,
                current_interest=entry.current_interest, principal_balance=entry.principal_balance,
                interest_balance=entry.interest_balance, accrued_days=entry.accrued_days,
                writeoff_principal=entry.writeoff_principal, writeoff_interest=entry.writeoff_interest,
                created_by=actor.username, request_id=request_id if index == 0 else None,
                receipt_no=receipt_no,
            )
        await repos.loans.update_cache(loan_number, final.principal_balance, final.interest_balance)
        if closing is not None:  # as loans_service.close: closed at the closing entry's stamp
            closed_at = at_values[-1] if final.on == closing.on else dates.business_datetime(closing.on, now)
            await repos.loans.mark_closed(loan_number, closed_at)
        await repos.customers.refresh_loan_status(customer["customerid"])
        closed_note = f", closed on {closing.on}" if closing is not None else ""
        await repos.audit.log(
            username=actor.username, action="IMPORT_HISTORY", entity_type="LOAN", entity_id=loan_number,
            details=f"Imported loan dated {loan.loan_date} with {len(entries)} past entr{'y' if len(entries) == 1 else 'ies'}"
                    f"{closed_note}",
            ip=(context or {}).get("ip"), request_id=(context or {}).get("request_id"),
        )
    return {"loan_number": loan_number, "customer_id": customer["customerid"], "replayed": False}
