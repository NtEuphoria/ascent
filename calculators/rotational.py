"""Rotational mechanics.

Every moment-of-inertia formula here has the form I = k * m * d², so the shapes
are stored as a coefficient plus the dimension the coefficient applies to. That
keeps the formula, its axis and its coefficient together in one place - add a new
shape by adding one row to MOI_SHAPES.
"""
from __future__ import annotations

from collections import OrderedDict

import numpy as np
import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import A_SL, G0
from utils.plotting import PRIMARY, mark_point, new_figure, show

# ---------------------------------------------------------------------------
# Moment-of-inertia shape library
# ---------------------------------------------------------------------------

MOI_SHAPES = OrderedDict([
    ("Point mass at distance r from the axis", {
        "coefficient": 1.0,
        "dimension": ("Distance from axis r", "m", 0.25),
        "latex": r"I = m\,r^{2}",
        "axis": "Any axis at distance r from the mass.",
    }),
    ("Thin hoop or ring, about its central axis", {
        "coefficient": 1.0,
        "dimension": ("Radius r", "m", 0.25),
        "latex": r"I = m\,r^{2}",
        "axis": "Central axis, perpendicular to the plane of the hoop. All the "
                "mass sits at radius r, so it matches the point-mass formula.",
    }),
    ("Solid disk, about its central axis", {
        "coefficient": 0.5,
        "dimension": ("Radius r", "m", 0.25),
        "latex": r"I = \tfrac{1}{2}\,m\,r^{2}",
        "axis": "Central axis, perpendicular to the face of the disk.",
    }),
    ("Solid cylinder, about its central (long) axis", {
        "coefficient": 0.5,
        "dimension": ("Radius r", "m", 0.25),
        "latex": r"I = \tfrac{1}{2}\,m\,r^{2}",
        "axis": "The long axis of the cylinder. Identical to the solid disk: "
                "length does not appear, because every slice is the same disk.",
    }),
    ("Solid sphere, about a diameter", {
        "coefficient": 0.4,
        "dimension": ("Radius r", "m", 0.25),
        "latex": r"I = \tfrac{2}{5}\,m\,r^{2}",
        "axis": "Any axis through the centre.",
    }),
    ("Thin rod, about its centre", {
        "coefficient": 1.0 / 12.0,
        "dimension": ("Rod length L", "m", 0.5),
        "latex": r"I = \tfrac{1}{12}\,m\,L^{2}",
        "axis": "Perpendicular to the rod, through its midpoint.",
    }),
    ("Thin rod, about one end", {
        "coefficient": 1.0 / 3.0,
        "dimension": ("Rod length L", "m", 0.5),
        "latex": r"I = \tfrac{1}{3}\,m\,L^{2}",
        "axis": "Perpendicular to the rod, through one end. Four times the "
                "centre value - moving the axis outward costs a lot.",
    }),
])

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def rpm_to_rad_s(rpm: float) -> float:
    """ω = RPM * 2*π / 60   [rad/s]"""
    rpm = v.finite(rpm, "Rotational speed", "rpm")
    return rpm * 2.0 * np.pi / 60.0


def rad_s_to_rpm(omega: float) -> float:
    """RPM = ω * 60 / (2*π)"""
    omega = v.finite(omega, "Angular velocity", "rad/s")
    return omega * 60.0 / (2.0 * np.pi)


def rotational_power(torque_nm: float, omega: float) -> float:
    """P = τ * ω   [W]  (ω must be in rad/s, not rpm)"""
    torque_nm = v.finite(torque_nm, "Torque", "N·m")
    omega = v.finite(omega, "Angular velocity", "rad/s")
    return torque_nm * omega


def centripetal_force(mass: float, velocity: float, radius: float) -> float:
    """Fc = m * v² / r   [N], directed toward the centre of the circle."""
    mass = v.positive(mass, "Mass", "kg")
    velocity = v.finite(velocity, "Tangential velocity", "m/s")
    radius = v.positive(radius, "Radius", "m")
    return mass * velocity ** 2 / radius


def moment_of_inertia(shape: str, mass: float, dimension: float) -> float:
    """I = k * m * d²   [kg·m²], with k and d set by the chosen shape."""
    if shape not in MOI_SHAPES:
        raise v.ValidationError(f"Unknown shape: {shape}")
    mass = v.positive(mass, "Mass", "kg")
    dimension = v.non_negative(dimension, "Dimension", "m")
    return MOI_SHAPES[shape]["coefficient"] * mass * dimension ** 2


def rotational_kinetic_energy(inertia: float, omega: float) -> float:
    """KE_rot = 0.5 * I * ω^2   [J]"""
    inertia = v.non_negative(inertia, "Moment of inertia", "kg·m²")
    omega = v.finite(omega, "Angular velocity", "rad/s")
    return 0.5 * inertia * omega ** 2


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def render_angular_velocity() -> None:
    p = "rot_omega"
    ui.page_header(
        "Angular velocity from RPM",
        r"\omega = \frac{2\pi\,n}{60}",
        "Motors are specified in RPM, but every rotational equation needs radians "
        "per second. One revolution is 2*π radians and one minute is 60 seconds, "
        "so the conversion factor is 2*π/60, about 0.1047.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        rpm = ui.number("Rotational speed n", "rpm", f"{p}_rpm", 8000.0)
    with c2:
        radius = ui.number("Radius (optional, for tip speed)", "m", f"{p}_r", 0.127,
                           min_value=0.0,
                           help="Propeller radius: a 10-inch prop has a 5-inch "
                                "(0.127 m) radius.")

    value = ui.compute(lambda: rpm_to_rad_s(rpm))
    if value is not None:
        tip_speed = value * radius
        ui.result(
            "Angular velocity ω", value, "rad/s",
            secondary=[
                ("Revolutions per second", rpm / 60.0, "rev/s"),
                ("Time for one revolution", 60.0 / rpm if rpm != 0
                 else float("nan"), "s"),
                ("Tip speed at this radius", tip_speed, "m/s"),
                ("Tip Mach number (ISA sea level)", tip_speed / A_SL, "-"),
            ],
        )
        if tip_speed / A_SL > 0.7:
            st.caption("Tip Mach above about 0.7 causes a sharp rise in noise and "
                       "a loss of propeller efficiency as compressibility sets in.")
    ui.assumptions([
        "An exact unit conversion, not an approximation.",
        "Tip speed v = ω × r is the rotational component only; in forward "
        "flight the advancing blade sees the vehicle's airspeed on top of it.",
        "Tip Mach number uses the ISA sea-level speed of sound, 340.29 m/s. It is "
        "lower in cold air, so the same RPM is closer to the limit at altitude.",
    ])
    ui.reference(
        variables=[
            ("$\\omega$", "Angular velocity", "rad/s"),
            ("$n$", "Rotational speed", "rpm"),
            ("$r$", "Radius", "m"),
        ],
        example="Propeller design check. A 10x4.5 prop at 8000 rpm has a tip speed "
                "of 106 m/s, Mach 0.31 - comfortable. Spin the same prop at 20,000 "
                "rpm and the tip reaches Mach 0.78, where it gets loud and "
                "inefficient.",
    )


def render_rotational_power() -> None:
    p = "rot_power"
    ui.page_header(
        "Rotational power",
        r"P = \tau\,\omega = \frac{2\pi\,n\,\tau}{60}",
        "The rotating equivalent of P = F × v. This is the bridge between a "
        "motor's torque curve and the power it actually delivers - and it is why "
        "a motor that makes good torque at low RPM can still be low-powered.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        torque_nm = ui.number("Torque τ", "N·m", f"{p}_tq", 0.35)
    with c2:
        rpm = ui.number("Rotational speed n", "rpm", f"{p}_rpm", 8000.0)

    omega = ui.compute(lambda: rpm_to_rad_s(rpm))
    value = None if omega is None else ui.compute(
        lambda: rotational_power(torque_nm, omega))
    if value is not None:
        ui.result(
            "Mechanical power P", value, "W",
            secondary=[
                ("Angular velocity", omega, "rad/s"),
                ("In horsepower (mechanical)", value / 745.6998715822702, "hp"),
                ("Torque in kgf·cm", torque_nm / G0 * 100.0, "kgf·cm"),
            ],
        )
    ui.assumptions([
        "ω must be in rad/s. Using RPM directly here is a very common error "
        "and gives an answer 9.55 times too large - the conversion is done for you.",
        "This is shaft power out of the motor, before gearbox and propeller "
        "losses.",
        "Torque and speed are taken at the same operating point. A motor's torque "
        "falls as speed rises, so you cannot combine peak torque with peak RPM.",
    ])

    if ui.graph_toggle(p):
        speeds = np.linspace(0.0, max(rpm * 1.6, 1000.0), 200)
        fig, (ax,) = new_figure()
        ax.plot(speeds, torque_nm * speeds * 2.0 * np.pi / 60.0, color=PRIMARY,
                linewidth=2)
        mark_point(ax, rpm, torque_nm * rpm_to_rad_s(rpm), "current")
        ax.set_xlabel("Rotational speed [rpm]")
        ax.set_ylabel("Power [W]")
        ax.set_title("Power vs speed at constant torque", fontsize=10, loc="left")
        show(fig)

    ui.reference(
        variables=[
            ("$P$", "Mechanical (shaft) power", "W"),
            ("$\\tau$", "Torque", "N·m"),
            ("$\\omega$", "Angular velocity", "rad/s"),
            ("$n$", "Rotational speed", "rpm"),
        ],
        example="Motor selection for a drone. A motor holding 0.35 N·m at 8000 rpm "
                "delivers 293 W of shaft power. If the ESC draws 400 W electrical "
                "at that point, the motor is running at about 73% efficiency.",
    )


def render_centripetal() -> None:
    p = "rot_fc"
    ui.page_header(
        "Centripetal force",
        r"F_c = \frac{m\,v^{2}}{r} = m\,\omega^{2} r",
        "The inward force needed to keep something moving in a circle. It does not "
        "push outward - the outward feeling is inertia. This is what holds a "
        "propeller blade onto its hub and what the wing supplies in a banked turn.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        mass = ui.number("Mass m", "kg", f"{p}_m", 0.01, min_value=0.0,
                         help="For a propeller blade, use the blade's own mass.")
    with c2:
        velocity = ui.number("Tangential velocity v", "m/s", f"{p}_v", 106.0)
    with c3:
        radius = ui.number("Radius r", "m", f"{p}_r", 0.127, min_value=0.0)

    value = ui.compute(lambda: centripetal_force(mass, velocity, radius))
    if value is not None:
        accel = velocity ** 2 / radius if radius > 0 else float("nan")
        ui.result(
            "Centripetal force F_c", value, "N",
            secondary=[
                ("Centripetal acceleration", accel, "m/s²"),
                ("As a multiple of gravity", accel / G0, "g"),
                ("Angular velocity", velocity / radius if radius > 0
                 else float("nan"), "rad/s"),
                ("Equivalent rotational speed", rad_s_to_rpm(velocity / radius)
                 if radius > 0 else float("nan"), "rpm"),
            ],
        )
    ui.assumptions([
        "Uniform circular motion at constant speed and constant radius.",
        "The mass is treated as concentrated at radius r. For a real propeller "
        "blade the mass is distributed, so use the radius of its centre of mass.",
        "F_c points toward the centre. There is no outward 'centrifugal force' in "
        "an inertial frame - only the inertia of the mass.",
    ])
    ui.reference(
        variables=[
            ("$F_c$", "Centripetal force", "N"),
            ("$m$", "Mass in circular motion", "kg"),
            ("$v$", "Tangential speed", "m/s"),
            ("$r$", "Radius of the circular path", "m"),
            ("$\\omega$", "Angular velocity", "rad/s"),
        ],
        example="Propeller hub loads. A 10 g blade section whose centre of mass "
                "sits at 0.127 m, moving at 106 m/s, pulls 885 N on the hub - about "
                "9000 times its own weight. That is why propeller root failures are "
                "so violent, and why cracked props must never be flown.",
    )


def render_moment_of_inertia() -> None:
    p = "rot_moi"
    shapes = list(MOI_SHAPES.keys())
    # Read the selection before drawing the header so the title and equation
    # match the shape the user picked on the previous run.
    shape = st.session_state.get(f"{p}_shape", shapes[0])
    spec = MOI_SHAPES[shape]
    ui.page_header(
        f"Moment of inertia - {shape[0].lower() + shape[1:]}",
        spec["latex"],
        "Moment of inertia is rotational inertia: how hard it is to change a "
        "body's spin. It depends on where the mass sits, not just how much there "
        f"is. <b>Axis used here:</b> {spec['axis']}",
        p,
    )
    dim_label, dim_unit, dim_default = spec["dimension"]
    shape = st.selectbox("Shape and axis", shapes, key=f"{p}_shape")
    spec = MOI_SHAPES[shape]
    dim_label, dim_unit, dim_default = spec["dimension"]
    c1, c2, c3 = st.columns(3)
    with c1:
        mass = ui.number("Mass m", "kg", f"{p}_m", 0.05, min_value=0.0)
    with c2:
        dimension = ui.number(dim_label, dim_unit, f"{p}_d", dim_default,
                              min_value=0.0)
    with c3:
        rpm = ui.number("Rotational speed (optional)", "rpm", f"{p}_rpm", 8000.0)

    value = ui.compute(lambda: moment_of_inertia(shape, mass, dimension))
    if value is not None:
        omega = rpm_to_rad_s(rpm)
        ui.result(
            "Moment of inertia I", value, "kg·m²",
            secondary=[
                ("Coefficient used", spec["coefficient"], "x m d²"),
                ("Rotational kinetic energy at this speed",
                 rotational_kinetic_energy(value, omega), "J"),
                ("Angular momentum L = I ω", value * omega, "kg·m²/s"),
                ("Torque to spin it up to this speed in 0.5 s",
                 value * omega / 0.5, "N·m"),
            ],
        )
    ui.assumptions([
        f"Formula in use: I = {spec['coefficient']:.4g} × m × d², where d is "
        f"the '{dim_label}' input above.",
        "Uniform density and an idealised shape. A real propeller, wheel or rotor "
        "is none of these - measure or CAD it if the number matters structurally.",
        "The axis matters as much as the shape. Move the axis and the answer "
        "changes (parallel-axis theorem: I_new = I_centre + m d²).",
        "'Thin' rod and hoop mean the cross-section is small compared with the "
        "length or radius.",
    ])
    ui.reference(
        variables=[
            ("$I$", "Moment of inertia about the stated axis", "kg·m²"),
            ("$m$", "Mass", "kg"),
            ("$r$", "Radius", "m"),
            ("$L$", "Length", "m"),
            ("$\\omega$", "Angular velocity", "rad/s"),
        ],
        example="Reaction-wheel sizing for a satellite or a balancing robot. A "
                "50 g, 50 mm-radius solid disk has I = 6.25e-5 kg·m². Spinning it "
                "to 8000 rpm stores 21.9 J and 0.052 kg·m²/s of angular "
                "momentum - the budget available for attitude control.",
    )


def render_rotational_ke() -> None:
    p = "rot_ke"
    ui.page_header(
        "Rotational kinetic energy",
        r"KE_{rot} = \tfrac{1}{2}\,I\,\omega^{2}",
        "The rotating twin of 0.5 m v². Angular velocity is squared, so a "
        "flywheel or rotor at high RPM stores a surprising amount of energy - "
        "which is exactly why a spinning rotor is dangerous even when small.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        inertia = ui.number("Moment of inertia I", "kg·m²", f"{p}_i", 6.25e-5,
                            min_value=0.0,
                            help="Use the moment-of-inertia page to work this out.")
    with c2:
        rpm = ui.number("Rotational speed", "rpm", f"{p}_rpm", 8000.0)

    omega = ui.compute(lambda: rpm_to_rad_s(rpm))
    value = None if omega is None else ui.compute(
        lambda: rotational_kinetic_energy(inertia, omega))
    if value is not None:
        ui.result(
            "Rotational kinetic energy", value, "J",
            secondary=[
                ("Angular velocity", omega, "rad/s"),
                ("Angular momentum", inertia * omega, "kg·m²/s"),
                ("Braking torque to stop it in 0.5 s",
                 inertia * omega / 0.5, "N·m"),
                ("Energy at twice the speed", value * 4.0, "J"),
            ],
        )
    ui.assumptions([
        "I must be taken about the actual axis of rotation.",
        "Rigid body: no flexing, no mass moving relative to the body.",
        "This is rotational energy only. A wheel that is also travelling has "
        "translational kinetic energy on top of this.",
        "The braking-torque figure assumes constant torque over the stopping time.",
    ])
    ui.reference(
        variables=[
            ("$KE_{rot}$", "Rotational kinetic energy", "J"),
            ("$I$", "Moment of inertia", "kg·m²"),
            ("$\\omega$", "Angular velocity", "rad/s"),
        ],
        example="Motor braking and flywheel storage. Stopping a spinning propeller "
                "means dumping this energy somewhere - into the ESC as heat, or "
                "back into the battery through regenerative braking. It is also "
                "the figure behind flywheel energy-storage systems.",
    )


CALCULATORS = {
    "Angular velocity (RPM to rad/s)": render_angular_velocity,
    "Rotational power": render_rotational_power,
    "Centripetal force": render_centripetal,
    "Moment of inertia": render_moment_of_inertia,
    "Rotational kinetic energy": render_rotational_ke,
}
