"""Robotics: drive kinematics, drivetrain sizing, actuators and encoders.

The calculators a student actually reaches for when building a robot rather
than analysing an aircraft. Reflected inertia in particular is rarely available
in free tools and is where most drivetrain sizing goes wrong.
"""
from __future__ import annotations

import numpy as np

from utils import validation as v
from utils.constants import G0
from utils.spec import Calculator, Field, Output, Secondary, Sweep

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def wheel_speed(rpm: float, radius: float) -> float:
    """v = omega * r = 2 pi r n / 60   [m/s]"""
    rpm = v.finite(rpm, "Wheel speed", "rpm")
    radius = v.positive(radius, "Wheel radius", "m")
    return 2.0 * np.pi * radius * rpm / 60.0


def body_velocity(v_left: float, v_right: float) -> float:
    """v = (v_r + v_l) / 2   [m/s] - the robot's forward speed."""
    v_left = v.finite(v_left, "Left wheel speed", "m/s")
    v_right = v.finite(v_right, "Right wheel speed", "m/s")
    return (v_right + v_left) / 2.0


def body_angular_velocity(v_left: float, v_right: float,
                          track_width: float) -> float:
    """omega = (v_r - v_l) / L   [rad/s], positive counter-clockwise."""
    v_left = v.finite(v_left, "Left wheel speed", "m/s")
    v_right = v.finite(v_right, "Right wheel speed", "m/s")
    track_width = v.positive(track_width, "Track width", "m")
    return (v_right - v_left) / track_width


def turn_radius(v_left: float, v_right: float, track_width: float) -> float:
    """R = (L/2)(v_r + v_l)/(v_r - v_l)   [m]

    Infinite when the wheels match, which is a straight line, not an error.
    """
    omega = body_angular_velocity(v_left, v_right, track_width)
    if omega == 0:
        return float("inf")
    return body_velocity(v_left, v_right) / omega


def reflected_inertia(load_inertia: float, ratio: float) -> float:
    """J_ref = J_load / N^2   [kg*m^2]

    Inertia reflects as 1/N squared while torque reflects as 1/N. Missing the
    square is the most common drivetrain sizing error.
    """
    load_inertia = v.non_negative(load_inertia, "Load inertia", "kg*m^2")
    ratio = v.positive(ratio, "Gear ratio")
    return load_inertia / ratio ** 2


def motor_torque_required(load_torque: float, load_inertia: float,
                          motor_inertia: float, ratio: float,
                          efficiency: float, load_acceleration: float) -> float:
    """Motor torque to drive a load through a reduction   [N*m]

        tau_m = tau_load/(N eta) + (J_m + J_load/N^2) * (N * alpha_load)

    The acceleration specified is the LOAD's, which is what a design actually
    calls for. The motor must then turn N times faster, so alpha_motor is
    N * alpha_load - and that is what gives the result a genuine minimum over
    gear ratio. With motor acceleration held fixed instead, the expression
    decreases monotonically toward J_m * alpha and there is no optimum to find.
    """
    load_torque = v.non_negative(load_torque, "Load torque", "N*m")
    motor_inertia = v.non_negative(motor_inertia, "Motor inertia", "kg*m^2")
    ratio = v.positive(ratio, "Gear ratio")
    efficiency = v.in_range(efficiency, "Gearbox efficiency", 0.05, 1.0)
    load_acceleration = v.finite(load_acceleration, "Load acceleration",
                                 "rad/s^2")
    total_inertia = motor_inertia + reflected_inertia(load_inertia, ratio)
    return (load_torque / (ratio * efficiency)
            + total_inertia * ratio * load_acceleration)


def torque_minimising_ratio(load_torque: float, load_inertia: float,
                            motor_inertia: float, efficiency: float,
                            load_acceleration: float) -> float:
    """The gear ratio needing the least motor torque.

    Differentiating the expression above and solving for zero:
        N^2 = (tau_load/eta + J_load * alpha_load) / (J_motor * alpha_load)
    """
    load_torque = v.non_negative(load_torque, "Load torque", "N*m")
    load_inertia = v.non_negative(load_inertia, "Load inertia", "kg*m^2")
    motor_inertia = v.positive(motor_inertia, "Motor inertia", "kg*m^2")
    efficiency = v.in_range(efficiency, "Gearbox efficiency", 0.05, 1.0)
    load_acceleration = v.positive(load_acceleration, "Load acceleration",
                                   "rad/s^2")
    numerator = load_torque / efficiency + load_inertia * load_acceleration
    return float(np.sqrt(numerator / (motor_inertia * load_acceleration)))


def optimal_ratio(load_inertia: float, motor_inertia: float) -> float:
    """N_opt = sqrt(J_load / J_motor) - inertia matching for peak acceleration."""
    load_inertia = v.non_negative(load_inertia, "Load inertia", "kg*m^2")
    motor_inertia = v.positive(motor_inertia, "Motor inertia", "kg*m^2")
    return float(np.sqrt(load_inertia / motor_inertia))


def arm_holding_torque(mass: float, length_to_cg: float,
                       angle_deg: float = 0.0) -> float:
    """tau = m g L cos(theta)   [N*m] - worst case is horizontal (theta = 0)."""
    mass = v.positive(mass, "Payload mass", "kg")
    length_to_cg = v.positive(length_to_cg, "Distance to centre of mass", "m")
    angle_deg = v.in_range(angle_deg, "Arm angle", -90.0, 90.0, "deg")
    return mass * G0 * length_to_cg * float(np.cos(np.radians(angle_deg)))


def encoder_resolution_deg(pulses_per_rev: int, gear_ratio: float = 1.0,
                           quadrature: bool = True) -> float:
    """Smallest measurable angle at the output   [deg]

    Quadrature decoding gives four counts per pulse (both edges of both
    channels), which is why CPR is 4x PPR.
    """
    pulses_per_rev = v.positive_int(pulses_per_rev, "Pulses per revolution")
    gear_ratio = v.positive(gear_ratio, "Gear ratio")
    counts = pulses_per_rev * (4 if quadrature else 1) * gear_ratio
    return 360.0 / counts


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def _diff_note(i, value):
    left = wheel_speed(i.rpm_left, i.wheel_radius)
    right = wheel_speed(i.rpm_right, i.wheel_radius)
    if left == right:
        return "Both wheels match, so the robot drives straight - turn radius is infinite."
    if left == -right:
        return "Equal and opposite: the robot spins in place about its own centre."
    return None


_DIFF_DRIVE = Calculator(
    slug="robot.differential_drive",
    name="Differential drive kinematics",
    latex=(r"v = \frac{v_r + v_l}{2}, \qquad \omega = \frac{v_r - v_l}{L}, "
           r"\qquad R = \frac{v}{\omega}"),
    explanation=(
        "Two independently driven wheels, which is how most small robots move. "
        "The average of the wheel speeds is how fast the robot goes; the "
        "difference is how fast it turns. Everything else - arc radius, heading "
        "rate, dead reckoning - follows from those two numbers."),
    inputs=[
        Field("wheel_radius", "Wheel radius r", "m", 0.04, min=0.0),
        Field("track_width", "Track width L", "m", 0.20, min=0.0,
              help="Measured between the wheel CONTACT PATCHES, not between "
                   "hubs or inner faces."),
        Field("rpm_left", "Left wheel speed", "rpm", 120.0),
        Field("rpm_right", "Right wheel speed", "rpm", 180.0),
    ],
    compute=lambda i: body_velocity(wheel_speed(i.rpm_left, i.wheel_radius),
                                    wheel_speed(i.rpm_right, i.wheel_radius)),
    result=Output("Forward speed v", "m/s"),
    secondary=[
        Secondary("Turn rate ω", "rad/s",
                  lambda i, r: body_angular_velocity(
                      wheel_speed(i.rpm_left, i.wheel_radius),
                      wheel_speed(i.rpm_right, i.wheel_radius), i.track_width)),
        Secondary("Turn rate", "°/s",
                  lambda i, r: float(np.degrees(body_angular_velocity(
                      wheel_speed(i.rpm_left, i.wheel_radius),
                      wheel_speed(i.rpm_right, i.wheel_radius), i.track_width)))),
        Secondary("Turn radius R", "m",
                  lambda i, r: turn_radius(
                      wheel_speed(i.rpm_left, i.wheel_radius),
                      wheel_speed(i.rpm_right, i.wheel_radius), i.track_width)),
        Secondary("Left / right wheel speed", "m/s",
                  lambda i, r: wheel_speed(i.rpm_left, i.wheel_radius)),
    ],
    note=_diff_note,
    assumptions=[
        "PURE ROLLING, no slip. Skid-steer robots - four or six wheels, or "
        "tracks - violate this by design: they must scrub sideways to turn. The "
        "model still works there but needs an EFFECTIVE track width calibrated "
        "by experiment, typically 1.2-1.5x the geometric one.",
        "Track width is measured between the wheel contact patches. Using the "
        "hub-to-hub distance is a common and quietly wrong substitution.",
        "Rigid wheels, flat ground, both wheels on a common axle.",
        "Sign convention: positive ω is counter-clockwise seen from above, and "
        "follows from v_r minus v_l in that order.",
        "Instantaneous kinematics. Dead reckoning by integrating these values "
        "accumulates error without bound - wheel slip and radius error grow "
        "linearly with distance travelled.",
    ],
    graph=Sweep(over="rpm_right", y_label="Forward speed v [m/s]",
                lo_factor=0.0, hi_factor=2.0,
                title="Forward speed vs right-wheel speed (the left wheel is "
                      "held fixed)"),
    variables=[
        ("$v$", "Forward speed of the robot body", "m/s"),
        ("$\\omega$", "Turn rate about the body centre", "rad/s"),
        ("$v_l, v_r$", "Left and right wheel ground speeds", "m/s"),
        ("$L$", "Track width, contact patch to contact patch", "m"),
        ("$R$", "Radius of the arc being driven", "m"),
    ],
    example=(
        "Driving an arc. With 40 mm wheels on a 200 mm track, running the left "
        "wheel at 120 rpm and the right at 180 rpm gives 0.63 m/s forward while "
        "turning at 1.26 rad/s - an arc of half a metre radius. Matching the "
        "wheels straightens it; reversing one spins it on the spot."),
    keywords=("differential", "drive", "kinematics", "wheels", "odometry",
              "skid steer", "turn radius"),
)

_GEAR_INERTIA = Calculator(
    slug="robot.reflected_inertia",
    name="Gear train: reflected inertia",
    latex=(r"J_{ref} = \frac{J_{load}}{N^{2}}, \qquad "
           r"\tau_m = \frac{\tau_{load}}{N\,\eta} + "
           r"\left(J_m + \frac{J_{load}}{N^{2}}\right)\alpha"),
    explanation=(
        "What the motor actually feels through a gearbox. Torque reflects as "
        "1/N but inertia reflects as <b>1/N²</b> - missing that square is the "
        "most common drivetrain sizing error. It also means required motor "
        "torque has a genuine minimum: too little reduction and the load "
        "dominates, too much and accelerating the motor's own rotor does."),
    inputs=[
        Field("ratio", "Gear ratio N", "-", 10.0, min=0.0,
              help="Reduction: motor turns N times per output turn."),
        Field("load_torque", "Load torque at the output", "N·m", 2.0, min=0.0),
        Field("load_inertia", "Load inertia J_load", "kg·m²", 0.02, min=0.0,
              help="Use the Moment of inertia page to work this out."),
        Field("motor_inertia", "Motor rotor inertia J_m", "kg·m²", 1.5e-5,
              min=0.0),
        Field("efficiency", "Gearbox efficiency η", "-", 0.90, min=0.05,
              max=1.0, help="Spur stage 0.97 each; worm drive 0.4-0.7."),
        Field("acceleration", "Required output acceleration α", "rad/s²", 20.0,
              help="At the LOAD, not the motor. The motor turns N times faster, "
                   "which is what gives the torque curve a minimum."),
    ],
    compute=lambda i: motor_torque_required(i.load_torque, i.load_inertia,
                                            i.motor_inertia, i.ratio,
                                            i.efficiency, i.acceleration),
    result=Output("Required motor torque", "N·m"),
    secondary=[
        Secondary("Reflected load inertia", "kg·m²",
                  lambda i, r: reflected_inertia(i.load_inertia, i.ratio)),
        Secondary("Inertia ratio J_ref / J_motor", "-",
                  lambda i, r: reflected_inertia(i.load_inertia, i.ratio)
                  / i.motor_inertia),
        Secondary("Ratio needing the least motor torque", "-",
                  lambda i, r: torque_minimising_ratio(
                      i.load_torque, i.load_inertia, i.motor_inertia,
                      i.efficiency, i.acceleration)),
        Secondary("Inertia-matched ratio (peak load acceleration)", "-",
                  lambda i, r: optimal_ratio(i.load_inertia, i.motor_inertia)),
        Secondary("Output torque delivered", "N·m",
                  lambda i, r: i.load_torque),
    ],
    note=lambda i, r: (
        "Inertia ratio above 10:1 - the load dominates and the loop will be "
        "hard to tune. Servo vendors generally want under 5:1, ideally under 3."
        if reflected_inertia(i.load_inertia, i.ratio) / i.motor_inertia > 10
        else None),
    assumptions=[
        "Rigid, backlash-free gearing. Real gearheads have 0.1-1° of backlash "
        "and finite torsional stiffness, and that - not the motor - usually "
        "limits achievable control bandwidth.",
        "Constant efficiency. Real efficiency falls at light load, and a worm "
        "drive may not back-drive at all.",
        "Efficiency divides torque going up through the reduction. Driving the "
        "load backwards reverses which side pays the loss.",
        "Acceleration is specified at the OUTPUT. The motor turns N times "
        "faster, so its own rotor inertia costs more torque as the ratio rises "
        "- which is why the curve has a minimum rather than falling forever.",
        "The inertia-matched ratio sqrt(J_load/J_motor) maximises load "
        "acceleration for a given motor torque. That is a different question "
        "from which ratio needs the least torque, and the two answers differ.",
    ],
    # Log scale on purpose: the 1/N term dominates so far that on a linear axis
    # the curve reads as a plain hyperbola and the minimum - the entire point of
    # the plot - is invisible. On a log axis both branches show as a V.
    graph=Sweep(over="ratio", y_label="Required motor torque [N·m]",
                lo_factor=0.15, hi_factor=30.0, log_y=True,
                title="Required motor torque vs gear ratio (log scale) - "
                      "under-gear and the load dominates, over-gear and the "
                      "motor's own rotor does"),
    variables=[
        ("$N$", "Gear ratio (reduction)", "-"),
        ("$J_{load}$", "Load inertia at the output", "kg·m²"),
        ("$J_{ref}$", "Load inertia as the motor feels it", "kg·m²"),
        ("$J_m$", "Motor rotor inertia", "kg·m²"),
        ("$\\eta$", "Gearbox efficiency", "-"),
        ("$\\alpha$", "Angular acceleration at the motor", "rad/s²"),
    ],
    example=(
        "Sizing a joint drive. A 0.02 kg·m² load through 10:1 reflects as only "
        "2.0e-4 kg·m² at the motor - a hundredth of the raw figure. Halve the "
        "ratio to 5:1 and the reflected inertia quadruples to 8.0e-4, which is "
        "why an under-geared joint feels sluggish however strong the motor is. "
        "Gear too far the other way and the motor spends its torque "
        "accelerating its own rotor instead."),
    keywords=("gear", "reflected inertia", "drivetrain", "servo", "sizing",
              "inertia ratio", "backlash"),
)

_SERVO_TORQUE = Calculator(
    slug="robot.servo_torque",
    name="Servo / arm holding torque",
    latex=r"\tau = m\,g\,L\,\cos\theta",
    explanation=(
        "What it takes to hold a load out on an arm. Worst case is horizontal, "
        "where the full moment applies; at vertical it is nothing. Servo "
        "datasheets quote <b>stall</b> torque in kgf·cm - a torque wearing a "
        "mass label - and continuous capability is far lower."),
    inputs=[
        Field("mass", "Payload mass m", "kg", 0.5, min=0.0),
        Field("length", "Distance to centre of mass L", "m", 0.15, min=0.0),
        Field("angle", "Arm angle above horizontal θ", "°", 0.0, min=-90.0,
              max=90.0, help="0° is horizontal, the worst case."),
        Field("safety", "Safety factor", "-", 2.5, min=1.0,
              help="2-3 is usual, because the rating is stall torque."),
    ],
    compute=lambda i: arm_holding_torque(i.mass, i.length, i.angle),
    result=Output("Holding torque required", "N·m"),
    secondary=[
        Secondary("In kgf·cm (servo datasheet units)", "kgf·cm",
                  lambda i, r: r / G0 * 100.0),
        Secondary("In oz·in", "oz·in", lambda i, r: r * 141.612),
        Secondary("With safety factor applied", "N·m",
                  lambda i, r: r * i.safety),
        Secondary("Servo to specify (stall rating)", "kgf·cm",
                  lambda i, r: r * i.safety / G0 * 100.0),
    ],
    assumptions=[
        "Static holding only. Accelerating the arm needs J × α on top, and a "
        "sudden stop can need several times the holding torque.",
        "Servo ratings are STALL torque at a stated voltage. Continuous duty is "
        "typically 30-50% of stall - sizing to the stall figure burns servos.",
        "The arm's own mass is ignored. Include it by adding its mass at its "
        "own centre of mass, or lump it in above.",
        "kgf·cm and oz·in are torque units despite the mass-sounding names. "
        "1 kgf·cm = 0.0980665 N·m; 1 oz·in = 0.00706 N·m.",
        "Gravity only. Springs, counterweights or a four-bar can offload most "
        "of this and are worth considering before a bigger servo.",
    ],
    graph=Sweep(over="length", y_label="Holding torque [N·m]", lo_factor=0.0,
                hi_factor=2.5,
                title="Torque vs arm length - linear, and why long arms need "
                      "gearboxes not bigger servos"),
    variables=[
        ("$\\tau$", "Torque the actuator must hold", "N·m"),
        ("$m$", "Payload mass", "kg"),
        ("$L$", "Distance from pivot to centre of mass", "m"),
        ("$\\theta$", "Arm angle above horizontal", "°"),
    ],
    example=(
        "Picking a servo. Holding 500 g at 150 mm horizontally needs 0.736 N·m, "
        "which is 7.5 kgf·cm. With a 2.5x factor for stall-rated parts you want "
        "about 19 kgf·cm - so a 20 kgf·cm servo, not the 10 kgf·cm one the raw "
        "number suggests."),
    keywords=("servo", "torque", "arm", "holding", "kgcm", "actuator", "sizing"),
)

_ENCODER = Calculator(
    slug="robot.encoder_resolution",
    name="Encoder resolution",
    latex=r"\Delta\theta = \frac{360°}{4 \times PPR \times N}",
    explanation=(
        "The smallest movement a robot can actually measure - the floor on "
        "position accuracy no amount of control tuning can beat. Quadrature "
        "decoding reads both edges of both channels, giving <b>four counts per "
        "pulse</b>, and a gearbox between encoder and output multiplies "
        "resolution by the ratio."),
    inputs=[
        Field("ppr", "Pulses per revolution (PPR)", "", 500, min=1, kind="int",
              help="Per channel, before quadrature. Datasheets sometimes quote "
                   "the post-quadrature count as 'PPR' to look better."),
        Field("gear_ratio", "Gear ratio between encoder and output", "-", 10.0,
              min=0.0, help="1 if the encoder is on the output shaft."),
        Field("wheel_diameter", "Wheel / pulley diameter", "m", 0.08, min=0.0,
              help="For the linear resolution at the rim."),
    ],
    compute=lambda i: encoder_resolution_deg(i.ppr, i.gear_ratio),
    result=Output("Angular resolution at the output", "°"),
    secondary=[
        Secondary("Counts per output revolution", "counts",
                  lambda i, r: i.ppr * 4 * i.gear_ratio),
        Secondary("Quadrature counts per encoder revolution", "CPR",
                  lambda i, r: i.ppr * 4),
        Secondary("Linear resolution at the rim", "mm",
                  lambda i, r: np.pi * i.wheel_diameter * 1000.0
                  / (i.ppr * 4 * i.gear_ratio)),
        Secondary("In arcminutes", "arcmin", lambda i, r: r * 60.0),
    ],
    assumptions=[
        "PPR, CPR, 'lines' and 'counts' are used inconsistently across "
        "datasheets. Quadrature gives 4 counts per pulse per channel pair; if a "
        "figure already includes that, do not multiply again.",
        "Ideal decoding with no missed counts. At high speed a slow interrupt "
        "or polling loop drops counts and the error never comes back.",
        "Resolution is not accuracy: eccentricity, disc tolerance and backlash "
        "in the gearbox all add error beyond this floor.",
        "Measuring velocity by differencing position gives poor resolution at "
        "low speed. Timing the interval between counts is the usual fix.",
    ],
    graph=Sweep(over="gear_ratio", y_label="Angular resolution [°]",
                lo_factor=0.1, hi_factor=3.0, log_y=True,
                title="Resolution vs gear ratio (log scale) - gearing down "
                      "multiplies resolution"),
    variables=[
        ("$\\Delta\\theta$", "Smallest measurable angle at the output", "°"),
        ("$PPR$", "Pulses per revolution, per channel", "-"),
        ("$N$", "Gear ratio between encoder and output", "-"),
    ],
    example=(
        "Odometry accuracy. A 500 PPR encoder behind a 10:1 gearbox gives 2000 "
        "counts per motor turn and 20,000 per output turn - 0.018° per count. "
        "On an 80 mm wheel that is 0.013 mm of travel, so wheel slip, not "
        "encoder resolution, is what limits dead reckoning."),
    keywords=("encoder", "quadrature", "ppr", "cpr", "resolution", "odometry"),
)

CALCULATORS = [_DIFF_DRIVE, _GEAR_INERTIA, _SERVO_TORQUE, _ENCODER]
