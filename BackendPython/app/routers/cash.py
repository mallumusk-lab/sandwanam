"""Branch cash ledger. Every write returns the fresh overview of that branch."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Path, Query

from ..auth import ActorDep, ContextDep, ReposDep
from ..domain.dates import now_utc
from ..schemas import CashCloseIn, CashDayIn, CashEntryIn, CashVoidIn
from ..services import cash_service

router = APIRouter()
Branch = Annotated[Optional[str], Query(max_length=10)]
RowId = Annotated[int, Path(ge=1, le=2_147_483_647)]


@router.get("/cash")
async def overview(repos: ReposDep, actor: ActorDep, branch: Branch = None) -> dict:
    return await cash_service.overview(repos, actor, branch, now_utc())


@router.post("/cash/days", status_code=201)
async def start_day(body: CashDayIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await cash_service.start_day(repos, actor, branch=body.branch, opening_counted=body.opening_counted,
                                        request_id=body.request_id, now=now_utc(), context=context)


@router.post("/cash/days/{day_id}/entries", status_code=201)
async def add_entry(day_id: RowId, body: CashEntryIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await cash_service.add_entry(
        repos, actor, day_id, direction=body.direction, category=body.category, description=body.description,
        reference=body.reference, amount=body.amount, request_id=body.request_id, now=now_utc(), context=context,
    )


@router.post("/cash/entries/{entry_id}/void")
async def void_entry(entry_id: RowId, body: CashVoidIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await cash_service.void_entry(repos, actor, entry_id, reason=body.reason, now=now_utc(), context=context)


@router.post("/cash/days/{day_id}/close")
async def close_day(day_id: RowId, body: CashCloseIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await cash_service.close_day(repos, actor, day_id, closing_counted=body.closing_counted,
                                        expected_total=body.expected_total, now=now_utc(), context=context)


@router.post("/cash/days/{day_id}/reopen")
async def reopen_day(day_id: RowId, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await cash_service.reopen_day(repos, actor, day_id, now=now_utc(), context=context)
