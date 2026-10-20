"""Health checks and the daily cron endpoint."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import db
from ..config import settings
from ..domain.dates import now_utc
from ..errors import Unauthorized
from ..repositories import Repos
from ..services import maintenance_service

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> JSONResponse:
    try:
        pool = await db.pool()
        async with pool.acquire(timeout=5) as connection:
            await connection.fetchval("SELECT 1")
    except Exception:  # report not-ready without leaking connection details
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ready"})


@router.get("/cron/daily")
async def daily(request: Request) -> dict:
    secret = settings().cron_secret
    provided = request.headers.get("authorization", "")
    if not secret or not secrets.compare_digest(provided.encode(), f"Bearer {secret}".encode()):
        raise Unauthorized("Invalid cron credentials.", code="cron_unauthorized")
    pool = await db.pool()
    async with pool.acquire(timeout=10) as connection:
        return await maintenance_service.run_daily(Repos(connection), now_utc())
