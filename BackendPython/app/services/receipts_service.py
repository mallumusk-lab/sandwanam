"""Data for printed receipts. Everything comes from the server: nothing a receipt shows
can be altered by editing the page address."""
from __future__ import annotations

from datetime import datetime

from ..domain import dates
from ..errors import NotFound
from . import serialize
from .context import Actor, ensure_visible
from .loans_service import CLOSING_PAIR_GAP, live_quote


async def _letterhead(repos, branch_prefix: str | None) -> dict | None:
    if not branch_prefix:
        return None
    row = await repos.users.branch(branch_prefix)
    return serialize.branch(row) if row else None


async def for_loan(repos, actor: Actor, loan_number: str, now: datetime) -> dict:
    actor.require("userlist")
    loan = await repos.loans.get(loan_number)
    if loan is None:
        raise NotFound(f"Loan {loan_number} was not found.")
    ensure_visible(actor, loan.get("branch_prefix"), f"Loan {loan_number}")
    return {
        "letterhead": await _letterhead(repos, loan.get("branch_prefix")),
        "customer": {"name": loan.get("customername"), "phone": loan.get("phone"),
                     "customer_number": loan.get("user_id"), "address": loan.get("address")},
        "loan": serialize.loan(loan, live_quote(loan, dates.business_date(now))),
        "printed_at": serialize.stamp(now),
        "printed_on": dates.business_date(now).isoformat(),
    }


async def for_statement(repos, actor: Actor, statement_id: int, now: datetime) -> dict:
    row = await repos.statements.get(statement_id)
    if row is None:
        raise NotFound("Receipt was not found.")
    receipt = await for_loan(repos, actor, row["loan_number"], now)
    loan_start = dates.parse_business_date(receipt["loan"]["date"]) if receipt["loan"]["date"] else None
    entries = await repos.statements.for_loan(row["loan_number"])  # newest first
    closing_ids: set[int] = set()
    writeoff = None
    if receipt["loan"]["status"] == "closed" and entries:
        last = entries[0]
        closing_ids.add(last["statementid"])
        if last["transactiontype"] == "writeoff":
            writeoff = serialize.statement(last, loan_start=loan_start)
            previous = entries[1] if len(entries) > 1 else None
            if (
                previous is not None
                and previous["transactiontype"] == "addColl"
                # the closing payment is stored 1 µs before the write-off (loans_service.stamps_for)
                and dates.as_aware(last["date"]) - dates.as_aware(previous["date"]) <= CLOSING_PAIR_GAP
            ):
                closing_ids.add(previous["statementid"])
    is_closing = row["statementid"] in closing_ids
    if is_closing and row["transactiontype"] == "writeoff" and len(closing_ids) == 2:
        # the closing receipt is the payment's: it shows the cash received and the write-off
        row = next(e for e in entries if e["statementid"] in closing_ids and e["transactiontype"] == "addColl")
    receipt.update({
        "entry": serialize.statement(row, loan_start=loan_start),
        "is_closing": is_closing,
        "closing_writeoff": writeoff if is_closing else None,
    })
    return receipt
