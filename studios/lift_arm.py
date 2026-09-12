"""Lift and arm studio: size a mechanism that swings a payload.

Chains four disciplines that are separate pages elsewhere, in the order the
design actually happens:

    the job  ->  the drive  ->  the arm as a beam  ->  a verdict

Everything is computed by the existing verified functions - arm torque and
motor sizing from calculators/robotics.py, section properties and bending from
calculators/structures.py - so this page cannot drift away from what those
pages say.
"""
from __future__ import annotations

import math
from typing import Dict, List, NamedTuple

import streamlit as st

from calculators import robotics, structures
from utils import project as store
from utils import ui
from utils.constants import G0
from utils.formatting import format_number
from utils.spec import Calculator

PREFIX = "studio_liftarm"

MATERIALS = {
    "Aluminium 6061-T6": (69e9, 276e6),
    "Aluminium 7075-T6": (72e9, 503e6),
    "Steel, mild (A36)": (200e9, 250e6),
    "4130 steel, normalised": (205e9, 435e6),
    "Titanium 6Al-4V": (114e9, 880e6),
    "Carbon fibre (quasi-isotropic)": (70e9, 600e6),
}

DEFLECTION_LIMIT = 100.0
"""Tip deflection allowed, as a fraction of arm length (L/100). A common
workshop rule for a mechanism that has to repeat a position; a display arm can
be far floppier and a machine tool must be far stiffer."""

TORQUE_MARGIN = 0.5
"""Fraction of stall torque treated as usable. A brushed motor at stall is
drawing locked-rotor current and turning all of it into heat, so continuous
design sits well below it."""


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------
class Job(NamedTuple):
    load_torque: float          # N*m at the joint, worst case (arm horizontal)
    load_inertia: float         # kg*m^2 about the joint
    acceleration: float         # rad/s^2 demanded of the load
    peak_speed: float           # rad/s
    sweep: float                # rad


def job(payload_kg: float, arm_kg: float, length_m: float, sweep_deg: float,
        time_s: float) -> Job:
    """What the mechanism is being asked to do.

    Worst-case torque is with the arm horizontal, which is where gravity has
    the full moment arm. The payload acts at the tip and the arm's own weight
    at its midpoint, so the arm contributes half its mass at the same length.

    The move is taken as accelerate for half the time and decelerate for the
    other half - a triangular speed profile. That gives the highest
    acceleration any smooth profile of that duration needs, so sizing to it is
    conservative in the right direction.
    """
    payload_kg = max(float(payload_kg), 0.0)
    arm_kg = max(float(arm_kg), 0.0)
    length_m = float(length_m)
    time_s = float(time_s)
    if length_m <= 0:
        raise ValueError("Arm length must be greater than zero.")
    if time_s <= 0:
        raise ValueError("Move time must be greater than zero.")

    payload_torque = robotics.arm_holding_torque(payload_kg, length_m, 0.0) \
        if payload_kg > 0 else 0.0
    arm_torque = arm_kg * G0 * length_m / 2.0
    # Point mass at the tip, plus a uniform rod about its end.
    inertia = payload_kg * length_m ** 2 + arm_kg * length_m ** 2 / 3.0

    sweep = math.radians(float(sweep_deg))
    acceleration = 4.0 * abs(sweep) / time_s ** 2
    peak_speed = acceleration * time_s / 2.0
    return Job(payload_torque + arm_torque, inertia, acceleration, peak_speed,
               sweep)


# ---------------------------------------------------------------------------
# The drive
# ---------------------------------------------------------------------------
class Drive(NamedTuple):
    motor_torque: float         # N*m required at the motor
    motor_speed_rpm: float      # rpm required at the motor
    torque_headroom: float      # usable stall torque / required, 1.0 = exactly
    speed_headroom: float


def drive(work: Job, ratio: float, efficiency: float, motor_inertia: float,
          stall_torque: float, free_speed_rpm: float) -> Drive:
    required = robotics.motor_torque_required(
        work.load_torque, work.load_inertia, motor_inertia, ratio, efficiency,
        work.acceleration)
    speed_rpm = work.peak_speed * ratio * 60.0 / (2.0 * math.pi)
    usable = stall_torque * TORQUE_MARGIN
    return Drive(
        required, speed_rpm,
        usable / required if required > 0 else float("inf"),
        free_speed_rpm / speed_rpm if speed_rpm > 0 else float("inf"))


# ---------------------------------------------------------------------------
# The arm as a beam
# ---------------------------------------------------------------------------
class Beam(NamedTuple):
    second_moment: float
    stress: float               # Pa at the root
    deflection: float           # m at the tip
    stress_headroom: float      # yield / stress
    deflection_headroom: float  # limit / actual


def beam(work: Job, payload_kg: float, arm_kg: float, length_m: float,
         section: str, width_mm: float, depth_mm: float, wall_mm: float,
         modulus: float, yield_strength: float) -> Beam:
    width, depth, wall = width_mm / 1000.0, depth_mm / 1000.0, wall_mm / 1000.0
    second_moment = structures.second_moment_of_area(section, width, depth,
                                                     wall)
    extreme = structures.extreme_fibre(section, width, depth, wall)

    # The root moment is the same quantity as the holding torque: gravity on
    # the payload and on the arm's own mass, about the joint.
    moment = work.load_torque
    stress = structures.bending_stress(moment, extreme, second_moment)
    deflection = structures.beam_deflection(
        "Cantilever, point load at the end", payload_kg * G0, length_m,
        modulus, second_moment)
    deflection += structures.beam_deflection(
        "Cantilever, uniform load", arm_kg * G0 / length_m, length_m, modulus,
        second_moment)

    limit = length_m / DEFLECTION_LIMIT
    return Beam(second_moment, stress, deflection,
                yield_strength / stress if stress > 0 else float("inf"),
                limit / deflection if deflection > 0 else float("inf"))


def verdicts(drive_result: Drive, beam_result: Beam) -> List[Dict[str, object]]:
    """Every check this studio makes, with the margin that decided it."""
    return [
        {"label": "Motor torque",
         "ok": drive_result.torque_headroom >= 1.0,
         "margin": drive_result.torque_headroom,
         "detail": f"needs {format_number(drive_result.motor_torque, 3)} N·m "
                   f"against {int(TORQUE_MARGIN * 100)}% of stall"},
        {"label": "Motor speed",
         "ok": drive_result.speed_headroom >= 1.0,
         "margin": drive_result.speed_headroom,
         "detail": f"needs {format_number(drive_result.motor_speed_rpm, 4)} rpm"},
        {"label": "Arm stress",
         "ok": beam_result.stress_headroom >= 1.5,
         "margin": beam_result.stress_headroom,
         "detail": f"{format_number(beam_result.stress / 1e6, 3)} MPa at the "
                   f"root, wanted a factor of 1.5 on yield"},
        {"label": "Arm stiffness",
         "ok": beam_result.deflection_headroom >= 1.0,
         "margin": beam_result.deflection_headroom,
         "detail": f"tip drops {format_number(beam_result.deflection * 1000, 3)}"
                   f" mm, limit is L/{int(DEFLECTION_LIMIT)}"},
    ]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def _step(number: int, title: str, blurb: str) -> None:
    st.markdown(f'<div class="a-step"><span>{number}</span>'
                f'<div><b>{title}</b><i>{blurb}</i></div></div>',
                unsafe_allow_html=True)


def _figures(items) -> None:
    """A row of derived values, in the same treatment as a result card."""
    cells = "".join(
        f'<div><div class="a-sec-k">{label}</div>'
        f'<div class="a-sec-v">{format_number(value, 4)}'
        f'<span class="a-sec-u"> {unit}</span></div></div>'
        for label, value, unit in items)
    st.markdown(f'<div class="a-result"><div class="a-sec">{cells}</div></div>',
                unsafe_allow_html=True)


def render(prefs=None, catalogue=None) -> None:
    prefs = prefs or {}
    ui.page_header(
        "Lift and arm",
        r"\tau = g L\left(m_p + \tfrac{m_a}{2}\right), \qquad "
        r"\tau_m = \frac{\tau}{N\eta} + \left(J_m + \frac{J}{N^{2}}\right)N\alpha",
        "Size a mechanism that swings a payload: what the job demands, whether "
        "a motor and gearbox can deliver it, and whether the arm itself will "
        "survive being the thing that carries it. Every number comes from the "
        "same functions the individual calculator pages use.",
        PREFIX)

    # -- 1 ------------------------------------------------------------------
    _step(1, "The job", "What is being moved, how far, and how quickly.")
    a, b, c, d, e = st.columns(5)
    with a:
        payload = st.number_input("Payload [kg]", value=2.0, min_value=0.0,
                                  step=0.1, key=f"{PREFIX}_payload")
    with b:
        length = st.number_input("Arm length [m]", value=0.6, min_value=0.01,
                                 step=0.05, key=f"{PREFIX}_length")
    with c:
        arm_mass = st.number_input("Arm mass [kg]", value=0.5, min_value=0.0,
                                   step=0.1, key=f"{PREFIX}_armmass",
                                   help="Acts at its midpoint, so it "
                                        "contributes half as much torque as "
                                        "the same mass at the tip.")
    with d:
        sweep = st.number_input("Sweep [deg]", value=90.0, min_value=1.0,
                                max_value=180.0, step=5.0,
                                key=f"{PREFIX}_sweep")
    with e:
        move_time = st.number_input("Move time [s]", value=1.2, min_value=0.05,
                                    step=0.1, key=f"{PREFIX}_time")

    try:
        work = job(payload, arm_mass, length, sweep, move_time)
    except ValueError as exc:
        st.error(str(exc))
        return

    _figures([("Torque at the joint", work.load_torque, "N·m"),
              ("Load inertia", work.load_inertia, "kg·m²"),
              ("Angular acceleration", work.acceleration, "rad/s²"),
              ("Peak joint speed",
               work.peak_speed * 60.0 / (2.0 * math.pi), "rpm")])
    st.caption("Worst case is the arm horizontal, where gravity has the full "
               "moment arm. The move is taken as accelerating for half the "
               "time and decelerating for the other half, which is the most "
               "any smooth profile of that duration demands.")

    # -- 2 ------------------------------------------------------------------
    _step(2, "The drive", "A motor and a reduction that can deliver it.")
    f, g, h = st.columns(3)
    with f:
        ratio = st.number_input("Gear ratio N : 1", value=50.0, min_value=1.0,
                                step=1.0, key=f"{PREFIX}_ratio")
        efficiency = st.slider("Gearbox efficiency", 0.3, 1.0, 0.85, 0.01,
                               key=f"{PREFIX}_eff")
    with g:
        stall = st.number_input("Motor stall torque [N·m]", value=1.2,
                                min_value=0.001, step=0.1,
                                key=f"{PREFIX}_stall")
        free_speed = st.number_input("Motor free speed [rpm]", value=8000.0,
                                     min_value=1.0, step=100.0,
                                     key=f"{PREFIX}_free")
    with h:
        motor_inertia = st.number_input(
            "Motor rotor inertia [kg·m²]", value=2.0e-5, min_value=0.0,
            format="%.6g", step=1e-6, key=f"{PREFIX}_jm",
            help="From the motor's datasheet. It matters more than it looks: "
                 "the gearbox multiplies its effect by the ratio.")

    drive_result = drive(work, ratio, efficiency, motor_inertia, stall,
                         free_speed)
    _figures([("Motor torque needed", drive_result.motor_torque, "N·m"),
              ("Motor speed needed", drive_result.motor_speed_rpm, "rpm"),
              ("Torque headroom", drive_result.torque_headroom, "x"),
              ("Speed headroom", drive_result.speed_headroom, "x")])

    # -- 3 ------------------------------------------------------------------
    _step(3, "The arm", "The thing carrying the load has to survive it.")
    i, j_col, k, m = st.columns(4)
    with i:
        section = st.selectbox("Section", list(structures.SECTIONS),
                               index=3, key=f"{PREFIX}_section")
    with j_col:
        width = st.number_input("Width or diameter [mm]", value=30.0,
                                min_value=0.1, step=1.0, key=f"{PREFIX}_w")
    with k:
        depth = st.number_input("Depth [mm]", value=40.0, min_value=0.1,
                                step=1.0, key=f"{PREFIX}_d",
                                help="The dimension parallel to the load. "
                                     "Ignored for circular sections.")
    with m:
        wall = st.number_input("Wall [mm]", value=2.0, min_value=0.0, step=0.5,
                               key=f"{PREFIX}_t")
    material = st.selectbox("Material", list(MATERIALS), key=f"{PREFIX}_mat")
    modulus, yield_strength = MATERIALS[material]

    try:
        beam_result = beam(work, payload, arm_mass, length, section, width,
                           depth, wall, modulus, yield_strength)
    except Exception as exc:
        st.error(f"{exc}")
        return

    _figures([("Second moment I", beam_result.second_moment * 1e12, "mm⁴"),
              ("Stress at the root", beam_result.stress / 1e6, "MPa"),
              ("Tip deflection", beam_result.deflection * 1000.0, "mm"),
              ("Factor on yield", beam_result.stress_headroom, "x")])

    # -- 4 ------------------------------------------------------------------
    _step(4, "The verdict", "Whether what you described will actually work.")
    checks = verdicts(drive_result, beam_result)
    passing = sum(1 for check in checks if check["ok"])
    for check in checks:
        style = "a-ok" if check["ok"] else "a-bad"
        text = "Passes" if check["ok"] else "Fails"
        st.markdown(
            f'<div class="a-req"><span class="a-badge {style}">{text}</span>'
            f'<span class="a-req-label">{check["label"]}</span>'
            f'<span class="a-req-rule">{check["detail"]}  ·  '
            f'{format_number(check["margin"], 3)}x</span></div>',
            unsafe_allow_html=True)

    if passing == len(checks):
        st.success("Every check passes. The margins above are what you have "
                   "to spend on the things this studio does not model.")
    else:
        st.warning(f"{len(checks) - passing} of {len(checks)} checks fail. "
                   "The headroom figures say how far off each one is.")

    _to_project(payload, length, arm_mass, work)

    ui.assumptions([
        "Worst-case torque only - the arm horizontal, gravity at full moment "
        "arm. It is not a simulation of the move, so a mechanism that passes "
        "here can still fail on a transient this page does not model.",
        "The arm is treated as a cantilever of uniform section carrying a "
        "point load at the tip and its own weight spread along it. A real arm "
        "tapers, has joints and holes, and is weaker at every one of them.",
        "The payload is a point mass at the tip. A bulky payload adds its own "
        "inertia about its centre, which is not included.",
        "Static stress only. Nothing here checks fatigue, and an aluminium arm "
        "cycling millions of times has no endurance limit to hide behind.",
        "Motor torque and speed are checked separately. A real motor cannot "
        "deliver peak torque at peak speed - check both against its curve, not "
        "just its two end points.",
        "Gearbox efficiency is a single number applied to torque. Backlash, "
        "preload and the efficiency falling at low load are all ignored.",
        f"Stiffness is judged against L/{int(DEFLECTION_LIMIT)}, a workshop "
        "rule of thumb rather than a standard. Decide your own limit.",
    ])


def _to_project(payload: float, length: float, arm_mass: float,
                work: Job) -> None:
    """Push this studio's inputs into the project as shared parameters."""
    st.write("")
    with st.popover("Send to project", use_container_width=False):
        st.markdown('<div class="a-note">Adds these as shared parameters, so '
                    'the same payload and arm length drive every calculator '
                    'page you link them on.</div>', unsafe_allow_html=True)
        with st.form(f"{PREFIX}_toproject", border=False):
            source = st.selectbox("Mark them as", store.SOURCES, index=2)
            if st.form_submit_button("Add to project", type="primary"):
                project = store.load()
                for label, value, unit in (
                        ("Payload mass", payload, "kg"),
                        ("Arm length", length, "m"),
                        ("Arm mass", arm_mass, "kg"),
                        ("Joint torque", work.load_torque, "N·m")):
                    store.add_parameter(project, label, value, unit, source,
                                        "from the lift and arm studio")
                store.save(project)
                st.success("Added. Open Project to see where they are used.")


CALCULATORS = [
    Calculator(slug="studio.lift_arm", name="Lift and arm", latex="",
               explanation="", render=render,
               keywords=("studio", "arm", "lift", "gantry", "joint", "servo",
                         "gearbox", "payload", "mechanism", "workflow")),
]
