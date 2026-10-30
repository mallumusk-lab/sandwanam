"""Loans and the ledger.

Every write runs in one transaction holding a row lock on the loan, so concurrent
postings (two cashiers, a double-click, the compounding cron) serialise. Each write:
  1. applies any compounding that has fallen due,
  2. accrues interest once for the period (first-7-days rule: app/domain/ledger.py),
  3. appends the entries and refreshes the cached balances on the loan.
Daily entries are always dated today (IST); only history import records past dates.
Requests carry a client request id; replaying one returns the original result.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Sequence

from ..domain import dates, ledger, particulars, statement_calc, validation
from ..domain.ledger import Entry, LoanTerms, Position, Quote
from ..domain.money import ZERO, AmountError, money, parse_amount
from ..errors import Conflict, Invalid, NotFound
from . import serialize
from .context import Actor, ensure_visible


@dataclass(frozen=True)
class NewLoan:
    customer_id: int
    items: Sequence[dict]
    gross_weight: str
    deduction: str
    principal: str
    rate: str
    tenure_months: int


def terms_of(loan: dict) -> LoanTerms:
    return LoanTerms.of(dates.business_date(loan["date"]), loan.get("interest"))


def position_of(loan: dict, latest: dict | None, totals: dict | None) -> Position:
    """`totals` holds the ledger totals (repositories.loans.LEDGER_TOTALS)."""
    totals = totals or {}
    compoundings = int(totals.get("compoundings") or 0)
    peak = max(money(loan.get("principle_amount")), money(totals.get("peak_principal")))
    interest_paid = money(totals.get("interest_collected"))
    if latest is None:
        return Position(dates.business_date(loan["date"]), money(loan["principle_amount"]), ZERO, compoundings,
                        peak, interest_paid)
    return Position(
        dates.business_date(latest["date"]),
        money(latest.get("principlebalance") or 0),
        money(latest.get("interestbalance") or 0),
        compoundings,
        peak,
        interest_paid,
    )


def position_from_row(row: dict) -> Position:
    """Position from a loan row that carries the LATERAL position columns."""
    latest = None
    if row.get("last_entry_at") is not None:
        latest = {
            "date": row["last_entry_at"],
            "principlebalance": row.get("last_principal"),
            "interestbalance": row.get("last_interest"),
        }
    return position_of(row, latest, row)


def live_quote(row: dict, today: date) -> Quote | None:
    if row.get("loantype") != "open":
        return None
    position = position_from_row(row)
    if today < position.as_of:  # an entry dated later today in another timezone view
        today = position.as_of
    return ledger.quote(terms_of(row), position, today)


def _as_money(value: str):
    try:
        return money(value)
    except AmountError as exc:
        raise Invalid("The expected outstanding amount is not a number.", code="invalid_amount") from exc


# A closing payment and its write-off are stored 1 µs apart (stamps_for); receipts treat an
# addColl at most this far before a closing write-off as the same closing event.
CLOSING_PAIR_GAP = timedelta(milliseconds=1)


def stamps_for(entries: Sequence[Entry], previous_at: datetime | None, now: datetime) -> list[datetime]:
    """Storage timestamps that keep the ledger strictly ordered."""
    result: list[datetime] = []
    last = dates.as_aware(previous_at) if previous_at else None
    for entry in entries:
        at = dates.business_datetime(entry.on, now)
        if last is not None and at <= last:
            at = last + timedelta(microseconds=1)
        result.append(at)
        last = at
    return result


async def _load_visible(repos, actor: Actor, loan_number: str) -> dict:
    loan = await repos.loans.get(loan_number)
    if loan is None:
        raise NotFound(f"Loan {loan_number} was not found.")
    ensure_visible(actor, loan.get("branch_prefix"), f"Loan {loan_number}")
    return loan


async def _letterhead(repos, branch_prefix: str | None) -> dict | None:
    if not branch_prefix:
        return None
    row = await repos.users.branch(branch_prefix)
    return serialize.branch(row) if row else None


async def detail(repos, actor: Actor, loan_number: str, now: datetime) -> dict:
    actor.require("userlist")
    loan = await _load_visible(repos, actor, loan_number)
    statements = await repos.statements.for_loan(loan["loan_number"])  # newest first
    terms = terms_of(loan)
    oldest_first = list(reversed(statements))
    calculations = statement_calc.explain(terms, oldest_first, opening=loan.get("principle_amount"))
    by_id = {row["statementid"]: calc for row, calc in zip(oldest_first, calculations)}
    branch_info = await _letterhead(repos, loan.get("branch_prefix"))
    return {
        "letterhead": branch_info,
        "loan": serialize.loan(loan, live_quote(loan, dates.business_date(now))),
        "statements": [
            serialize.statement(row, by_id.get(row["statementid"]), loan_start=terms.start_date) for row in statements
        ],
    }


async def closing_quote(repos, actor: Actor, loan_number: str, now: datetime) -> dict:
    actor.require("userlist")
    loan = await _load_visible(repos, actor, loan_number)
    if loan.get("loantype") != "open":
        raise Conflict("This loan is already closed.", code="loan_closed")
    position = position_from_row(loan)
    q = ledger.quote(terms_of(loan), position, max(dates.business_date(now), position.as_of), closing=True)
    return serialize.quote(q)


async def _post(
    repos,
    actor: Actor,
    loan_number: str,
    build: Callable[[Quote], list[Entry]],
    *,
    expected_total: str | None,
    request_id: str | None,
    now: datetime,
    closing: bool = False,
) -> tuple[dict, list[Entry], int | None, list[datetime], bool]:
    """Post entries for one business event. Returns (loan, entries, primary statement id,
    storage timestamps, replayed). Must be called inside a transaction."""
    loan = await repos.loans.lock(loan_number)
    if loan is None:
        raise NotFound(f"Loan {loan_number} was not found.")
    ensure_visible(actor, loan.get("branch_prefix"), f"Loan {loan_number}")
    if request_id:
        prior = await repos.statements.by_request_id(request_id)
        if prior is not None:
            if prior["loan_number"] != loan["loan_number"]:
                raise Conflict("This request id was already used for another loan.", code="request_id_reused")
            return loan, [], prior["statementid"], [], True
    if loan.get("loantype") != "open":
        raise Conflict("This loan is closed.", code="loan_closed")

    latest = await repos.statements.latest(loan["loan_number"])
    position = position_of(loan, latest, await repos.statements.totals(loan["loan_number"]))
    try:
        q = ledger.quote(terms_of(loan), position, dates.business_date(now), closing=closing)
    except ledger.LedgerError as exc:
        raise Invalid(exc.message, code=exc.code) from exc
    if expected_total is not None and _as_money(expected_total) != q.total:
        raise Conflict(
            "The outstanding amount has changed since it was shown. Review the new amount and try again.",
            code="outstanding_changed",
            details={"outstanding": serialize.quote(q)},
        )

    try:
        entries = list(q.compoundings) + build(q)  # may be empty: closing a loan with nothing owed
    except ledger.LedgerError as exc:
        raise Invalid(exc.message, code=exc.code) from exc
    except AmountError as exc:
        raise Invalid(str(exc), code="invalid_amount") from exc
    at_values = stamps_for(entries, latest["date"] if latest else loan["date"], now)
    primary_index = len(q.compoundings)
    primary_id: int | None = None
    receipt_no: int | None = None
    user_entries = entries[primary_index:]
    if any(e.kind in (ledger.COLLECTION, "disbursement", "modify", ledger.WRITE_OFF) for e in user_entries):
        branch = loan.get("branch_prefix")
        if branch:
            for _ in range(25):
                receipt_no = await repos.statements.next_receipt_number(branch)
                if receipt_no is None:
                    await repos.users.ensure_counter(branch)
                    continue
                break
    for index, (entry, at) in enumerate(zip(entries, at_values)):
        statement_id = await repos.statements.insert(
                loan_id=loan["loanid"],
                loan_number=loan["loan_number"],
                kind=entry.kind,
                at=at,
                amount_paid=entry.amount_paid,
                current_principal=entry.current_principal,
                current_interest=entry.current_interest,
                principal_balance=entry.principal_balance,
                interest_balance=entry.interest_balance,
                accrued_days=entry.accrued_days,
                writeoff_principal=entry.writeoff_principal,
                writeoff_interest=entry.writeoff_interest,
                created_by=actor.username,
                request_id=request_id if index == primary_index else None,
                receipt_no=receipt_no if index == primary_index else None,
            )
        if index == primary_index:
            primary_id = statement_id
    if entries:
        final = entries[-1]
        await repos.loans.update_cache(loan["loan_number"], final.principal_balance, final.interest_balance)
    return loan, entries, primary_id, at_values, False


async def _audit(repos, actor: Actor, action: str, loan_number: str, details: str, context: dict | None) -> None:
    context = context or {}
    await repos.audit.log(
        username=actor.username,
        action=action,
        entity_type="LOAN",
        entity_id=loan_number,
        details=details,
        ip=context.get("ip"),
        request_id=context.get("request_id"),
    )


async def collect(
    repos,
    actor: Actor,
    loan_number: str,
    *,
    amount: str,
    expected_total: str | None,
    request_id: str,
    now: datetime,
    context: dict | None = None,
) -> dict:
    actor.require("userlist")
    async with repos.transaction():
        loan, entries, statement_id, _, replayed = await _post(
            repos, actor, loan_number, lambda q: [ledger.collect(q, amount)],
            expected_total=expected_total, request_id=request_id, now=now,
        )
        if not replayed:
            payment = entries[-1]
            await _audit(
                repos, actor, "ADD_COLLECTION", loan["loan_number"],
                f"Received {payment.amount_paid}: interest {payment.current_interest}, "
                f"principal {-payment.current_principal}", context,
            )
    return {"loan_number": loan["loan_number"], "statement_id": statement_id, "replayed": replayed}


async def top_up(
    repos,
    actor: Actor,
    loan_number: str,
    *,
    amount: str,
    expected_total: str | None,
    request_id: str,
    now: datetime,
    context: dict | None = None,
) -> dict:
    actor.require("newcustomer")
    async with repos.transaction():
        loan, entries, statement_id, _, replayed = await _post(
            repos, actor, loan_number, lambda q: [ledger.top_up(q, amount)],
            expected_total=expected_total, request_id=request_id, now=now,
        )
        if not replayed:
            await _audit(repos, actor, "TOP_UP", loan["loan_number"], f"Added principal {entries[-1].current_principal}", context)
    return {"loan_number": loan["loan_number"], "statement_id": statement_id, "replayed": replayed}


async def close(
    repos,
    actor: Actor,
    loan_number: str,
    *,
    amount_received: str,
    write_off_remaining: bool,
    expected_total: str | None,
    request_id: str,
    now: datetime,
    context: dict | None = None,
) -> dict:
    actor.require("userlist")
    async with repos.transaction():
        loan, entries, statement_id, at_values, replayed = await _post(
            repos, actor, loan_number,
            lambda q: ledger.close(q, amount_received, write_off_remaining=write_off_remaining),
            expected_total=expected_total, request_id=request_id, now=now, closing=True,
        )
        if not replayed:
            closed_at = at_values[-1] if at_values else dates.business_datetime(dates.business_date(now), now)
            await repos.loans.mark_closed(loan["loan_number"], closed_at)
            if loan.get("customerid") is not None:
                await repos.customers.refresh_loan_status(loan["customerid"])
            received = sum((e.amount_paid for e in entries if e.kind == ledger.COLLECTION), ZERO)
            written = sum(
                ((e.writeoff_principal or ZERO) + (e.writeoff_interest or ZERO) for e in entries if e.kind == ledger.WRITE_OFF),
                ZERO,
            )
            await _audit(repos, actor, "CLOSE_LOAN", loan["loan_number"], f"Received {received}, written off {written}", context)
    return {"loan_number": loan["loan_number"], "statement_id": statement_id, "replayed": replayed}


async def edit_items(repos, actor: Actor, loan_number: str, raw_items: Sequence[dict], context: dict | None = None) -> dict:
    actor.require("newcustomer")
    try:
        items = particulars.validate(raw_items)
    except particulars.ItemsError as exc:
        raise Invalid(str(exc), code="invalid_items") from exc
    async with repos.transaction():
        loan = await repos.loans.lock(loan_number)
        if loan is None:
            raise NotFound(f"Loan {loan_number} was not found.")
        ensure_visible(actor, loan.get("branch_prefix"), f"Loan {loan_number}")
        if loan.get("loantype") != "open":
            raise Conflict("Items of a closed loan cannot be changed.", code="loan_closed")
        before = serialize.items_of(loan)
        text = particulars.to_display(items)
        await repos.loans.set_items(loan["loan_number"], json.dumps([i.as_dict() for i in items]), text,
                                    particulars.total_quantity(items))
        await _audit(repos, actor, "EDIT_ITEMS", loan["loan_number"],
                     f"Items changed from '{particulars.to_display(particulars.Item(i['name'], i['qty']) for i in before)}' "
                     f"to '{text}'", context)
    return {"loan_number": loan["loan_number"], "items": [i.as_dict() for i in items]}


async def set_follow_up(repos, actor: Actor, loan_number: str, follow_up: date | None, now: datetime) -> dict:
    actor.require("userlist")
    loan = await _load_visible(repos, actor, loan_number)
    if loan.get("loantype") != "open":
        raise Conflict("Follow-ups only apply to open loans.", code="loan_closed")
    if follow_up is not None and follow_up < dates.business_date(now):
        raise Invalid("The follow-up date cannot be in the past.", code="invalid_date")
    await repos.loans.set_follow_up(loan["loan_number"], follow_up)
    return {"loan_number": loan["loan_number"], "follow_up_date": follow_up.isoformat() if follow_up else None}


async def create(repos, actor: Actor, data: NewLoan, *, request_id: str, now: datetime, context: dict | None = None) -> dict:
    actor.require("newcustomer")
    try:
        items = particulars.validate(list(data.items))
        gross, deduction, net = validation.weights(data.gross_weight, data.deduction)
        principal = parse_amount(data.principal, field="Loan amount")
        rate = validation.rate(data.rate)
        tenure = validation.tenure(data.tenure_months)
    except (particulars.ItemsError, validation.ValidationError, AmountError) as exc:
        raise Invalid(str(exc), code="invalid_loan", details={"field": getattr(exc, "field", "items")}) from exc
    as_of = dates.business_date(now)

    async with repos.transaction():
        customer = await repos.customers.lock(data.customer_id)
        if customer is None:
            raise NotFound("Customer was not found.")
        ensure_visible(actor, customer["branch_prefix"], "Customer")
        prior = await repos.statements.by_request_id(request_id)
        if prior is not None:
            earlier = await repos.loans.get(prior["loan_number"])
            if earlier is None or earlier.get("customerid") != customer["customerid"]:
                raise Conflict("This request id was already used for another customer.", code="request_id_reused")
            return {"loan_number": prior["loan_number"], "statement_id": prior["statementid"], "replayed": True}

        for _ in range(25):
            number = await repos.customers.next_loan_number(customer["customerid"])
            loan_number = f"{customer['user_id']}L{number}"
            if not await repos.loans.exists(loan_number):
                break
        else:
            raise Conflict("Could not allocate a loan number. Try again.", code="loan_number_unavailable")

        at = dates.business_datetime(as_of, now)
        row = await repos.loans.insert(
            customer_id=customer["customerid"],
            loan_number=loan_number,
            items_json=json.dumps([i.as_dict() for i in items]),
            particulars=particulars.to_display(items),
            number_of_items=particulars.total_quantity(items),
            weight=gross,
            deduction=deduction,
            net_weight=net,
            principal=principal,
            rate=rate,
            tenure=tenure,
            branch=customer["branch_prefix"],
            loan_date=at,
            created_by=actor.username,
        )
        opening = ledger.opening_entry(LoanTerms.of(as_of, rate), principal)
        statement_id = await repos.statements.insert(
            loan_id=row["loanid"], loan_number=loan_number, kind=opening.kind, at=at,
            amount_paid=ZERO, current_principal=ZERO, current_interest=ZERO,
            principal_balance=opening.principal_balance, interest_balance=ZERO, accrued_days=0,
            writeoff_principal=None, writeoff_interest=None, created_by=actor.username, request_id=request_id,
        )
        await repos.customers.refresh_loan_status(customer["customerid"])
        await _audit(repos, actor, "CREATE_LOAN", loan_number,
                     f"Principal {principal} at {rate}% p.a. for {tenure} months; net weight {net} g", context)
    return {"loan_number": loan_number, "statement_id": statement_id, "replayed": False}


async def apply_due_compounding(repos, loan_number: str, now: datetime) -> int:
    """Post compounding entries that have fallen due (daily cron). Returns entries added."""
    async with repos.transaction():
        loan = await repos.loans.lock(loan_number)
        if loan is None or loan.get("loantype") != "open":
            return 0
        latest = await repos.statements.latest(loan_number)
        position = position_of(loan, latest, await repos.statements.totals(loan_number))
        today = max(dates.business_date(now), position.as_of)
        entries, _ = ledger.due_compoundings(terms_of(loan), position, today)
        if not entries:
            return 0
        for entry, at in zip(entries, stamps_for(entries, latest["date"] if latest else loan["date"], now)):
            await repos.statements.insert(
                loan_id=loan["loanid"], loan_number=loan_number, kind=entry.kind, at=at,
                amount_paid=entry.amount_paid, current_principal=entry.current_principal,
                current_interest=entry.current_interest, principal_balance=entry.principal_balance,
                interest_balance=entry.interest_balance, accrued_days=entry.accrued_days,
                writeoff_principal=None, writeoff_interest=None, created_by="system", request_id=None,
            )
        last = entries[-1]
        await repos.loans.update_cache(loan_number, last.principal_balance, last.interest_balance)
        await repos.audit.log(
            username="system", action="COMPOUNDING", entity_type="LOAN", entity_id=loan_number,
            details=f"{len(entries)} annual compounding(s); principal now {last.principal_balance}",
        )
    return len(entries)


def due_for_compounding(row: dict, today: date) -> bool:
    position = position_from_row(row)
    return ledger.anniversary(terms_of(row), position.compoundings + 1) <= today

