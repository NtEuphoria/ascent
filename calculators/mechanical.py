"""Core mechanical-engineering equations."""
from __future__ import annotations

import numpy as np

from utils import validation as v
from utils.constants import G0
from utils.spec import (Calculator, Check, Field, Output, Reference, Secondary,
                        Sweep)

# Unit conversions used by the supporting values. Kept here as named constants
# so a stray digit shows up as a wrong name rather than a plausible number.
LBF_PER_N = 0.224808943
KGF_CM_PER_NM = 100.0 / G0           # 1 N·m = 10.197 kgf·cm
OZ_IN_PER_NM = 141.611932            # 1 N·m = 141.61 oz·in (servo datasheets)
LBF_FT_PER_NM = 0.737562149
FT_LBF_PER_J = 0.737562149           # same number, different quantity
HP_PER_W = 1.0 / 745.6998715822702   # mechanical horsepower
EARTH_RADIUS_M = 6.371e6             # mean radius, for the g-with-altitude check

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


def friction_force(normal_force: float, mu: float) -> float:
    """F_f = μ * N   [N]

    For a static coefficient this is the MAXIMUM friction available, not the
    force that is actually acting: a block pushed with 5 N when 20 N of static
    friction is available feels 5 N of friction back, not 20 N.
    """
    normal_force = v.non_negative(normal_force, "Normal force", "N")
    mu = v.non_negative(mu, "Coefficient of friction")
    return mu * normal_force


def friction_on_slope(mass: float, mu: float, angle_deg: float = 0.0,
                      gravity: float = G0) -> float:
    """F_f = μ * m * g * cos(θ)   [N]

    The normal force on a slope is only the component of weight perpendicular
    to the surface, so friction falls away as the slope steepens even though
    the weight has not changed. θ = 0 is level ground, where N = m g.
    """
    mass = v.positive(mass, "Mass", "kg")
    angle_deg = v.in_range(angle_deg, "Slope angle", 0.0, 90.0, "°")
    gravity = v.non_negative(gravity, "Gravitational acceleration", "m/s²")
    normal = mass * gravity * float(np.cos(np.radians(angle_deg)))
    return friction_force(normal, mu)


def angle_of_repose(mu: float) -> float:
    """θ = atan(μ)   [°]

    The slope angle at which a body starts to slide under its own weight. It
    depends only on μ - the mass cancels, because both the driving force and
    the friction that resists it are proportional to weight.
    """
    mu = v.non_negative(mu, "Coefficient of friction")
    return float(np.degrees(np.arctan(mu)))


def slope_acceleration(mu: float, angle_deg: float,
                       gravity: float = G0) -> float:
    """a = g (sin θ - μ cos θ)   [m/s²], floored at zero.

    Zero means the body stays put: friction is at least as large as the
    downslope component of weight.
    """
    mu = v.non_negative(mu, "Coefficient of friction")
    angle_deg = v.in_range(angle_deg, "Slope angle", 0.0, 90.0, "°")
    gravity = v.non_negative(gravity, "Gravitational acceleration", "m/s²")
    theta = np.radians(angle_deg)
    return max(0.0, gravity * float(np.sin(theta) - mu * np.cos(theta)))


def lead_angle(mean_diameter: float, lead: float) -> float:
    """λ = atan(l / (π d_m))   [°]

    The helix angle of the thread, measured at the mean diameter. It is the
    slope of the inclined plane wrapped around the screw.
    """
    mean_diameter = v.positive(mean_diameter, "Mean thread diameter", "m")
    lead = v.positive(lead, "Lead", "m")
    return float(np.degrees(np.arctan(lead / (np.pi * mean_diameter))))


def _sec_alpha(half_angle_deg: float) -> float:
    """1 / cos(α) for the thread half-angle, checked for sanity."""
    half_angle_deg = v.in_range(half_angle_deg, "Thread half-angle",
                                0.0, 45.0, "°")
    return 1.0 / float(np.cos(np.radians(half_angle_deg)))


def lead_screw_torque(load: float, mean_diameter: float, lead: float,
                      mu: float, half_angle_deg: float = 0.0) -> float:
    """Torque to RAISE a load on a power screw   [N·m]

        T = (F d_m / 2) * (l + π μ d_m secα) / (π d_m - μ l secα)

    Square threads have α = 0; ACME is 14.5 degrees and metric trapezoidal
    15 degrees, where the thread flank angle presses the flanks together and
    raises the effective friction by secα. Collar/thrust-bearing friction is
    NOT included - add it separately.
    """
    load = v.non_negative(load, "Axial load", "N")
    mean_diameter = v.positive(mean_diameter, "Mean thread diameter", "m")
    lead = v.positive(lead, "Lead", "m")
    mu = v.non_negative(mu, "Coefficient of friction")
    sec_a = _sec_alpha(half_angle_deg)
    denominator = np.pi * mean_diameter - mu * lead * sec_a
    if denominator <= 0:
        raise v.ValidationError(
            "This thread cannot be driven: μ × lead exceeds π × mean diameter, "
            "so the flanks jam. Reduce the lead or the friction.")
    numerator = lead + np.pi * mu * mean_diameter * sec_a
    return load * mean_diameter / 2.0 * numerator / denominator


def lead_screw_lowering_torque(load: float, mean_diameter: float, lead: float,
                               mu: float, half_angle_deg: float = 0.0) -> float:
    """Torque to LOWER a load on a power screw   [N·m]

        T = (F d_m / 2) * (π μ d_m secα - l) / (π d_m + μ l secα)

    Positive means the screw is self-locking: torque has to be applied to let
    the load down. Negative means the load drives the screw backwards on its
    own and the mechanism needs a brake.
    """
    load = v.non_negative(load, "Axial load", "N")
    mean_diameter = v.positive(mean_diameter, "Mean thread diameter", "m")
    lead = v.positive(lead, "Lead", "m")
    mu = v.non_negative(mu, "Coefficient of friction")
    sec_a = _sec_alpha(half_angle_deg)
    numerator = np.pi * mu * mean_diameter * sec_a - lead
    denominator = np.pi * mean_diameter + mu * lead * sec_a
    return load * mean_diameter / 2.0 * numerator / denominator


def lead_screw_efficiency(mean_diameter: float, lead: float, mu: float,
                          half_angle_deg: float = 0.0) -> float:
    """e = F l / (2 π T_raise)   [-]

    The load cancels, so efficiency is a property of the thread geometry and
    the friction alone. Typical sliding lead screws land at 0.2-0.4, which is
    why they are so often driven by a much larger motor than the load implies.
    """
    torque_per_newton = lead_screw_torque(1.0, mean_diameter, lead, mu,
                                          half_angle_deg)
    if torque_per_newton <= 0:
        return 0.0
    return lead / (2.0 * np.pi * torque_per_newton)


def spring_force(rate: float, deflection: float) -> float:
    """F = k x   [N]. Hooke's law, with x measured from the free length."""
    rate = v.non_negative(rate, "Spring rate", "N/m")
    deflection = v.finite(deflection, "Deflection", "m")
    return rate * deflection


def spring_energy(rate: float, deflection: float) -> float:
    """U = 0.5 k x²   [J] - the area under the force-deflection line."""
    rate = v.non_negative(rate, "Spring rate", "N/m")
    deflection = v.finite(deflection, "Deflection", "m")
    return 0.5 * rate * deflection ** 2


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
        Secondary("In pound-force", "lbf", lambda i, r: r * LBF_PER_N),
        Secondary("In kilogram-force", "kgf", lambda i, r: r / G0),
        Secondary("Total force if this acceleration is vertically upward", "N",
                  lambda i, r: i.mass * (i.accel + G0)),
        Secondary("Time to reach 10 m/s from rest", "s",
                  lambda i, r: 10.0 / abs(i.accel)),
    ],
    assumptions=[
        "Mass is constant. A rocket burning propellant loses mass, which needs "
        "the full momentum form of the law instead.",
        "F is the NET force - the vector sum of everything acting on the body. "
        "An actuator that must also fight gravity, friction or drag has to "
        "produce more than this.",
        "Inertial (non-rotating, non-accelerating) reference frame. On a "
        "spinning arm or a turning vehicle, centrifugal and Coriolis terms "
        "appear and this number alone is not the whole load.",
        "Weight is a specific case of this law: a = g, so W = m g.",
        "Size structure for the PEAK acceleration, not the average. A 5 g "
        "spike lasting 20 ms still asks the mount for five times the weight, "
        "and a mount sized on the average simply breaks.",
        "The mass is the whole moving mass. Forgetting the gearbox, the cable "
        "loom or the tool in the gripper is the usual way this comes out low.",
    ],
    graphs=[
        Sweep(over="mass", y_label="Force F [N]", hi_factor=2.0, hi_min=1.0,
              title="Force vs mass"),
        Sweep(over="accel", y_label="Force F [N]", hi_factor=2.0, hi_min=5.0,
              title="Force vs acceleration"),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            f"{abs(i.accel) / G0:.1f} g is a severe "
                            "acceleration. Above about 10 g you are in "
                            "crash-load, launch or drop-shock territory: "
                            "fasteners, connectors and solder joints all need "
                            "checking, not just the main structure.")
              if abs(i.accel) > 10.0 * G0 else None),
        Check(lambda i, r: ("info",
                            "Negative acceleration means braking. The force "
                            "points opposite to the motion, and whatever is "
                            "holding the payload has to pull as hard as it "
                            "would push to speed it up.")
              if i.accel < 0 else None),
        Check(lambda i, r: ("info",
                            "Zero acceleration means zero NET force - not zero "
                            "force. A body moving at constant speed can still "
                            "have large forces on it that happen to cancel.")
              if i.accel == 0 else None),
    ],
    references=[
        Reference(
            title="Accelerations to compare against",
            columns=("Situation", "Acceleration", "In m/s²"),
            rows=[
                ("Lift starting to move", "0.1 g", "~1"),
                ("Car, brisk acceleration", "0.3 - 0.4 g", "3 - 4"),
                ("Airliner takeoff roll", "0.25 - 0.35 g", "2.5 - 3.5"),
                ("Car, emergency braking on dry tarmac", "0.8 - 1.0 g", "8 - 10"),
                ("Aggressive multirotor manoeuvre", "1.5 - 3 g", "15 - 30"),
                ("Aerobatic aircraft structural limit", "+6 / -3 g", "59 / -29"),
                ("Fighter pilot, sustained turn", "9 g", "88"),
                ("Packaged goods, drop onto a hard floor", "25 - 100 g",
                 "250 - 1000"),
            ],
            note="Orders of magnitude for sanity-checking an answer, not design "
                 "limits. Drop shock in particular depends entirely on the drop "
                 "height and how much the packaging crushes.",
        ),
    ],
    related=["mech.momentum", "mech.work", "mech.kinetic_energy",
             "materials.normal_stress", "robot.servo_torque"],
    variables=[("$F$", "Net force", "N"), ("$m$", "Mass", "kg"),
               ("$a$", "Acceleration", "m/s²")],
    example=(
        "Sizing a robot-arm actuator. Moving a 2 kg gripper at 5 m/s² needs 10 N "
        "of net force - plus whatever it takes to hold the gripper's 19.6 N weight "
        "against gravity if the motion is vertical. Vertically, that is 29.6 N "
        "total: three times the number you get if you forget gravity."),
    keywords=("newton", "second law", "fma", "acceleration", "g force",
              "inertia", "net force", "mass"),
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
                  lambda i, r: r * KGF_CM_PER_NM),
        Secondary("In ounce-inches (RC servo units)", "oz·in",
                  lambda i, r: r * OZ_IN_PER_NM),
        Secondary("In pound-feet", "lbf·ft", lambda i, r: r * LBF_FT_PER_NM),
        Secondary("Force needed on a 100 mm arm for the same torque", "N",
                  lambda i, r: r / 0.100),
        Secondary("Mechanical power if this turns at 100 rpm", "W",
                  lambda i, r: r * 100.0 * 2.0 * np.pi / 60.0),
    ],
    assumptions=[
        "r is measured from the axis of rotation to the point where the force is "
        "applied, in a straight line.",
        "Torque is a vector; this gives its magnitude about the chosen axis. "
        "A force that also pushes the shaft sideways loads the bearings without "
        "adding any torque at all.",
        "Static or quasi-static case. Accelerating a rotating body also needs "
        "τ = I × α (see Rotational mechanics), which on a fast-spinning load "
        "can dwarf the static torque.",
        "Servo and gearmotor datasheets usually quote torque in kgf·cm or "
        "oz·in - both are a force times a distance, converted above.",
        "A servo's quoted torque is its STALL torque at a stated voltage. "
        "Running it near stall overheats it; size for roughly a third of the "
        "quoted figure for continuous holding.",
        "Nothing here accounts for the lever arm bending or the mounting "
        "flexing. On a long thin arm those decide the real behaviour.",
    ],
    graphs=[
        Sweep(over="radius", y_label="Torque [N·m]", hi_factor=2.0, hi_min=0.1,
              title="Torque vs lever-arm length (linear at constant force)"),
        Sweep(over="force_n", y_label="Torque [N·m]", hi_factor=2.0,
              hi_min=10.0, title="Torque vs applied force"),
        Sweep(over="angle", y_label="Torque [N·m]", lo=0.0, hi_factor=2.0,
              hi_min=180.0, title="Torque vs the angle between r and F"),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            f"At {i.angle:.0f}° only "
                            f"{abs(float(np.sin(np.radians(i.angle)))) * 100:.0f}% "
                            "of the force is doing any turning. The rest is "
                            "pulling straight along the arm and into the "
                            "bearings - a common cause of a linkage that "
                            "binds instead of moving.")
              if 0 < i.angle < 20 or i.angle > 160 else None),
        Check(lambda i, r: ("info",
                            "Past 90° the sine falls again: 120° gives exactly "
                            "the same torque as 60°. Only the component across "
                            "the arm ever counts.")
              if i.angle > 90 else None),
        Check(lambda i, r: ("info",
                            "A negative force simply reverses the direction of "
                            "rotation; the magnitude of the torque is "
                            "unchanged.") if i.force_n < 0 else None),
    ],
    references=[
        Reference(
            title="What real actuators produce",
            columns=("Actuator", "Torque [N·m]", "In kgf·cm"),
            rows=[
                ("Micro hobby servo (9 g class)", "0.15 - 0.20", "1.5 - 2.0"),
                ("Standard hobby servo (40 g class)", "0.3 - 0.5", "3 - 5"),
                ("High-torque digital servo (55 g class)", "0.9 - 1.2",
                 "9 - 12"),
                ("NEMA 17 stepper, holding torque", "0.3 - 0.6", "3 - 6"),
                ("NEMA 23 stepper, holding torque", "1.0 - 3.0", "10 - 30"),
                ("Cordless drill in low gear", "30 - 60", "300 - 600"),
                ("Car wheel nut, typical tightening spec", "110 - 140",
                 "1100 - 1400"),
                ("Small petrol car engine, peak", "150 - 250", "1500 - 2500"),
            ],
            note="Servo figures are stall torque at the datasheet voltage, "
                 "which is the number printed on the box; continuous duty is "
                 "much lower. Stepper holding torque falls steeply with speed.",
        ),
        Reference(
            title="Torque unit conversions",
            columns=("1 of this", "In N·m"),
            rows=[
                ("newton-metre (N·m)", "1"),
                ("kilogram-force centimetre (kgf·cm)", "0.0980665"),
                ("ounce-inch (oz·in)", "0.00706155"),
                ("pound-force inch (lbf·in)", "0.112985"),
                ("pound-force foot (lbf·ft)", "1.35582"),
                ("newton-millimetre (N·mm)", "0.001"),
            ],
            note="Exact conversions (kgf uses standard gravity, 9.80665 m/s²). "
                 "The trap is kgf·cm vs kgf·m - a factor of 100 that has sized "
                 "more than one gearbox wrongly.",
        ),
    ],
    related=["robot.servo_torque", "rotational_mechanics.rotational_power",
             "mech.gear_ratio", "mech.mechanical_advantage"],
    variables=[
        ("$\\tau$", "Torque about the axis", "N·m"),
        ("$r$", "Lever arm (perpendicular distance to the axis)", "m"),
        ("$F$", "Applied force", "N"),
        ("$\\theta$", "Angle between the lever arm and the force", "°"),
    ],
    example=(
        "Choosing a servo for a control surface. If the hinge moment is 0.8 N·m "
        "and the horn is 15 mm from the hinge line, the pushrod must pull 53.3 N - "
        "and the servo must make 0.8 N·m, which is 8.16 kgf·cm or 113 oz·in in "
        "the units the datasheet uses. That is past a standard 40 g servo and "
        "into the high-torque digital class - and since 8.16 kgf·cm would be a "
        "stall figure, the sensible choice is a servo rated well above it."),
    keywords=("torque", "moment", "lever", "servo", "kgf.cm", "oz-in",
              "hinge moment", "wrench"),
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
        Secondary("In kilojoules", "kJ", lambda i, r: r / 1000.0),
        Secondary("Effective force along the motion", "N",
                  lambda i, r: i.force_n * float(np.cos(np.radians(i.angle)))),
        Secondary("Battery capacity this needs at 11.1 V (3S)", "mAh",
                  lambda i, r: r / 3600.0 / 11.1 * 1000.0),
    ],
    assumptions=[
        "Constant force along a straight path. A varying force needs the integral "
        "form, W = the integral of F dot ds - a spring, for example, needs "
        "0.5 k x² rather than F d.",
        "cos(θ) can be negative: a force opposing the motion (like friction or "
        "braking) does negative work and removes energy.",
        "Work is a scalar in joules. 1 J = 1 N·m, the same units as torque, but "
        "the two are physically different quantities and must never be added.",
        "This is the work done BY this force, not the energy drawn from the "
        "supply. Divide by the drivetrain efficiency to get that, and for a "
        "motor-gearbox-screw chain the efficiencies multiply.",
        "Work says nothing about how long it takes. A job needing 1 kJ can be "
        "done by a 10 W motor in 100 s or a 1 kW motor in 1 s - the energy is "
        "identical and the machine is not.",
        "Energy recovered on the way back down is only recovered if the system "
        "can regenerate. A resistive brake or a worm drive throws it away as "
        "heat.",
    ],
    graphs=[
        Sweep(over="distance", y_label="Work W [J]", hi_factor=2.0, hi_min=1.0,
              title="Work vs distance"),
        Sweep(over="force_n", y_label="Work W [J]", hi_factor=2.0, hi_min=10.0,
              title="Work vs applied force"),
        Sweep(over="angle", y_label="Work W [J]", lo=0.0, hi_factor=2.0,
              hi_min=180.0, title="Work vs angle (negative past 90°)"),
    ],
    checks=[
        Check(lambda i, r: ("info",
                            "Past 90° the force opposes the motion, so the work "
                            "is negative: this force is taking energy out of "
                            "the system rather than putting it in. That is "
                            "exactly what a brake or a friction force does.")
              if i.angle > 90 else None),
        Check(lambda i, r: ("info",
                            "At exactly 90° the force does no work at all, "
                            "however large it is. Holding a mass still, or a "
                            "centripetal force on a circular path, are both "
                            "this case.")
              if abs(i.angle - 90.0) < 1e-9 else None),
        Check(lambda i, r: ("info",
                            "No distance means no work, whatever the force. "
                            "A motor stalled against a stop does zero work and "
                            "still burns its full current as heat.")
              if i.distance == 0 else None),
    ],
    references=[
        Reference(
            title="Energy to compare against",
            columns=("Energy source or event", "Roughly"),
            rows=[
                ("Lifting 1 kg by 1 m", "9.8 J"),
                ("A 2 kg drone flying at 15 m/s", "225 J"),
                ("AA alkaline cell", "12 - 14 kJ (3 - 4 Wh)"),
                ("18650 Li-ion cell, 3000 mAh", "39 kJ (10.8 Wh)"),
                ("3S 2200 mAh LiPo pack", "88 kJ (24 Wh)"),
                ("Laptop battery, 60 Wh", "216 kJ"),
                ("Food energy in a chocolate bar", "~1 MJ"),
                ("1 litre of petrol, burned", "~32 MJ"),
            ],
            note="Cell figures are nominal capacity times nominal voltage; "
                 "usable energy is lower once you stop at a safe cut-off "
                 "voltage and allow for the voltage sag under load.",
        ),
    ],
    related=["mech.power", "mech.potential_energy", "mech.kinetic_energy",
             "elec.battery_energy"],
    variables=[
        ("$W$", "Work (energy transferred)", "J"),
        ("$F$", "Applied force", "N"), ("$d$", "Distance moved", "m"),
        ("$\\theta$", "Angle between force and motion", "°"),
    ],
    example=(
        "Battery sizing for a lift mechanism. Raising a 5 kg payload 2 m needs "
        "98.1 J against gravity. At 60% drivetrain efficiency the battery must "
        "supply about 163 J - and that is per lift, so a 50-cycle mission needs "
        "8.17 kJ (2.27 Wh, or 205 mAh from a 3S pack) just for lifting."),
    keywords=("work", "energy", "joule", "force times distance", "lifting"),
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
                  lambda i, r: r * HP_PER_W),
        Secondary("Current needed at 22.2 V", "A", lambda i, r: r / 22.2),
        Secondary("Current needed at 12 V", "A", lambda i, r: r / 12.0),
        Secondary("Input power at 75% overall efficiency", "W",
                  lambda i, r: r / 0.75),
        Secondary("Heat to get rid of at that efficiency", "W",
                  lambda i, r: r / 0.75 - r),
    ],
    assumptions=[
        "Average power over the interval. Peak power can be much higher - size "
        "motors and wiring for the peak, not the average.",
        "This is useful mechanical power out. Input power is higher by whatever "
        "the efficiency of the drivetrain is, and every watt of the difference "
        "turns into heat somewhere you have to cool.",
        "The current figures assume 100% conversion efficiency at a fixed bus "
        "voltage; they are an illustration, not a design value. A real ESC and "
        "motor draw appreciably more.",
        "A motor's continuous rating is a THERMAL limit, not a mechanical one. "
        "It can usually make several times that for a few seconds, and will "
        "cook itself if asked to hold it.",
        "Power is independent of how the work is done - lifting, pushing or "
        "spinning. Rotational power is the same quantity written as τ × ω.",
        "Battery packs have a current limit of their own (the C rating). A "
        "power figure a motor can take is not automatically one the pack can "
        "deliver.",
    ],
    graphs=[
        Sweep(over="work_j", y_label="Power P [W]", hi_factor=2.0,
              hi_min=100.0, title="Power vs work done"),
        Sweep(over="time_s", y_label="Power P [W]", lo_factor=0.2,
              hi_factor=3.0, hi_min=2.0,
              title="Power vs time allowed (the same job, done slower)"),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            f"{r * HP_PER_W:.1f} hp of useful output is a "
                            "serious machine - well beyond any hobby-scale "
                            "motor, and beyond what a small battery pack can "
                            "supply. Check the time you entered before "
                            "believing it.")
              if r > 1500.0 else None),
        Check(lambda i, r: ("info",
                            f"Over {i.time_s:g} s this is a PEAK figure. Most "
                            "motors will make several times their continuous "
                            "rating for a burst this short, so compare it "
                            "against the peak column of the datasheet, not the "
                            "continuous one.")
              if 0 < i.time_s < 0.5 else None),
        Check(lambda i, r: ("info",
                            "Negative work means the machine is absorbing "
                            "energy rather than delivering it - braking, or "
                            "lowering a load. That energy has to go somewhere: "
                            "into the battery if it can regenerate, into heat "
                            "if it cannot.")
              if i.work_j < 0 else None),
    ],
    references=[
        Reference(
            title="Continuous power of familiar machines",
            columns=("Source", "Useful output"),
            rows=[
                ("Person, comfortable cycling", "75 - 150 W"),
                ("Trained cyclist, one hour", "250 - 400 W"),
                ("Person, 10-second sprint", "700 - 1500 W"),
                ("E-bike motor (EU legal limit)", "250 W"),
                ("2212-class hobby BLDC motor", "100 - 200 W"),
                ("Racing quadcopter, per motor", "300 - 600 W"),
                ("Cordless drill", "300 - 600 W"),
                ("Domestic kettle", "2 - 3 kW"),
                ("Small car engine", "60 - 100 kW"),
            ],
            note="Useful output, not electrical input. Human figures are "
                 "mechanical output at the pedals; the metabolic cost is "
                 "roughly four times higher.",
        ),
    ],
    related=["mech.work", "rotational_mechanics.rotational_power",
             "flight.power_to_weight", "drone.power", "elec.power"],
    variables=[("$P$", "Power", "W"), ("$W$", "Work done", "J"),
               ("$t$", "Time taken", "s")],
    example=(
        "Drone climb performance. Lifting a 2 kg quad 50 m takes 981 J of work. "
        "Doing it in 10 s needs 98.1 W of useful climb power - 0.13 hp, or "
        "4.4 A at 22.2 V if everything were perfect - on top of the power "
        "already needed to hover. Ask for the same climb in 2 s and it becomes "
        "490 W, which is a completely different motor."),
    keywords=("power", "watt", "rate", "horsepower", "kw", "duty"),
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
        Secondary("Average force to stop it in 5 ms (rigid impact)", "N",
                  lambda i, r: abs(r) / 0.005),
        Secondary("Distance to stop it at 1 g braking", "m",
                  lambda i, r: i.velocity ** 2 / (2.0 * G0)),
        Secondary("Speed a stationary 10 kg body would gain absorbing it", "m/s",
                  lambda i, r: abs(r) / 10.0),
    ],
    assumptions=[
        "Non-relativistic speeds (anything far below the speed of light).",
        "Momentum is a vector. Adding momenta means adding components, not "
        "magnitudes - two bodies of equal and opposite momentum sum to zero.",
        "The stopping-force figures come from impulse: F × t = change in momentum, "
        "assuming a constant force over that time. Real impact forces peak well "
        "above their average, often by a factor of two or three.",
        "Momentum is conserved in a collision; kinetic energy generally is not. "
        "Anything that deforms, heats up or makes a noise has lost energy while "
        "keeping its momentum.",
        "The stopping distance assumes a constant 1 g and ignores what is doing "
        "the decelerating. Braking harder than the available friction allows "
        "simply means skidding.",
        "It is momentum that decides what a mount must react, but energy that "
        "decides what gets crushed. Size structure against both.",
    ],
    graphs=[
        Sweep(over="velocity", y_label="Momentum p [kg·m/s]", hi_factor=2.0,
              hi_min=10.0, title="Momentum vs velocity"),
        Sweep(over="mass", y_label="Momentum p [kg·m/s]", hi_factor=2.0,
              hi_min=1.0, title="Momentum vs mass"),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            f"Stopping this in 0.1 s takes "
                            f"{abs(r) / 0.1:,.0f} N - about "
                            f"{abs(r) / 0.1 / (i.mass * G0):.0f} times the "
                            "object's own weight. Mounts, fasteners and the "
                            "payload itself have to survive that, not just the "
                            "static load.")
              if i.mass > 0 and abs(r) / 0.1 > 5.0 * i.mass * G0 else None),
        Check(lambda i, r: ("info",
                            "A negative velocity just means the body is "
                            "travelling the other way. Momentum carries the "
                            "sign; kinetic energy does not.")
              if i.velocity < 0 else None),
        Check(lambda i, r: ("info",
                            f"At {abs(i.velocity):.0f} m/s this is faster than "
                            "the speed of sound in air. Impact behaviour "
                            "changes completely at these speeds - the material "
                            "cannot get out of the way fast enough and shock "
                            "waves, not bending, carry the load.")
              if abs(i.velocity) > 340.3 else None),
    ],
    references=[
        Reference(
            title="How long an impact actually lasts",
            columns=("What is hit", "Contact time"),
            rows=[
                ("Steel onto concrete, nothing crushes", "1 - 5 ms"),
                ("Rigid plastic shell cracking", "5 - 15 ms"),
                ("Crumpling airframe or crush structure", "20 - 50 ms"),
                ("Closed-cell foam bumper", "50 - 150 ms"),
                ("Catching a ball, arm giving way", "100 - 300 ms"),
            ],
            note="Approximate, and the only number in an impact calculation "
                 "you can actually design: the momentum is fixed by mass and "
                 "speed, so the only way to cut the force is to make the stop "
                 "last longer.",
        ),
    ],
    related=["mech.kinetic_energy", "mech.force", "mech.work",
             "materials.normal_stress"],
    variables=[("$p$", "Linear momentum", "kg·m/s"), ("$m$", "Mass", "kg"),
               ("$v$", "Velocity (signed)", "m/s")],
    example=(
        "Crash-protection design. A 2 kg drone hitting the ground at 15 m/s "
        "carries 30 kg·m/s. Stopping in 0.1 s (a crumpling frame) takes 300 N; "
        "stopping in 0.005 s (rigid concrete) takes 6000 N. That ratio is the "
        "whole argument for energy-absorbing structure: the momentum is the "
        "same in both cases, and only the time you allow for the stop is under "
        "your control."),
    keywords=("momentum", "impulse", "collision", "crash", "impact force",
              "conservation"),
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
        Secondary("In foot-pounds", "ft·lbf", lambda i, r: r * FT_LBF_PER_J),
        Secondary("Average force to stop it in 1 m", "N", lambda i, r: r / 1.0),
        Secondary("Power needed to reach this speed in 5 s", "W",
                  lambda i, r: r / 5.0),
    ],
    assumptions=[
        "Translational kinetic energy only. A spinning body also stores rotational "
        "energy, 0.5 I ω² (see Rotational mechanics) - on a flywheel or a "
        "propeller that term can be the larger of the two.",
        "Non-relativistic speeds.",
        "Velocity is relative to the chosen reference frame - ground speed and "
        "airspeed give different answers, and it is the closing speed that "
        "matters in an impact.",
        "Kinetic energy is not conserved in a real collision. It goes into "
        "permanent deformation, heat and noise, which is precisely how a crush "
        "structure protects what is behind it.",
        "The stopping force assumes the resisting force is constant over that "
        "distance. A real crush curve rises and falls, so the peak is higher "
        "than this average.",
        "Energy scales with the square of speed but only linearly with mass: "
        "shedding 20% of the speed does more for impact safety than shedding "
        "20% of the mass.",
    ],
    graphs=[
        Sweep(over="velocity", y_label="Kinetic energy [J]", hi_factor=2.0,
              hi_min=10.0, title="Kinetic energy vs speed (quadratic)"),
        Sweep(over="mass", y_label="Kinetic energy [J]", hi_factor=2.0,
              hi_min=1.0, title="Kinetic energy vs mass (linear)"),
    ],
    checks=[
        Check(lambda i, r: ("info",
                            "Speed is squared, so the direction makes no "
                            "difference: a body moving backwards at this speed "
                            "carries exactly the same kinetic energy. Momentum "
                            "is the quantity that keeps the sign.")
              if i.velocity < 0 else None),
        Check(lambda i, r: ("warning",
                            f"{r:,.0f} J is the energy this mass would have "
                            f"after falling {r / (i.mass * G0):.0f} m. At that "
                            "level the honest answer is containment - a guard, "
                            "a tether or a test cell - rather than a stronger "
                            "bracket.")
              if r > 500.0 else None),
        Check(lambda i, r: ("info",
                            "Above the speed of sound the material at the "
                            "impact point cannot flow out of the way in time, "
                            "and the energy goes into a shock wave. Ordinary "
                            "crush-structure reasoning stops applying.")
              if abs(i.velocity) > 340.3 else None),
    ],
    references=[
        Reference(
            title="Drop height and impact speed",
            columns=("Dropped from", "Hits at", "Energy per kg"),
            rows=[
                ("0.5 m", "3.1 m/s", "4.9 J"),
                ("1 m", "4.4 m/s", "9.8 J"),
                ("2 m", "6.3 m/s", "19.6 J"),
                ("5 m", "9.9 m/s", "49 J"),
                ("10 m", "14.0 m/s", "98 J"),
                ("30 m", "24.3 m/s", "294 J"),
                ("100 m", "44.3 m/s", "981 J"),
            ],
            note="v = sqrt(2 g h), ignoring air resistance, so these are upper "
                 "bounds. Anything light and bluffly shaped reaches terminal "
                 "velocity long before the 100 m row.",
        ),
        Reference(
            title="Kinetic energy of familiar things",
            columns=("Object", "Kinetic energy"),
            rows=[
                ("0.2 g airsoft BB at 100 m/s", "1.0 J"),
                ("25 g arrow at 60 m/s", "45 J"),
                ("1 kg hammer head at 10 m/s", "50 J"),
                ("145 g baseball at 40 m/s", "116 J"),
                ("2 kg drone at 15 m/s", "225 J"),
                ("8 g pistol bullet at 360 m/s", "518 J"),
                ("1500 kg car at 50 km/h", "145 kJ"),
            ],
            note="Each row is 0.5 m v² for the stated mass and speed, so you "
                 "can check any of them on this page.",
        ),
    ],
    related=["mech.momentum", "mech.potential_energy", "mech.work",
             "mech.power"],
    variables=[("$KE$", "Kinetic energy", "J"), ("$m$", "Mass", "kg"),
               ("$v$", "Speed", "m/s")],
    example=(
        "Safety analysis for flight over people. A 2 kg drone at 15 m/s carries "
        "225 J - the same energy it would have after falling 11.5 m, and about "
        "twice that of a baseball thrown at 40 m/s. Slowing the same drone to "
        "10 m/s drops it to 100 J: a 33% cut in speed removes 56% of the "
        "energy."),
    keywords=("kinetic", "ke", "energy", "impact", "half mv squared",
              "braking", "collision"),
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
