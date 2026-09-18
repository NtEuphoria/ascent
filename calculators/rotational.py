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
from utils.spec import (Calculator, Check, Field, Output, Secondary,
                        Sweep)

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




# ---------------------------------------------------------------------------
# Declarative pages
#
# Moment of inertia keeps render= above: its shape picker rewrites the equation,
# the dimension's label and its unit as you choose, which is genuinely
# imperative. The four below are plain equations and get the renderer's
# influence table, uncertainty propagation, project binding and sweeps.
# ---------------------------------------------------------------------------

ANGULAR_VELOCITY = Calculator(
    slug="rotational_mechanics.angular_velocity_(rpm_to_rad/s)",
    name="Angular velocity (RPM to rad/s)",
    latex=r"\omega = \frac{2\pi\,n}{60}",
    explanation=(
        "Motors are specified in RPM, but every rotational equation needs "
        "radians per second. One revolution is 2*π radians and one minute is 60 "
        "seconds, so the conversion factor is 2*π/60, about 0.1047."
    ),
    inputs=[
        Field("rpm", "Rotational speed n", "rpm", 8000.0),
        Field("radius", "Radius (optional, for tip speed)", "m", 0.127, min=0.0,
              help="Propeller radius: a 10-inch prop has a 5-inch (0.127 m) "
                   "radius. It does not affect ω itself, only the tip figures."),
    ],
    compute=lambda i: rpm_to_rad_s(i.rpm),
    result=Output("Angular velocity ω", "rad/s"),
    secondary=[
        Secondary("Revolutions per second", "rev/s", lambda i, r: i.rpm / 60.0),
        Secondary("Time for one revolution", "s",
                  lambda i, r: 60.0 / i.rpm if i.rpm else float("nan")),
        Secondary("Tip speed at this radius", "m/s", lambda i, r: r * i.radius),
        Secondary("Tip Mach number (ISA sea level)", "-",
                  lambda i, r: r * i.radius / A_SL),
    ],
    assumptions=[
        "An exact unit conversion, not an approximation.",
        "Tip speed v = ω × r is the rotational component only; in forward "
        "flight the advancing blade sees the vehicle's airspeed on top of it.",
        "Tip Mach number uses the ISA sea-level speed of sound, 340.29 m/s. It is "
        "lower in cold air, so the same RPM is closer to the limit at altitude.",
        "Radius changes none of the tip figures' parent quantity: ω depends only "
        "on RPM, which is why the influence table shows radius as having no "
        "effect on the headline number.",
    ],
    variables=[
        ("$\\omega$", "Angular velocity", "rad/s"),
        ("$n$", "Rotational speed", "rpm"),
        ("$r$", "Radius", "m"),
    ],
    example="Propeller design check. A 10x4.5 prop at 8000 rpm has a tip speed "
            "of 106 m/s, Mach 0.31 - comfortable. Spin the same prop at 20,000 "
            "rpm and the tip reaches Mach 0.78, where it gets loud and "
            "inefficient.",
    checks=[
        Check(lambda i, r: ("warning",
                            "Tip Mach %.2f. Above about 0.7 compressibility sets "
                            "in: noise rises sharply and propeller efficiency "
                            "falls away." % (r * i.radius / A_SL))
              if i.radius > 0 and r * i.radius / A_SL > 0.7 else None),
    ],
    related=["rotational_mechanics.rotational_power",
             "rotational_mechanics.centripetal_force",
             "rotational_mechanics.rotational_kinetic_energy"],
    keywords=("rpm", "omega", "rad/s", "tip speed", "mach", "conversion"),
)


ROTATIONAL_POWER = Calculator(
    slug="rotational_mechanics.rotational_power",
    name="Rotational power",
    latex=r"P = \tau\,\omega = \frac{2\pi\,n\,\tau}{60}",
    explanation=(
        "The rotating equivalent of P = F × v. This is the bridge between a "
        "motor's torque curve and the power it actually delivers - and it is why "
        "a motor that makes good torque at low RPM can still be low-powered."
    ),
    inputs=[
        Field("torque_nm", "Torque τ", "N·m", 0.35),
        Field("rpm", "Rotational speed n", "rpm", 8000.0),
    ],
    compute=lambda i: rotational_power(i.torque_nm, rpm_to_rad_s(i.rpm)),
    result=Output("Mechanical power P", "W"),
    secondary=[
        Secondary("Angular velocity", "rad/s", lambda i, r: rpm_to_rad_s(i.rpm)),
        Secondary("In horsepower (mechanical)", "hp",
                  lambda i, r: r / 745.6998715822702),
        Secondary("Torque in kgf·cm", "kgf·cm",
                  lambda i, r: i.torque_nm / G0 * 100.0),
    ],
    assumptions=[
        "ω must be in rad/s. Using RPM directly here is a very common error "
        "and gives an answer 9.55 times too large - the conversion is done for "
        "you.",
        "This is shaft power out of the motor, before gearbox and propeller "
        "losses.",
        "Torque and speed are taken at the same operating point. A motor's torque "
        "falls as speed rises, so you cannot combine peak torque with peak RPM.",
    ],
    variables=[
        ("$P$", "Mechanical (shaft) power", "W"),
        ("$\\tau$", "Torque", "N·m"),
        ("$\\omega$", "Angular velocity", "rad/s"),
        ("$n$", "Rotational speed", "rpm"),
    ],
    example="Motor selection for a drone. A motor holding 0.35 N·m at 8000 rpm "
            "delivers 293 W of shaft power. If the ESC draws 400 W electrical "
            "at that point, the motor is running at about 73% efficiency.",
    graphs=[
        Sweep(over="rpm", y_label="Power P [W]",
              title="Power vs speed at constant torque", hi_factor=1.6),
    ],
    related=["mech.torque", "mech.power", "elec.power",
             "rotational_mechanics.angular_velocity_(rpm_to_rad/s)"],
    keywords=("shaft power", "torque", "watts", "horsepower", "motor"),
)


CENTRIPETAL_FORCE = Calculator(
    slug="rotational_mechanics.centripetal_force",
    name="Centripetal force",
    latex=r"F_c = \frac{m\,v^{2}}{r} = m\,\omega^{2} r",
    explanation=(
        "The inward force needed to keep something moving in a circle. It does "
        "not push outward - the outward feeling is inertia. This is what holds a "
        "propeller blade onto its hub and what the wing supplies in a banked turn."
    ),
    inputs=[
        Field("mass", "Mass m", "kg", 0.01, min=0.0,
              help="For a propeller blade, use the blade's own mass."),
        Field("velocity", "Tangential velocity v", "m/s", 106.0),
        Field("radius", "Radius r", "m", 0.127, min=0.0),
    ],
    compute=lambda i: centripetal_force(i.mass, i.velocity, i.radius),
    result=Output("Centripetal force F_c", "N"),
    secondary=[
        Secondary("Centripetal acceleration", "m/s²",
                  lambda i, r: i.velocity ** 2 / i.radius),
        Secondary("As a multiple of gravity", "g",
                  lambda i, r: i.velocity ** 2 / i.radius / G0),
        Secondary("Angular velocity", "rad/s",
                  lambda i, r: i.velocity / i.radius),
        Secondary("Equivalent rotational speed", "rpm",
                  lambda i, r: rad_s_to_rpm(i.velocity / i.radius)),
        Secondary("As a multiple of the mass's own weight", "-",
                  lambda i, r: r / (i.mass * G0)),
    ],
    assumptions=[
        "Uniform circular motion at constant speed and constant radius.",
        "The mass is treated as concentrated at radius r. For a real propeller "
        "blade the mass is distributed, so use the radius of its centre of mass.",
        "F_c points toward the centre. There is no outward 'centrifugal force' in "
        "an inertial frame - only the inertia of the mass.",
    ],
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
    graphs=[
        Sweep(over="velocity", y_label="Centripetal force F_c [N]",
              title="Force rises with the square of speed", hi_factor=1.6),
    ],
    checks=[
        Check(lambda i, r: ("info",
                            "That is %.0f times the mass's own weight. Rotating "
                            "parts routinely see loads like this, which is why "
                            "hub and root joints are sized by centripetal load "
                            "rather than by aerodynamic load."
                            % (r / (i.mass * G0)))
              if i.mass > 0 and r / (i.mass * G0) > 1000.0 else None),
    ],
    related=["rotational_mechanics.angular_velocity_(rpm_to_rad/s)",
             "rotational_mechanics.moment_of_inertia", "mech.force"],
    keywords=("centripetal", "circular", "hub", "blade", "g-force", "rotor"),
)


ROTATIONAL_KE = Calculator(
    slug="rotational_mechanics.rotational_kinetic_energy",
    name="Rotational kinetic energy",
    latex=r"KE_{rot} = \tfrac{1}{2}\,I\,\omega^{2}",
    explanation=(
        "The rotating twin of 0.5 m v². Angular velocity is squared, so a "
        "flywheel or rotor at high RPM stores a surprising amount of energy - "
        "which is exactly why a spinning rotor is dangerous even when small."
    ),
    inputs=[
        Field("inertia", "Moment of inertia I", "kg·m²", 6.25e-5, min=0.0,
              help="Use the moment-of-inertia page to work this out."),
        Field("rpm", "Rotational speed", "rpm", 8000.0),
    ],
    compute=lambda i: rotational_kinetic_energy(i.inertia, rpm_to_rad_s(i.rpm)),
    result=Output("Rotational kinetic energy", "J"),
    secondary=[
        Secondary("Angular velocity", "rad/s", lambda i, r: rpm_to_rad_s(i.rpm)),
        Secondary("Angular momentum", "kg·m²/s",
                  lambda i, r: i.inertia * rpm_to_rad_s(i.rpm)),
        Secondary("Braking torque to stop it in 0.5 s", "N·m",
                  lambda i, r: i.inertia * rpm_to_rad_s(i.rpm) / 0.5),
        Secondary("Energy at twice the speed", "J", lambda i, r: r * 4.0),
    ],
    assumptions=[
        "I must be taken about the actual axis of rotation.",
        "Rigid body: no flexing, no mass moving relative to the body.",
        "This is rotational energy only. A wheel that is also travelling has "
        "translational kinetic energy on top of this.",
        "The braking-torque figure assumes constant torque over the stopping "
        "time.",
    ],
    variables=[
        ("$KE_{rot}$", "Rotational kinetic energy", "J"),
        ("$I$", "Moment of inertia", "kg·m²"),
        ("$\\omega$", "Angular velocity", "rad/s"),
    ],
    example="Motor braking and flywheel storage. Stopping a spinning propeller "
            "means dumping this energy somewhere - into the ESC as heat, or "
            "back into the battery through regenerative braking. It is also "
            "the figure behind flywheel energy-storage systems.",
    graphs=[
        Sweep(over="rpm", y_label="Rotational kinetic energy [J]",
              title="Energy rises with the square of speed", hi_factor=1.8),
    ],
    related=["rotational_mechanics.moment_of_inertia", "mech.kinetic_energy",
             "rotational_mechanics.rotational_power"],
    keywords=("flywheel", "rotor", "energy", "angular momentum", "braking"),
)


MOMENT_OF_INERTIA = Calculator(
    slug="rotational_mechanics.moment_of_inertia",
    name="Moment of inertia",
    latex="", explanation="",
    render=render_moment_of_inertia,
    keywords=("I", "inertia", "shapes", "flywheel", "disc", "rod", "sphere"),
)


CALCULATORS = [
    ANGULAR_VELOCITY,
    ROTATIONAL_POWER,
    CENTRIPETAL_FORCE,
    MOMENT_OF_INERTIA,
    ROTATIONAL_KE,
]
