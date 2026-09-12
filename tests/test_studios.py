"""The lift-and-arm studio.

A studio reimplements no physics - it chains the same hand-checked functions
the calculator pages use - so what these tests defend is the chaining: that the
quantities handed from one step to the next mean what the next step thinks they
mean, and that the verdicts change in the right direction.
"""
from __future__ import annotations

import math

import pytest

from studios import lift_arm
from studios.lift_arm import beam, drive, job, verdicts
from utils.constants import G0


# --------------------------------------------------------------------------
# The job
# --------------------------------------------------------------------------
def test_joint_torque_is_the_payload_plus_half_the_arm():
    """The arm's own weight acts at its midpoint, so the same mass at the tip
    would demand twice as much."""
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    assert work.load_torque == pytest.approx(2.0 * G0 * 0.6
                                             + 0.5 * G0 * 0.6 / 2.0)


def test_a_massless_arm_contributes_no_torque():
    assert job(2.0, 0.0, 0.6, 90.0, 1.2).load_torque == \
        pytest.approx(2.0 * G0 * 0.6)


def test_inertia_is_a_tip_mass_plus_a_rod_about_its_end():
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    assert work.load_inertia == pytest.approx(2.0 * 0.36 + 0.5 * 0.36 / 3.0)


def test_torque_grows_linearly_with_length_and_inertia_quadratically():
    """The reason a long arm is punishing twice over."""
    short = job(2.0, 0.0, 0.5, 90.0, 1.0)
    long = job(2.0, 0.0, 1.0, 90.0, 1.0)
    assert long.load_torque / short.load_torque == pytest.approx(2.0)
    assert long.load_inertia / short.load_inertia == pytest.approx(4.0)


def test_halving_the_move_time_quadruples_the_acceleration():
    slow = job(2.0, 0.5, 0.6, 90.0, 2.0)
    fast = job(2.0, 0.5, 0.6, 90.0, 1.0)
    assert fast.acceleration / slow.acceleration == pytest.approx(4.0)


def test_the_speed_profile_is_self_consistent():
    """Triangular profile: the area under it must be the sweep."""
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    swept = 0.5 * work.peak_speed * 1.2
    assert swept == pytest.approx(math.radians(90.0))


def test_a_zero_length_arm_is_refused_rather_than_dividing_by_zero():
    with pytest.raises(ValueError):
        job(2.0, 0.5, 0.0, 90.0, 1.2)
    with pytest.raises(ValueError):
        job(2.0, 0.5, 0.6, 90.0, 0.0)


# --------------------------------------------------------------------------
# The drive
# --------------------------------------------------------------------------
def test_motor_speed_is_the_joint_speed_through_the_ratio():
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    result = drive(work, 50.0, 0.85, 2e-5, 1.2, 8000.0)
    assert result.motor_speed_rpm == pytest.approx(
        work.peak_speed * 50.0 * 60.0 / (2.0 * math.pi))


def test_headroom_of_one_is_exactly_at_the_limit():
    """The number a reader has to be able to trust: below one it does not fit."""
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    result = drive(work, 50.0, 0.85, 2e-5, 1.2, 8000.0)
    needed_stall = result.motor_torque / lift_arm.TORQUE_MARGIN
    exact = drive(work, 50.0, 0.85, 2e-5, needed_stall, 8000.0)
    assert exact.torque_headroom == pytest.approx(1.0)


def test_only_half_of_stall_is_treated_as_usable():
    """A motor at stall is turning locked-rotor current into heat."""
    assert lift_arm.TORQUE_MARGIN == 0.5
    work = job(1.0, 0.0, 0.5, 90.0, 1.5)
    result = drive(work, 20.0, 0.9, 1e-5, 1.0, 6000.0)
    assert result.torque_headroom == pytest.approx(
        0.5 / result.motor_torque)


def test_a_bigger_reduction_trades_torque_for_speed():
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    low = drive(work, 20.0, 0.85, 2e-5, 1.2, 8000.0)
    high = drive(work, 100.0, 0.85, 2e-5, 1.2, 8000.0)
    assert high.motor_speed_rpm > low.motor_speed_rpm
    assert high.torque_headroom > low.torque_headroom


# --------------------------------------------------------------------------
# The arm
# --------------------------------------------------------------------------
def test_the_root_moment_is_the_joint_torque():
    """Same quantity, two names - gravity about the joint. If these ever
    disagreed the studio would be sizing the motor and the beam for different
    loads."""
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    result = beam(work, 2.0, 0.5, 0.6, "Hollow rectangle (box)", 30.0, 40.0,
                  2.0, 69e9, 276e6)
    from calculators import structures
    expected = structures.bending_stress(
        work.load_torque,
        structures.extreme_fibre("Hollow rectangle (box)", 0.030, 0.040, 0.002),
        result.second_moment)
    assert result.stress == pytest.approx(expected)


def test_standing_the_section_on_edge_stiffens_it():
    """Depth is cubed, so orientation matters more than material."""
    work = job(2.0, 0.0, 0.6, 90.0, 1.2)
    flat = beam(work, 2.0, 0.0, 0.6, "Solid rectangle", 40.0, 20.0, 0.0,
                69e9, 276e6)
    edge = beam(work, 2.0, 0.0, 0.6, "Solid rectangle", 20.0, 40.0, 0.0,
                69e9, 276e6)
    assert edge.deflection < flat.deflection
    assert flat.deflection / edge.deflection == pytest.approx(4.0, rel=1e-6)


def test_a_stiffer_material_does_not_change_the_stress():
    """Stress is geometry and load; only deflection cares about E. A common
    and expensive misunderstanding."""
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    args = (work, 2.0, 0.5, 0.6, "Hollow rectangle (box)", 30.0, 40.0, 2.0)
    aluminium = beam(*args, 69e9, 276e6)
    steel = beam(*args, 200e9, 276e6)
    assert steel.stress == pytest.approx(aluminium.stress)
    assert steel.deflection < aluminium.deflection


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------
def test_a_sensible_design_passes_everything():
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    result = verdicts(drive(work, 50.0, 0.85, 2e-5, 1.2, 8000.0),
                      beam(work, 2.0, 0.5, 0.6, "Hollow rectangle (box)",
                           30.0, 40.0, 2.0, 69e9, 276e6))
    assert all(check["ok"] for check in result)


def test_an_undersized_motor_fails_the_torque_check_only():
    work = job(2.0, 0.5, 0.6, 90.0, 1.2)
    result = verdicts(drive(work, 5.0, 0.85, 2e-5, 0.05, 8000.0),
                      beam(work, 2.0, 0.5, 0.6, "Hollow rectangle (box)",
                           30.0, 40.0, 2.0, 69e9, 276e6))
    failed = [check["label"] for check in result if not check["ok"]]
    assert "Motor torque" in failed
    assert "Arm stress" not in failed


def test_a_flimsy_arm_fails_on_stress_and_stiffness():
    work = job(8.0, 0.3, 1.2, 90.0, 1.0)
    result = verdicts(drive(work, 200.0, 0.85, 2e-5, 2.0, 12000.0),
                      beam(work, 8.0, 0.3, 1.2, "Solid circle", 6.0, 0.0, 0.0,
                           69e9, 276e6))
    failed = [check["label"] for check in result if not check["ok"]]
    assert "Arm stress" in failed and "Arm stiffness" in failed


def test_stress_is_judged_against_a_factor_of_safety_not_bare_yield():
    """Exactly at yield is a failure, not a pass."""
    work = job(2.0, 0.0, 0.6, 90.0, 1.2)
    result = beam(work, 2.0, 0.0, 0.6, "Solid circle", 12.0, 0.0, 0.0,
                  69e9, 276e6)
    at_yield = beam(work, 2.0, 0.0, 0.6, "Solid circle", 12.0, 0.0, 0.0,
                    69e9, result.stress)
    check = next(c for c in verdicts(
        drive(work, 50.0, 0.85, 2e-5, 1.2, 8000.0), at_yield)
        if c["label"] == "Arm stress")
    assert not check["ok"]


def test_the_studio_is_registered_in_its_own_section():
    import app
    assert "Studios" in app.MODES
    assert "Studios" in app.MODES["Studios"]
    slugs = {c.slug for c in app.CATEGORIES["Studios"]}
    assert "studio.lift_arm" in slugs
