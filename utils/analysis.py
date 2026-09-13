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
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

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


def derivative(calc: Calculator, values: Inputs, key: str,
               result: float) -> Optional[float]:
    """df/dx for one input, by central difference.

    A central difference rather than a one-sided one because many of these
    equations are curved, and a forward difference on a parabola carries a
    first-order error that would show velocity in the lift equation as 2.01
    rather than 2.00. The step is relative so it suits both a wingspan of 10 m
    and a viscosity of 1.8e-5.
    """
    base = values.as_dict()
    x = base.get(key)
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return None
    x = float(x)

    step = 1e-4 * abs(x) if x != 0 else 1e-6
    up = _evaluate(calc, base, key, x + step)
    down = _evaluate(calc, base, key, x - step)
    if up is None or down is None:
        # An input sitting on its own limit (a zero area, a zero speed) cannot
        # be stepped in both directions. One-sided is better than nothing.
        one_sided = up if up is not None else down
        if one_sided is None:
            return None
        slope = (one_sided - result) / (step if up is not None else -step)
    else:
        slope = (up - down) / (2.0 * step)
    return slope if math.isfinite(slope) else None


def elasticity(calc: Calculator, values: Inputs, key: str,
               result: float) -> Optional[float]:
    """Percentage change in the result per one percent change in an input."""
    x = values.as_dict().get(key)
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return None
    x = float(x)
    if abs(result) < _NEAR_ZERO or x == 0:
        return None          # x/f says nothing at the origin
    slope = derivative(calc, values, key, result)
    if slope is None:
        return None
    value = slope * x / result
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


# ---------------------------------------------------------------------------
# Uncertainty
# ---------------------------------------------------------------------------
class Contribution(NamedTuple):
    """How much one input's uncertainty contributes to the result's."""

    key: str
    label: str
    unit: str
    input_sigma: float          # the +/- on the input, in its own unit
    result_sigma: float         # what that alone would put on the result
    share: float                # fraction of the total variance, 0 to 1


class Uncertainty(NamedTuple):
    sigma: float                            # combined, on the result
    contributions: List[Contribution]       # largest share first

    @property
    def known(self) -> bool:
        return self.sigma > 0 and bool(self.contributions)

    def band(self, result: float) -> Tuple[float, float]:
        return result - self.sigma, result + self.sigma

    def relative(self, result: float) -> Optional[float]:
        """The +/- as a fraction of the result, or None at zero."""
        return self.sigma / abs(result) if abs(result) > _NEAR_ZERO else None


def uncertainty(calc: Calculator, values: Inputs, result: float,
                sigmas: Dict[str, float]) -> Uncertainty:
    """Propagate input uncertainties through to the result.

    First-order propagation, the standard approach:

        sigma_f^2 = sum over i of (df/dx_i * sigma_i)^2

    Each input's uncertainty is scaled by how hard that input drives the
    result, and the scaled terms are added in quadrature rather than linearly -
    which is why four inputs each contributing 1% give 2% rather than 4%.
    Independent errors partly cancel; they do not all go the same way at once.

    Two assumptions ride on that formula and both are stated on the page:
    the inputs must be independent of each other, and the function must be
    near enough to linear across the width of each uncertainty. A large
    uncertainty on a sharply curved term breaks the second, and the answer
    comes out too small.

    The per-input contributions are the useful part. They say which
    measurement is actually costing you the confidence, which turns "my answer
    is +/- 9%" into "go and measure this one thing".
    """
    terms: List[Contribution] = []
    variance = 0.0
    for field in calc.inputs:
        sigma_in = float(sigmas.get(field.key, 0.0) or 0.0)
        if sigma_in <= 0 or field.kind not in _NUMERIC_KINDS:
            continue
        slope = derivative(calc, values, field.key, result)
        if slope is None:
            continue
        term = abs(slope) * sigma_in
        if not math.isfinite(term) or term <= 0:
            continue
        variance += term * term
        terms.append(Contribution(field.key, field.label, field.unit,
                                  sigma_in, term, 0.0))

    if variance <= 0:
        return Uncertainty(0.0, [])

    total = math.sqrt(variance)
    # Share of the VARIANCE, not of the standard deviation: variances are what
    # add, so these are the numbers that sum to one.
    ranked = [c._replace(share=(c.result_sigma ** 2) / variance) for c in terms]
    ranked.sort(key=lambda c: -c.share)
    return Uncertainty(total, ranked)
