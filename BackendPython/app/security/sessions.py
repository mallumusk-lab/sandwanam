"""Opaque server-side sessions.

The browser holds a random token in an HttpOnly cookie; the database stores only its
SHA-256. The CSRF token is derived from the session token with HMAC, so it needs no
storage, survives page reloads and is useless without the cookie.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SessionPolicy:
    absolute: timedelta = timedelta(hours=8)
    idle: timedelta = timedelta(minutes=60)
    touch_interval: timedelta = timedelta(minutes=5)


DEFAULT_POLICY = SessionPolicy()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def csrf_token(session_token: str) -> str:
    return hmac.new(session_token.encode("utf-8"), b"csrf-v1", hashlib.sha256).hexdigest()


def csrf_matches(session_token: str, provided: str | None) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(csrf_token(session_token), provided)


def expires_at(created: datetime, policy: SessionPolicy = DEFAULT_POLICY) -> datetime:
    return created + policy.absolute


def is_active(expires: datetime, last_seen: datetime, now: datetime, policy: SessionPolicy = DEFAULT_POLICY) -> bool:
    return now < expires and now - last_seen < policy.idle


def should_touch(last_seen: datetime, now: datetime, policy: SessionPolicy = DEFAULT_POLICY) -> bool:
    return now - last_seen >= policy.touch_interval
