from decimal import Decimal, InvalidOperation


def to_cents(amount) -> int | None:
    """Valid positive money with at most 2 decimals -> cents, else None. Never raises."""
    if isinstance(amount, bool) or not isinstance(amount, (int, float, str)):
        return None
    try:
        d = Decimal(str(amount).strip())
    except InvalidOperation:
        return None
    if not d.is_finite() or d <= 0 or d.as_tuple().exponent < -2:
        return None
    return int(d * 100)
