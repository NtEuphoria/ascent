"""Robot drivetrain studio: will this thing actually move?

Four steps in the order a drivetrain is designed:

    the robot  ->  the motors  ->  the gearing  ->  a verdict

The check most drivetrain spreadsheets leave out is traction. It is easy to
gear a robot for enormous wheel torque and discover that the wheels simply
spin, because the floor can only accept mu times the weight on them however
much torque arrives. That limit is checked here first.

No physics is reimplemented. Motor behaviour comes from
calculators/propulsion.py, friction and gearing from calculators/mechanical.py,
wheel speed from calculators/robotics.py.
"""
from __future__ import annotations

import math
from typing import List, NamedTuple

import streamlit as st

from calculators import mechanical, propulsion, robotics
from studios import shell
from utils import ui
from utils.constants import G0
from utils.formatting import format_number
from utils.spec import Calculator

PREFIX = "studio_drivetrain"

SURFACES = {
    "Rubber on dry concrete": 0.90,
    "Rubber on wet concrete": 0.60,
    "Rubber on smooth vinyl": 0.70,
    "Plastic wheel on carpet": 0.55,
    "Plastic wheel on smooth floor": 0.30,
    "Steel wheel on steel": 0.20,
}
"""Static coefficients between a driven wheel and the floor. Ranges, not
constants: dust, polish and wheel wear move them more than the table suggests,
so design against the low end of whatever you expect."""

THERMAL_FRACTION = 0.30
"""Fraction of stall current treated as continuously sustainable. A brushed
motor at stall turns every watt into heat in the windings; a few seconds is
fine, a few minutes is a burnt motor."""


class Robot(NamedTuple):
    weight: float               # N
    normal_per_wheel: float     # N on each driven wheel
    traction_limit: float       # N, the most the floor will accept
    force_for_target: float     # N needed for the target acceleration
    slope_force: float          # N needed to hold the stated slope


def robot(mass: float, driven_wheels: int, mu: float, target_accel: float,
          slope_deg: float) -> Robot:
    """What the floor and the target demand, before any motor is chosen.

    Weight is assumed shared evenly over the driven wheels. A robot with
    undriven casters carrying part of its weight has less on the driven ones
    and correspondingly less traction, which is why that fraction is an input
    elsewhere in real designs.
    """
    if driven_wheels < 1:
        raise ValueError("A drivetrain needs at least one driven wheel.")
    weight = mass * G0
    normal = weight / driven_wheels
    # The whole robot's traction is the per-wheel friction times the wheels.
    traction = mechanical.friction_force(normal, mu) * driven_wheels
    return Robot(
        weight, normal, traction,
        mechanical.force(mass, target_accel),
        weight * math.sin(math.radians(slope_deg)))


class Drivetrain(NamedTuple):
    wheel_torque: float         # N*m at one wheel
    tractive_force: float       # N the motors can push with, ignoring the floor
    usable_force: float         # N after the floor has its say
    top_speed: float            # m/s at the free-running motor speed
    current_per_motor: float    # A to deliver the tractive force
    acceleration: float         # m/s^2 actually achievable
    gradeability_deg: float     # steepest slope it can hold


def drivetrain(machine: Robot, mass: float, motors: int, kv: float,
               stall_torque: float, stall_current: float, no_load_current: float,
               voltage: float, resistance: float, ratio: float,
               efficiency: float, wheel_diameter_m: float) -> Drivetrain:
    radius = wheel_diameter_m / 2.0
    # Torque at the wheel is the motor's, through the reduction, after losses.
    wheel_torque = stall_torque * ratio * efficiency
    tractive = wheel_torque * motors / radius
    usable = min(tractive, machine.traction_limit)

    free_rpm = propulsion.motor_speed_rpm(kv, voltage, no_load_current,
                                          resistance)
    top_speed = robotics.wheel_speed(free_rpm / ratio, radius)

    # Current to produce the force actually usable, back through the chain.
    per_motor_torque = (usable * radius / (motors * ratio * efficiency)
                        if motors and ratio and efficiency else 0.0)
    kt = propulsion.torque_constant(kv)
    current = per_motor_torque / kt + no_load_current if kt > 0 else 0.0

    acceleration = usable / mass if mass > 0 else 0.0
    # The steepest slope it can hold: sin(theta) = F/W, and beyond F = W there
    # is no angle - it could hold vertical, which means the limit is traction
    # rather than torque.
    ratio_to_weight = usable / machine.weight if machine.weight > 0 else 0.0
    gradeability = (math.degrees(math.asin(min(ratio_to_weight, 1.0)))
                    if ratio_to_weight > 0 else 0.0)

    return Drivetrain(wheel_torque, tractive, usable, top_speed, current,
                      acceleration, gradeability)


def verdicts(machine: Robot, result: Drivetrain, target_speed: float,
             target_accel: float, slope_deg: float,
             stall_current: float) -> List[dict]:
    thermal_limit = stall_current * THERMAL_FRACTION
    return [
        shell.check(
            "Top speed", result.top_speed >= target_speed,
            result.top_speed / target_speed if target_speed > 0 else float("inf"),
            f"reaches {format_number(result.top_speed, 3)} m/s against a "
            f"target of {format_number(target_speed, 3)}"),
        shell.check(
            "Traction", result.tractive_force <= machine.traction_limit,
            machine.traction_limit / result.tractive_force
            if result.tractive_force > 0 else float("inf"),
            f"motors push {format_number(result.tractive_force, 4)} N, the "
            f"floor accepts {format_number(machine.traction_limit, 4)} N "
            "before the wheels spin"),
        shell.check(
            "Acceleration", result.acceleration >= target_accel,
            result.acceleration / target_accel if target_accel > 0
            else float("inf"),
            f"manages {format_number(result.acceleration, 3)} m/s² against a "
            f"target of {format_number(target_accel, 3)}"),
        shell.check(
            "Slope", result.usable_force >= machine.slope_force,
            result.usable_force / machine.slope_force
            if machine.slope_force > 0 else float("inf"),
            f"holds up to {format_number(result.gradeability_deg, 3)}°, "
            f"asked for {format_number(slope_deg, 3)}°"),
        shell.check(
            "Motor current", result.current_per_motor <= thermal_limit,
            thermal_limit / result.current_per_motor
            if result.current_per_motor > 0 else float("inf"),
            f"draws {format_number(result.current_per_motor, 3)} A per motor "
            f"against {int(THERMAL_FRACTION * 100)}% of stall"),
    ]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def render(prefs=None, catalogue=None) -> None:
    prefs = prefs or {}
    ui.page_header(
        "Robot drivetrain",
        r"F_{\text{wheel}} = \frac{\tau_m N \eta}{r}, \qquad "
        r"F_{\text{traction}} = \mu m g",
        "Gear a robot to hit a target speed and acceleration, and find out "
        "whether the floor will let it. Torque at the wheel is the easy half; "
        "the half that decides whether the robot moves is how much of it the "
        "tyre can put down.",
        PREFIX)

    # -- 1 ------------------------------------------------------------------
    shell.step(1, "The robot", "Its mass, its wheels, and what you want of it.")
    a, b, c = st.columns(3)
    with a:
        mass = st.number_input("Mass [kg]", value=20.0, min_value=0.1,
                               step=1.0, key=f"{PREFIX}_mass")
        wheels = st.number_input("Driven wheels", value=4, min_value=1,
                                 max_value=12, step=1, key=f"{PREFIX}_wheels")
    with b:
        wheel_mm = st.number_input("Wheel diameter [mm]", value=100.0,
                                   min_value=5.0, step=5.0,
                                   key=f"{PREFIX}_wheel")
        surface = st.selectbox("Surface", list(SURFACES), key=f"{PREFIX}_surf")
    with c:
        target_speed = st.number_input("Target top speed [m/s]", value=2.0,
                                       min_value=0.01, step=0.1,
                                       key=f"{PREFIX}_vtarget")
        target_accel = st.number_input("Target acceleration [m/s²]", value=1.5,
                                       min_value=0.01, step=0.1,
                                       key=f"{PREFIX}_atarget")
    slope = st.slider("Steepest slope it must climb [deg]", 0.0, 45.0, 15.0,
                      0.5, key=f"{PREFIX}_slope")
    mu = SURFACES[surface]

    try:
        machine = robot(mass, int(wheels), mu, target_accel, slope)
    except ValueError as exc:
        st.error(str(exc))
        return

    shell.figures([("Weight", machine.weight, "N"),
                   ("On each driven wheel", machine.normal_per_wheel, "N"),
                   ("Traction available", machine.traction_limit, "N"),
                   ("Force to climb the slope", machine.slope_force, "N")])
    st.caption(f"{surface} is taken as μ = {mu:.2f}. Weight is assumed shared "
               "evenly over the driven wheels - undriven casters carrying part "
               "of it would leave less traction than this.")

    # -- 2 ------------------------------------------------------------------
    shell.step(2, "The motors", "What is turning the wheels.")
    d, e, f = st.columns(3)
    with d:
        motors = st.number_input("Motors", value=4, min_value=1, max_value=12,
                                 step=1, key=f"{PREFIX}_motors")
        kv = st.number_input("Kv [rpm/V]", value=380.0, min_value=1.0,
                             step=10.0, key=f"{PREFIX}_kv")
    with e:
        voltage = st.number_input("Supply voltage [V]", value=12.0,
                                  min_value=0.1, step=0.5,
                                  key=f"{PREFIX}_volts")
        stall_torque = st.number_input("Stall torque [N·m]", value=0.7,
                                       min_value=0.001, step=0.05,
                                       key=f"{PREFIX}_stall")
    with f:
        stall_current = st.number_input("Stall current [A]", value=90.0,
                                        min_value=0.1, step=5.0,
                                        key=f"{PREFIX}_istall")
        no_load = st.number_input("No-load current [A]", value=1.2,
                                  min_value=0.0, step=0.1,
                                  key=f"{PREFIX}_i0")
    resistance = st.number_input(
        "Winding resistance [Ω]", value=0.06, min_value=0.0, step=0.01,
        format="%.4g", key=f"{PREFIX}_res",
        help="Sets how far the speed droops under load. Without it, free "
             "speed would be Kv times voltage, which no motor achieves.")

    # -- 3 ------------------------------------------------------------------
    shell.step(3, "The gearing", "The number you actually get to choose.")
    g, h = st.columns(2)
    with g:
        ratio = st.number_input("Reduction ratio N : 1", value=20.0,
                                min_value=1.0, step=1.0, key=f"{PREFIX}_ratio")
    with h:
        efficiency = st.slider("Drivetrain efficiency", 0.3, 1.0, 0.80, 0.01,
                               key=f"{PREFIX}_eff")

    result = drivetrain(machine, mass, int(motors), kv, stall_torque,
                        stall_current, no_load, voltage, resistance, ratio,
                        efficiency, wheel_mm / 1000.0)

    shell.figures([("Torque at each wheel", result.wheel_torque, "N·m"),
                   ("Force the motors make", result.tractive_force, "N"),
                   ("Force the floor allows", result.usable_force, "N"),
                   ("Top speed", result.top_speed, "m/s")])
    shell.figures([("Acceleration", result.acceleration, "m/s²"),
                   ("Steepest slope held", result.gradeability_deg, "deg"),
                   ("Current per motor", result.current_per_motor, "A"),
                   ("Wheel speed at top", result.top_speed
                    / (wheel_mm / 2000.0) * 60.0 / (2.0 * math.pi), "rpm")])

    if result.tractive_force > machine.traction_limit:
        st.info(
            "The motors can push harder than the floor will accept, so the "
            f"usable force is capped at {format_number(machine.traction_limit, 4)} "
            "N and the rest turns into wheelspin. Gearing down further buys "
            "nothing here - more weight on the driven wheels, a grippier "
            "surface or more wheels would.")

    # -- 4 ------------------------------------------------------------------
    shell.step(4, "The verdict", "Whether it will do what you asked.")
    checks = verdicts(machine, result, target_speed, target_accel, slope,
                      stall_current)
    shell.verdict_board(checks)

    shell.send_to_project(PREFIX, [
        ("Robot mass", mass, "kg"),
        ("Wheel diameter", wheel_mm, "mm"),
        ("Drive ratio", ratio, "-"),
        ("Supply voltage", voltage, "V"),
    ], note="from the robot drivetrain studio")

    ui.assumptions([
        "Straight-line only. Nothing here describes turning, and a skid-steer "
        "robot turns by deliberately breaking the no-slip assumption this "
        "whole page rests on - its turning current draw is far higher than "
        "anything shown above.",
        "Weight is shared evenly over the driven wheels. Undriven casters, a "
        "high centre of mass, or weight transfer under acceleration all take "
        "load off a driven wheel and reduce traction below what is shown.",
        "The coefficient of friction is a single static number from the table. "
        "Real values move with dust, polish, wheel wear and temperature, so "
        "design against the low end of the range you expect rather than this.",
        "Tractive force is computed at stall torque, which a motor can deliver "
        "only momentarily. The current check is what keeps that honest, but it "
        "is a rule of thumb rather than a thermal model.",
        "Top speed is the free-running speed through the gearing, with no "
        "rolling resistance, no aerodynamic drag and no bearing losses. A real "
        "robot tops out below it.",
        "Efficiency is one number applied to torque. Backlash, preload and "
        "the sharp fall in gearbox efficiency at light load are all ignored.",
        "Nothing here checks whether the gearbox can take the torque, whether "
        "the wheels can take the load, or whether the battery can supply the "
        "current for as long as you need it.",
    ])


CALCULATORS = [
    Calculator(slug="studio.drivetrain", name="Robot drivetrain", latex="",
               explanation="", render=render,
               keywords=("studio", "drivetrain", "robot", "wheels", "traction",
                         "gearing", "gear ratio", "top speed", "motors",
                         "slip", "gradeability", "workflow")),
]
