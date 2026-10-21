"""Password hashing.

Current format:  pbkdf2_sha256$<iterations>$<salt b64>$<hash b64>  (OWASP 2023: 600k)
Legacy formats are verified so existing users can sign in once and be upgraded:
  pbkdf2:<hex salt>:<hex hash>   (260,000 iterations)
  sha256:<hex>                   (single SHA-256 with a static salt)
Plaintext values are never accepted.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from functools import lru_cache

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
_LEGACY_PBKDF2_ITERATIONS = 260_000
_LEGACY_STATIC_SALT = "salthere"
KNOWN_DEFAULT_PASSWORDS = ("1234", "super1234")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not isinstance(password, str):
        return False
    candidate = password.encode("utf-8")
    try:
        if stored.startswith(ALGORITHM + "$"):
            _, iterations, salt, digest = stored.split("$")
            computed = hashlib.pbkdf2_hmac("sha256", candidate, _unb64(salt), int(iterations))
            return hmac.compare_digest(computed, _unb64(digest))
        if stored.startswith("pbkdf2:"):
            _, salt_hex, digest_hex = stored.split(":")
            computed = hashlib.pbkdf2_hmac("sha256", candidate, bytes.fromhex(salt_hex), _LEGACY_PBKDF2_ITERATIONS)
            return hmac.compare_digest(computed, bytes.fromhex(digest_hex))
        if stored.startswith("sha256:"):
            computed = hashlib.sha256(candidate + _LEGACY_STATIC_SALT.encode("utf-8")).hexdigest()
            return hmac.compare_digest(computed.encode("ascii"), stored[len("sha256:"):].encode("ascii"))
    except (ValueError, TypeError):
        return False
    return False


def needs_rehash(stored: str | None) -> bool:
    if not stored or not stored.startswith(ALGORITHM + "$"):
        return True
    try:
        return int(stored.split("$")[1]) < ITERATIONS
    except (IndexError, ValueError):
        return True


def is_recognised_hash(stored: str | None) -> bool:
    return bool(stored) and stored.startswith((ALGORITHM + "$", "pbkdf2:", "sha256:"))


def uses_known_default(stored: str | None) -> bool:
    """True when a stored credential is plaintext or matches a published default."""
    if not stored:
        return False
    if not is_recognised_hash(stored):
        return True
    return any(verify_password(default, stored) for default in KNOWN_DEFAULT_PASSWORDS)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password(base64.b64encode(os.urandom(18)).decode("ascii"))


def burn_verification_time(password: str) -> None:
    """Spend the same CPU as a real check so response time doesn't reveal unknown users."""
    verify_password(password, _dummy_hash())
