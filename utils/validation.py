"""Input validation.

Every pure calculation function validates its own inputs so that a bad value can
never silently produce a nonsense result. The UI catches ValidationError and
shows the message instead of a number.
"""
from __future__ import annotations

import math


class ValidationError(ValueError):
    """Raised when an input is outside the physically meaningful range."""


def _label(name: str, unit: str = "") -> str:
    return f"{name} [{unit}]" if unit else name


def finite(value: float, name: str, unit: str = "") -> float:
    """Reject NaN and infinity."""
    value = float(value)
    if not math.isfinite(value):
        raise ValidationError(f"{_label(name, unit)} must be a finite number.")
    return value


def positive(value: float, name: str, unit: str = "") -> float:
    """Require value > 0 (lengths, areas, masses, time constants...)."""
    value = finite(value, name, unit)
    if value <= 0:
        raise ValidationError(
            f"{_label(name, unit)} must be greater than zero (got {value:g})."
        )
    return value


def non_negative(value: float, name: str, unit: str = "") -> float:
    """Require value >= 0 (speeds, densities, areas that may be zero)."""
    value = finite(value, name, unit)
    if value < 0:
        raise ValidationError(
            f"{_label(name, unit)} cannot be negative (got {value:g})."
        )
    return value


def non_zero(value: float, name: str, unit: str = "") -> float:
    """Require value != 0. Used wherever a value appears in a denominator."""
    value = finite(value, name, unit)
    if value == 0:
        raise ValidationError(
            f"{_label(name, unit)} cannot be zero - it would divide by zero."
        )
    return value


def in_range(value: float, name: str, low: float, high: float, unit: str = "") -> float:
    """Require low <= value <= high."""
    value = finite(value, name, unit)
    if value < low or value > high:
        raise ValidationError(
            f"{_label(name, unit)} must be between {low:g} and {high:g} (got {value:g})."
        )
    return value


def positive_int(value: int, name: str) -> int:
    """Require an integer >= 1 (motor counts, gear teeth...)."""
    ivalue = int(value)
    if ivalue < 1:
        raise ValidationError(f"{name} must be a whole number of 1 or more (got {value}).")
    return ivalue
