"""Application factory. `app` is the ASGI entry point served by Vercel (via ../main.py)."""
from __future__ import annotations

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import logs
from .config import settings
from .errors import AppError
from .middleware import ApiPrefixMiddleware, OriginGuardMiddleware, PayloadTooLarge, RequestContextMiddleware
from .routers import admin, auth, business, insights, ops


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse({"error": error}, status_code=status)


def _request_id(request: Request) -> str | None:
    return request.scope.get("state", {}).get("request_id")


def create_fastapi() -> FastAPI:
    config = settings()
    api = FastAPI(
        title="Gold Loan Management API",
        version="2.0.0",
        docs_url="/docs" if config.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.docs_enabled else None,
    )
    for module in (auth, business, insights, admin, ops):
        api.include_router(module.router)

    @api.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        response = JSONResponse(exc.body(), status_code=exc.status)
        if exc.status == 429 and "retry_after" in exc.details:
            response.headers["Retry-After"] = str(exc.details["retry_after"])
        return response

    @api.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(p) for p in err.get("loc", [])[1:]) or "body", "message": err.get("msg", "Invalid")}
            for err in exc.errors()
        ]
        return _error(422, "invalid_request", "Some of the information is missing or invalid.", {"fields": fields})

    @api.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        message = "This page or action does not exist." if exc.status_code in (404, 405) else str(exc.detail)
        return _error(exc.status_code, codes.get(exc.status_code, "http_error"), message)

    @api.exception_handler(PayloadTooLarge)
    async def too_large(request: Request, exc: PayloadTooLarge) -> JSONResponse:
        return _error(413, "payload_too_large", "The request is too large.")

    @api.exception_handler(asyncpg.UniqueViolationError)
    async def unique_violation(request: Request, exc: asyncpg.UniqueViolationError) -> JSONResponse:
        logs.warning("unique_violation", constraint=getattr(exc, "constraint_name", None), request_id=_request_id(request))
        return _error(409, "conflict", "This record was changed by someone else at the same time. Please try again.")

    @api.exception_handler(asyncpg.CheckViolationError)
    async def check_violation(request: Request, exc: asyncpg.CheckViolationError) -> JSONResponse:
        logs.warning("check_violation", constraint=getattr(exc, "constraint_name", None), request_id=_request_id(request))
        return _error(409, "invalid_record", "This record has invalid data from the earlier system. Ask head office to correct it.")

    @api.exception_handler(asyncpg.PostgresConnectionError)
    async def database_down(request: Request, exc: Exception) -> JSONResponse:
        logs.error("database_unavailable", request_id=_request_id(request))
        return _error(503, "database_unavailable", "The database is unavailable. Try again shortly.")

    @api.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        logs.error("unhandled_error", request_id=_request_id(request), path=request.url.path, exc_info=True)
        return _error(500, "internal_error",
                      f"Something went wrong. Quote reference {_request_id(request) or 'unknown'} if it keeps happening.")

    return api


def create_app():
    logs.configure()
    config = settings()
    api = create_fastapi()
    return RequestContextMiddleware(OriginGuardMiddleware(ApiPrefixMiddleware(api), config.trusted_origins))


app = create_app()
