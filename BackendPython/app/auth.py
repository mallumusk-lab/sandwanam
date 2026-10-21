"""FastAPI dependencies for authentication, CSRF and per-request context."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from . import db
from .config import settings
from .domain.dates import now_utc
from .errors import Forbidden
from .middleware import UNSAFE_METHODS
from .repositories import Repos
from .security import sessions, throttle
from .services import auth_service
from .services.context import Actor

ReposDep = Annotated[Repos, Depends(db.repos)]


@dataclass(frozen=True)
class Session:
    actor: Actor
    token: str


def session_token(request: Request) -> str | None:
    return request.cookies.get(settings().cookie_name)


async def require_session(request: Request, repos: ReposDep) -> Session:
    """A valid session; state-changing requests must also carry the CSRF token."""
    token = session_token(request)
    actor = await auth_service.resolve_session(repos, token, now_utc())
    if request.method in UNSAFE_METHODS and not sessions.csrf_matches(token, request.headers.get("x-csrf-token")):
        raise Forbidden("Your session security token is missing or out of date. Reload the page.", code="csrf_failed")
    return Session(actor, token)


SessionDep = Annotated[Session, Depends(require_session)]


async def require_actor(current: SessionDep) -> Actor:
    """A signed-in user who has completed any required password change."""
    if current.actor.must_change_password:
        raise Forbidden("Change your temporary password to continue.", code="password_change_required")
    return current.actor


ActorDep = Annotated[Actor, Depends(require_actor)]


def request_context(request: Request) -> dict:
    headers = {k.lower(): v for k, v in request.headers.items()}
    return {
        "ip": throttle.client_ip(headers, request.client.host if request.client else None, settings().trust_proxy_headers),
        "request_id": request.scope.get("state", {}).get("request_id"),
    }


ContextDep = Annotated[dict, Depends(request_context)]
