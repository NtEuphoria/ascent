"""The live page's own display logic.

These are the pieces that turn a stream of numbers into something readable,
and they are the pieces most able to lie: an arrow pointing the wrong way or a
sparkline drawn from a divide-by-zero is worse than showing neither.
"""
from __future__ import annotations

import math

from calculators.live import _readout, _sparkline, _trend


# --------------------------------------------------------------------------
# Trend direction
# --------------------------------------------------------------------------
def test_a_rising_channel_points_up():
    assert _trend([float(i) for i in range(40)]) == "up"


def test_a_falling_channel_points_down():
    assert _trend([float(40 - i) for i in range(40)]) == "down"


def test_a_flat_channel_gets_no_arrow():
    assert _trend([5.0] * 40) == ""


def test_noise_alone_does_not_produce_an_arrow():
    """The reason this compares averaged ends rather than the last two
    samples: at 20 Hz, consecutive samples differ by noise, and an arrow
    driven by that flickers several times a second while meaning nothing."""
    assert _trend([5.0 + 0.4 * math.sin(i) for i in range(40)]) == ""


def test_a_trend_is_still_found_underneath_noise():
    assert _trend([i * 0.5 + 3.0 * math.sin(i) for i in range(40)]) == "up"


def test_too_little_history_gets_no_arrow():
    """Better to show nothing than to call a direction from three samples."""
    assert _trend([1.0, 2.0]) == ""
    assert _trend([1.0, 2.0, 3.0, 4.0]) == ""


def test_the_arrow_agrees_with_the_range_shown_beside_it():
    """They are read together, so they must not disagree."""
    series = [16.8 - 0.03 * i for i in range(60)]
    assert _trend(series) == "down"
    assert series[-1] == min(series)


# --------------------------------------------------------------------------
# Sparkline
# --------------------------------------------------------------------------
def test_a_sparkline_has_one_point_per_sample():
    svg = _sparkline([float(i) for i in range(10)])
    assert svg.count(",") == 10


def test_a_flat_channel_draws_a_flat_line_rather_than_dividing_by_zero():
    """A constant channel is real data - a sensor that has settled - not an
    error state, and it must not blank the trace."""
    svg = _sparkline([5.0] * 8)
    assert "<polyline" in svg
    heights = {point.split(",")[1] for point in
               svg.split('points="')[1].split('"')[0].split(" ")}
    assert len(heights) == 1        # every point at the same height


def test_a_sparkline_needs_at_least_two_points():
    assert _sparkline([1.0]) == ""
    assert _sparkline([]) == ""


def test_the_trace_stays_inside_its_box():
    svg = _sparkline([0.0, 100.0, 50.0, -20.0], width=100, height=26)
    points = svg.split('points="')[1].split('"')[0].split(" ")
    for point in points:
        x, y = (float(n) for n in point.split(","))
        assert 0.0 <= x <= 100.0
        assert 0.0 <= y <= 26.0


# --------------------------------------------------------------------------
# The readout as a whole
# --------------------------------------------------------------------------
def test_a_readout_carries_the_name_value_trace_and_range():
    html = _readout("voltage", 16.05, [16.8 - 0.03 * i for i in range(60)])
    assert "voltage" in html
    assert "16.05" in html
    assert "a-spark" in html
    assert "a-live-down" in html
    assert " to " in html          # the min-to-max range


def test_a_readout_with_no_history_still_shows_its_value():
    """The first sample must render, not wait for a second one."""
    html = _readout("voltage", 16.05, [16.05])
    assert "16.05" in html and "a-live-trend" not in html
