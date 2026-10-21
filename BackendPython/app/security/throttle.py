"""Sign-in throttling.

Two counters are kept for every username:
- per client address: a few free attempts, then exponential delays (stops guessing from one place);
- per account across all addresses: a higher threshold and shorter cap (stops guessing spread over
  many addresses without letting a stranger lock staff out for long).

An attempt is *claimed* (counted, under a row lock) before the password is checked, so parallel
requests cannot all slip past the limit. A successful sign-in clears the counters.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta

ACCOUNT_KEY = "*"
PASSWORD_CHANGE_KEY = "password-change"
TRUSTED_PREFIX = "trusted:"
TRUST_PERIOD = timedelta(days=30)
MAX_COUNTED_FAILURES = 10_000


@dataclass(frozen=True)
class Limits:
    free_attempts: int
    base_delay: timedelta
    max_delay: timedelta
    window: timedelta = timedelta(hours=1)


PER_ADDRESS = Limits(3, timedelta(seconds=30), timedelta(minutes=15))
PER_ACCOUNT = Limits(20, timedelta(seconds=30), timedelta(minutes=5))

# Kept for callers that only need the per-address defaults.
FREE_ATTEMPTS = PER_ADDRESS.free_attempts
WINDOW = PER_ADDRESS.window


def lock_duration(failures: int, limits: Limits = PER_ADDRESS) -> timedelta:
    if failures < limits.free_attempts:
        return timedelta(0)
    steps = min(failures - limits.free_attempts, 30)  # bounded: no overflow however long an attack runs
    return min(limits.base_delay * (1 << steps), limits.max_delay)


def is_locked(locked_until: datetime | None, now: datetime) -> bool:
    return locked_until is not None and now < locked_until


def failures_after_window(failures: int, updated_at: datetime | None, now: datetime,
                          window: timedelta = WINDOW) -> int:
    """Old failures expire so a forgotten password doesn't punish someone forever."""
    if updated_at is None or now - updated_at > window:
        return 0
    return failures


@dataclass(frozen=True)
class Claim:
    allowed: bool
    failures: int
    locked_until: datetime | None

    def retry_after(self, now: datetime) -> int:
        if self.locked_until is None:
            return 1
        return max(1, int((self.locked_until - now).total_seconds()) + 1)


def claim(record: dict | None, now: datetime, limits: Limits = PER_ADDRESS) -> Claim:
    """Decide whether an attempt may proceed, and what to store if it does."""
    if record is None:
        failures, locked_until = 0, None
    else:
        failures = failures_after_window(record["failures"], record["updated_at"], now, limits.window)
        locked_until = record["locked_until"]
    if is_locked(locked_until, now):
        return Claim(False, failures, locked_until)
    failures = min(failures + 1, MAX_COUNTED_FAILURES)
    delay = lock_duration(failures, limits)
    return Claim(True, failures, now + delay if delay else None)


def trusted_key(address: str) -> str:
    """Marks an address that has signed in to the account before."""
    return f"{TRUSTED_PREFIX}{address}"[:64]


def is_trusted(record: dict | None, now: datetime) -> bool:
    """Recent successful sign-ins from an address exempt it from the account-wide limit, so a
    stranger guessing from elsewhere cannot keep staff locked out of their usual device."""
    return record is not None and record.get("updated_at") is not None and now - record["updated_at"] <= TRUST_PERIOD


def address_key(ip: str) -> str:
    """IPv6 clients are grouped by /64, since one household or phone gets a whole /64."""
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return ip[:64] or "unknown"
    if isinstance(parsed, ipaddress.IPv6Address):
        if parsed.ipv4_mapped is not None:
            return str(parsed.ipv4_mapped)
        return str(ipaddress.IPv6Network(f"{parsed}/64", strict=False))
    return str(parsed)


def client_ip(headers: dict[str, str], fallback: str | None, trust_proxy_headers: bool = True) -> str:
    """Vercel sets x-real-ip / x-forwarded-for itself; elsewhere they could be forged."""
    if trust_proxy_headers:
        real = headers.get("x-real-ip")
        if real:
            return real.strip()[:64]
        forwarded = headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return (fallback or "unknown")[:64]
