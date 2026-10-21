"""Pure ASGI middleware (no framework imports, so it is unit-tested directly)."""
from __future__ import annotations

import json
import time
import uuid
from typing import Awaitable, Callable, Iterable
from urllib.parse import urlsplit

from . import logs

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MAX_BODY_BYTES = 5 * 1024 * 1024
SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
)


class PayloadTooLarge(Exception):
    """Raised while reading a streamed body that exceeds the limit."""


def _headers(scope: Scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


async def _json(send: Send, status: int, code: str, message: str, extra_headers: Iterable[tuple[bytes, bytes]] = ()) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                    *SECURITY_HEADERS, *extra_headers],
    })
    await send({"type": "http.response.body", "body": body})


class ApiPrefixMiddleware:
    """Vercel forwards the original /api/... path; the app's routes are mounted at /."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path == "/api" or path.startswith("/api/"):
                scope = dict(scope, path=path[4:] or "/", raw_path=(path[4:] or "/").encode("latin-1"))
        await self.app(scope, receive, send)


class RequestContextMiddleware:
    """Request id, security headers, no-store caching, body limit and an access log line."""

    def __init__(self, app: ASGIApp, max_body: int = MAX_BODY_BYTES):
        self.app = app
        self.max_body = max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        incoming = headers.get("x-request-id", "")
        request_id = incoming if incoming.replace("-", "").isalnum() and len(incoming) <= 64 else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        rid = request_id.encode("ascii")
        started = time.perf_counter()
        status_holder = {"status": 500}

        length = headers.get("content-length")
        if length and length.isdigit() and int(length) > self.max_body:
            await _json(send, 413, "payload_too_large", "The request is too large.", [(b"x-request-id", rid)])
            return

        received = 0

        async def limited_receive() -> dict:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise PayloadTooLarge()
            return message

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(b"x-request-id", rid)] + [h for h in SECURITY_HEADERS if h[0] not in existing]
                if b"cache-control" not in existing:
                    extra.append((b"cache-control", b"no-store"))
                message = dict(message, headers=list(message.get("headers", [])) + extra)
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        finally:
            logs.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_holder["status"],
                ms=round((time.perf_counter() - started) * 1000, 1),
                request_id=request_id,
            )


class OriginGuardMiddleware:
    """Reject state-changing browser requests from other sites (defence in depth on top
    of SameSite=Strict cookies and CSRF tokens)."""

    def __init__(self, app: ASGIApp, trusted_origins: Iterable[str] = ()):
        self.app = app
        self.trusted = {o.rstrip("/").lower() for o in trusted_origins}

    def _allowed(self, headers: dict[str, str]) -> bool:
        origin = headers.get("origin")
        if not origin:
            return True  # non-browser clients; cookies + CSRF still apply
        if origin.rstrip("/").lower() in self.trusted:
            return True
        host = (headers.get("x-forwarded-host") or headers.get("host") or "").split(",")[0].strip().lower()
        return bool(host) and urlsplit(origin).netloc.lower() == host

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method") in UNSAFE_METHODS and not self._allowed(_headers(scope)):
            await _json(send, 403, "cross_origin", "Cross-site requests are not allowed.")
            return
        await self.app(scope, receive, send)
