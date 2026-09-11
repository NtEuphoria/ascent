"""Core mechanical-engineering equations."""
from __future__ import annotations

import numpy as np
import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import G0
from utils.plotting import PRIMARY, mark_point, new_figure, show

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def force(mass: float, acceleration: float) -> float:
    """F = m * a   [N]. Acceleration may be negative (deceleration)."""
    mass = v.positive(mass, "Mass", "kg")
    acceleration = v.finite(acceleration, "Acceleration", "m/s²")
    return mass * acceleration


def torque(radius: float, force_n: float, angle_deg: float = 90.0) -> float:
    """τ = r * F * sin(θ)   [N·m]

    θ is the angle between the lever arm and the force. At 90 degrees
    (the usual case) sin(θ) = 1 and this reduces to τ = r F.
    """
    radius = v.non_negative(radius, "Lever arm", "m")
    force_n = v.finite(force_n, "Force", "N")
    angle_deg = v.in_range(angle_deg, "Angle", 0.0, 180.0, "°")
    return radius * force_n * float(np.sin(np.radians(angle_deg)))


def work(force_n: float, distance: float, angle_deg: float = 0.0) -> float:
    """W = F * d * cos(θ)   [J]

    θ is the angle between the force and the direction of motion. Force
    perpendicular to motion (90 degrees) does no work.
    """
    force_n = v.finite(force_n, "Force", "N")
    distance = v.non_negative(distance, "Distance", "m")
    angle_deg = v.in_range(angle_deg, "Angle", 0.0, 180.0, "°")
    return force_n * distance * float(np.cos(np.radians(angle_deg)))


def power(work_j: float, time_s: float) -> float:
    """P = W / t   [W]"""
    work_j = v.finite(work_j, "Work", "J")
    time_s = v.positive(time_s, "Time", "s")
    return work_j / time_s


def momentum(mass: float, velocity: float) -> float:
    """p = m * v   [kg·m/s]. Velocity is signed: direction matters."""
    mass = v.positive(mass, "Mass", "kg")
    velocity = v.finite(velocity, "Velocity", "m/s")
    return mass * velocity


def kinetic_energy(mass: float, velocity: float) -> float:
    """KE = 0.5 * m * v²   [J]"""
    mass = v.positive(mass, "Mass", "kg")
    velocity = v.finite(velocity, "Velocity", "m/s")
    return 0.5 * mass * velocity ** 2


def potential_energy(mass: float, height: float, gravity: float = G0) -> float:
    """PE = m * g * h   [J], relative to the chosen reference height."""
    mass = v.positive(mass, "Mass", "kg")
    height = v.finite(height, "Height", "m")
    gravity = v.non_negative(gravity, "Gravitational acceleration", "m/s²")
    return mass * gravity * height


def mechanical_advantage(output_force: float, input_force: float) -> float:
    """MA = F_out / F_in   [-]"""
    output_force = v.finite(output_force, "Output force", "N")
    input_force = v.positive(input_force, "Input force", "N")
    return output_force / input_force


def gear_ratio(driven_teeth: int, driving_teeth: int) -> float:
    """Gear ratio = driven teeth / driving teeth   [-]

    Greater than 1 is a reduction: slower output, more torque.
    """
    driven_teeth = v.positive_int(driven_teeth, "Driven gear teeth")
    driving_teeth = v.positive_int(driving_teeth, "Driving gear teeth")
    return driven_teeth / driving_teeth


def output_rpm(input_rpm: float, ratio: float) -> float:
    """Output RPM = input RPM / gear ratio"""
    input_rpm = v.finite(input_rpm, "Input speed", "rpm")
    ratio = v.positive(ratio, "Gear ratio")
    return input_rpm / ratio


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def render_force() -> None:
    p = "mech_force"
    ui.page_header(
        "Newton's second law",
        r"F = m\,a",
        "The force needed to accelerate a mass. Everything in dynamics starts "
        "here: a control surface, a landing-gear strut and a robot arm are all "
        "sized by the accelerations they must produce or survive.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        mass = ui.number("Mass m", "kg", f"{p}_m", 2.0, min_value=0.0)
    with c2:
        accel = ui.number("Acceleration a", "m/s²", f"{p}_a", 9.80665,
                          help="Negative values mean deceleration.")

    value = ui.compute(lambda: force(mass, accel))
    if value is not None:
        ui.result(
            "Force F", value, "N",
            secondary=[
                ("As a multiple of the object's weight", accel / G0, "g"),
                ("Weight of this mass on Earth", mass * G0, "N"),
                ("In pound-force", value * 0.224808943, "lbf"),
            ],
        )
    ui.assumptions([
        "Mass is constant. A rocket burning propellant loses mass, which needs "
        "the full momentum form of the law instead.",
        "F is the NET force - the vector sum of everything acting on the body.",
        "Inertial (non-rotating, non-accelerating) reference frame.",
        "Weight is a specific case of this law: a = g, so W = m g.",
    ])
    ui.reference(
        variables=[
            ("$F$", "Net force", "N"),
            ("$m$", "Mass", "kg"),
            ("$a$", "Acceleration", "m/s²"),
        ],
        example="Sizing a robot-arm actuator. Moving a 2 kg gripper at 5 m/s² "
                "needs 10 N of net force - plus whatever it takes to hold the "
                "gripper's 19.6 N weight against gravity if the motion is vertical.",
    )


def render_torque() -> None:
    p = "mech_torque"
    ui.page_header(
        "Torque",
        r"\tau = r\,F\,\sin\theta",
        "Torque is the turning effect of a force: how hard you push, times how far "
        "from the pivot you push. Only the component perpendicular to the lever "
        "arm turns anything, which is what the sine term accounts for.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        radius = ui.number("Lever arm r", "m", f"{p}_r", 0.25, min_value=0.0)
    with c2:
        force_n = ui.number("Force F", "N", f"{p}_f", 40.0)
    with c3:
        angle = ui.number("Angle between r and F", "°", f"{p}_ang", 90.0,
                          min_value=0.0, max_value=180.0,
                          help="90 degrees is the usual case and gives the maximum "
                               "torque for a given force.")

    value = ui.compute(lambda: torque(radius, force_n, angle))
    if value is not None:
        ui.result(
            "Torque τ", value, "N·m",
            secondary=[
                ("Effective (perpendicular) force", force_n * float(
                    np.sin(np.radians(angle))), "N"),
                ("In kgf·cm (servo datasheet units)",
                 value / G0 * 100.0, "kgf·cm"),
                ("In pound-feet", value * 0.737562, "lbf·ft"),
            ],
        )
    ui.assumptions([
        "r is measured from the axis of rotation to the point where the force is "
        "applied, in a straight line.",
        "Torque is a vector; this gives its magnitude about the chosen axis.",
        "Static or quasi-static case. Accelerating a rotating body also needs "
        "τ = I × α (see Rotational mechanics).",
        "Servo and gearmotor datasheets usually quote torque in kgf·cm - that is a "
        "force times a distance, converted above.",
    ])

    if ui.graph_toggle(p):
        radii = np.linspace(0.0, max(radius * 2.0, 0.1), 200)
        fig, (ax,) = new_figure()
        ax.plot(radii, radii * force_n * float(np.sin(np.radians(angle))),
                color=PRIMARY, linewidth=2)
        mark_point(ax, radius, torque(radius, force_n, angle), "current")
        ax.set_xlabel("Lever arm r [m]")
        ax.set_ylabel("Torque [N·m]")
        ax.set_title("Torque vs lever-arm length (linear at constant force)",
                     fontsize=10, loc="left")
        show(fig)

    ui.reference(
        variables=[
            ("$\\tau$", "Torque about the axis", "N·m"),
            ("$r$", "Lever arm (perpendicular distance to the axis)", "m"),
            ("$F$", "Applied force", "N"),
            ("$\\theta$", "Angle between the lever arm and the force", "°"),
        ],
        example="Choosing a servo for a control surface. If the hinge moment is "
                "0.8 N·m and the horn is 15 mm from the hinge line, the pushrod "
                "must pull 53 N - and the servo must make 0.8 N·m, about 8 kgf·cm, "
                "with margin on top.",
    )


def render_work() -> None:
    p = "mech_work"
    ui.page_header(
        "Work",
        r"W = F\,d\,\cos\theta",
        "Work is energy transferred by a force acting through a distance. A force "
        "at right angles to the motion does no work at all - which is why carrying "
        "a box across a level floor does no work on the box, however tiring.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        force_n = ui.number("Force F", "N", f"{p}_f", 50.0)
    with c2:
        distance = ui.number("Distance d", "m", f"{p}_d", 3.0, min_value=0.0)
    with c3:
        angle = ui.number("Angle between F and motion", "°", f"{p}_ang", 0.0,
                          min_value=0.0, max_value=180.0)

    value = ui.compute(lambda: work(force_n, distance, angle))
    if value is not None:
        ui.result(
            "Work W", value, "J",
            secondary=[
                ("In watt-hours", value / 3600.0, "Wh"),
                ("Power if done in 10 s", value / 10.0, "W"),
                ("Height this would lift 1 kg", value / G0, "m"),
            ],
        )
    ui.assumptions([
        "Constant force along a straight path. A varying force needs the integral "
        "form, W = the integral of F dot ds.",
        "cos(θ) can be negative: a force opposing the motion (like friction "
        "or braking) does negative work and removes energy.",
        "Work is a scalar in joules. 1 J = 1 N·m, the same units as torque, but "
        "the two are physically different quantities.",
    ])
    ui.reference(
        variables=[
            ("$W$", "Work (energy transferred)", "J"),
            ("$F$", "Applied force", "N"),
            ("$d$", "Distance moved", "m"),
            ("$\\theta$", "Angle between force and motion", "°"),
        ],
        example="Battery sizing for a lift mechanism. Raising a 5 kg payload 2 m "
                "needs 98 J against gravity. At 60% drivetrain efficiency the "
                "battery must supply about 163 J - and that is per lift, so a "
                "50-cycle mission needs 8.2 kJ (2.3 Wh) just for lifting.",
    )


def render_power_page() -> None:
    p = "mech_power"
    ui.page_header(
        "Mechanical power",
        r"P = \frac{W}{t}",
        "Power is the rate of doing work. The same job done in half the time needs "
        "twice the power - which is usually what decides motor and battery size, "
        "not the total energy.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        work_j = ui.number("Work W", "J", f"{p}_w", 1000.0)
    with c2:
        time_s = ui.number("Time t", "s", f"{p}_t", 5.0, min_value=0.0)

    value = ui.compute(lambda: power(work_j, time_s))
    if value is not None:
        ui.result(
            "Power P", value, "W",
            secondary=[
                ("In kilowatts", value / 1000.0, "kW"),
                ("In horsepower (mechanical)", value / 745.6998715822702, "hp"),
                ("Current needed at 22.2 V", value / 22.2, "A"),
            ],
        )
    ui.assumptions([
        "Average power over the interval. Peak power can be much higher - size "
        "motors and wiring for the peak, not the average.",
        "This is useful mechanical power out. Input power is higher by whatever "
        "the efficiency of the drivetrain is.",
        "The current figure assumes a 22.2 V (6S) supply and 100% efficiency; it "
        "is an illustration, not a design value.",
    ])
    ui.reference(
        variables=[
            ("$P$", "Power", "W"),
            ("$W$", "Work done", "J"),
            ("$t$", "Time taken", "s"),
        ],
        example="Drone climb performance. Lifting a 2 kg quad 50 m takes 981 J of "
                "work. Doing it in 10 s needs 98 W of useful climb power on top of "
                "the power already needed to hover.",
    )


def render_momentum() -> None:
    p = "mech_mom"
    ui.page_header(
        "Linear momentum",
        r"p = m\,v",
        "Momentum is conserved in every collision, which makes it the natural tool "
        "for impacts, recoil and anything involving two bodies interacting. It is "
        "a vector: the sign of the velocity carries the direction.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        mass = ui.number("Mass m", "kg", f"{p}_m", 2.0, min_value=0.0)
    with c2:
        velocity = ui.number("Velocity v", "m/s", f"{p}_v", 15.0)

    value = ui.compute(lambda: momentum(mass, velocity))
    if value is not None:
        ui.result(
            "Momentum p", value, "kg·m/s",
            secondary=[
                ("Kinetic energy of this body", 0.5 * mass * velocity ** 2, "J"),
                ("Average force to stop it in 0.1 s", abs(value) / 0.1, "N"),
                ("Average force to stop it in 1.0 s", abs(value) / 1.0, "N"),
            ],
        )
    ui.assumptions([
        "Non-relativistic speeds (anything far below the speed of light).",
        "Momentum is a vector. Adding momenta means adding components, not "
        "magnitudes.",
        "The stopping-force figures come from impulse: F × t = change in "
        "momentum, assuming a constant force over that time.",
    ])
    ui.reference(
        variables=[
            ("$p$", "Linear momentum", "kg·m/s"),
            ("$m$", "Mass", "kg"),
            ("$v$", "Velocity (signed)", "m/s"),
        ],
        example="Crash-protection design. A 2 kg drone hitting the ground at 15 "
                "m/s carries 30 kg·m/s. Stopping in 0.1 s (a crumpling frame) takes "
                "300 N; stopping in 0.005 s (rigid concrete) takes 6000 N. That "
                "ratio is the whole argument for energy-absorbing structure.",
    )


def render_kinetic_energy() -> None:
    p = "mech_ke"
    ui.page_header(
        "Kinetic energy",
        r"KE = \tfrac{1}{2}\,m\,v^{2}",
        "The energy of motion. Velocity is squared, so energy grows far faster "
        "than speed: doubling speed quadruples the energy that has to be absorbed "
        "in a crash or dissipated in braking.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        mass = ui.number("Mass m", "kg", f"{p}_m", 2.0, min_value=0.0)
    with c2:
        velocity = ui.number("Velocity v", "m/s", f"{p}_v", 15.0)

    value = ui.compute(lambda: kinetic_energy(mass, velocity))
    if value is not None:
        ui.result(
            "Kinetic energy KE", value, "J",
            secondary=[
                ("Momentum", mass * velocity, "kg·m/s"),
                ("Equivalent fall height", value / (mass * G0), "m"),
                ("At twice this speed", value * 4.0, "J"),
            ],
        )
    ui.assumptions([
        "Translational kinetic energy only. A spinning body also stores "
        "rotational energy, 0.5 I ω^2 (see Rotational mechanics).",
        "Non-relativistic speeds.",
        "Velocity is relative to the chosen reference frame - ground speed and "
        "airspeed give different answers.",
    ])
    ui.reference(
        variables=[
            ("$KE$", "Kinetic energy", "J"),
            ("$m$", "Mass", "kg"),
            ("$v$", "Speed", "m/s"),
        ],
        example="Safety analysis for flight over people. A 2 kg drone at 15 m/s "
                "carries 225 J - comparable to a brick dropped from 11 m. Most "
                "regulators classify impact risk by exactly this number.",
    )


def render_potential_energy() -> None:
    p = "mech_pe"
    ui.page_header(
        "Gravitational potential energy",
        r"PE = m\,g\,h",
        "Energy stored by height. For an aircraft, altitude is a battery: a glider "
        "spends potential energy to stay airborne, and a quadcopter can trade "
        "height back into distance when the battery runs low.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        mass = ui.number("Mass m", "kg", f"{p}_m", 2.0, min_value=0.0)
    with c2:
        height = ui.number("Height h", "m", f"{p}_h", 100.0,
                           help="Measured from whatever reference level you choose.")
    with c3:
        gravity = ui.number("Gravitational acceleration g", "m/s²", f"{p}_g", G0,
                            min_value=0.0,
                            help="Earth standard 9.80665. Moon 1.62, Mars 3.72.")

    value = ui.compute(lambda: potential_energy(mass, height, gravity))
    if value is not None:
        ui.result(
            "Potential energy PE", value, "J",
            secondary=[
                ("In watt-hours", value / 3600.0, "Wh"),
                ("Impact speed if dropped from rest", float(
                    np.sqrt(2.0 * gravity * abs(height))), "m/s"),
                ("Weight of this mass", mass * gravity, "N"),
            ],
        )
    ui.assumptions([
        "Uniform gravitational field - valid for any height near the Earth's "
        "surface; orbital mechanics needs the full inverse-square form.",
        "PE is always relative to a chosen reference height. Only differences in "
        "potential energy have physical meaning.",
        "The impact-speed figure ignores air drag, so it is an upper bound. A real "
        "falling drone reaches terminal velocity.",
    ])
    ui.reference(
        variables=[
            ("$PE$", "Gravitational potential energy", "J"),
            ("$m$", "Mass", "kg"),
            ("$g$", "Gravitational acceleration", "m/s²"),
            ("$h$", "Height above the reference level", "m"),
        ],
        example="Energy budgeting for a climb. Lifting a 2 kg drone to 100 m "
                "stores 1962 J (0.55 Wh). A 111 Wh pack could in principle do that "
                "climb 200 times - in practice hovering losses dominate, which is "
                "why altitude is cheap and hovering is expensive.",
    )


def render_mechanical_advantage() -> None:
    p = "mech_ma"
    ui.page_header(
        "Mechanical advantage",
        r"MA = \frac{F_{out}}{F_{in}}",
        "How much a machine multiplies force. Levers, pulleys, gears and screws "
        "all trade distance for force - energy is never created, so a machine that "
        "doubles force must halve the distance moved.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        f_out = ui.number("Output force F_out", "N", f"{p}_fo", 500.0)
    with c2:
        f_in = ui.number("Input force F_in", "N", f"{p}_fi", 100.0, min_value=0.0)

    value = ui.compute(lambda: mechanical_advantage(f_out, f_in))
    if value is not None:
        ui.result(
            "Mechanical advantage MA", value, "-",
            secondary=[
                ("Output distance per 1 m of input (ideal)",
                 1.0 / value if value != 0 else float("nan"), "m"),
                ("Force gained", f_out - f_in, "N"),
            ],
        )
        if value < 1:
            st.caption("MA below 1 means the machine trades force for speed or "
                       "distance - exactly what a bicycle in a high gear, or a "
                       "robot arm's output link, is doing.")
    ui.assumptions([
        "This is the ACTUAL mechanical advantage if the forces are measured. The "
        "IDEAL mechanical advantage, computed from geometry alone, is higher: "
        "efficiency = actual MA / ideal MA.",
        "Friction, flex and backlash all reduce the real output force.",
        "Energy is conserved: in the ideal case, output force times output "
        "distance equals input force times input distance.",
    ])
    ui.reference(
        variables=[
            ("$MA$", "Mechanical advantage", "-"),
            ("$F_{out}$", "Force produced by the machine", "N"),
            ("$F_{in}$", "Force applied to the machine", "N"),
        ],
        example="Landing-gear retract linkage. If the actuator pushes 100 N and "
                "the leg resists 500 N at the point of interest, the linkage gives "
                "MA = 5 - but the actuator must then travel five times as far as "
                "the leg moves.",
    )


def render_gear_ratio() -> None:
    p = "mech_gear"
    ui.page_header(
        "Gear ratio",
        r"i = \frac{z_{driven}}{z_{driving}}, \qquad n_{out} = \frac{n_{in}}{i},"
        r"\qquad \tau_{out} = \tau_{in}\,i",
        "A gear ratio above 1 is a reduction: the output turns slower than the "
        "input and, ignoring losses, produces proportionally more torque. Speed "
        "down, torque up - power stays the same.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        driving = ui.integer("Driving gear teeth (input)", f"{p}_zin", 12,
                             min_value=1)
    with c2:
        driven = ui.integer("Driven gear teeth (output)", f"{p}_zout", 60,
                            min_value=1)
    with c3:
        rpm_in = ui.number("Input speed", "rpm", f"{p}_rpm", 3000.0)
        torque_in = ui.number("Input torque", "N·m", f"{p}_tq", 0.5)

    value = ui.compute(lambda: gear_ratio(driven, driving))
    if value is not None:
        ui.result(
            "Gear ratio i", value, ": 1",
            secondary=[
                ("Output speed", output_rpm(rpm_in, value), "rpm"),
                ("Output torque (ideal, no losses)", torque_in * value, "N·m"),
                ("Input power", torque_in * rpm_in * 2.0 * np.pi / 60.0, "W"),
            ],
        )
        st.caption("Reduction drive: output is slower and stronger than the input."
                   if value > 1 else
                   "Overdrive: output is faster and weaker than the input."
                   if value < 1 else "1:1 - direct drive.")
    ui.assumptions([
        "Ideal gears: no friction, no backlash, 100% efficient. A real spur-gear "
        "stage loses 1-3% per mesh; a worm drive can lose 40% or more.",
        "Torque multiplication is the ideal value. Multiply by the efficiency to "
        "get the real output torque.",
        "Power is unchanged by an ideal gearbox - it only trades speed for torque.",
        "For a multi-stage gearbox, multiply the stage ratios together.",
    ])
    ui.reference(
        variables=[
            ("$i$", "Gear ratio (reduction if > 1)", "-"),
            ("$z_{driven}$", "Teeth on the output gear", "-"),
            ("$z_{driving}$", "Teeth on the input gear", "-"),
            ("$n$", "Rotational speed", "rpm"),
            ("$\\tau$", "Torque", "N·m"),
        ],
        example="Robot joint design. A motor making 0.5 N·m at 3000 rpm through a "
                "5:1 reduction gives 2.5 N·m at 600 rpm at the joint - the trade "
                "that makes a small fast motor useful for slow, strong motion.",
    )


CALCULATORS = {
    "Force (F = ma)": render_force,
    "Torque": render_torque,
    "Work": render_work,
    "Power": render_power_page,
    "Linear momentum": render_momentum,
    "Kinetic energy": render_kinetic_energy,
    "Potential energy": render_potential_energy,
    "Mechanical advantage": render_mechanical_advantage,
    "Gear ratio": render_gear_ratio,
}
