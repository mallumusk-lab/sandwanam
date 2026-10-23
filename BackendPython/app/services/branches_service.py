"""Branch and account administration (SuperAdmin) and the public branch directory."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..domain import validation
from ..errors import Conflict, Forbidden, Invalid, NotFound
from ..security import passwords
from . import serialize
from .context import DEFAULT_PERMISSIONS, Actor, parse_permissions

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")
_BRANCH_PHONE = re.compile(r"^[0-9+\-\s]{6,20}$")


@dataclass(frozen=True)
class BranchFields:
    display_name: str | None = None
    legal_name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    logo: str | None = None
    clear_logo: bool = False
    permissions: list[str] | None = None


def _clean(fields: BranchFields) -> dict:
    cleaned: dict = {}
    try:
        if fields.display_name is not None:
            cleaned["display_name"] = validation.person_name(fields.display_name, "display_name")
        if fields.legal_name is not None:
            cleaned["legal_name"] = " ".join(fields.legal_name.split())[:255] or None
        if fields.address is not None:
            cleaned["address"] = " ".join(fields.address.split())[:500] or None
        if fields.phone is not None:
            phone = fields.phone.strip()
            if phone and not _BRANCH_PHONE.match(phone):
                raise validation.ValidationError("phone", "Enter a valid phone number.")
            cleaned["phone"] = phone or None
        if fields.email is not None:
            email = fields.email.strip()
            if email and not _EMAIL.match(email):
                raise validation.ValidationError("email", "Enter a valid email address.")
            cleaned["email"] = email or None
        if fields.clear_logo:
            cleaned["logo"] = None
        elif fields.logo is not None:
            cleaned["logo"] = validation.logo_data_url(fields.logo)
        if fields.permissions is not None:
            chosen = set(parse_permissions(",".join(fields.permissions)))
            if "newcustomer" in chosen:
                chosen.add("userlist")  # adding customers and loans needs the customer pages too
            cleaned["permissions"] = ",".join(sorted(chosen))
    except validation.ValidationError as exc:
        raise Invalid(exc.message, code="invalid_branch", details={"field": exc.field}) from exc
    return cleaned


def _account_view(row: dict) -> dict:
    view = serialize.branch(row, include_logo=True, include_username=True)
    view.update({
        "account_type": row["account_type"],
        "permissions": sorted(parse_permissions(row.get("permissions"))),
        "is_active": bool(row.get("is_active")),
        "must_change_password": bool(row.get("must_change_password")),
        "has_password": bool(row.get("has_password", row.get("password"))),
    })
    return view


async def directory(repos) -> list[dict]:
    """Branch names and letterheads, for selectors and receipts (any signed-in user)."""
    return [serialize.branch(row) for row in await repos.users.branches()]


async def list_accounts(repos, actor: Actor) -> list[dict]:
    actor.require_superadmin()
    return [_account_view(row) for row in await repos.users.list_accounts() if row["account_type"] != "superadmin"]


async def create_branch(repos, actor: Actor, *, username: str, branch_prefix: str, temporary_password: str,
                        fields: BranchFields) -> dict:
    actor.require_superadmin()
    try:
        username = validation.username(username)
        prefix = validation.branch_prefix(branch_prefix)
        validation.password(temporary_password, username)
    except validation.ValidationError as exc:
        raise Invalid(exc.message, code="invalid_branch", details={"field": exc.field}) from exc
    if not fields.display_name:
        raise Invalid("Enter the branch name.", code="invalid_branch", details={"field": "display_name"})
    cleaned = _clean(fields)
    async with repos.transaction():
        if await repos.users.get(username) is not None:
            raise Conflict(f"The username {username} is already taken.", code="username_taken")
        if prefix in await repos.users.branch_prefixes():
            raise Conflict(f"The customer ID prefix {prefix} is already used.", code="prefix_taken")
        await repos.users.create(
            username=username,
            password_hash=passwords.hash_password(temporary_password),
            account_type="branch",
            branch_prefix=prefix,
            display_name=cleaned["display_name"],
            legal_name=cleaned.get("legal_name"),
            address=cleaned.get("address"),
            phone=cleaned.get("phone"),
            email=cleaned.get("email"),
            logo=cleaned.get("logo"),
            permissions=cleaned.get("permissions", DEFAULT_PERMISSIONS),
        )
        await repos.users.ensure_counter(prefix)
        await repos.audit.log(username=actor.username, action="CREATE_BRANCH", entity_type="ACCOUNT",
                              entity_id=username, details=f"Created branch {cleaned['display_name']} ({prefix})")
    return _account_view(await repos.users.get(username))


async def _target(repos, username: str) -> dict:
    row = await repos.users.get(username)
    if row is None or row["account_type"] == "superadmin":
        raise NotFound("Account was not found.")
    return row


async def update_branch(repos, actor: Actor, username: str, fields: BranchFields) -> dict:
    actor.require_superadmin()
    row = await _target(repos, username)
    cleaned = _clean(fields)
    if row["account_type"] == "hq":
        cleaned.pop("permissions", None)  # head office always has every feature
    await repos.users.update_settings(row["username"], cleaned)
    await repos.audit.log(username=actor.username, action="UPDATE_BRANCH", entity_type="ACCOUNT",
                          entity_id=row["username"],
                          details=("Updated: " + ", ".join(sorted(cleaned))) if cleaned else "No changes")
    return _account_view(await repos.users.get(row["username"]))


async def reset_password(repos, actor: Actor, username: str, temporary_password: str) -> None:
    actor.require_superadmin()
    row = await _target(repos, username)
    try:
        validation.password(temporary_password, row["username"])
    except validation.ValidationError as exc:
        raise Invalid(exc.message, code="weak_password", details={"field": "temporary_password"}) from exc
    async with repos.transaction():
        await repos.users.set_password(row["username"], passwords.hash_password(temporary_password), must_change=True)
        await repos.sessions.delete_for_user(row["username"])
        await repos.throttle.clear_user(row["username"])
        await repos.audit.log(username=actor.username, action="RESET_PASSWORD", entity_type="ACCOUNT",
                              entity_id=row["username"], details="Temporary password issued")


async def set_active(repos, actor: Actor, username: str, active: bool) -> None:
    actor.require_superadmin()
    row = await _target(repos, username)
    if row["account_type"] == "hq" and not active:
        raise Forbidden("The head office account cannot be deactivated.")
    async with repos.transaction():
        await repos.users.set_active(row["username"], active)
        if not active:
            await repos.sessions.delete_for_user(row["username"])
        await repos.audit.log(username=actor.username, action="ACTIVATE_BRANCH" if active else "DEACTIVATE_BRANCH",
                              entity_type="ACCOUNT", entity_id=row["username"], details="")


async def unlock(repos, actor: Actor, username: str) -> None:
    actor.require_superadmin()
    row = await _target(repos, username)
    await repos.throttle.clear_user(row["username"])
    await repos.audit.log(username=actor.username, action="UNLOCK_ACCOUNT", entity_type="ACCOUNT",
                          entity_id=row["username"], details="Sign-in throttling cleared")


async def delete_branch(repos, actor: Actor, username: str) -> None:
    actor.require_superadmin()
    row = await _target(repos, username)
    if row["account_type"] == "hq":
        raise Forbidden("The head office account cannot be deleted.")
    if await repos.users.customer_count(row["branch_prefix"]):
        raise Conflict("This branch has customers. Deactivate it instead of deleting it.", code="branch_in_use")
    if await repos.cash.latest_day(row["branch_prefix"]):
        raise Conflict("This branch has cash ledger days. Deactivate it instead of deleting it.",
                       code="branch_in_use")
    async with repos.transaction():
        await repos.users.delete(row["username"])
        await repos.audit.log(username=actor.username, action="DELETE_BRANCH", entity_type="ACCOUNT",
                              entity_id=row["username"], details=f"Deleted branch {row['branch_prefix']}")
