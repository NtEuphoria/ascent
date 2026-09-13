"""The wing study studio."""
from __future__ import annotations

import math

import pytest

from calculators import flight
from conftest import goto
from studios import wing
from utils.constants import G0

MASS, SPAN, AREA = 3.2, 2.4, 0.48
CD0, OSWALD, CLMAX = 0.030, 0.85, 1.30


def _craft(mass=MASS, span=SPAN, area=AREA, altitude=0.0):
    return wing.aircraft(mass, span, area, altitude)


def _polar(craft=None, cd0=CD0, oswald=OSWALD, cl_max=CLMAX):
    return wing.polar(craft or _craft(), cd0, oswald, cl_max)


def _flying(speed=22.0, thrust=8.0, bank=0.0, craft=None, wing_polar=None):
    craft = craft or _craft()
    return wing.envelope(craft, wing_polar or _polar(craft), AREA, speed,
                         thrust, bank)


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
def test_aspect_ratio_and_wing_loading():
    craft = _craft()
    assert craft.aspect_ratio == pytest.approx(SPAN ** 2 / AREA)
    assert craft.wing_loading == pytest.approx(MASS * G0 / AREA)


def test_altitude_thins_the_air():
    assert _craft(altitude=2000.0).density < _craft(altitude=0.0).density


# --------------------------------------------------------------------------
# The drag polar
# --------------------------------------------------------------------------
def test_the_induced_factor_is_one_over_pi_e_ar():
    polar = _polar()
    assert polar.induced_factor == pytest.approx(
        1.0 / (math.pi * OSWALD * (SPAN ** 2 / AREA)))


def test_at_best_lift_to_drag_induced_drag_equals_parasite_drag():
    """The classic result, and a good check that the optimum is the real one
    rather than a scan: CD at best L/D is exactly twice CD0."""
    polar = _polar()
    assert polar.cd_best == pytest.approx(2.0 * CD0)
    assert polar.cl_best == pytest.approx(math.sqrt(CD0 / polar.induced_factor))
    assert polar.ld_max == pytest.approx(polar.cl_best / polar.cd_best)


def test_a_longer_wing_glides_better():
    """Span matters more than anything else in the polar, which is why
    sailplanes look like they do."""
    stubby = wing.polar(_craft(span=1.6), CD0, OSWALD, CLMAX)
    long = wing.polar(_craft(span=3.2), CD0, OSWALD, CLMAX)
    assert long.ld_max > stubby.ld_max


# --------------------------------------------------------------------------
# The flight envelope
# --------------------------------------------------------------------------
def test_cruise_coefficients_come_from_the_polar():
    craft = _craft()
    polar = _polar(craft)
    flying = _flying(speed=22.0, craft=craft, wing_polar=polar)
    q = 0.5 * craft.density * 22.0 ** 2
    cl = craft.weight / (q * AREA)
    assert flying.cl == pytest.approx(cl)
    assert flying.cd == pytest.approx(CD0 + polar.induced_factor * cl ** 2)
    assert flying.drag == pytest.approx(q * AREA * flying.cd)
    assert flying.power == pytest.approx(flying.drag * 22.0)


def test_stall_speed_matches_the_calculator_page():
    craft = _craft()
    assert _flying().stall == pytest.approx(
        flight.stall_speed(craft.weight, craft.density, AREA, CLMAX))


def test_banking_raises_the_stall_speed_by_root_load_factor():
    level = _flying(bank=0.0)
    turning = _flying(bank=60.0)
    assert turning.load_factor == pytest.approx(2.0, rel=1e-6)
    assert turning.stall_banked / level.stall == pytest.approx(
        math.sqrt(2.0), rel=1e-6)


def test_glide_ratio_is_independent_of_weight():
    """It depends on L/D alone. Best glide SPEED does change with weight -
    that distinction is the whole point of the page."""
    light = _flying(craft=_craft(mass=2.0))
    heavy = _flying(craft=_craft(mass=4.0))
    assert light.glide_ratio == pytest.approx(heavy.glide_ratio)
    assert heavy.glide_speed > light.glide_speed


def test_flying_faster_than_best_ld_costs_efficiency():
    slow = _flying(speed=14.0)
    fast = _flying(speed=32.0)
    polar = _polar()
    assert slow.lift_to_drag <= polar.ld_max
    assert fast.lift_to_drag <= polar.ld_max


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------
def _checks(speed=22.0, stall_target=14.0, ld_target=6.0, craft=None):
    return {c["label"]: c for c in wing.verdicts(
        _flying(speed=speed, craft=craft), stall_target, ld_target)}


def test_a_reasonable_wing_passes():
    failed = [name for name, c in _checks().items() if not c["ok"]]
    assert failed == [], failed


def test_a_heavily_loaded_wing_fails_its_stall_target():
    checks = _checks(craft=_craft(mass=9.0), speed=30.0)
    assert not checks["Stall speed"]["ok"]


def test_flying_close_to_the_stall_fails_the_margin_check():
    checks = _checks(speed=13.0)
    failed = [name for name, c in checks.items() if not c["ok"]]
    assert failed, "flying just above the stall should not pass everything"


def test_the_studio_page_renders():
    at = goto("Studios")
    at.sidebar.radio[0].set_value("Wing study").run()
    assert not at.exception
