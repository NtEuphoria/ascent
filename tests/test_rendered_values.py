"""End-to-end value tests: render every page and check the headline number.

The unit tests in test_calculations.py prove the physics functions are right.
These prove the *pages* are wired to them correctly - that a calculator's spec
points at the right compute function with the right inputs in the right order.

A wrong lambda, a swapped field, or a mis-typed default would pass every unit
test and still show a wrong number. This catches that.

Baselines were hand-verified against v1.0.0 before the declarative refactor.
"""
import os
import re
import sys

import pytest

from conftest import goto

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


APP_PATH = os.path.join(ROOT, "app.py")

# Couples to the result-card markup in utils/ui.py. If that changes, update
# this one line rather than loosening the assertions.
RESULT_PATTERN = (r'a-result-label">(.*?)</div><div class="a-result-value">(.*?)'
                  r'<span class="a-result-unit">(.*?)</span>')

# category -> {calculator name: (displayed value, unit)} at default inputs
BASELINES = {
    "Aerodynamics": {
        "Lift": ("12,403", "N"),
        "Drag": ("793.8", "N"),
        "Dynamic pressure": ("1,531", "Pa"),
        "Lift-to-drag ratio": ("15.62", "-"),
        "Wing loading": ("726.4", "N/m²"),
        "Aspect ratio": ("7.334", "-"),
        "Reynolds number": ("427,963", "-"),
    },
    "Flight performance": {
        "Thrust-to-weight ratio": ("1.36", "-"),
        "Power-to-weight ratio": ("600", "W/kg"),
        "Stall speed": ("15.08", "m/s"),
        "Rate of climb": ("4.861", "m/s"),
        "Glide performance": ("15,000", "m"),
    },
    "Drones": {
        "Total thrust": ("47.07", "N"),
        "Thrust-to-weight ratio": ("2.4", "-"),
        "Hover thrust per motor": ("4.903", "N"),
        "Flight time (estimate)": ("9.6", "minutes"),
        "Electrical power": ("1,332", "W"),
        "Battery energy": ("111", "Wh"),
    },
    "Propulsion": {
        "Momentum theory (hover)": ("30.78", "W"),
        "Hover power & endurance": ("280.1", "W"),
        "Motor constants (Kv, Kt, back-EMF)": ("0.2003", "N·m"),
        "Rocket equation": ("3,542", "m/s"),
    },
    "Mechanical": {
        "Force (F = ma)": ("19.61", "N"),
        "Torque": ("10", "N·m"),
        "Work": ("150", "J"),
        "Power": ("200", "W"),
        "Linear momentum": ("30", "kg·m/s"),
        "Kinetic energy": ("225", "J"),
        "Potential energy": ("1,961", "J"),
        "Mechanical advantage": ("5", "-"),
        "Gear ratio": ("5", ": 1"),
    },
    "Rotational mechanics": {
        "Angular velocity (RPM to rad/s)": ("837.8", "rad/s"),
        "Rotational power": ("293.2", "W"),
        "Centripetal force": ("884.7", "N"),
        "Moment of inertia": ("0.003125", "kg·m²"),
        "Rotational kinetic energy": ("21.93", "J"),
    },
    "Structures": {
        "Second moment of area": ("1.067e-07", "m⁴"),
        "Beam bending": ("100", "MPa"),
        "Elastic constants (E, ν, G, K)": ("25.94", "GPa"),
    },
    "Materials": {
        "Normal stress": ("63.66", "MPa"),
        "Strain": ("0.0012", "-"),
        "Young's modulus": ("69.85", "GPa"),
        # Only baselined once the page became declarative: its result label
        # used to carry the chosen strength basis, so it changed with a radio.
        "Factor of safety": ("4.333", "-"),
        "Density": ("2,700", "kg/m³"),
        "Specific strength": ("102.2", "kN·m/kg"),
    },
    "Robotics": {
        "Differential drive kinematics": ("0.6283", "m/s"),
        "Gear train: reflected inertia": ("0.2652", "N·m"),
        "Servo / arm holding torque": ("0.7355", "N·m"),
        "Encoder resolution": ("0.018", "°"),
    },
    "Electrical / robotics": {
        "Resistors in series": ("600", "Ω"),
        "Resistors in parallel": ("54.55", "Ω"),
        "Battery energy": ("74", "Wh"),
    },
    "Control systems": {
        "Control error": ("8", "units"),
        "Second-order step response": ("16.3", "%"),
        "Ziegler–Nichols tuning": ("4.8", "-"),
    },
    "Unit converter": {
        "Length": ("3.28084", "ft"),
        "Velocity": ("3.6", "km/h"),
        "Mass": ("2.20462", "lb"),
        "Force": ("0.224809", "lbf"),
        "Pressure": ("145.038", "psi"),
        "Energy": ("3,600", "J"),
        "Power": ("0.001341", "hp"),
        "Temperature": ("288.15", "K"),
    },
    "Constants / reference": {
        "Standard atmosphere (ISA)": ("1.225", "kg/m³"),
    },
}


def _headline(at):
    html = " ".join(block.value for block in at.markdown)
    match = re.search(RESULT_PATTERN, html)
    return (match.group(2), match.group(3)) if match else (None, None)


@pytest.mark.parametrize("category", list(BASELINES.keys()))
def test_headline_values_unchanged(category):
    at = goto(category)

    for name, (expected_value, expected_unit) in BASELINES[category].items():
        at.sidebar.radio[0].set_value(name).run()
        assert not at.exception, f"{category} / {name} raised"
        value, unit = _headline(at)
        assert value == expected_value, (
            f"{category} / {name}: showed {value!r}, expected {expected_value!r}")
        assert unit == expected_unit, (
            f"{category} / {name}: unit {unit!r}, expected {expected_unit!r}")
