"""Dashboard, reports, gold rate and audit log."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Query
from fastapi.responses import Response

from ..auth import ActorDep, ReposDep
from ..domain.dates import now_utc
from ..schemas import GoldRateIn
from ..services import maintenance_service, reports_service

router = APIRouter()
CSV_BOM = "\N{ZERO WIDTH NO-BREAK SPACE}"  # lets spreadsheet apps detect UTF-8 (₹, Malayalam)
Branch = Annotated[Optional[str], Query(max_length=10)]
From = Annotated[Optional[str], Query(alias="from", max_length=10)]
To = Annotated[Optional[str], Query(alias="to", max_length=10)]


@router.get("/dashboard")
async def dashboard(repos: ReposDep, actor: ActorDep, branch: Branch = None) -> dict:
    return await reports_service.dashboard(repos, actor, branch, now_utc())


@router.get("/dashboard/performance")
async def performance(repos: ReposDep, actor: ActorDep, branch: Branch = None,
                      start: From = None,
                      end: To = None) -> dict:
    return await reports_service.performance(repos, actor, branch, start, end, now_utc())


@router.get("/dashboard/details/{metric}")
async def details(metric: str, repos: ReposDep, actor: ActorDep, branch: Branch = None,
                  start: From = None,
                  end: To = None) -> dict:
    return await reports_service.details(repos, actor, metric, branch, start, end, now_utc())


@router.get("/dashboard/portfolio")
async def portfolio(repos: ReposDep, actor: ActorDep, branch: Branch = None) -> dict:
    return await reports_service.portfolio(repos, actor, branch, now_utc())


@router.get("/reports/transactions")
async def transactions(repos: ReposDep, actor: ActorDep, branch: Branch = None,
                       start: From = None,
                       end: To = None,
                       q: Annotated[Optional[str], Query(max_length=60)] = None,
                       kind: Annotated[Optional[str], Query(max_length=20)] = None,
                       page: Annotated[int, Query(ge=1, le=10_000)] = 1,
                       page_size: Annotated[int, Query(ge=1, le=200)] = 50) -> dict:
    return await reports_service.transactions(repos, actor, branch=branch, start=start, end=end, term=q, kind=kind,
                                              page=page, page_size=page_size, now=now_utc())


@router.get("/reports/transactions.csv")
async def transactions_csv(repos: ReposDep, actor: ActorDep, branch: Branch = None,
                           start: From = None,
                           end: To = None,
                           q: Annotated[Optional[str], Query(max_length=60)] = None,
                           kind: Annotated[Optional[str], Query(max_length=20)] = None) -> Response:
    filename, body = await reports_service.transactions_csv(repos, actor, branch=branch, start=start, end=end,
                                                            term=q, kind=kind, now=now_utc())
    return Response(
        content=CSV_BOM + body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/settings/gold-rate")
async def get_gold_rate(repos: ReposDep, actor: ActorDep) -> dict:
    return {"gold_rate": await reports_service.gold_rate(repos)}


@router.put("/settings/gold-rate")
async def put_gold_rate(body: GoldRateIn, repos: ReposDep, actor: ActorDep) -> dict:
    return {"gold_rate": await reports_service.set_gold_rate(repos, actor, body.per_gram)}


@router.get("/audit-logs")
async def audit_logs(repos: ReposDep, actor: ActorDep,
                     q: Annotated[Optional[str], Query(max_length=60)] = None,
                     page: Annotated[int, Query(ge=1, le=10_000)] = 1,
                     page_size: Annotated[int, Query(ge=1, le=100)] = 50) -> dict:
    return await maintenance_service.audit_page(repos, actor, q, page, page_size)
