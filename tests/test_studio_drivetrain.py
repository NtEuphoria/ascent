"""The robot drivetrain studio.

The interesting behaviour is the traction ceiling: it is possible to gear a
robot for enormous wheel torque and have it go nowhere, because the floor only
accepts mu times the weight on the driven wheels however much torque arrives.
Most of these tests are about that cap holding.
"""
from __future__ import annotations

import math

import pytest

from conftest import goto
from studios import drivetrain as dt
from utils.constants import G0

BASE = dict(mass=20.0, motors=4, kv=380.0, stall_torque=0.7,
            stall_current=90.0, no_load_current=1.2, voltage=12.0,
            resistance=0.06, ratio=20.0, efficiency=0.80,
            wheel_diameter_m=0.10)


def _machine(mu=0.90, wheels=4, accel=1.5, slope=15.0, mass=20.0):
    return dt.robot(mass, wheels, mu, accel, slope)


# --------------------------------------------------------------------------
# What the floor allows
# --------------------------------------------------------------------------
def test_traction_is_mu_times_the_whole_weight():
    """Splitting the weight over more wheels does not create grip - each wheel
    carries less, and the total is unchanged."""
    four = _machine(wheels=4)
    two = _machine(wheels=2)
    assert four.traction_limit == pytest.approx(0.90 * 20.0 * G0)
    assert two.traction_limit == pytest.approx(four.traction_limit)


def test_a_slipperier_floor_gives_proportionally_less():
    dry = _machine(mu=0.90)
    wet = _machine(mu=0.60)
    assert wet.traction_limit / dry.traction_limit == pytest.approx(0.6 / 0.9)


def test_slope_force_is_weight_times_sine():
    assert _machine(slope=15.0).slope_force == pytest.approx(
        20.0 * G0 * math.sin(math.radians(15.0)))


def test_a_drivetrain_with_no_driven_wheels_is_refused():
    with pytest.raises(ValueError):
        dt.robot(20.0, 0, 0.9, 1.5, 15.0)


# --------------------------------------------------------------------------
# The traction ceiling
# --------------------------------------------------------------------------
def test_usable_force_is_capped_by_the_floor():
    """The whole point of the studio. 20:1 on these motors makes 896 N at the
    wheels and the floor accepts 177 N - the rest is wheelspin."""
    machine = _machine()
    result = dt.drivetrain(machine, **BASE)
    assert result.tractive_force > machine.traction_limit
    assert result.usable_force == pytest.approx(machine.traction_limit)


def test_gearing_down_further_buys_nothing_once_traction_limited():
    """The finding a torque-only calculator cannot give you."""
    machine = _machine()
    modest = dt.drivetrain(machine, **{**BASE, "ratio": 20.0})
    extreme = dt.drivetrain(machine, **{**BASE, "ratio": 60.0})
    assert extreme.tractive_force > modest.tractive_force
    assert extreme.usable_force == pytest.approx(modest.usable_force)
    assert extreme.acceleration == pytest.approx(modest.acceleration)
    # And it costs top speed, which is the trade being made.
    assert extreme.top_speed < modest.top_speed


def test_below_the_traction_limit_the_motors_set_the_force():
    machine = _machine()
    weak = dt.drivetrain(machine, **{**BASE, "ratio": 2.0})
    assert weak.tractive_force < machine.traction_limit
    assert weak.usable_force == pytest.approx(weak.tractive_force)


def test_acceleration_follows_the_usable_force_not_the_motor_force():
    machine = _machine()
    result = dt.drivetrain(machine, **BASE)
    assert result.acceleration == pytest.approx(
        result.usable_force / 20.0)


# --------------------------------------------------------------------------
# Speed and current
# --------------------------------------------------------------------------
def test_wheel_torque_is_motor_torque_through_the_reduction():
    machine = _machine()
    result = dt.drivetrain(machine, **BASE)
    assert result.wheel_torque == pytest.approx(0.7 * 20.0 * 0.80)


def test_top_speed_halves_when_the_reduction_doubles():
    machine = _machine()
    low = dt.drivetrain(machine, **{**BASE, "ratio": 20.0})
    high = dt.drivetrain(machine, **{**BASE, "ratio": 40.0})
    assert low.top_speed / high.top_speed == pytest.approx(2.0)


def test_free_speed_accounts_for_the_winding_drop():
    """Kv times voltage is the speed no motor reaches."""
    machine = _machine()
    ideal = dt.drivetrain(machine, **{**BASE, "resistance": 0.0})
    real = dt.drivetrain(machine, **BASE)
    assert real.top_speed < ideal.top_speed


def test_current_includes_the_no_load_draw():
    """A motor turning against nothing still pulls its no-load current."""
    machine = _machine()
    result = dt.drivetrain(machine, **BASE)
    assert result.current_per_motor > BASE["no_load_current"]


def test_gradeability_is_capped_at_vertical():
    """asin of anything past 1 has no answer; a robot that could out-pull its
    own weight is traction-limited long before it is torque-limited."""
    machine = _machine(mu=5.0)          # absurd grip, on purpose
    result = dt.drivetrain(machine, **{**BASE, "ratio": 60.0})
    assert result.gradeability_deg <= 90.0


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------
def _verdicts(**overrides):
    machine = _machine()
    result = dt.drivetrain(machine, **{**BASE, **overrides})
    return {v["label"]: v for v in dt.verdicts(
        machine, result, 2.0, 1.5, 15.0, BASE["stall_current"])}


def test_an_over_geared_robot_fails_traction_and_speed_together():
    checks = _verdicts(ratio=20.0)
    assert not checks["Traction"]["ok"]
    assert not checks["Top speed"]["ok"]
    assert checks["Acceleration"]["ok"]


def test_no_gearing_rescues_an_oversized_motor():
    """A finding the studio gives that a torque-only calculator cannot: four
    0.7 N·m motors are simply too much for a 20 kg robot on this floor. Gear
    it down and traction fails; gear it up and the motors cook. There is no
    ratio in between."""
    for ratio in (3.0, 4.0, 5.0, 8.0, 20.0):
        checks = _verdicts(ratio=ratio)
        assert [name for name, c in checks.items() if not c["ok"]], \
            f"ratio {ratio} unexpectedly passed everything"


def test_a_correctly_sized_motor_passes_everything():
    """Same robot, same floor, smaller motors - now every check clears."""
    machine = _machine()
    result = dt.drivetrain(machine, **{**BASE, "stall_torque": 0.35,
                                       "ratio": 4.0})
    checks = dt.verdicts(machine, result, 2.0, 1.5, 15.0, BASE["stall_current"])
    assert [c["label"] for c in checks if not c["ok"]] == []


def test_only_thirty_percent_of_stall_current_is_treated_as_continuous():
    """At stall a brushed motor turns every watt into winding heat."""
    assert dt.THERMAL_FRACTION == 0.30


def test_the_studio_page_renders():
    at = goto("Studios")
    at.sidebar.radio[0].set_value("Robot drivetrain").run()
    assert not at.exception
    text = " ".join(element.value for element in at.markdown)
    assert "Traction" in text
