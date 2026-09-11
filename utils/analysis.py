"""Numerical analysis applied to whatever a calculator already computes.

The point of this module is leverage: it derives new insight from the
`compute` function a page already has, so every calculator gains the feature
without its author writing anything.

Elasticity is the useful one. For a result f and an input x,

    E = (df/dx) * (x/f)

is the percentage change in the result per one percent change in the input.
It is dimensionless, so inputs measured in completely different units can be
ranked against each other - which is exactly the question an engineer asks
("what actually drives this number?") and the one a formula alone does not
answer.

For a power law f = k*x^n the elasticity is exactly n, so the table also reads
out the exponent of each variable: velocity in the lift equation comes back as
2.00 because lift really is quadratic in speed. Nothing declares that; it falls
out of the arithmetic.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, NamedTuple, Optional

from .spec import Calculator, Inputs
from .validation import ValidationError

# Inputs whose elasticity is meaningless or undefined.
_NUMERIC_KINDS = {"float", "int", "slider", "weight"}

# Below this the result is indistinguishable from zero and the ratio x/f
# explodes; report the change in absolute terms instead of as a percentage.
_NEAR_ZERO = 1e-12


class Influence(NamedTuple):
    """How strongly one input drives the result."""

    key: str
    label: str
    unit: str
    elasticity: Optional[float]   # % change in result per 1% change in input
    reason: Optional[str]         # why it could not be computed, if it could not

    @property
    def usable(self) -> bool:
        return self.elasticity is not None and math.isfinite(self.elasticity)


def _evaluate(calc: Calculator, values: Dict[str, Any], key: str,
              x: float) -> Optional[float]:
    trial = dict(values)
    trial[key] = x
    try:
        out = calc.compute(Inputs(trial))
    except (ValidationError, ZeroDivisionError, ValueError, OverflowError):
        return None
    if out is None or not isinstance(out, (int, float)) or not math.isfinite(out):
        return None
    return float(out)


def elasticity(calc: Calculator, values: Inputs, key: str,
               result: float) -> Optional[float]:
    """Central-difference elasticity of the result with respect to one input.

    A central difference is used rather than a one-sided one because many of
    these equations are curved, and a forward difference on a parabola carries
    a first-order error that would show velocity in the lift equation as 2.01
    rather than 2.00. The step is relative so it suits both a wingspan of 10 m
    and a viscosity of 1.8e-5.
    """
    base = values.as_dict()
    x = base.get(key)
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return None
    x = float(x)
    if abs(result) < _NEAR_ZERO:
        return None

    step = 1e-4 * abs(x) if x != 0 else 1e-6
    up = _evaluate(calc, base, key, x + step)
    down = _evaluate(calc, base, key, x - step)
    if up is None or down is None:
        # An input sitting on its own limit (a zero area, a zero speed) cannot
        # be stepped in both directions. One-sided is better than nothing.
        one_sided = up if up is not None else down
        if one_sided is None:
            return None
        derivative = (one_sided - result) / (step if up is not None else -step)
    else:
        derivative = (up - down) / (2.0 * step)

    if x == 0:
        return None          # x/f is zero: elasticity says nothing at the origin
    value = derivative * x / result
    return value if math.isfinite(value) else None


def influences(calc: Calculator, values: Inputs, result: float) -> List[Influence]:
    """Rank every numeric input by how hard it drives the result."""
    out: List[Influence] = []
    for field in calc.inputs:
        if field.kind not in _NUMERIC_KINDS:
            continue
        raw = values.as_dict().get(field.key)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue
        reason = None
        value = None
        if abs(result) < _NEAR_ZERO:
            reason = "the result is zero here"
        elif float(raw) == 0.0:
            reason = "this input is zero here"
        else:
            value = elasticity(calc, values, field.key, result)
            if value is None:
                reason = "not differentiable at this point"
        out.append(Influence(field.key, field.label, field.unit, value, reason))

    out.sort(key=lambda i: (-abs(i.elasticity) if i.usable else 0.0, i.label))
    return out


def describe(influence: Influence) -> str:
    """Plain-English reading of one elasticity."""
    if not influence.usable:
        return f"No effect can be measured here - {influence.reason}."
    e = influence.elasticity
    if abs(e) < 0.005:
        return "Changing this barely moves the result at all."
    direction = "increases" if e > 0 else "decreases"
    magnitude = abs(e)
    # Matched on the signed elasticity, not its magnitude: -1 is an inverse
    # proportionality, not a direct one.
    shape = ""
    for exponent, name in ((1.0, "directly proportional to"),
                           (2.0, "proportional to the square of"),
                           (3.0, "proportional to the cube of"),
                           (0.5, "proportional to the square root of"),
                           (-1.0, "inversely proportional to"),
                           (-2.0, "proportional to the inverse square of")):
        if abs(e - exponent) < 0.02:
            shape = f" The result is {name} this input."
            break
    return (f"A 1% increase here {direction} the result by "
            f"{magnitude:.2f}%.{shape}")
