"""Input rules shared by the API schemas and the services."""
from __future__ import annotations

import base64
import binascii
import re
from decimal import Decimal

from .money import to_decimal

PHONE = re.compile(r"^[6-9]\d{9}$")
USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
BRANCH_PREFIX = re.compile(r"^[A-Z]{2,5}$")
MAX_WEIGHT_GRAMS = Decimal("100000")
MAX_RATE = Decimal("100")
MAX_TENURE_MONTHS = 120
MAX_LOGO_BYTES = 200 * 1024
PASSWORD_MIN = 10
PASSWORD_MAX = 128

_COMMON_PASSWORDS = frozenset(
    {
        "1234567890", "0123456789", "password", "password1", "password12", "password123",
        "passw0rd", "qwertyuiop", "1q2w3e4r5t", "iloveyou", "admin12345", "administrator",
        "superadmin", "super1234", "welcome123", "letmein123", "1111111111", "abcdefghij",
        "qwerty1234", "india12345", "gold123456", "finance123", "changeme123",
    }
)

_LOGO_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
}
_DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\s]+)$")


class ValidationError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def phone(value: str) -> str:
    digits = re.sub(r"[\s-]", "", value or "")
    if digits.startswith("+91"):
        digits = digits[3:]
    if not PHONE.match(digits):
        raise ValidationError("phone", "Enter a 10-digit mobile number starting with 6, 7, 8 or 9.")
    return digits


def person_name(value: str, field: str = "name") -> str:
    text = " ".join((value or "").split())
    if not 2 <= len(text) <= 100 or not text.isprintable():
        raise ValidationError(field, "Enter a name between 2 and 100 characters.")
    return text


def address(value: str) -> str:
    text = " ".join((value or "").split())
    if not 3 <= len(text) <= 255:
        raise ValidationError("address", "Enter an address between 3 and 255 characters.")
    return text


def weights(gross: object, deduction: object) -> tuple[Decimal, Decimal, Decimal]:
    gross_w = to_decimal(gross).quantize(Decimal("0.01"))
    deduction_w = to_decimal(deduction).quantize(Decimal("0.01"))
    if gross_w <= 0 or gross_w > MAX_WEIGHT_GRAMS:
        raise ValidationError("weight", "Gross weight must be more than 0 g.")
    if deduction_w < 0:
        raise ValidationError("deduction", "Deduction cannot be negative.")
    if deduction_w >= gross_w:
        raise ValidationError("deduction", "Deduction must be less than the gross weight.")
    return gross_w, deduction_w, gross_w - deduction_w


def rate(value: object) -> Decimal:
    raw = to_decimal(value)
    if raw.as_tuple().exponent < -2:  # type: ignore[operator]
        raise ValidationError("interest", "The interest rate can have at most 2 decimal places.")
    result = raw.quantize(Decimal("0.01"))
    if result <= 0 or result > MAX_RATE:
        raise ValidationError("interest", "The interest rate must be between 0.01 and 100 % p.a.")
    return result


def tenure(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_TENURE_MONTHS:
        raise ValidationError("tenure", f"Tenure must be 1 to {MAX_TENURE_MONTHS} months.")
    return value


def username(value: str) -> str:
    if not USERNAME.match(value or ""):
        raise ValidationError("username", "Usernames are 3–32 letters, digits, dots, dashes or underscores.")
    return value


def branch_prefix(value: str) -> str:
    prefix = (value or "").strip().upper()
    if not BRANCH_PREFIX.match(prefix):
        raise ValidationError("branch_prefix", "The customer ID prefix must be 2–5 letters (for example SAN).")
    return prefix


def password(value: str, user: str = "") -> str:
    if not isinstance(value, str) or not PASSWORD_MIN <= len(value) <= PASSWORD_MAX:
        raise ValidationError("password", f"Passwords must be {PASSWORD_MIN}–{PASSWORD_MAX} characters long.")
    lowered = value.lower()
    if lowered in _COMMON_PASSWORDS or len(set(value)) < 4:
        raise ValidationError("password", "This password is too easy to guess. Choose a longer, less common one.")
    if user and user.lower() in lowered:
        raise ValidationError("password", "The password must not contain the username.")
    return value


def logo_data_url(value: str | None) -> str | None:
    """Accept PNG, JPEG or WebP data URLs up to 200 KB, verified by magic bytes."""
    if value in (None, ""):
        return None
    match = _DATA_URL.match(value)
    if not match:
        raise ValidationError("logo", "Logos must be PNG, JPEG or WebP images.")
    try:
        raw = base64.b64decode(match.group(2), validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError("logo", "The logo image could not be read.") from exc
    if len(raw) > MAX_LOGO_BYTES:
        raise ValidationError("logo", "Logos must be 200 KB or smaller.")
    mime = match.group(1)
    if not any(raw.startswith(sig) for sig in _LOGO_SIGNATURES[mime]):
        raise ValidationError("logo", "The file content does not match its image type.")
    if mime == "image/webp" and raw[8:12] != b"WEBP":
        raise ValidationError("logo", "The file content does not match its image type.")
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
