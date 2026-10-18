import hashlib
import os
import hmac

# Per-user random salt + PBKDF2-HMAC-SHA256 password hashing.
# Format stored in DB: "pbkdf2:<hex_salt>:<hex_hash>"
# Backward-compatible: also handles legacy "sha256:<hash>" format.

ITERATIONS = 260_000  # OWASP recommended minimum for PBKDF2-SHA256

def get_password_hash(password: str) -> str:
    """Hash a password with a random per-user salt using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(32)  # 256-bit random salt, unique per user
    hash_bytes = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        ITERATIONS
    )
    return f"pbkdf2:{salt.hex()}:{hash_bytes.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored hash. Supports pbkdf2 and legacy sha256 formats."""
    if not hashed_password:
        return False

    # New format: pbkdf2:<hex_salt>:<hex_hash>
    if hashed_password.startswith("pbkdf2:"):
        parts = hashed_password.split(":")
        if len(parts) != 3:
            return False
        try:
            salt = bytes.fromhex(parts[1])
            stored_hash = bytes.fromhex(parts[2])
        except ValueError:
            return False
        check_hash = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt,
            ITERATIONS
        )
        # Use hmac.compare_digest to prevent timing attacks
        return hmac.compare_digest(check_hash, stored_hash)

    # Legacy format: sha256:<hash> (global static salt — kept for backward compatibility)
    if hashed_password.startswith("sha256:"):
        parts = hashed_password.split(":")
        if len(parts) < 2:
            return False
        legacy_salt = "salthere"
        db_val = parts[1]
        check_val = hashlib.sha256((plain_password + legacy_salt).encode()).hexdigest()
        return hmac.compare_digest(check_val, db_val)

    # Plaintext fallback (very old records)
    return hmac.compare_digest(plain_password, hashed_password)
