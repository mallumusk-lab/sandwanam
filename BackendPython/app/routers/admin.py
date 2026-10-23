"""SuperAdmin account management, Import backup (check / restore) and the backup email."""
from __future__ import annotations

from fastapi import APIRouter

from ..auth import ActorDep, ContextDep, ReposDep
from ..config import settings
from ..domain.dates import now_utc
from ..infra import aeszip
from ..infra import mailer as backup_mailer
from ..schemas import ActiveIn, BackupEmailIn, BackupSourceIn, BranchCreateIn, BranchFieldsIn, ResetPasswordIn, RestoreIn
from ..services import backup_email_service, backup_service, branches_service
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


def _source(body: BackupSourceIn) -> dict:
    # The emailed ZIP is opened in memory by app.infra (the service never imports infra),
    # after the service has checked who is asking.
    return {"document": body.backup, "packed": body.backup_gzip, "zipped": body.backup_zip,
            "zip_password": body.zip_password, "unzip": aeszip.read_backup_zip}


@router.post("/backup/check")
async def check(body: BackupSourceIn, repos: ReposDep, actor: ActorDep) -> dict:
    return await backup_service.check(repos, actor, **_source(body))


@router.post("/backup/restore")
async def restore(body: RestoreIn, repos: ReposDep, actor: ActorDep, context: ContextDep) -> dict:
    return await backup_service.restore(repos, actor, **_source(body), confirmation=body.confirmation,
                                        now=now_utc(), context=context)


@router.get("/backup/email")
async def backup_email(repos: ReposDep, actor: ActorDep) -> dict:
    _, missing = backup_mailer.from_settings(settings())
    return await backup_email_service.email_settings(repos, actor, missing=missing)


@router.put("/backup/email")
async def set_backup_email(body: BackupEmailIn, repos: ReposDep, actor: ActorDep) -> dict:
    _, missing = backup_mailer.from_settings(settings())
    return await backup_email_service.set_email_settings(repos, actor, recipient=body.recipient, enabled=body.enabled,
                                                         missing=missing)


@router.post("/backup/email/send")
async def email_backup_now(repos: ReposDep, actor: ActorDep) -> dict:
    mailer, missing = backup_mailer.from_settings(settings())
    return await backup_email_service.send_now(repos, actor, mailer, missing=missing, now=now_utc())
