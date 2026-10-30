"""JSON views of database rows. Money is always a string with two decimals.

Quotes carry the first-7-days state (`first_week`, `window_peak`, `first_week_interest`);
statement rows carry `in_first_week` and, on the loan statement only, `calculation`.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..domain import dates, particulars, reports
from ..domain.interest import CLOSING_MINIMUM_DAYS
from ..domain.ledger import NEW_LOAN, Quote
from ..domain.money import fmt
from ..domain.statement_calc import Calculation


def money(value: Decimal | None) -> str | None:
    return None if value is None else fmt(value)


def stamp(value: datetime | None) -> str | None:
    return None if value is None else dates.as_aware(value).isoformat()


def day(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return dates.business_date(value).isoformat()


def items_of(row: dict) -> list[dict]:
    raw = row.get("items")
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, list) and raw:
        return [{"name": str(i.get("name", "")), "qty": int(i.get("qty", 1))} for i in raw if isinstance(i, dict)]
    return [item.as_dict() for item in particulars.parse_legacy(row.get("particulars"))]


def customer(row: dict) -> dict:
    view = {
        "id": row["customerid"],
        "customer_number": row.get("user_id"),
        "name": row.get("customername"),
        "phone": row.get("phone"),
        "address": row.get("address"),
        "branch": row.get("branch_prefix"),
        "has_open_loan": row.get("loanstatus") == "1",
    }
    if "open_loans" in row:
        view["open_loans"] = int(row["open_loans"] or 0)
    return view


def quote(q: Quote | None) -> dict | None:
    if q is None:
        return None
    return {
        "as_of": q.as_of.isoformat(),
        "principal": money(q.principal),
        "interest": money(q.interest),
        "total": money(q.total),
        "period_days": q.period_days,
        "compoundings_due": len(q.compoundings),
        "first_week": q.first_week,
        "window_peak": money(q.window_peak),
        "first_week_interest": money(q.first_week_interest),
    }


def follow_up(row: dict) -> tuple[str | None, bool]:
    """(effective follow-up date, whether staff set it). Open loans without a stored date
    default to the loan date + 364 days; closed loans have none."""
    stored = row.get("follow_up_date")
    start = dates.business_date(row["date"]) if row.get("date") else None
    effective = reports.effective_follow_up(stored, start, (row.get("loantype") or "open") == "open")
    return (effective.isoformat() if effective else None), stored is not None and effective is not None


def loan(row: dict, live: Quote | None = None) -> dict:
    items = items_of(row)
    follow_up_date, follow_up_set = follow_up(row)
    principal_balance = (
        money(live.principal)
        if live is not None
        else (money(row.get("last_principal")) if row.get("last_principal") is not None else ("0.00" if row.get("loantype") == "closed" else money(row.get("principle_amount"))))
    )
    interest_balance = (
        money(live.interest)
        if live is not None
        else (money(row.get("last_interest")) if row.get("last_interest") is not None else "0.00")
    )
    return {
        "loan_number": row["loan_number"],
        "customer_id": row.get("customerid"),
        "customer_number": row.get("user_id"),
        "customer_name": row.get("customername"),
        "branch": row.get("branch_prefix"),
        "status": row.get("loantype") or "open",
        "date": day(row.get("date")),
        "created_at": stamp(row.get("date")),
        "closed_on": day(row.get("closed_at")),
        "items": items,
        "items_text": particulars.to_display(particulars.Item(i["name"], i["qty"]) for i in items),
        "item_count": sum(i["qty"] for i in items),
        "gross_weight": money(row.get("weight")),
        "deduction": money(row.get("deduction")),
        "net_weight": money(row.get("net_weight")),
        "principal": money(row.get("principle_amount")),
        "principal_balance": principal_balance,
        "interest_balance": interest_balance,
        "rate": money(row.get("interest")),
        "tenure_months": row.get("tenure"),
        "follow_up_date": follow_up_date,
        "follow_up_set": follow_up_set,
        "outstanding": quote(live),
    }


def in_first_week(row: dict, loan_start: date | None) -> bool:
    """A new-system entry (not the opening) dated in days 1-7 of the loan that charged nothing
    (the first-7-days rule stores accrued_days 0 and no interest). Rows posted in days 1-7 under
    the earlier rule charged interest, so they are not flagged."""
    if loan_start is None or row.get("created_at") is None or row.get("transactiontype") == NEW_LOAN:
        return False
    if row.get("accrued_days") != 0 or Decimal(row.get("currentinterest") or 0) != 0:
        return False
    on = dates.business_date(row["date"])
    return loan_start <= on and (on - loan_start).days < CLOSING_MINIMUM_DAYS


def calculation(c: Calculation) -> dict:
    return {
        "method": c.method,
        "period_from": c.period_from.isoformat() if c.period_from else None,
        "period_to": c.period_to.isoformat() if c.period_to else None,
        "days": c.days,
        "principal_charged": money(c.principal_charged),
        "rate": money(c.rate),
        "interest_accrued": money(c.interest_accrued),
        "peak_principal": money(c.peak_principal),
        "first_week_days": c.first_week_days,
        "extra_days": c.extra_days,
        "extra_principal": money(c.extra_principal),
        "interest_paid": fmt(c.interest_paid),
        "principal_paid": fmt(c.principal_paid),
        "principal_balance": fmt(c.principal_balance),
        "interest_balance": fmt(c.interest_balance),
        "note": c.note,
    }


def statement(row: dict, calc: Calculation | None = None, *, loan_start: date | None = None) -> dict:
    """`loan_start` defaults to the row's `loan_date` column when the query joins it."""
    kind = row.get("transactiontype")
    legacy_writeoff = kind == "writeoff" and row.get("writeoff_principal") is None
    written_off = None
    if kind == "writeoff":
        written_off = (
            row.get("principlebalance")
            if legacy_writeoff
            else (row.get("writeoff_principal") or Decimal(0)) + (row.get("writeoff_interest") or Decimal(0))
        )
    principal_paid = None
    if kind == "addColl":
        if calc is not None and getattr(calc, "principal_paid", None) is not None:
            principal_paid = fmt(calc.principal_paid)
        else:
            pc = row.get("currentprincipal")
            if pc is not None:
                pc_dec = Decimal(str(pc))
                principal_paid = fmt(-pc_dec) if pc_dec < 0 else fmt(Decimal(0))
            else:
                principal_paid = fmt(Decimal(0))
    view = {
        "id": row["statementid"],
        "receipt_no": row.get("receipt_no"),
        "loan_number": row.get("loan_number"),
        "kind": kind,
        "date": day(row.get("date")),
        "at": stamp(row.get("date")),
        "amount_paid": money(row.get("amountpaid")),
        "principal_change": money(row.get("currentprincipal")),
        "interest_paid": money(row.get("currentinterest")),
        "principal_paid": principal_paid,
        "principal_balance": money(row.get("principlebalance")) if not legacy_writeoff else money(Decimal(0)),
        "interest_balance": money(row.get("interestbalance")),
        "accrued_days": row.get("accrued_days"),
        "written_off": money(written_off),
        "legacy": row.get("created_at") is None and "created_at" in row,
        "recorded_by": row.get("created_by"),
        "in_first_week": in_first_week(row, loan_start or _start_of(row)),
    }
    if calc is not None:
        view["calculation"] = calculation(calc)
    return view


def _start_of(row: dict) -> date | None:
    return dates.business_date(row["loan_date"]) if row.get("loan_date") else None


def branch(row: dict, *, include_logo: bool = True, include_username: bool = False) -> dict:
    view: dict[str, Any] = {
        "code": row.get("branch_prefix"),
        "name": row.get("display_name") or row.get("username"),
        "legal_name": row.get("legal_name") or row.get("display_name") or row.get("username"),
        "address": row.get("address"),
        "phone": row.get("phone"),
        "email": row.get("email"),
        "is_head_office": row.get("account_type") == "hq",
    }
    if include_logo:
        view["logo"] = row.get("logo")
    if include_username:
        view["username"] = row.get("username")
    return view
