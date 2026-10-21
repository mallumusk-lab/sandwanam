"""Money and weight arithmetic. Always Decimal, always rounded half-up to 2 places."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_AMOUNT = Decimal("1000000000.00")  # ₹100 crore: far above any single gold loan


class AmountError(ValueError):
    """An amount that cannot be accepted."""


def to_decimal(value: object) -> Decimal:
    """Convert user/DB input to Decimal without going through binary floats."""
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, bool):
        raise AmountError("Amounts must be numbers.")
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip().replace(",", ""))
        except InvalidOperation as exc:
            raise AmountError("Amounts must be numbers.") from exc
    elif value is None:
        return ZERO
    else:
        raise AmountError("Amounts must be numbers.")
    if not result.is_finite():
        raise AmountError("Amounts must be finite numbers.")
    return result


def money(value: object) -> Decimal:
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_amount(value: object, *, field: str = "Amount", allow_zero: bool = False) -> Decimal:
    """Validate a user-entered rupee amount (positive, ≤ 2 decimals, bounded)."""
    amount = to_decimal(value)
    if amount.as_tuple().exponent < -2:  # type: ignore[operator]
        raise AmountError(f"{field} can have at most 2 decimal places.")
    if amount < 0 or (amount == 0 and not allow_zero):
        raise AmountError(f"{field} must be greater than zero.")
    if amount > MAX_AMOUNT:
        raise AmountError(f"{field} is too large.")
    return amount.quantize(CENT)


def fmt(value: Decimal | None) -> str:
    """Serialise money for JSON (string, 2 decimals) so clients never see float drift."""
    return str(money(value if value is not None else ZERO))
