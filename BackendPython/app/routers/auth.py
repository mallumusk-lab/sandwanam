from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..auth import ContextDep, ReposDep, SessionDep, session_token
from ..config import settings
from ..domain.dates import now_utc
from ..schemas import ChangePasswordIn, LoginIn
from ..security import sessions
from ..services import auth_service
from ..services.context import Actor

router = APIRouter(prefix="/auth", tags=["auth"])


def user_view(actor: Actor) -> dict:
    return {
        "username": actor.username,
        "display_name": actor.display_name,
        "account_type": actor.account_type,
        "branch": actor.branch_prefix,
        "is_head_office": actor.is_head_office,
        "is_superadmin": actor.is_superadmin,
        "permissions": actor.effective_permissions(),
        "must_change_password": actor.must_change_password,
    }


def _set_cookie(response: Response, token: str, max_age: int) -> None:
    config = settings()
    response.set_cookie(
        config.cookie_name, token, max_age=max_age, path="/", secure=config.cookie_secure,
        httponly=True, samesite="strict",
    )


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, repos: ReposDep, context: ContextDep) -> dict:
    now = now_utc()
    signed = await auth_service.login(
        repos, body.username, body.password, ip=context["ip"],
        user_agent=request.headers.get("user-agent", ""), now=now,
    )
    _set_cookie(response, signed.token, int((signed.expires_at - now).total_seconds()))
    await repos.audit.log(username=signed.actor.username, action="SIGN_IN", entity_type="ACCOUNT",
                          entity_id=signed.actor.username, details="Signed in", ip=context["ip"],
                          request_id=context["request_id"])
    return {"user": user_view(signed.actor), "csrf_token": signed.csrf_token}


@router.get("/me")
async def me(current: SessionDep) -> dict:
    return {"user": user_view(current.actor), "csrf_token": sessions.csrf_token(current.token)}


@router.post("/logout")
async def logout(request: Request, response: Response, repos: ReposDep, current: SessionDep) -> dict:
    await auth_service.logout(repos, session_token(request))
    response.delete_cookie(settings().cookie_name, path="/", secure=settings().cookie_secure, httponly=True,
                           samesite="strict")
    return {"signed_out": True}


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, repos: ReposDep, current: SessionDep) -> dict:
    await auth_service.change_password(repos, current.actor, current.token, body.current_password, body.new_password,
                                       now_utc())
    refreshed = await auth_service.resolve_session(repos, current.token, now_utc())
    return {"user": user_view(refreshed), "csrf_token": sessions.csrf_token(current.token)}
