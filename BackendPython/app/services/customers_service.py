from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..domain import dates, validation
from ..errors import Conflict, Invalid, NotFound
from . import serialize
from .context import Actor, ensure_visible, resolve_scope
from .loans_service import live_quote

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class NewCustomer:
    name: str
    phone: str
    address: str
    branch: str | None = None


def _paging(page: int, page_size: int) -> tuple[int, int, int]:
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    current = max(1, page)
    return current, size, (current - 1) * size


async def search(repos, actor: Actor, *, branch: str | None, term: str | None, page: int, page_size: int) -> dict:
    actor.require("userlist")
    scope = resolve_scope(actor, branch, await repos.users.branch_prefixes())
    current, size, offset = _paging(page, page_size)
    cleaned = " ".join((term or "").split())[:60] or None
    rows, total = await repos.customers.search(scope.branch, cleaned, size, offset)
    return {"items": [serialize.customer(r) for r in rows], "total": total, "page": current, "page_size": size}


async def detail(repos, actor: Actor, customer_id: int, now: datetime) -> dict:
    actor.require("userlist")
    row = await repos.customers.get(customer_id)
    if row is None:
        raise NotFound("Customer was not found.")
    ensure_visible(actor, row["branch_prefix"], "Customer")
    today = dates.business_date(now)
    loans = await repos.loans.for_customer(customer_id)
    return {
        "customer": serialize.customer(row),
        "loans": [serialize.loan(loan, live_quote(loan, today)) for loan in loans],
    }


async def create(repos, actor: Actor, data: NewCustomer, context: dict | None = None) -> dict:
    actor.require("newcustomer")
    try:
        name = validation.person_name(data.name)
        phone = validation.phone(data.phone)
        address = validation.address(data.address)
    except validation.ValidationError as exc:
        raise Invalid(exc.message, code="invalid_customer", details={"field": exc.field}) from exc

    known = await repos.users.branch_prefixes()
    branch = actor.branch_prefix if not actor.is_head_office else (data.branch or "").strip().upper() or actor.branch_prefix
    if branch not in known:
        raise Invalid("Choose the branch this customer belongs to.", code="invalid_customer", details={"field": "branch"})

    context = context or {}
    async with repos.transaction():
        existing = await repos.customers.by_phone(phone)
        if existing is not None:
            visible = actor.is_head_office or existing["branch_prefix"] == actor.branch_prefix
            raise Conflict(
                "A customer with this phone number already exists." if visible
                else "This phone number is already registered at another branch.",
                code="duplicate_phone",
                details={"customer_id": existing["customerid"]} if visible else {},
            )
        for _ in range(25):
            number = await repos.customers.next_customer_number(branch)
            if number is None:
                await repos.users.ensure_counter(branch)
                continue
            user_id = f"{branch}{number}"
            if not await repos.customers.user_id_taken(user_id):
                break
        else:
            raise Conflict("Could not allocate a customer number. Try again.", code="customer_number_unavailable")
        row = await repos.customers.insert(name=name, phone=phone, address=address, user_id=user_id, branch=branch)
        await repos.audit.log(
            username=actor.username, action="CREATE_CUSTOMER", entity_type="CUSTOMER", entity_id=user_id,
            details=f"Created customer {user_id} at branch {branch}", ip=context.get("ip"),
            request_id=context.get("request_id"),
        )
    return serialize.customer(row)
