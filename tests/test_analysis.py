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
