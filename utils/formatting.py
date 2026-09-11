"""Number formatting for readable engineering output."""
from __future__ import annotations

import math


def format_number(value: float, sig: int = 4) -> str:
    """Format a number to at least `sig` significant digits.

    `sig` sets how many DECIMALS are shown, and the whole-number part is never
    truncated: 12403.125 stays "12,403" at any setting rather than rounding to
    "12,400". That is deliberate for an engineering tool - discarding 403 N of
    a real answer to satisfy a display preference would be worse than showing
    an extra digit.

    Switches to scientific notation outside 1e-3 .. 1e6, which is where fixed
    notation stops being readable (e.g. viscosity or a Young's modulus in Pa).
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(value):
        return "-"
    if value == 0:
        return "0"

    magnitude = abs(value)
    if magnitude >= 1e6 or magnitude < 1e-3:
        return f"{value:.{max(sig - 1, 0)}e}"

    decimals = sig - 1 - int(math.floor(math.log10(magnitude)))
    decimals = min(max(decimals, 0), 6)
    text = f"{value:,.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_with_unit(value: float, unit: str, sig: int = 4) -> str:
    """'1,225 N' style output."""
    number = format_number(value, sig)
    return f"{number} {unit}" if unit else number
