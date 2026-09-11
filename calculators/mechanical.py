"""Core mechanical-engineering equations."""
from __future__ import annotations

import numpy as np

from utils import validation as v
from utils.constants import G0
from utils.spec import Calculator, Field, Output, Secondary, Sweep

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

_FORCE = Calculator(
    slug="mech.force", name="Force (F = ma)",
    latex=r"F = m\,a",
    explanation=(
        "The force needed to accelerate a mass. Everything in dynamics starts "
        "here: a control surface, a landing-gear strut and a robot arm are all "
        "sized by the accelerations they must produce or survive."),
    inputs=[
        Field("mass", "Mass m", "kg", 2.0, min=0.0),
        Field("accel", "Acceleration a", "m/s²", 9.80665,
              help="Negative values mean deceleration."),
    ],
    compute=lambda i: force(i.mass, i.accel),
    result=Output("Force F", "N"),
    secondary=[
        Secondary("As a multiple of the object's weight", "g",
                  lambda i, r: i.accel / G0),
        Secondary("Weight of this mass on Earth", "N", lambda i, r: i.mass * G0),
        Secondary("In pound-force", "lbf", lambda i, r: r * 0.224808943),
    ],
    assumptions=[
        "Mass is constant. A rocket burning propellant loses mass, which needs "
        "the full momentum form of the law instead.",
        "F is the NET force - the vector sum of everything acting on the body.",
        "Inertial (non-rotating, non-accelerating) reference frame.",
        "Weight is a specific case of this law: a = g, so W = m g.",
    ],
    variables=[("$F$", "Net force", "N"), ("$m$", "Mass", "kg"),
               ("$a$", "Acceleration", "m/s²")],
    example=(
        "Sizing a robot-arm actuator. Moving a 2 kg gripper at 5 m/s² needs 10 N "
        "of net force - plus whatever it takes to hold the gripper's 19.6 N weight "
        "against gravity if the motion is vertical."),
    keywords=("newton", "second law", "fma", "acceleration"),
)

_TORQUE = Calculator(
    slug="mech.torque", name="Torque",
    latex=r"\tau = r\,F\,\sin\theta",
    explanation=(
        "Torque is the turning effect of a force: how hard you push, times how far "
        "from the pivot you push. Only the component perpendicular to the lever "
        "arm turns anything, which is what the sine term accounts for."),
    inputs=[
        Field("radius", "Lever arm r", "m", 0.25, min=0.0),
        Field("force_n", "Force F", "N", 40.0),
        Field("angle", "Angle between r and F", "°", 90.0, min=0.0, max=180.0,
              help="90 degrees is the usual case and gives the maximum torque "
                   "for a given force."),
    ],
    compute=lambda i: torque(i.radius, i.force_n, i.angle),
    result=Output("Torque τ", "N·m"),
    secondary=[
        Secondary("Effective (perpendicular) force", "N",
                  lambda i, r: i.force_n * float(np.sin(np.radians(i.angle)))),
        Secondary("In kgf·cm (servo datasheet units)", "kgf·cm",
                  lambda i, r: r / G0 * 100.0),
        Secondary("In pound-feet", "lbf·ft", lambda i, r: r * 0.737562),
    ],
    assumptions=[
        "r is measured from the axis of rotation to the point where the force is "
        "applied, in a straight line.",
        "Torque is a vector; this gives its magnitude about the chosen axis.",
        "Static or quasi-static case. Accelerating a rotating body also needs "
        "τ = I × α (see Rotational mechanics).",
        "Servo and gearmotor datasheets usually quote torque in kgf·cm - that is a "
        "force times a distance, converted above.",
    ],
    graph=Sweep(over="radius", y_label="Torque [N·m]", hi_factor=2.0, hi_min=0.1,
                title="Torque vs lever-arm length (linear at constant force)"),
    variables=[
        ("$\\tau$", "Torque about the axis", "N·m"),
        ("$r$", "Lever arm (perpendicular distance to the axis)", "m"),
        ("$F$", "Applied force", "N"),
        ("$\\theta$", "Angle between the lever arm and the force", "°"),
    ],
    example=(
        "Choosing a servo for a control surface. If the hinge moment is 0.8 N·m "
        "and the horn is 15 mm from the hinge line, the pushrod must pull 53 N - "
        "and the servo must make 0.8 N·m, about 8 kgf·cm, with margin on top."),
    keywords=("torque", "moment", "lever", "servo"),
)

_WORK = Calculator(
    slug="mech.work", name="Work",
    latex=r"W = F\,d\,\cos\theta",
    explanation=(
        "Work is energy transferred by a force acting through a distance. A force "
        "at right angles to the motion does no work at all - which is why carrying "
        "a box across a level floor does no work on the box, however tiring."),
    inputs=[
        Field("force_n", "Force F", "N", 50.0),
        Field("distance", "Distance d", "m", 3.0, min=0.0),
        Field("angle", "Angle between F and motion", "°", 0.0, min=0.0, max=180.0),
    ],
    compute=lambda i: work(i.force_n, i.distance, i.angle),
    result=Output("Work W", "J"),
    secondary=[
        Secondary("In watt-hours", "Wh", lambda i, r: r / 3600.0),
        Secondary("Power if done in 10 s", "W", lambda i, r: r / 10.0),
        Secondary("Height this would lift 1 kg", "m", lambda i, r: r / G0),
    ],
    assumptions=[
        "Constant force along a straight path. A varying force needs the integral "
        "form, W = the integral of F dot ds.",
        "cos(θ) can be negative: a force opposing the motion (like friction or "
        "braking) does negative work and removes energy.",
        "Work is a scalar in joules. 1 J = 1 N·m, the same units as torque, but "
        "the two are physically different quantities.",
    ],
    variables=[
        ("$W$", "Work (energy transferred)", "J"),
        ("$F$", "Applied force", "N"), ("$d$", "Distance moved", "m"),
        ("$\\theta$", "Angle between force and motion", "°"),
    ],
    example=(
        "Battery sizing for a lift mechanism. Raising a 5 kg payload 2 m needs "
        "98 J against gravity. At 60% drivetrain efficiency the battery must "
        "supply about 163 J - and that is per lift, so a 50-cycle mission needs "
        "8.2 kJ (2.3 Wh) just for lifting."),
    keywords=("work", "energy", "joule"),
)

_POWER = Calculator(
    slug="mech.power", name="Power",
    latex=r"P = \frac{W}{t}",
    explanation=(
        "Power is the rate of doing work. The same job done in half the time needs "
        "twice the power - which is usually what decides motor and battery size, "
        "not the total energy."),
    inputs=[
        Field("work_j", "Work W", "J", 1000.0),
        Field("time_s", "Time t", "s", 5.0, min=0.0),
    ],
    compute=lambda i: power(i.work_j, i.time_s),
    result=Output("Power P", "W"),
    secondary=[
        Secondary("In kilowatts", "kW", lambda i, r: r / 1000.0),
        Secondary("In horsepower (mechanical)", "hp",
                  lambda i, r: r / 745.6998715822702),
        Secondary("Current needed at 22.2 V", "A", lambda i, r: r / 22.2),
    ],
    assumptions=[
        "Average power over the interval. Peak power can be much higher - size "
        "motors and wiring for the peak, not the average.",
        "This is useful mechanical power out. Input power is higher by whatever "
        "the efficiency of the drivetrain is.",
        "The current figure assumes a 22.2 V (6S) supply and 100% efficiency; it "
        "is an illustration, not a design value.",
    ],
    variables=[("$P$", "Power", "W"), ("$W$", "Work done", "J"),
               ("$t$", "Time taken", "s")],
    example=(
        "Drone climb performance. Lifting a 2 kg quad 50 m takes 981 J of work. "
        "Doing it in 10 s needs 98 W of useful climb power on top of the power "
        "already needed to hover."),
    keywords=("power", "watt", "rate"),
)

_MOMENTUM = Calculator(
    slug="mech.momentum", name="Linear momentum",
    latex=r"p = m\,v",
    explanation=(
        "Momentum is conserved in every collision, which makes it the natural tool "
        "for impacts, recoil and anything involving two bodies interacting. It is "
        "a vector: the sign of the velocity carries the direction."),
    inputs=[
        Field("mass", "Mass m", "kg", 2.0, min=0.0),
        Field("velocity", "Velocity v", "m/s", 15.0),
    ],
    compute=lambda i: momentum(i.mass, i.velocity),
    result=Output("Momentum p", "kg·m/s"),
    secondary=[
        Secondary("Kinetic energy of this body", "J",
                  lambda i, r: 0.5 * i.mass * i.velocity ** 2),
        Secondary("Average force to stop it in 0.1 s", "N",
                  lambda i, r: abs(r) / 0.1),
        Secondary("Average force to stop it in 1.0 s", "N", lambda i, r: abs(r)),
    ],
    assumptions=[
        "Non-relativistic speeds (anything far below the speed of light).",
        "Momentum is a vector. Adding momenta means adding components, not "
        "magnitudes.",
        "The stopping-force figures come from impulse: F × t = change in momentum, "
        "assuming a constant force over that time.",
    ],
    variables=[("$p$", "Linear momentum", "kg·m/s"), ("$m$", "Mass", "kg"),
               ("$v$", "Velocity (signed)", "m/s")],
    example=(
        "Crash-protection design. A 2 kg drone hitting the ground at 15 m/s "
        "carries 30 kg·m/s. Stopping in 0.1 s (a crumpling frame) takes 300 N; "
        "stopping in 0.005 s (rigid concrete) takes 6000 N. That ratio is the "
        "whole argument for energy-absorbing structure."),
    keywords=("momentum", "impulse", "collision"),
)

_KINETIC = Calculator(
    slug="mech.kinetic_energy", name="Kinetic energy",
    latex=r"KE = \tfrac{1}{2}\,m\,v^{2}",
    explanation=(
        "The energy of motion. Velocity is squared, so energy grows far faster "
        "than speed: doubling speed quadruples the energy that has to be absorbed "
        "in a crash or dissipated in braking."),
    inputs=[
        Field("mass", "Mass m", "kg", 2.0, min=0.0),
        Field("velocity", "Velocity v", "m/s", 15.0),
    ],
    compute=lambda i: kinetic_energy(i.mass, i.velocity),
    result=Output("Kinetic energy KE", "J"),
    secondary=[
        Secondary("Momentum", "kg·m/s", lambda i, r: i.mass * i.velocity),
        Secondary("Equivalent fall height", "m", lambda i, r: r / (i.mass * G0)),
        Secondary("At twice this speed", "J", lambda i, r: r * 4.0),
    ],
    assumptions=[
        "Translational kinetic energy only. A spinning body also stores rotational "
        "energy, 0.5 I ω² (see Rotational mechanics).",
        "Non-relativistic speeds.",
        "Velocity is relative to the chosen reference frame - ground speed and "
        "airspeed give different answers.",
    ],
    variables=[("$KE$", "Kinetic energy", "J"), ("$m$", "Mass", "kg"),
               ("$v$", "Speed", "m/s")],
    example=(
        "Safety analysis for flight over people. A 2 kg drone at 15 m/s carries "
        "225 J - comparable to a brick dropped from 11 m. Most regulators classify "
        "impact risk by exactly this number."),
    keywords=("kinetic", "ke", "energy", "impact"),
)

_POTENTIAL = Calculator(
    slug="mech.potential_energy", name="Potential energy",
    latex=r"PE = m\,g\,h",
    explanation=(
        "Energy stored by height. For an aircraft, altitude is a battery: a glider "
        "spends potential energy to stay airborne, and a quadcopter can trade "
        "height back into distance when the battery runs low."),
    inputs=[
        Field("mass", "Mass m", "kg", 2.0, min=0.0),
        Field("height", "Height h", "m", 100.0,
              help="Measured from whatever reference level you choose."),
        Field("gravity", "Gravitational acceleration g", "m/s²", G0, min=0.0,
              help="Earth standard 9.80665. Moon 1.62, Mars 3.72."),
    ],
    compute=lambda i: potential_energy(i.mass, i.height, i.gravity),
    result=Output("Potential energy PE", "J"),
    secondary=[
        Secondary("In watt-hours", "Wh", lambda i, r: r / 3600.0),
        Secondary("Impact speed if dropped from rest", "m/s",
                  lambda i, r: float(np.sqrt(2.0 * i.gravity * abs(i.height)))),
        Secondary("Weight of this mass", "N", lambda i, r: i.mass * i.gravity),
    ],
    assumptions=[
        "Uniform gravitational field - valid for any height near the Earth's "
        "surface; orbital mechanics needs the full inverse-square form.",
        "PE is always relative to a chosen reference height. Only differences in "
        "potential energy have physical meaning.",
        "The impact-speed figure ignores air drag, so it is an upper bound. A real "
        "falling drone reaches terminal velocity.",
    ],
    variables=[
        ("$PE$", "Gravitational potential energy", "J"), ("$m$", "Mass", "kg"),
        ("$g$", "Gravitational acceleration", "m/s²"),
        ("$h$", "Height above the reference level", "m"),
    ],
    example=(
        "Energy budgeting for a climb. Lifting a 2 kg drone to 100 m stores 1962 J "
        "(0.55 Wh). A 111 Wh pack could in principle do that climb 200 times - in "
        "practice hovering losses dominate, which is why altitude is cheap and "
        "hovering is expensive."),
    keywords=("potential", "pe", "height", "gravity"),
)

_MECH_ADVANTAGE = Calculator(
    slug="mech.mechanical_advantage", name="Mechanical advantage",
    latex=r"MA = \frac{F_{out}}{F_{in}}",
    explanation=(
        "How much a machine multiplies force. Levers, pulleys, gears and screws "
        "all trade distance for force - energy is never created, so a machine that "
        "doubles force must halve the distance moved."),
    inputs=[
        Field("f_out", "Output force F_out", "N", 500.0),
        Field("f_in", "Input force F_in", "N", 100.0, min=0.0),
    ],
    compute=lambda i: mechanical_advantage(i.f_out, i.f_in),
    result=Output("Mechanical advantage MA", "-"),
    secondary=[
        Secondary("Output distance per 1 m of input (ideal)", "m",
                  lambda i, r: 1.0 / r),
        Secondary("Force gained", "N", lambda i, r: i.f_out - i.f_in),
    ],
    note=lambda i, r: ("MA below 1 means the machine trades force for speed or "
                       "distance - exactly what a bicycle in a high gear, or a "
                       "robot arm's output link, is doing.") if r < 1 else None,
    assumptions=[
        "This is the ACTUAL mechanical advantage if the forces are measured. The "
        "IDEAL mechanical advantage, computed from geometry alone, is higher: "
        "efficiency = actual MA / ideal MA.",
        "Friction, flex and backlash all reduce the real output force.",
        "Energy is conserved: in the ideal case, output force times output "
        "distance equals input force times input distance.",
    ],
    variables=[
        ("$MA$", "Mechanical advantage", "-"),
        ("$F_{out}$", "Force produced by the machine", "N"),
        ("$F_{in}$", "Force applied to the machine", "N"),
    ],
    example=(
        "Landing-gear retract linkage. If the actuator pushes 100 N and the leg "
        "resists 500 N at the point of interest, the linkage gives MA = 5 - but "
        "the actuator must then travel five times as far as the leg moves."),
    keywords=("mechanical advantage", "lever", "pulley", "ma"),
)


def _gear_note(i, r):
    if r > 1:
        return "Reduction drive: output is slower and stronger than the input."
    if r < 1:
        return "Overdrive: output is faster and weaker than the input."
    return "1:1 - direct drive."


_GEAR_RATIO = Calculator(
    slug="mech.gear_ratio", name="Gear ratio",
    latex=(r"i = \frac{z_{driven}}{z_{driving}}, \qquad n_{out} = \frac{n_{in}}{i},"
           r"\qquad \tau_{out} = \tau_{in}\,i"),
    explanation=(
        "A gear ratio above 1 is a reduction: the output turns slower than the "
        "input and, ignoring losses, produces proportionally more torque. Speed "
        "down, torque up - power stays the same."),
    inputs=[
        Field("driving", "Driving gear teeth (input)", "", 12, min=1, kind="int"),
        Field("driven", "Driven gear teeth (output)", "", 60, min=1, kind="int"),
        Field("rpm_in", "Input speed", "rpm", 3000.0),
        Field("torque_in", "Input torque", "N·m", 0.5),
    ],
    compute=lambda i: gear_ratio(i.driven, i.driving),
    result=Output("Gear ratio i", ": 1"),
    secondary=[
        Secondary("Output speed", "rpm", lambda i, r: output_rpm(i.rpm_in, r)),
        Secondary("Output torque (ideal, no losses)", "N·m",
                  lambda i, r: i.torque_in * r),
        Secondary("Input power", "W",
                  lambda i, r: i.torque_in * i.rpm_in * 2.0 * np.pi / 60.0),
    ],
    note=_gear_note,
    assumptions=[
        "Ideal gears: no friction, no backlash, 100% efficient. A real spur-gear "
        "stage loses 1-3% per mesh; a worm drive can lose 40% or more.",
        "Torque multiplication is the ideal value. Multiply by the efficiency to "
        "get the real output torque.",
        "Power is unchanged by an ideal gearbox - it only trades speed for torque.",
        "For a multi-stage gearbox, multiply the stage ratios together.",
    ],
    variables=[
        ("$i$", "Gear ratio (reduction if > 1)", "-"),
        ("$z_{driven}$", "Teeth on the output gear", "-"),
        ("$z_{driving}$", "Teeth on the input gear", "-"),
        ("$n$", "Rotational speed", "rpm"), ("$\\tau$", "Torque", "N·m"),
    ],
    example=(
        "Robot joint design. A motor making 0.5 N·m at 3000 rpm through a 5:1 "
        "reduction gives 2.5 N·m at 600 rpm at the joint - the trade that makes a "
        "small fast motor useful for slow, strong motion."),
    keywords=("gear", "ratio", "reduction", "teeth"),
)

CALCULATORS = [_FORCE, _TORQUE, _WORK, _POWER, _MOMENTUM, _KINETIC,
               _POTENTIAL, _MECH_ADVANTAGE, _GEAR_RATIO]
