"""The control tuning studio."""
from __future__ import annotations

import pytest

from calculators import controls
from conftest import goto
from studios import control_tuning as ct


# --------------------------------------------------------------------------
# What the requirement implies
# --------------------------------------------------------------------------
def test_the_damping_comes_from_the_overshoot_limit():
    spec = ct.target(10.0, 0.8, 100.0)
    assert spec.damping == pytest.approx(controls.damping_for_overshoot(10.0))


def test_the_natural_frequency_hits_the_settling_target_exactly():
    """The inversion has to round-trip, or the page promises a settling time
    it does not deliver."""
    spec = ct.target(10.0, 0.8, 100.0)
    assert controls.settling_time(spec.natural_frequency,
                                  spec.damping) == pytest.approx(0.8, rel=1e-6)


def test_a_tighter_overshoot_limit_demands_more_damping():
    loose = ct.target(25.0, 0.8, 100.0)
    tight = ct.target(2.0, 0.8, 100.0)
    assert tight.damping > loose.damping


def test_a_faster_settling_target_demands_a_faster_loop():
    slow = ct.target(10.0, 2.0, 100.0)
    fast = ct.target(10.0, 0.2, 100.0)
    assert fast.natural_frequency > slow.natural_frequency
    assert fast.bandwidth_hz > slow.bandwidth_hz


# --------------------------------------------------------------------------
# The response it implies
# --------------------------------------------------------------------------
def test_the_overshoot_round_trips():
    """Ask for 10%, derive the damping, compute the overshoot back: 10%."""
    spec = ct.target(10.0, 0.8, 100.0)
    assert ct.shape(spec).overshoot == pytest.approx(10.0, rel=1e-6)


def test_the_metrics_match_the_calculator_page():
    spec = ct.target(10.0, 0.8, 100.0)
    shape = ct.shape(spec)
    wn, zeta = spec.natural_frequency, spec.damping
    assert shape.peak_time == pytest.approx(controls.peak_time(wn, zeta))
    assert shape.rise_time == pytest.approx(controls.rise_time(wn, zeta))
    assert shape.damped_frequency == pytest.approx(
        controls.damped_frequency(wn, zeta))


def test_less_damping_means_more_visible_ringing():
    bouncy = ct.shape(ct.target(40.0, 0.8, 100.0))
    calm = ct.shape(ct.target(2.0, 0.8, 100.0))
    assert bouncy.cycles > calm.cycles


# --------------------------------------------------------------------------
# Sampling - the check most tuning tools omit
# --------------------------------------------------------------------------
def test_the_sample_rate_is_compared_against_the_bandwidth():
    spec = ct.target(10.0, 0.8, 100.0)
    assert spec.sample_ratio == pytest.approx(100.0 / spec.bandwidth_hz)


def test_phase_lag_matches_the_calculator_page():
    spec = ct.target(10.0, 0.8, 100.0)
    assert spec.phase_lag == pytest.approx(
        controls.sampling_phase_lag(spec.bandwidth_hz, 100.0))


def test_a_slow_loop_gives_away_more_phase():
    """Why a design that simulated perfectly oscillates on real hardware."""
    quick = ct.target(10.0, 0.1, 1000.0)
    sluggish = ct.target(10.0, 0.1, 50.0)
    assert sluggish.phase_lag > quick.phase_lag
    assert sluggish.sample_ratio < quick.sample_ratio


def test_a_loop_sampled_too_slowly_fails_its_check():
    spec = ct.target(10.0, 0.05, 30.0)       # very fast target, slow loop
    result = ct.loop(1.0, 0.5, 0.05, 1.0, 0.5, 5.0, 1.0)
    labels = {c["label"]: c for c in ct.verdicts(spec, result, False)}
    sampling = next((c for name, c in labels.items()
                     if "ample" in name), None)
    assert sampling is not None and not sampling["ok"]


# --------------------------------------------------------------------------
# The simulated loop
# --------------------------------------------------------------------------
def test_the_simulation_reports_metrics_for_a_stable_loop():
    result = ct.loop(2.0, 1.0, 0.1, 1.0, 0.5, 10.0, 1.0)
    assert result.overshoot >= 0.0
    assert result.settling_time > 0.0


@pytest.mark.parametrize("kp", [0.5, 1.0, 2.0, 4.0, 8.0])
def test_proportional_control_leaves_an_offset_that_theory_predicts(kp):
    """A P-only loop never reaches the setpoint. The remaining error is
    setpoint / (1 + Kp*K), and more gain shrinks it without ever closing it -
    which is the reason integral action exists."""
    result = ct.loop(kp, 0.0, 0.0, 1.0, 0.5, 10.0, 1.0)
    assert result.offset == pytest.approx(1.0 / (1.0 + kp * 1.0), rel=1e-6)


def test_the_simulation_agrees_with_the_closed_form_offset():
    """The simulated steady state and the analytic one are derived
    independently; if they disagree one of them is wrong."""
    for kp in (0.5, 2.0, 8.0):
        result = ct.loop(kp, 0.0, 0.0, 1.0, 0.5, 20.0, 1.0)
        assert result.final_error == pytest.approx(result.offset, rel=1e-3)


def test_integral_action_removes_the_offset():
    proportional = ct.loop(1.0, 0.0, 0.0, 1.0, 0.5, 10.0, 1.0)
    with_integral = ct.loop(1.0, 1.0, 0.0, 1.0, 0.5, 10.0, 1.0)
    assert with_integral.final_error < proportional.final_error / 100.0


# --------------------------------------------------------------------------
# Safety content
# --------------------------------------------------------------------------
def test_the_page_warns_about_finding_the_ultimate_gain():
    """Ziegler-Nichols requires driving a real plant into sustained
    oscillation. That must never be presented as a routine step."""
    source = open(ct.__file__, encoding="utf-8").read().lower()
    assert "oscillat" in source
    assert "detun" in source or "aggressive" in source
    assert "starting point" in source


def test_the_studio_page_renders():
    at = goto("Studios")
    at.sidebar.radio[0].set_value("Control tuning").run()
    assert not at.exception
