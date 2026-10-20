"""Customers, loans, receipts and history imports."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Query

from ..auth import ActorDep, ContextDep, ReposDep
from ..domain.dates import now_utc
from ..schemas import CloseIn, CustomerIn, FollowUpIn, ImportIn, ImportPreviewIn, ItemsIn, LoanIn, PostingIn
from ..services import branches_service, customers_service, import_service, loans_service, receipts_service
from ..services.customers_service import NewCustomer
from ..services.import_service import HistoryEntry, HistoryLoan
from ..services.loans_service import NewLoan

router = APIRouter()


@router.get("/branches")
async def branches(repos: ReposDep, actor: ActorDep) -> list[dict]:
    return await branches_service.directory(repos)


@router.get("/customers")
async def search_customers(
    repos: ReposDep,
    actor: ActorDep,
    q: Annotated[Optional[str], Query(max_length=60)] = None,
    branch: Annotated[Optional[str], Query(max_length=10)] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    return await customers_service.search(repos, actor, branch=branch, term=q, page=page, page_size=page_size)


@router.post("/customers", status_code=201)
async def create_customer(body: CustomerIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await customers_service.create(repos, actor, NewCustomer(body.name, body.phone, body.address, body.branch),
                                          context)


@router.get("/customers/{customer_id}")
async def customer_detail(customer_id: int, repos: ReposDep, actor: ActorDep) -> dict:
    return await customers_service.detail(repos, actor, customer_id, now_utc())


@router.post("/loans", status_code=201)
async def create_loan(body: LoanIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    data = NewLoan(body.customer_id, [i.model_dump() for i in body.items], body.gross_weight, body.deduction,
                   body.principal, body.rate, body.tenure_months, body.loan_date)
    return await loans_service.create(repos, actor, data, request_id=body.request_id, now=now_utc(), context=context)


@router.get("/loans/{loan_number}")
async def loan_detail(loan_number: str, repos: ReposDep, actor: ActorDep) -> dict:
    return await loans_service.detail(repos, actor, loan_number, now_utc())


@router.get("/loans/{loan_number}/closing-quote")
async def closing_quote(loan_number: str, repos: ReposDep, actor: ActorDep) -> dict:
    return await loans_service.closing_quote(repos, actor, loan_number, now_utc())


@router.post("/loans/{loan_number}/collections", status_code=201)
async def collect(loan_number: str, body: PostingIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await loans_service.collect(
        repos, actor, loan_number, amount=body.amount, on=body.date, expected_total=body.expected_total,
        request_id=body.request_id, now=now_utc(), context=context,
    )


@router.post("/loans/{loan_number}/top-ups", status_code=201)
async def top_up(loan_number: str, body: PostingIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await loans_service.top_up(
        repos, actor, loan_number, amount=body.amount, on=body.date, expected_total=body.expected_total,
        request_id=body.request_id, now=now_utc(), context=context,
    )


@router.post("/loans/{loan_number}/close")
async def close(loan_number: str, body: CloseIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await loans_service.close(
        repos, actor, loan_number, amount_received=body.amount_received,
        write_off_remaining=body.write_off_remaining, expected_total=body.expected_total,
        request_id=body.request_id, now=now_utc(), context=context,
    )


@router.put("/loans/{loan_number}/items")
async def edit_items(loan_number: str, body: ItemsIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await loans_service.edit_items(repos, actor, loan_number, [i.model_dump() for i in body.items], context)


@router.put("/loans/{loan_number}/follow-up")
async def follow_up(loan_number: str, body: FollowUpIn, repos: ReposDep, actor: ActorDep) -> dict:
    return await loans_service.set_follow_up(repos, actor, loan_number, body.follow_up_date, now_utc())


@router.get("/receipts/loans/{loan_number}")
async def loan_receipt(loan_number: str, repos: ReposDep, actor: ActorDep) -> dict:
    return await receipts_service.for_loan(repos, actor, loan_number, now_utc())


@router.get("/receipts/statements/{statement_id}")
async def statement_receipt(statement_id: int, repos: ReposDep, actor: ActorDep) -> dict:
    return await receipts_service.for_statement(repos, actor, statement_id, now_utc())


def _history(body: ImportPreviewIn) -> tuple[HistoryLoan, list[HistoryEntry]]:
    loan = HistoryLoan([i.model_dump() for i in body.loan.items], body.loan.gross_weight, body.loan.deduction,
                       body.loan.principal, body.loan.rate, body.loan.tenure_months, body.loan.loan_date)
    return loan, [HistoryEntry(e.date, e.kind, e.amount) for e in body.entries]


@router.post("/imports/preview")
async def preview_import(body: ImportPreviewIn, actor: ActorDep) -> dict:
    loan, entries = _history(body)
    return await import_service.preview(actor, loan, entries, now_utc())


@router.post("/imports", status_code=201)
async def commit_import(body: ImportIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    loan, entries = _history(body)
    new_customer = None
    if body.new_customer is not None:
        c = body.new_customer
        new_customer = NewCustomer(c.name, c.phone, c.address, c.branch)
    return await import_service.commit(
        repos, actor, customer_id=body.customer_id, new_customer=new_customer, loan=loan, entries=entries,
        request_id=body.request_id, now=now_utc(), context=context,
        expected=body.expected.model_dump() if body.expected else None,
    )
