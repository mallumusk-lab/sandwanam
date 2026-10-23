"""Who is acting, and which branches they may see.

Account types:
- superadmin  manages branches, backups and restores; sees every branch and works with
              customers and loans there (SUPERADMIN_FEATURES), but has no analytics,
              reports, history import, cash ledger, gold rate or audit log
- hq          head office; sees every branch, may pick one and has every feature
- branch      sees only its own branch; feature access follows `permissions`
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import Forbidden, NotFound

PERMISSIONS = ("newcustomer", "userlist", "form1", "analytics", "report", "history", "cashbook")
# History import enters past-dated loans, so new branches get it only when a SuperAdmin grants it.
# Keep in step with the role.permissions column default (migrations/005_cash_ledger.sql).
DEFAULT_PERMISSIONS = ",".join(p for p in PERMISSIONS if p != "history")
# A SuperAdmin views and edits customers and loans of any branch, nothing else of the branch
# features (no cash ledger either).
SUPERADMIN_FEATURES = ("newcustomer", "userlist")


def parse_permissions(raw: str | None) -> frozenset[str]:
    return frozenset(p.strip() for p in (raw or "").split(",") if p.strip() in PERMISSIONS)


@dataclass(frozen=True)
class Actor:
    username: str
    account_type: str
    branch_prefix: str | None
    display_name: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    must_change_password: bool = False

    @property
    def is_superadmin(self) -> bool:
        return self.account_type == "superadmin"

    @property
    def is_head_office(self) -> bool:
        """Head office and SuperAdmin see all branches."""
        return self.account_type in ("hq", "superadmin")

    def can(self, permission: str) -> bool:
        if self.is_superadmin:
            return permission in SUPERADMIN_FEATURES
        return self.account_type == "hq" or permission in self.permissions

    def effective_permissions(self) -> list[str]:
        return [p for p in PERMISSIONS if self.can(p)]

    def require(self, permission: str) -> None:
        if not self.can(permission):
            if self.is_superadmin:
                raise Forbidden("A SuperAdmin account cannot use this feature.")
            raise Forbidden("Your branch does not have access to this feature.")

    def require_head_office(self) -> None:
        """Head office staff only (gold rate, audit log). Backups use `is_head_office`."""
        if self.account_type != "hq":
            raise Forbidden("Only head office can do this.")

    def require_superadmin(self) -> None:
        if not self.is_superadmin:
            raise Forbidden("Only a SuperAdmin can do this.")


@dataclass(frozen=True)
class Scope:
    """Branch filter for queries: None means every branch."""

    branch: str | None

    def allows(self, branch_prefix: str | None) -> bool:
        return self.branch is None or self.branch == branch_prefix


def resolve_scope(actor: Actor, requested: str | None, known_branches: set[str]) -> Scope:
    wanted = (requested or "").strip().upper() or None
    if wanted == "ALL":
        wanted = None
    if not actor.is_head_office:
        if wanted and wanted != actor.branch_prefix:
            raise Forbidden("You can only see your own branch.")
        return Scope(actor.branch_prefix)
    if wanted and wanted not in known_branches:
        raise NotFound(f"Branch {wanted} does not exist.")
    return Scope(wanted)


def ensure_visible(actor: Actor, branch_prefix: str | None, what: str) -> None:
    """Hide other branches' records entirely (404, not 403, so IDs can't be probed)."""
    if not actor.is_head_office and branch_prefix != actor.branch_prefix:
        raise NotFound(f"{what} was not found.")
