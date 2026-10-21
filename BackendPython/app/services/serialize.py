"""JSON views of database rows. Money is always a string with two decimals."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..domain import dates, particulars
from ..domain.ledger import Quote
from ..domain.money import fmt


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
    }


def loan(row: dict, live: Quote | None = None) -> dict:
    items = items_of(row)
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
        "rate": money(row.get("interest")),
        "tenure_months": row.get("tenure"),
        "follow_up_date": row["follow_up_date"].isoformat() if row.get("follow_up_date") else None,
        "outstanding": quote(live),
    }


def statement(row: dict) -> dict:
    kind = row.get("transactiontype")
    legacy_writeoff = kind == "writeoff" and row.get("writeoff_principal") is None
    written_off = None
    if kind == "writeoff":
        written_off = (
            row.get("principlebalance")
            if legacy_writeoff
            else (row.get("writeoff_principal") or Decimal(0)) + (row.get("writeoff_interest") or Decimal(0))
        )
    return {
        "id": row["statementid"],
        "loan_number": row.get("loan_number"),
        "kind": kind,
        "date": day(row.get("date")),
        "at": stamp(row.get("date")),
        "amount_paid": money(row.get("amountpaid")),
        "principal_change": money(row.get("currentprincipal")),
        "interest_paid": money(row.get("currentinterest")),
        "principal_balance": money(row.get("principlebalance")) if not legacy_writeoff else money(Decimal(0)),
        "interest_balance": money(row.get("interestbalance")),
        "accrued_days": row.get("accrued_days"),
        "written_off": money(written_off),
        "legacy": row.get("created_at") is None and "created_at" in row,
        "recorded_by": row.get("created_by"),
    }


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
