"""SuperAdmin account management and backups."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from ..auth import ActorDep, ContextDep, ReposDep
from ..domain.dates import now_utc
from ..schemas import ActiveIn, BranchCreateIn, BranchFieldsIn, ResetPasswordIn, RestoreIn
from ..services import backup_service, branches_service
from ..services.branches_service import BranchFields

router = APIRouter()


def _fields(body: BranchFieldsIn) -> BranchFields:
    return BranchFields(
        display_name=body.display_name, legal_name=body.legal_name, address=body.address, phone=body.phone,
        email=body.email, logo=body.logo, clear_logo=body.clear_logo, permissions=body.permissions,
    )


@router.get("/admin/accounts")
async def accounts(repos: ReposDep, actor: ActorDep) -> list[dict]:
    return await branches_service.list_accounts(repos, actor)


@router.post("/admin/branches", status_code=201)
async def create_branch(body: BranchCreateIn, repos: ReposDep, actor: ActorDep) -> dict:
    return await branches_service.create_branch(
        repos, actor, username=body.username, branch_prefix=body.branch_prefix,
        temporary_password=body.temporary_password, fields=_fields(body),
    )


@router.patch("/admin/accounts/{username}")
async def update_account(username: str, body: BranchFieldsIn, repos: ReposDep, actor: ActorDep) -> dict:
    return await branches_service.update_branch(repos, actor, username, _fields(body))


@router.post("/admin/accounts/{username}/reset-password")
async def reset_password(username: str, body: ResetPasswordIn, repos: ReposDep, actor: ActorDep) -> dict:
    await branches_service.reset_password(repos, actor, username, body.temporary_password)
    return {"reset": True}


@router.post("/admin/accounts/{username}/active")
async def set_active(username: str, body: ActiveIn, repos: ReposDep, actor: ActorDep) -> dict:
    await branches_service.set_active(repos, actor, username, body.active)
    return {"active": body.active}


@router.post("/admin/accounts/{username}/unlock")
async def unlock(username: str, repos: ReposDep, actor: ActorDep) -> dict:
    await branches_service.unlock(repos, actor, username)
    return {"unlocked": True}


@router.delete("/admin/accounts/{username}")
async def delete_account(username: str, repos: ReposDep, actor: ActorDep) -> dict:
    await branches_service.delete_branch(repos, actor, username)
    return {"deleted": True}


def _download(filename: str, body: bytes) -> Response:
    return Response(content=body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/backup/snapshots")
async def snapshots(repos: ReposDep, actor: ActorDep) -> list[dict]:
    return await backup_service.list_snapshots(repos, actor)


@router.post("/backup/snapshots", status_code=201)
async def create_snapshot(repos: ReposDep, actor: ActorDep) -> dict:
    return await backup_service.manual_snapshot(repos, actor, now_utc())


@router.get("/backup/snapshots/{snapshot_id}/download")
async def download_snapshot(snapshot_id: int, repos: ReposDep, actor: ActorDep) -> Response:
    filename, body = await backup_service.snapshot_json(repos, actor, snapshot_id)
    return _download(filename, body)


@router.get("/backup/export")
async def export(repos: ReposDep, actor: ActorDep) -> Response:
    now = now_utc()
    body = await backup_service.export_json(repos, actor, now)
    return _download(f"backup_{now.strftime('%Y%m%dT%H%M%SZ')}.json", body)


@router.post("/backup/restore")
async def restore(body: RestoreIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await backup_service.restore(
        repos, actor, document=body.backup, snapshot_id=body.snapshot_id, confirmation=body.confirmation,
        now=now_utc(), context=context,
    )
