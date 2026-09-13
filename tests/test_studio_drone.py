"""The drone powertrain studio.

This is the one with a direct commercial competitor, so the numbers have to be
defensible. Expected values here are derived from momentum theory and Ohm's
law directly, not read back out of the studio.
"""
from __future__ import annotations

import math

import pytest

from conftest import goto
from studios import drone_powertrain as dp
from utils.constants import G0

RHO = 1.225


def _craft(mass=1.5, rotors=4, inches=10.0):
    return dp.aircraft(mass, rotors, inches, RHO)


def _drive(craft=None, rotors=4, fom=0.62, eff=0.80, rpm=7000.0, gf=900.0):
    return dp.powertrain(craft or _craft(), rotors, fom, eff, rpm, gf, RHO)


# --------------------------------------------------------------------------
# Momentum theory
# --------------------------------------------------------------------------
def test_disk_area_is_from_the_rotor_diameter_in_inches():
    craft = _craft(inches=10.0)
    assert craft.radius == pytest.approx(10.0 * 0.0254 / 2)
    assert craft.area == pytest.approx(math.pi * craft.radius ** 2)


def test_each_rotor_carries_an_equal_share_of_the_weight():
    craft = _craft(mass=1.5, rotors=4)
    assert craft.thrust_per_rotor == pytest.approx(1.5 * G0 / 4)


def test_induced_velocity_is_the_momentum_theory_result():
    craft = _craft()
    assert craft.induced_velocity == pytest.approx(
        math.sqrt(craft.thrust_per_rotor / (2 * RHO * craft.area)))


def test_ideal_power_is_the_total_over_all_rotors():
    """Not per rotor. The figure of merit divides into this total, so if it
    were per-rotor the shaft power would be out by the rotor count."""
    craft = _craft(rotors=4)
    assert craft.ideal_power == pytest.approx(
        4 * craft.thrust_per_rotor * craft.induced_velocity)


def test_bigger_rotors_hover_on_less_power():
    """The most important fact in multirotor design, and the reason a big slow
    prop beats a small fast one."""
    small = _craft(inches=8.0)
    big = _craft(inches=12.0)
    assert big.ideal_power < small.ideal_power
    assert big.disk_loading < small.disk_loading


def test_ideal_power_scales_as_thrust_to_the_three_halves():
    """Ten percent more mass costs about fifteen percent more power."""
    light = _craft(mass=1.0)
    heavy = _craft(mass=1.1)
    assert heavy.ideal_power / light.ideal_power == pytest.approx(
        1.1 ** 1.5, rel=1e-6)


# --------------------------------------------------------------------------
# Powertrain
# --------------------------------------------------------------------------
def test_figure_of_merit_and_efficiency_both_divide_into_the_power():
    craft = _craft()
    drive = _drive(craft, fom=0.62, eff=0.80)
    assert drive.shaft_power == pytest.approx(craft.ideal_power / 0.62)
    assert drive.electrical_power == pytest.approx(drive.shaft_power / 0.80)


def test_tip_mach_uses_the_rotor_tip_speed():
    drive = _drive(rpm=7000.0)
    craft = _craft()
    tip = 2 * math.pi * craft.radius * 7000.0 / 60.0
    assert drive.tip_speed == pytest.approx(tip)
    assert drive.tip_mach == pytest.approx(tip / 340.29, rel=1e-3)


def test_thrust_to_weight_comes_from_the_motors_rated_thrust():
    craft = _craft(mass=1.5, rotors=4)
    drive = _drive(craft, gf=900.0)
    assert drive.thrust_to_weight == pytest.approx(
        (900.0 * 4 * 0.00980665) / craft.weight, rel=1e-4)


# --------------------------------------------------------------------------
# Battery
# --------------------------------------------------------------------------
def test_the_pack_current_accounts_for_its_own_sag():
    """The ESC holds power, so a sagged pack is asked for more current, which
    sags it further. Dividing power by the resting voltage under-reads."""
    drive = _drive()
    pack = dp.battery(drive, 4, 3.7, 5.0, 3.0, 0.80)
    naive = drive.electrical_power / (4 * 3.7)
    assert pack.hover_current > naive
    # And the power balance closes at the sagged voltage.
    assert pack.hover_current * pack.loaded_voltage == pytest.approx(
        drive.electrical_power, rel=1e-3)


def test_pack_energy_and_resistance_are_the_obvious_products():
    drive = _drive()
    pack = dp.battery(drive, 4, 3.7, 5.0, 3.0, 0.80)
    assert pack.pack_voltage == pytest.approx(4 * 3.7)
    assert pack.energy_wh == pytest.approx(4 * 3.7 * 5.0)
    assert pack.resistance == pytest.approx(4 * 0.003)


def test_c_rate_is_current_as_a_multiple_of_capacity():
    drive = _drive()
    pack = dp.battery(drive, 4, 3.7, 5.0, 3.0, 0.80)
    assert pack.c_rate == pytest.approx(pack.hover_current / 5.0)


def test_a_higher_resistance_pack_sags_further_and_flies_less():
    drive = _drive()
    good = dp.battery(drive, 4, 3.7, 5.0, 2.0, 0.80)
    tired = dp.battery(drive, 4, 3.7, 5.0, 12.0, 0.80)
    assert tired.sag > good.sag
    assert tired.loaded_cell_voltage < good.loaded_cell_voltage
    assert tired.endurance < good.endurance


def test_only_the_usable_fraction_of_the_pack_is_flown():
    drive = _drive()
    full = dp.battery(drive, 4, 3.7, 5.0, 3.0, 1.0)
    safe = dp.battery(drive, 4, 3.7, 5.0, 3.0, 0.80)
    assert safe.endurance == pytest.approx(full.endurance * 0.8, rel=1e-6)


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------
def _checks(**kw):
    craft = _craft(**{k: v for k, v in kw.items() if k in ("mass", "inches")})
    drive = _drive(craft, gf=kw.get("gf", 900.0))
    pack = dp.battery(drive, 4, 3.7, kw.get("ah", 5.0), 3.0, 0.80)
    return {c["label"]: c for c in dp.verdicts(
        craft, drive, pack, kw.get("target", 12.0), kw.get("c_rating", 25.0))}


def test_a_sensible_quad_passes_its_checks():
    failed = [name for name, c in _checks().items() if not c["ok"]]
    assert failed == [], failed


def test_a_barely_lifting_quad_fails_thrust_to_weight():
    """Below about 2:1 a multirotor has no authority left to manoeuvre with."""
    checks = _checks(gf=400.0)
    assert not checks["Thrust-to-weight"]["ok"]


def test_a_small_pack_fails_endurance():
    checks = _checks(ah=1.0)
    assert not checks["Hover endurance"]["ok"]


def test_the_studio_page_renders():
    at = goto("Studios")
    at.sidebar.radio[0].set_value("Drone powertrain").run()
    assert not at.exception
