"""Elasticity is derived, not declared - so it needs checking against
equations whose exponents are known exactly by hand."""
from __future__ import annotations

import math

import pytest

from utils.analysis import describe, elasticity, influences
from utils.spec import Calculator, Field, Inputs, Output


def _calc(compute, *fields):
    return Calculator(slug="t.x", name="T", latex="", explanation="",
                      inputs=list(fields), compute=compute,
                      result=Output("R", "-"))


def _at(**values):
    return Inputs(values)


# --------------------------------------------------------------------------
# Known exponents
# --------------------------------------------------------------------------
def test_linear_input_has_elasticity_one():
    calc = _calc(lambda i: 3.0 * i.x, Field("x", "X", "-", 2.0))
    values = _at(x=2.0)
    assert elasticity(calc, values, "x", 6.0) == pytest.approx(1.0, abs=1e-6)


def test_squared_input_has_elasticity_two():
    """Lift is quadratic in velocity; the table should say so without being
    told."""
    calc = _calc(lambda i: 0.5 * i.v ** 2, Field("v", "V", "m/s", 50.0))
    values = _at(v=50.0)
    assert elasticity(calc, values, "v", 1250.0) == pytest.approx(2.0, abs=1e-6)


def test_cubed_input_has_elasticity_three():
    calc = _calc(lambda i: i.n ** 3, Field("n", "N", "-", 4.0))
    assert elasticity(calc, _at(n=4.0), "n", 64.0) == pytest.approx(3.0, abs=1e-6)


def test_a_divisor_has_elasticity_minus_one():
    calc = _calc(lambda i: 10.0 / i.d, Field("d", "D", "-", 5.0))
    assert elasticity(calc, _at(d=5.0), "d", 2.0) == pytest.approx(-1.0, abs=1e-6)


def test_a_square_root_has_elasticity_one_half():
    calc = _calc(lambda i: math.sqrt(i.a), Field("a", "A", "-", 9.0))
    assert elasticity(calc, _at(a=9.0), "a", 3.0) == pytest.approx(0.5, abs=1e-6)


def test_an_additive_constant_lowers_the_exponent():
    """f = x + 10 at x = 10 is only half as sensitive as f = x."""
    calc = _calc(lambda i: i.x + 10.0, Field("x", "X", "-", 10.0))
    assert elasticity(calc, _at(x=10.0), "x", 20.0) == pytest.approx(0.5, abs=1e-6)


# --------------------------------------------------------------------------
# Ranking and degenerate points
# --------------------------------------------------------------------------
def test_influences_rank_the_strongest_driver_first():
    calc = _calc(lambda i: i.a * i.b ** 2,
                 Field("a", "A", "-", 3.0), Field("b", "B", "-", 4.0))
    ranked = influences(calc, _at(a=3.0, b=4.0), 48.0)
    assert [i.key for i in ranked] == ["b", "a"]
    assert ranked[0].elasticity == pytest.approx(2.0, abs=1e-5)


def test_a_zero_input_is_reported_not_crashed():
    calc = _calc(lambda i: i.x * 2.0, Field("x", "X", "-", 0.0))
    only = influences(calc, _at(x=0.0), 0.0)[0]
    assert only.elasticity is None and only.reason


def test_a_choice_input_is_skipped():
    """An elasticity with respect to a dropdown is meaningless."""
    calc = _calc(lambda i: 1.0,
                 Field("m", "Mode", "", 0.0, kind="choice", options=["a", "b"]),
                 Field("x", "X", "-", 1.0))
    assert [i.key for i in influences(calc, _at(m="a", x=1.0), 1.0)] == ["x"]


def test_an_input_that_breaks_the_equation_degrades_to_one_sided():
    """At x = 1 a log is fine upward and fine downward; at the very edge of a
    domain only one direction survives, and that is still worth reporting."""
    def compute(i):
        if i.x < 1.0:
            raise ValueError("out of domain")
        return i.x ** 2
    calc = _calc(compute, Field("x", "X", "-", 1.0))
    assert elasticity(calc, _at(x=1.0), "x", 1.0) == pytest.approx(2.0, abs=1e-3)


# --------------------------------------------------------------------------
# Wording
# --------------------------------------------------------------------------
def test_describe_names_a_square_law():
    calc = _calc(lambda i: i.v ** 2, Field("v", "V", "-", 3.0))
    text = describe(influences(calc, _at(v=3.0), 9.0)[0])
    assert "square" in text and "2.00%" in text


def test_describe_calls_a_divisor_inverse_not_direct():
    calc = _calc(lambda i: 1.0 / i.d, Field("d", "D", "-", 2.0))
    text = describe(influences(calc, _at(d=2.0), 0.5)[0])
    assert "inversely proportional" in text and "decreases" in text


# --------------------------------------------------------------------------
# Uncertainty propagation
# --------------------------------------------------------------------------
from utils.analysis import uncertainty  # noqa: E402


def _u(fn, values, sigmas, *fields):
    calc = _calc(fn, *fields)
    inputs = Inputs(values)
    return uncertainty(calc, inputs, fn(inputs), sigmas)


def test_a_sum_adds_its_uncertainties_in_quadrature():
    """Independent errors partly cancel; they do not all go the same way."""
    spread = _u(lambda i: i.x + i.y, {"x": 3.0, "y": 4.0},
                {"x": 0.3, "y": 0.4},
                Field("x", "X", "-", 3.0), Field("y", "Y", "-", 4.0))
    assert spread.sigma == pytest.approx(math.hypot(0.3, 0.4))
    assert spread.sigma < 0.3 + 0.4          # not linear addition


def test_a_product_adds_relative_uncertainties_in_quadrature():
    spread = _u(lambda i: i.x * i.y, {"x": 3.0, "y": 4.0},
                {"x": 0.3, "y": 0.4},
                Field("x", "X", "-", 3.0), Field("y", "Y", "-", 4.0))
    assert spread.relative(12.0) == pytest.approx(
        math.hypot(0.3 / 3.0, 0.4 / 4.0), rel=1e-6)


def test_a_squared_input_doubles_its_relative_uncertainty():
    """sigma_f = 2 x sigma_x for f = x^2 - the exponent is the multiplier."""
    spread = _u(lambda i: i.x ** 2, {"x": 5.0}, {"x": 0.1},
                Field("x", "X", "-", 5.0))
    assert spread.sigma == pytest.approx(2 * 5.0 * 0.1, rel=1e-5)
    assert spread.relative(25.0) == pytest.approx(2 * (0.1 / 5.0), rel=1e-5)


def test_a_constant_factor_scales_the_uncertainty():
    spread = _u(lambda i: 7.0 * i.x, {"x": 2.0}, {"x": 0.25},
                Field("x", "X", "-", 2.0))
    assert spread.sigma == pytest.approx(7.0 * 0.25, rel=1e-6)


def test_shares_are_of_the_variance_and_sum_to_one():
    """Variances are what add, so these are the numbers that total 100%."""
    spread = _u(lambda i: i.x + i.y, {"x": 1.0, "y": 1.0},
                {"x": 0.1, "y": 0.3},
                Field("x", "X", "-", 1.0), Field("y", "Y", "-", 1.0))
    shares = {c.key: c.share for c in spread.contributions}
    assert sum(shares.values()) == pytest.approx(1.0)
    assert shares["y"] == pytest.approx(0.09 / (0.01 + 0.09))


def test_the_biggest_contributor_comes_first():
    """The page tells the user which one measurement to go and improve."""
    spread = _u(lambda i: i.x + i.y, {"x": 1.0, "y": 1.0},
                {"x": 0.05, "y": 0.5},
                Field("x", "X", "-", 1.0), Field("y", "Y", "-", 1.0))
    assert [c.key for c in spread.contributions] == ["y", "x"]


def test_an_input_with_no_stated_uncertainty_contributes_nothing():
    spread = _u(lambda i: i.x + i.y, {"x": 3.0, "y": 4.0}, {"x": 0.3},
                Field("x", "X", "-", 3.0), Field("y", "Y", "-", 4.0))
    assert [c.key for c in spread.contributions] == ["x"]
    assert spread.sigma == pytest.approx(0.3)


def test_no_uncertainties_at_all_is_reported_as_unknown_not_as_zero():
    """A result with no stated ± is not a result known exactly."""
    spread = _u(lambda i: i.x, {"x": 3.0}, {}, Field("x", "X", "-", 3.0))
    assert not spread.known and spread.contributions == []


def test_the_band_brackets_the_result():
    spread = _u(lambda i: i.x, {"x": 10.0}, {"x": 0.5},
                Field("x", "X", "-", 10.0))
    assert spread.band(10.0) == pytest.approx((9.5, 10.5))


def test_relative_uncertainty_is_none_at_a_zero_result():
    spread = _u(lambda i: i.x, {"x": 0.0}, {"x": 0.5},
                Field("x", "X", "-", 0.0))
    assert spread.relative(0.0) is None


def test_a_choice_input_cannot_carry_an_uncertainty():
    spread = _u(lambda i: 5.0, {"m": "a", "x": 1.0}, {"m": 1.0, "x": 0.1},
                Field("m", "Mode", "", 0, kind="choice", options=["a", "b"]),
                Field("x", "X", "-", 1.0))
    assert [c.key for c in spread.contributions] == []


def test_lift_carries_a_five_percent_coefficient_straight_through():
    """Lift is linear in C_L, so a 5% uncertainty on it is 5% on the answer -
    checked against a real page rather than a toy function."""
    from calculators import aerodynamics as aero

    lift = next(c for c in aero.CALCULATORS if c.slug == "aero.lift")
    values = Inputs({"rho": 1.225, "v": 50.0, "s": 16.2, "cl": 0.5})
    result = lift.compute(values)
    spread = uncertainty(lift, values, result, {"cl": 0.025})
    assert spread.relative(result) == pytest.approx(0.05, rel=1e-4)


def test_lift_doubles_a_velocity_uncertainty():
    """Lift goes as V squared, so the relative uncertainty doubles."""
    from calculators import aerodynamics as aero

    lift = next(c for c in aero.CALCULATORS if c.slug == "aero.lift")
    values = Inputs({"rho": 1.225, "v": 50.0, "s": 16.2, "cl": 0.5})
    result = lift.compute(values)
    spread = uncertainty(lift, values, result, {"v": 0.5})   # 1% on V
    assert spread.relative(result) == pytest.approx(0.02, rel=1e-3)
