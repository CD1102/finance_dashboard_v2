"""Presentation helpers.

Formatting lives outside the pages so that every screen renders money, dates
and deltas identically, and so the rules can be tested.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from financelib.models import month_to_date

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

#: Minus sign rather than a hyphen: it aligns better at large type sizes.
MINUS = "\u2212"


def _round_half_up(value: float, decimals: int) -> Decimal:
    """Round away from zero at the halfway point.

    Python rounds halves to even, so ``£1,234.50`` would display as ``£1,234``.
    Money is expected to round up, so currency formatting uses Decimal.
    """
    quantum = Decimal(1).scaleb(-decimals)
    try:
        return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return Decimal(0)


def money(value: float | None, symbol: str = "£", decimals: int = 0, blank: str = "—") -> str:
    """Format an amount, using a true minus sign for negatives."""
    if value is None:
        return blank
    rounded = _round_half_up(value, decimals)
    formatted = f"{abs(rounded):,.{decimals}f}"
    return f"{MINUS}{symbol}{formatted}" if rounded < 0 else f"{symbol}{formatted}"


def signed_money(value: float | None, symbol: str = "£", decimals: int = 0, blank: str = "—") -> str:
    """Format an amount with an explicit sign, for deltas."""
    if value is None:
        return blank
    rounded = _round_half_up(value, decimals)
    sign = "+" if rounded >= 0 else MINUS
    return f"{sign}{symbol}{abs(rounded):,.{decimals}f}"


def compact_money(value: float | None, symbol: str = "£", blank: str = "—") -> str:
    """Shorten large amounts for axis labels: £1.2k, £340k, £1.4m."""
    if value is None:
        return blank
    magnitude = abs(value)
    sign = MINUS if value < 0 else ""
    if magnitude >= 1_000_000:
        return f"{sign}{symbol}{magnitude / 1_000_000:.2f}m".replace(".00m", "m")
    if magnitude >= 1_000:
        return f"{sign}{symbol}{magnitude / 1_000:.1f}k".replace(".0k", "k")
    return f"{sign}{symbol}{magnitude:,.0f}"


def percent(value: float | None, decimals: int = 1, blank: str = "—") -> str:
    if value is None:
        return blank
    return f"{value:.{decimals}f}%"


def signed_percent(value: float | None, decimals: int = 1, blank: str = "—") -> str:
    if value is None:
        return blank
    return f"{'+' if value >= 0 else MINUS}{abs(value):.{decimals}f}%"


def month_label(month: str, style: str = "short") -> str:
    """``2026-09`` as ``Sep 2026``, ``September 2026`` or ``Sep``."""
    try:
        year, index = month.split("-")
        name = MONTH_NAMES[int(index) - 1]
    except (ValueError, IndexError):
        return month
    if style == "long":
        return f"{name} {year}"
    if style == "bare":
        return name[:3]
    return f"{name[:3]} {year}"


def month_axis_label(month: str) -> str:
    """Compact axis form: ``Sep 26``."""
    try:
        year, index = month.split("-")
        return f"{MONTH_NAMES[int(index) - 1][:3]} {year[-2:]}"
    except (ValueError, IndexError):
        return month


def date_label(value: date | None, blank: str = "—") -> str:
    if value is None:
        return blank
    return f"{value.day} {MONTH_NAMES[value.month - 1][:3]} {value.year}"


def month_date(month: str) -> date:
    return month_to_date(month)


def duration_label(months: int | None, blank: str = "—") -> str:
    """``18`` as ``1 yr 6 mo``."""
    if months is None:
        return blank
    if months <= 0:
        return "now"
    years, remainder = divmod(int(months), 12)
    parts = []
    if years:
        parts.append(f"{years} yr" + ("s" if years > 1 else ""))
    if remainder:
        parts.append(f"{remainder} mo")
    return " ".join(parts) or "now"


def file_size(num_bytes: int | None) -> str:
    if not num_bytes:
        return "0 KB"
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} GB"


def pluralise(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"
