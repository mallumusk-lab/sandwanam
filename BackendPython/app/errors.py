"""Application errors. Every error response has the same shape:

    {"error": {"code": "not_found", "message": "Loan SAN1L9 was not found.", "details": {...}}}
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}

    def body(self) -> dict:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"error": error}


class Unauthorized(AppError):
    status = 401
    code = "unauthorized"


class Forbidden(AppError):
    status = 403
    code = "forbidden"


class NotFound(AppError):
    status = 404
    code = "not_found"


class Conflict(AppError):
    status = 409
    code = "conflict"


class Invalid(AppError):
    status = 422
    code = "invalid"


class TooManyRequests(AppError):
    status = 429
    code = "too_many_requests"


class ServiceUnavailable(AppError):
    status = 503
    code = "unavailable"
