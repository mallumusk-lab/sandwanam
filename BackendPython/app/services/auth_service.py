"""Sign-in, sessions and password changes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .. import logs
from ..domain import validation
from ..errors import Invalid, TooManyRequests, Unauthorized
from ..security import passwords, sessions, throttle
from .context import Actor, parse_permissions

GENERIC_FAILURE = "The username or password is incorrect."


@dataclass(frozen=True)
class SignedIn:
    token: str
    csrf_token: str
    actor: Actor
    expires_at: datetime


def actor_from(row: dict) -> Actor:
    return Actor(
        username=row["username"],
        account_type=row["account_type"],
        branch_prefix=row.get("branch_prefix"),
        display_name=row.get("display_name") or row["username"],
        permissions=parse_permissions(row.get("permissions")),
        must_change_password=bool(row.get("must_change_password")),
    )


def can_sign_in(row: dict | None) -> bool:
    if row is None or not row.get("is_active") or not row.get("password"):
        return False
    if row.get("account_type") != "superadmin" and not row.get("branch_prefix"):
        return False  # a branch must have a customer ID prefix before it can operate
    return True


async def _claim(repos, username: str, keys: list[tuple[str, throttle.Limits]], now: datetime,
                 ip: str | None = None, starts_lock: list | None = None) -> tuple[str, throttle.Claim] | None:
    """Count this attempt against every key (under row locks). Returns (key, claim) if refused.
    Keys whose lock period this attempt would start are added to `starts_lock`."""
    async with repos.transaction():
        for key, limits in keys:
            record = await repos.throttle.lock_row(username, key, now)
            claim = throttle.claim(record, now, limits)
            if not claim.allowed:
                logs.warning("sign_in_throttled", username=username[:64], key=key, ip=ip)
                return key, claim
            await repos.throttle.save(username, key, claim.failures, claim.locked_until, now)
            if starts_lock is not None and claim.failures == limits.free_attempts:
                starts_lock.append(key)
    return None


def _too_many(blocked: tuple[str, throttle.Claim], now: datetime) -> TooManyRequests:
    key, claim = blocked
    if key == throttle.ACCOUNT_KEY:
        # No exact wait for the account-wide limit: it would tell an attacker when to strike next.
        return TooManyRequests(
            "Too many failed attempts for this account. Try again later, or sign in from a device you have used before.",
            code="account_throttled",
        )
    wait = claim.retry_after(now)
    return TooManyRequests(f"Too many attempts. Try again in {wait} seconds.", code="login_throttled",
                           details={"retry_after": wait})


def _verify(password: str, stored: str | None) -> bool:
    """Verify, spending the same time whatever the stored hash format (no timing hints)."""
    if not stored:
        passwords.burn_verification_time(password)
        return False
    valid = passwords.verify_password(password, stored)
    if passwords.needs_rehash(stored):
        passwords.burn_verification_time(password)
    return valid


async def login(repos, username: str, password: str, *, ip: str, user_agent: str, now: datetime) -> SignedIn:
    username = (username or "").strip()
    if not username or not password:
        raise Invalid("Enter your username and password.", code="missing_credentials")

    address = throttle.address_key(ip)
    trusted = throttle.is_trusted(await repos.throttle.get(username, throttle.trusted_key(address)), now)
    keys = [(address, throttle.PER_ADDRESS)]
    if not trusted:
        keys.append((throttle.ACCOUNT_KEY, throttle.PER_ACCOUNT))
    starts_lock: list[str] = []
    blocked = await _claim(repos, username, keys, now, ip=address, starts_lock=starts_lock)
    if blocked is not None:
        passwords.burn_verification_time(password)
        raise _too_many(blocked, now)

    row = await repos.users.get(username)
    allowed = can_sign_in(row)
    valid = _verify(password, row["password"] if allowed else None)
    if not (allowed and valid):
        logs.warning("sign_in_failed", username=username[:64], ip=address)
        if starts_lock:  # this failure starts a lock period: audit once, not per attempt
            await repos.audit.log(username=username[:64], action="SIGN_IN_LOCKED", entity_type="ACCOUNT",
                                  entity_id=username[:64], details=f"Repeated failures ({', '.join(starts_lock)})",
                                  ip=address)
        raise Unauthorized(GENERIC_FAILURE, code="invalid_credentials")

    if passwords.needs_rehash(row["password"]):
        await repos.users.upgrade_hash(row["username"], passwords.hash_password(password))
    await repos.throttle.clear(username, address)
    await repos.throttle.clear(username, throttle.ACCOUNT_KEY)
    await repos.throttle.save(username, throttle.trusted_key(address), 0, None, now)

    policy = sessions.DEFAULT_POLICY
    await repos.sessions.purge_expired(now, now - policy.idle)
    token = sessions.new_token()
    expires = sessions.expires_at(now, policy)
    await repos.sessions.create(sessions.token_hash(token), row["username"], now, expires, ip, user_agent or "")
    return SignedIn(token, sessions.csrf_token(token), actor_from(row), expires)


async def resolve_session(repos, token: str | None, now: datetime) -> Actor:
    if not token:
        raise Unauthorized("Please sign in.", code="not_signed_in")
    digest = sessions.token_hash(token)
    row = await repos.sessions.get(digest)
    if row is None or not sessions.is_active(row["expires_at"], row["last_seen_at"], now) or not can_sign_in(row):
        if row is not None:
            await repos.sessions.delete(digest)
        raise Unauthorized("Your session has ended. Please sign in again.", code="session_expired")
    if sessions.should_touch(row["last_seen_at"], now):
        await repos.sessions.touch(digest, now)
    return actor_from(row)


async def logout(repos, token: str | None) -> None:
    if token:
        await repos.sessions.delete(sessions.token_hash(token))


async def change_password(repos, actor: Actor, token: str, current: str, new: str, now: datetime) -> None:
    blocked = await _claim(repos, actor.username, [(throttle.PASSWORD_CHANGE_KEY, throttle.PER_ADDRESS)], now)
    if blocked is not None:
        raise _too_many(blocked, now)
    row = await repos.users.get(actor.username)
    if row is None or not _verify(current or "", row.get("password")):
        raise Invalid("Your current password is incorrect.", code="wrong_password", details={"field": "current_password"})
    if current == new:
        raise Invalid("Choose a password different from the current one.", code="password_reused",
                      details={"field": "new_password"})
    try:
        validation.password(new, actor.username)
    except validation.ValidationError as exc:
        raise Invalid(exc.message, code="weak_password", details={"field": "new_password"}) from exc
    async with repos.transaction():
        await repos.users.set_password(actor.username, passwords.hash_password(new), must_change=False)
        await repos.sessions.delete_for_user(actor.username, keep=sessions.token_hash(token))
        await repos.throttle.clear(actor.username, throttle.PASSWORD_CHANGE_KEY)
        await repos.audit.log(username=actor.username, action="CHANGE_PASSWORD", entity_type="ACCOUNT",
                              entity_id=actor.username, details="Password changed")
