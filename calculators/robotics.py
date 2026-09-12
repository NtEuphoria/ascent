"""Robotics: drive kinematics, drivetrain sizing, actuators and encoders.

The calculators a student actually reaches for when building a robot rather
than analysing an aircraft. Reflected inertia in particular is rarely available
in free tools and is where most drivetrain sizing goes wrong.

A note on symbols, because this app carries three quantities under two letters:

  * **I [kg*m^2]** - mass moment of inertia, "how hard this is to spin up".
  * **I [m^4]**    - second moment of AREA, a property of a cross-section,
                     used in beam bending (see `struct.second_moment`).
  * **J [m^4]**    - polar second moment of area, the torsion equivalent.

This module only ever means the first one, and writes it **J** because that is
the letter every motor and gearbox datasheet uses (J_m, J_load). It is a mass
moment of inertia in kg*m^2, not an area moment in m^4.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

from utils import validation as v
from utils.constants import G0
from utils.spec import (Calculator, Check, Field, Output, Reference, Secondary,
                        Sweep)

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


def lateral_acceleration(v_left: float, v_right: float,
                         track_width: float) -> float:
    """a_lat = v * omega = v^2 / R   [m/s^2]

    What the tyres have to supply to hold the arc. Compare it with mu * g:
    above that the robot understeers out of the turn however good the
    controller is, because friction has run out.
    """
    forward = body_velocity(v_left, v_right)
    omega = body_angular_velocity(v_left, v_right, track_width)
    return forward * omega


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


def encoder_count_rate(pulses_per_rev: int, rpm: float,
                       quadrature: bool = True) -> float:
    """Counts per second the decoder must keep up with   [1/s]

    f = PPR * 4 * rpm / 60. This is the number that decides whether the
    counting can be done in software at all: miss an edge and the position
    error is permanent, because a quadrature count carries no absolute
    reference to recover from.
    """
    pulses_per_rev = v.positive_int(pulses_per_rev, "Pulses per revolution")
    rpm = v.non_negative(rpm, "Shaft speed", "rpm")
    return pulses_per_rev * (4 if quadrature else 1) * rpm / 60.0


def two_link_reach(link1: float, link2: float) -> Tuple[float, float]:
    """(inner, outer) radius of the annulus a two-link arm can reach   [m]

    Outer is l1 + l2, straight out. Inner is |l1 - l2|, folded back on itself -
    and it is a hole in the workspace, not a point: with unequal links there is
    a disc around the shoulder the hand simply cannot enter.
    """
    link1 = v.positive(link1, "Upper arm length", "m")
    link2 = v.positive(link2, "Forearm length", "m")
    return abs(link1 - link2), link1 + link2


def two_link_ik(link1: float, link2: float, x: float, y: float,
                elbow_down: bool = True) -> Tuple[float, float]:
    """Inverse kinematics of a planar two-link arm -> (theta1, theta2)   [deg]

    theta1 is measured from the +x axis, theta2 from the upper arm. The
    reachability test happens BEFORE the arccos, because the cosine of the
    elbow angle leaves [-1, 1] the moment the target is outside the workspace
    and a bare arccos would return a domain error instead of the real reason.

    Two solutions always exist inside the workspace and both are valid: they
    are mirror images about the shoulder-to-hand line. elbow_down=True gives
    theta2 > 0.
    """
    link1 = v.positive(link1, "Upper arm length", "m")
    link2 = v.positive(link2, "Forearm length", "m")
    x = v.finite(x, "Target x", "m")
    y = v.finite(y, "Target y", "m")

    radius = float(np.hypot(x, y))
    inner, outer = two_link_reach(link1, link2)
    tolerance = 1e-12 + 1e-9 * outer
    if radius > outer + tolerance:
        raise v.ValidationError(
            f"Target is {radius:.4g} m from the shoulder but the arm only "
            f"reaches {outer:.4g} m. Move the target closer or lengthen a link."
        )
    if radius < inner - tolerance:
        raise v.ValidationError(
            f"Target is {radius:.4g} m from the shoulder, inside the "
            f"{inner:.4g} m dead zone the folded arm cannot enter. Move the "
            f"target further out, or make the two links closer in length."
        )

    cosine = (radius ** 2 - link1 ** 2 - link2 ** 2) / (2.0 * link1 * link2)
    cosine = min(1.0, max(-1.0, cosine))        # kill rounding at the boundary
    theta2 = float(np.arccos(cosine))
    if not elbow_down:
        theta2 = -theta2
    theta1 = float(np.arctan2(y, x)
                   - np.arctan2(link2 * np.sin(theta2),
                                link1 + link2 * np.cos(theta2)))
    return float(np.degrees(theta1)), float(np.degrees(theta2))


def two_link_forward(link1: float, link2: float, theta1_deg: float,
                     theta2_deg: float) -> Tuple[float, float]:
    """Forward kinematics -> hand position (x, y)   [m]

    Kept alongside the inverse so the page can show its own working: feeding
    the angles back through this must land on the target.
    """
    link1 = v.positive(link1, "Upper arm length", "m")
    link2 = v.positive(link2, "Forearm length", "m")
    a = np.radians(v.finite(theta1_deg, "Shoulder angle", "deg"))
    b = a + np.radians(v.finite(theta2_deg, "Elbow angle", "deg"))
    return (float(link1 * np.cos(a) + link2 * np.cos(b)),
            float(link1 * np.sin(a) + link2 * np.sin(b)))


def two_link_manipulability(link1: float, link2: float,
                            theta2_deg: float) -> float:
    """w = l1 * l2 * |sin(theta2)|   [m^2]

    The determinant of the arm's Jacobian, and the standard measure of how
    well it can move in every direction at once. It falls to zero at both
    workspace boundaries - fully extended and fully folded - which is exactly
    where a small hand movement demands an enormous joint rate.
    """
    link1 = v.positive(link1, "Upper arm length", "m")
    link2 = v.positive(link2, "Forearm length", "m")
    theta2_deg = v.finite(theta2_deg, "Elbow angle", "deg")
    return link1 * link2 * abs(float(np.sin(np.radians(theta2_deg))))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def _wheels(i):
    """(left, right) ground speeds for the differential-drive page."""
    return (wheel_speed(i.rpm_left, i.wheel_radius),
            wheel_speed(i.rpm_right, i.wheel_radius))


def _diff_note(i, value):
    left, right = _wheels(i)
    if left == right:
        return "Both wheels match, so the robot drives straight - turn radius is infinite."
    if left == -right:
        return "Equal and opposite: the robot spins in place about its own centre."
    return None


def _diff_straight_check(i, result):
    left, right = _wheels(i)
    if left != right:
        return None
    return ("info",
            "The wheels are commanded to the same speed, so the heading rate "
            "is exactly zero and the turn radius is infinite. That is the "
            "degenerate case of R = v/omega, not an error - but note that real "
            "wheels never match: a 1% radius difference between them curves a "
            "nominally straight 10 m run by roughly half a metre.")


def _diff_pivot_check(i, result):
    left, right = _wheels(i)
    radius = turn_radius(left, right, i.track_width)
    if not np.isfinite(radius) or abs(radius) >= i.track_width / 2.0:
        return None
    return ("warning",
            f"Turn radius {abs(radius):.3g} m is inside the half-track "
            f"({i.track_width / 2:.3g} m), so the centre of rotation lies "
            "between the wheels and the inner wheel must run BACKWARDS. A "
            "two-wheel robot does this happily; a four-wheel or tracked "
            "skid-steer chassis cannot, and will scrub, slip and draw far more "
            "current than this model predicts.")


def _diff_traction_check(i, result):
    left, right = _wheels(i)
    lateral = abs(lateral_acceleration(left, right, i.track_width))
    if lateral < 0.4 * G0:
        return None
    return ("warning",
            f"Holding this arc needs {lateral:.2f} m/s^2 sideways, which is "
            f"{lateral / G0:.2f} g. Rubber on a clean hard floor gives about "
            "0.7-0.9 g before it slides and a tall robot may tip before that, "
            "so the wheels will most likely slip and the robot will run wide "
            "of the commanded path.")


_DIFF_DRIVE = Calculator(
    slug="robot.differential_drive",
    name="Differential drive kinematics",
    latex=(r"v = \frac{v_r + v_l}{2}, \qquad \omega = \frac{v_r - v_l}{L}, "
           r"\qquad R = \frac{v}{\omega}"),
    explanation=(
        "Two independently driven wheels, which is how most small robots move. "
        "The average of the wheel speeds is how fast the robot goes; the "
        "difference is how fast it turns. Both follow from one geometric fact: "
        "at any instant the whole chassis is rotating about a single point on "
        "the wheel axle, the <b>instantaneous centre of curvature</b>, and both "
        "wheels must sweep the same angle about it per second. Everything else "
        "- arc radius, heading rate, dead reckoning - is bookkeeping on top."),
    inputs=[
        Field("wheel_radius", "Wheel radius r", "m", 0.04, min=0.0),
        Field("track_width", "Track width L", "m", 0.20, min=0.0,
              help="Measured between the wheel CONTACT PATCHES, not between "
                   "hubs or inner faces."),
        Field("rpm_left", "Left wheel speed", "rpm", 120.0),
        Field("rpm_right", "Right wheel speed", "rpm", 180.0),
    ],
    compute=lambda i: body_velocity(*_wheels(i)),
    result=Output("Forward speed v", "m/s"),
    secondary=[
        Secondary("Turn rate ω", "rad/s",
                  lambda i, r: body_angular_velocity(*_wheels(i),
                                                     i.track_width)),
        Secondary("Turn rate", "°/s",
                  lambda i, r: float(np.degrees(
                      body_angular_velocity(*_wheels(i), i.track_width)))),
        Secondary("Turn radius R (to the ICC)", "m",
                  lambda i, r: turn_radius(*_wheels(i), i.track_width)),
        Secondary("Circle driven by the body centre", "m diameter",
                  lambda i, r: 2.0 * abs(turn_radius(*_wheels(i),
                                                     i.track_width))),
        Secondary("Left wheel ground speed", "m/s", lambda i, r: _wheels(i)[0]),
        Secondary("Right wheel ground speed", "m/s", lambda i, r: _wheels(i)[1]),
        Secondary("Lateral acceleration in the turn", "m/s²",
                  lambda i, r: abs(lateral_acceleration(*_wheels(i),
                                                        i.track_width))),
    ],
    note=_diff_note,
    assumptions=[
        "PURE ROLLING, no slip. <b>Skid-steer robots violate this by design</b>: "
        "four wheels or two tracks cannot all roll around one centre, so they "
        "must scrub sideways to turn at all. The model still works there but "
        "needs an EFFECTIVE track width calibrated by experiment - spin the "
        "robot ten turns, measure the heading error, scale L. It typically "
        "comes out 1.2-1.5x the geometric value on carpet and closer to 1.0x "
        "on a smooth hard floor.",
        "Track width is measured between the wheel contact patches. Using the "
        "hub-to-hub distance is a common and quietly wrong substitution: on a "
        "200 mm robot with 15 mm wide tyres it is a 7% heading-rate error, "
        "which is 25 degrees lost over a single full turn.",
        "Rigid wheels of equal radius, flat ground, both wheels on a common "
        "axle. Unequal radii - a soft tyre, a heavier battery on one side - "
        "bias every straight line into a slow arc.",
        "Sign convention: positive ω is counter-clockwise seen from above, and "
        "follows from v_r minus v_l in that order. Swap the order and every "
        "heading in your odometry runs backwards.",
        "Instantaneous kinematics. Dead reckoning by integrating these values "
        "accumulates error without bound - wheel slip and radius error grow "
        "linearly with distance, heading error grows and then multiplies every "
        "later position estimate. Something absolute (IMU heading, a wall, a "
        "landmark) has to close the loop eventually.",
        "No dynamics. The wheels are assumed to reach the commanded speeds "
        "instantly; in reality motor torque, traction and the chassis's own "
        "rotational inertia all limit how fast ω can change.",
        "Lateral acceleration is assumed to be within the friction available. "
        "Above roughly mu*g the tyres let go and the robot runs wide - no "
        "amount of control tuning recovers a wheel that is already sliding.",
    ],
    graphs=[
        Sweep(over="rpm_right", y_label="Forward speed v [m/s]",
              lo_factor=0.0, hi_factor=2.0,
              title="Forward speed vs right-wheel speed (the left wheel is "
                    "held fixed)"),
        Sweep(over="rpm_left", y_label="Forward speed v [m/s]",
              lo=0.0, hi_factor=2.0,
              title="Forward speed vs left-wheel speed (the right wheel is "
                    "held fixed)"),
        Sweep(over="wheel_radius", y_label="Forward speed v [m/s]",
              lo_factor=0.2, hi_factor=2.0,
              title="Forward speed vs wheel radius - speed is linear in "
                    "radius, and so is every odometry error in it"),
    ],
    checks=[
        Check(_diff_straight_check),
        Check(_diff_pivot_check),
        Check(_diff_traction_check),
    ],
    references=[
        Reference(
            title="Ground speed per 100 rpm",
            columns=("Wheel diameter", "Circumference", "At 100 rpm",
                     "At 300 rpm"),
            rows=[
                ("32 mm (micro / line follower)", "0.101 m", "0.168 m/s",
                 "0.503 m/s"),
                ("60 mm", "0.188 m", "0.314 m/s", "0.942 m/s"),
                ("65 mm (Pololu / hobby gearmotor)", "0.204 m", "0.340 m/s",
                 "1.02 m/s"),
                ("80 mm", "0.251 m", "0.419 m/s", "1.26 m/s"),
                ("100 mm", "0.314 m", "0.524 m/s", "1.57 m/s"),
                ("152 mm (6 in competition wheel)", "0.478 m", "0.796 m/s",
                 "2.39 m/s"),
            ],
            note="Exact from v = 2*pi*r*n/60 - these are arithmetic, not "
                 "estimates. Use them to sanity-check a gearmotor choice "
                 "before buying: a 'fast' 300 rpm motor on 32 mm wheels is "
                 "still only walking pace.",
        ),
        Reference(
            title="Drive geometry of real platforms",
            columns=("Platform", "Wheel radius", "Track width"),
            rows=[
                ("TurtleBot3 Burger", "33 mm", "160 mm"),
                ("TurtleBot3 Waffle Pi", "33 mm", "287 mm"),
                ("iRobot Create 2 / Roomba 600", "36 mm", "235 mm"),
            ],
            note="Published nominal figures from each platform's own "
                 "configuration or interface specification. They are the "
                 "GEOMETRIC values; the effective track width a skid-steer "
                 "controller wants is found by calibration and is usually "
                 "larger. Always measure your own chassis.",
        ),
    ],
    related=["robot.encoder_resolution", "robot.reflected_inertia",
             "rotational_mechanics.angular_velocity_(rpm_to_rad/s)",
             "rotational_mechanics.centripetal_force", "mech.gear_ratio"],
    variables=[
        ("$v$", "Forward speed of the robot body", "m/s"),
        ("$\\omega$", "Turn rate about the body centre", "rad/s"),
        ("$v_l, v_r$", "Left and right wheel ground speeds", "m/s"),
        ("$L$", "Track width, contact patch to contact patch", "m"),
        ("$R$", "Radius of the arc being driven - the distance from the body "
                "centre to the instantaneous centre of curvature (ICC)", "m"),
        ("$r$", "Wheel radius", "m"),
        ("$n$", "Wheel speed", "rpm"),
    ],
    example=(
        "Driving an arc. With 40 mm wheels on a 200 mm track, running the left "
        "wheel at 120 rpm and the right at 180 rpm gives wheel ground speeds of "
        "0.503 and 0.754 m/s, so the body moves at <b>0.628 m/s</b> while "
        "turning at 1.257 rad/s (72 °/s) - an arc of exactly 0.5 m radius, a "
        "1.0 m circle completed in 5.0 s. That arc needs only 0.79 m/s² "
        "sideways (0.08 g), so traction is nowhere near the limit. Matching the "
        "wheels straightens it; reversing one spins it on the spot."),
    keywords=("differential", "drive", "kinematics", "wheels", "odometry",
              "skid steer", "turn radius", "icc", "dead reckoning", "unicycle",
              "track width", "wheel separation", "scrub"),
)


def _gear_optimum_check(i, result):
    best = torque_minimising_ratio(i.load_torque, i.load_inertia,
                                   i.motor_inertia, i.efficiency,
                                   i.acceleration)
    if 0.5 * best <= i.ratio <= 2.0 * best:
        return None
    least = motor_torque_required(i.load_torque, i.load_inertia,
                                  i.motor_inertia, best, i.efficiency,
                                  i.acceleration)
    if least <= 0:
        return None
    side = "under-geared" if i.ratio < best else "over-geared"
    return ("info",
            f"At N = {i.ratio:g} this job is {side}: it needs "
            f"{result / least:.1f}x the motor torque of the best ratio. "
            f"N = {best:.1f} would do the same work with {least:.3g} N·m. "
            "Below the optimum the load torque dominates; above it the motor "
            "is mostly accelerating its own rotor.")


def _gear_efficiency_check(i, result):
    if i.efficiency > 0.6:
        return None
    return ("warning",
            f"An efficiency of {i.efficiency:g} is worm-drive or "
            "high-ratio-harmonic territory. Two consequences this equation "
            "does not show: the losses become heat in the gearbox, and a worm "
            "set below about 0.5 efficiency usually will not BACK-DRIVE at "
            "all. That is free holding torque if you want it and a jammed, "
            "un-hand-movable joint if you do not.")


def _gear_overdrive_check(i, result):
    if i.ratio >= 1.0:
        return None
    return ("warning",
            f"N = {i.ratio:g} is a speed INCREASER, not a reduction. The load "
            "inertia is multiplied by 1/N² instead of divided, so the motor "
            f"now feels {1 / i.ratio ** 2:.1f}x the load's own inertia, and it "
            "gets the load torque multiplied too. If that was not deliberate, "
            "N should be greater than 1.")


_GEAR_INERTIA = Calculator(
    slug="robot.reflected_inertia",
    name="Gear train: reflected inertia",
    latex=(r"J_{ref} = \frac{J_{load}}{N^{2}}, \qquad "
           r"\tau_m = \frac{\tau_{load}}{N\,\eta} + "
           r"\left(J_m + \frac{J_{load}}{N^{2}}\right) N\,\alpha_{load}"),
    explanation=(
        "What the motor actually feels through a gearbox. Torque reflects as "
        "1/N but inertia reflects as <b>1/N²</b> - missing that square is the "
        "most common drivetrain sizing error. It also means required motor "
        "torque has a genuine minimum: too little reduction and the load "
        "torque dominates, too much and the motor spends everything "
        "accelerating its own rotor, because the rotor has to turn N times "
        "faster than the thing you actually wanted to move."),
    inputs=[
        Field("ratio", "Gear ratio N", "-", 10.0, min=0.0,
              help="Reduction: motor turns N times per output turn."),
        Field("load_torque", "Load torque at the output", "N·m", 2.0, min=0.0),
        Field("load_inertia", "Load inertia J_load", "kg·m²", 0.02, min=0.0,
              help="Mass moment of inertia in kg·m², not a beam's second "
                   "moment of area. Use the Moment of inertia page."),
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
        Secondary("Reflected load inertia J_ref", "kg·m²",
                  lambda i, r: reflected_inertia(i.load_inertia, i.ratio)),
        Secondary("Inertia ratio J_ref / J_motor", "-",
                  lambda i, r: reflected_inertia(i.load_inertia, i.ratio)
                  / i.motor_inertia),
        Secondary("Ratio needing the least motor torque", "-",
                  lambda i, r: torque_minimising_ratio(
                      i.load_torque, i.load_inertia, i.motor_inertia,
                      i.efficiency, i.acceleration)),
        Secondary("Motor torque at that ratio", "N·m",
                  lambda i, r: motor_torque_required(
                      i.load_torque, i.load_inertia, i.motor_inertia,
                      torque_minimising_ratio(
                          i.load_torque, i.load_inertia, i.motor_inertia,
                          i.efficiency, i.acceleration),
                      i.efficiency, i.acceleration)),
        Secondary("Inertia-matched ratio (peak load acceleration)", "-",
                  lambda i, r: optimal_ratio(i.load_inertia, i.motor_inertia)),
        Secondary("Motor acceleration N·α", "rad/s²",
                  lambda i, r: i.ratio * i.acceleration),
        Secondary("Share of torque spent accelerating inertia", "%",
                  lambda i, r: 100.0
                  * (i.motor_inertia
                     + reflected_inertia(i.load_inertia, i.ratio))
                  * i.ratio * i.acceleration / r),
    ],
    note=lambda i, r: (
        "Inertia ratio above 10:1 - the load dominates and the loop will be "
        "hard to tune. Servo vendors generally want under 5:1, ideally under 3."
        if reflected_inertia(i.load_inertia, i.ratio) / i.motor_inertia > 10
        else None),
    assumptions=[
        "<b>J here is a MASS moment of inertia in kg·m²</b> - resistance to "
        "angular acceleration. It is not the polar second moment of area J in "
        "m⁴ used for shaft torsion, and not the second moment of area I in m⁴ "
        "used for beam bending. Same letters, different quantities, different "
        "units; mixing them up produces an answer wrong by many orders of "
        "magnitude.",
        "Rigid, backlash-free gearing. Real gearheads have 0.1-1° of backlash "
        "and finite torsional stiffness, and that - not the motor - usually "
        "limits achievable control bandwidth. Backlash inside a position loop "
        "shows up as limit-cycle hunting that no gain will remove.",
        "Constant efficiency. Real efficiency falls at light load, falls "
        "further when cold, and a worm drive may not back-drive at all.",
        "Efficiency divides torque going up through the reduction. Driving the "
        "load backwards - lowering a mass, decelerating a flywheel - reverses "
        "which side pays the loss, so the motor sees MORE regenerated torque "
        "than η would suggest, not less.",
        "Acceleration is specified at the OUTPUT. The motor turns N times "
        "faster, so its own rotor inertia costs more torque as the ratio rises "
        "- which is why the curve has a minimum rather than falling forever.",
        "The inertia-matched ratio sqrt(J_load/J_motor) maximises load "
        "acceleration for a given motor torque. That is a different question "
        "from which ratio needs the least torque, and the two answers differ "
        "whenever there is any static load torque at all.",
        "The gearbox's own inertia is ignored. On a high-ratio planetary the "
        "first-stage carrier spins at nearly motor speed and can add 10-50% to "
        "the effective rotor inertia - check the gearhead datasheet.",
        "Nothing here checks SPEED. A ratio that minimises torque may leave "
        "the motor past its no-load speed at the required output rate; size "
        "for the torque-speed operating point, not torque alone.",
    ],
    graphs=[
        # Log scale on purpose: the 1/N term dominates so far that on a linear
        # axis the curve reads as a plain hyperbola and the minimum - the
        # entire point of the plot - is invisible. On a log axis both branches
        # show as a V.
        Sweep(over="ratio", y_label="Required motor torque [N·m]",
              lo_factor=0.15, hi_factor=30.0, log_y=True,
              title="Required motor torque vs gear ratio (log scale) - "
                    "under-gear and the load dominates, over-gear and the "
                    "motor's own rotor does"),
        Sweep(over="load_inertia", y_label="Required motor torque [N·m]",
              lo=0.0, hi_factor=3.0,
              title="Torque vs load inertia - the slope is α·N/N², so a high "
                    "ratio flattens this line"),
        Sweep(over="acceleration", y_label="Required motor torque [N·m]",
              lo=0.0, hi_factor=3.0,
              title="Torque vs demanded output acceleration - the intercept "
                    "is the static load, the slope is everything spinning"),
        Sweep(over="efficiency", y_label="Required motor torque [N·m]",
              lo=0.05, hi_factor=1.0, hi_min=1.0,
              title="Torque vs gearbox efficiency - only the static term "
                    "suffers, which is why worm drives hurt holding loads most"),
    ],
    checks=[
        Check(_gear_optimum_check),
        Check(_gear_efficiency_check),
        Check(_gear_overdrive_check),
    ],
    references=[
        Reference(
            title="Gearbox efficiency by type",
            columns=("Type", "Efficiency per stage", "Typical use"),
            rows=[
                ("Spur gear", "0.96 - 0.98", "Most robot gearheads"),
                ("Helical gear", "0.97 - 0.99", "Quieter, higher load"),
                ("Planetary", "0.95 - 0.98", "Compact, coaxial, 3-10:1/stage"),
                ("Bevel / mitre", "0.94 - 0.97", "Right-angle drives"),
                ("Toothed belt", "0.95 - 0.98", "Remote, compliant, quiet"),
                ("Cycloidal", "0.85 - 0.95", "High ratio, low backlash"),
                ("Harmonic (strain wave)", "0.70 - 0.90", "50-160:1 in one "
                                                          "stage, zero backlash"),
                ("Worm, single start", "0.40 - 0.70", "High ratio, usually "
                                                      "self-locking"),
            ],
            note="Ranges at rated load and temperature. Efficiency is PER "
                 "STAGE and multiplies: three spur stages at 0.97 give "
                 "0.97³ = 0.91, not 0.97. At light load and when cold, every "
                 "figure here is optimistic.",
        ),
        Reference(
            title="Inertia ratio targets (J_ref / J_motor)",
            columns=("Ratio", "What to expect"),
            rows=[
                ("under 1:1", "Motor rotor dominates. Easy to tune, but you "
                              "are over-geared and wasting torque and speed."),
                ("1:1 - 3:1", "Sweet spot for a high-bandwidth servo axis."),
                ("3:1 - 5:1", "Normal industrial practice; tunes well."),
                ("5:1 - 10:1", "Workable with stiff coupling and good "
                               "feedback; expect slower response."),
                ("over 10:1", "Load dominates. Any compliance in the "
                              "drivetrain shows up as resonance and the loop "
                              "becomes hard to tune at all."),
            ],
            note="Vendor rules of thumb for motion control, not hard limits - "
                 "a stiff direct-coupled load tolerates far more than a long "
                 "belt drive. They assume the drivetrain between motor and "
                 "load is rigid; if it is not, the number that matters is the "
                 "resonant frequency, not the ratio.",
        ),
    ],
    related=["rotational_mechanics.moment_of_inertia", "mech.gear_ratio",
             "prop.motor_constants", "robot.servo_torque", "mech.torque"],
    variables=[
        ("$N$", "Gear ratio (reduction: motor turns N times per output turn)",
         "-"),
        ("$J_{load}$", "Load MASS moment of inertia at the output", "kg·m²"),
        ("$J_{ref}$", "Load inertia as the motor feels it", "kg·m²"),
        ("$J_m$", "Motor rotor mass moment of inertia", "kg·m²"),
        ("$\\tau_{load}$", "Static torque at the output", "N·m"),
        ("$\\tau_m$", "Torque the motor must produce", "N·m"),
        ("$\\eta$", "Gearbox efficiency", "-"),
        ("$\\alpha_{load}$", "Angular acceleration at the OUTPUT (the motor's "
                             "own is N times this)", "rad/s²"),
    ],
    example=(
        "Sizing a joint drive. A 0.02 kg·m² load that needs 2 N·m held and "
        "20 rad/s² of acceleration, through a 10:1 gearbox at 90% onto a rotor "
        "of 1.5e-5 kg·m², asks the motor for <b>0.265 N·m</b>. The load reflects "
        "as only 2.0e-4 kg·m² - a hundredth of the raw figure - but that is "
        "still 13x the rotor's own inertia, so the loop will be sluggish. "
        "Halve the ratio to 5:1 and reflected inertia quadruples to 8.0e-4 and "
        "the motor torque doubles to 0.526 N·m. Push the other way to N = 93 "
        "and it bottoms out at 0.056 N·m, a fifth of the 10:1 figure; by "
        "N = 300 it has climbed back to 0.099 N·m, all of it spent spinning "
        "the rotor."),
    keywords=("gear", "reflected inertia", "drivetrain", "servo", "sizing",
              "inertia ratio", "backlash", "gearbox", "reduction",
              "inertia matching", "worm", "harmonic drive"),
)


def _servo_angle_check(i, result):
    if abs(i.angle) <= 60.0:
        return None
    worst = arm_holding_torque(i.mass, i.length, 0.0)
    return ("info",
            f"At {i.angle:g}° the cos θ term has hidden most of the load: this "
            f"is {result:.3g} N·m, but swing the arm to horizontal and the "
            f"same payload needs {worst:.3g} N·m "
            f"({worst / G0 * 100:.1f} kgf·cm). Size for the horizontal case "
            "unless the arm is mechanically stopped from ever reaching it.")


def _servo_class_check(i, result):
    rating = result * i.safety / G0 * 100.0
    if rating <= 35.0:
        return None
    return ("warning",
            f"You are asking for a {rating:.0f} kgf·cm stall rating. That is "
            "past ordinary hobby servos, where the output spline and the "
            "plastic horn become the weak point long before the motor does. "
            "Above roughly 35 kgf·cm, look at a geared DC motor with an "
            "encoder, a smart serial servo with a metal output bearing, or "
            "a counterweight/gas spring that removes the load instead.")


def _servo_factor_check(i, result):
    if i.safety >= 2.0:
        return None
    return ("warning",
            f"A safety factor of {i.safety:g} on a STALL torque rating is "
            "thin. A servo at stall is drawing locked-rotor current and "
            "heating fast; continuous capability is typically 30-50% of the "
            "rating. Sizing an arm that must hold position all day at 1.5x "
            "stall-rated torque is how servos burn out.")


_SERVO_TORQUE = Calculator(
    slug="robot.servo_torque",
    name="Servo / arm holding torque",
    latex=r"\tau = m\,g\,L\,\cos\theta",
    explanation=(
        "What it takes to hold a load out on an arm. Only the component of "
        "the weight perpendicular to the arm makes a moment, which is where "
        "the cosine comes from: worst case is horizontal, where the full "
        "moment applies, and at vertical it is nothing. Servo datasheets quote "
        "<b>stall</b> torque in kgf·cm - a torque wearing a mass label - and "
        "continuous capability is far lower."),
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
        Secondary("Worst case, arm horizontal", "N·m",
                  lambda i, r: arm_holding_torque(i.mass, i.length, 0.0)),
        Secondary("With safety factor applied", "N·m",
                  lambda i, r: r * i.safety),
        Secondary("Servo to specify (stall rating)", "kgf·cm",
                  lambda i, r: r * i.safety / G0 * 100.0),
        Secondary("Weight of the payload", "N", lambda i, r: i.mass * G0),
    ],
    assumptions=[
        "Static holding only. Accelerating the arm needs J·α on top, and a "
        "sudden stop can need several times the holding torque - an arm caught "
        "at the end of a fast slew is an impact, not a load.",
        "Servo ratings are STALL torque at a stated voltage, and they scale "
        "with that voltage: a servo quoted at 6.0 V loses roughly 20% at "
        "4.8 V. Continuous duty is typically 30-50% of stall - sizing to the "
        "stall figure burns servos.",
        "The arm's own mass is ignored. Include it by adding its weight at its "
        "own centre of mass (for a uniform bar, at L/2), or lump it into m "
        "above. On a long light-payload arm the structure often dominates.",
        "kgf·cm and oz·in are torque units despite the mass-sounding names. "
        "1 kgf·cm = 0.0980665 N·m; 1 oz·in = 0.0070616 N·m. A 'kg' on a servo "
        "box means kgf·cm at 1 cm, which is why the arm length matters so much.",
        "Gravity only. Springs, counterweights or a four-bar can offload most "
        "of this and are worth considering before a bigger servo - a "
        "counterbalanced joint can be an order of magnitude cheaper to drive.",
        "No friction, no preload, no cable drag. Harness routed across a joint "
        "can add a surprisingly large and very non-linear torque.",
        "The torque is what the OUTPUT SHAFT must produce. The horn, the "
        "spline and the arm's own bolted joint have to carry it too, and on "
        "hobby servos those usually fail first.",
    ],
    graphs=[
        Sweep(over="length", y_label="Holding torque [N·m]", lo_factor=0.0,
              hi_factor=2.5,
              title="Torque vs arm length - linear, and why long arms need "
                    "gearboxes not bigger servos"),
        Sweep(over="mass", y_label="Holding torque [N·m]", lo=0.0,
              hi_factor=3.0,
              title="Torque vs payload mass - also linear, so doubling the "
                    "gripper doubles the servo"),
        Sweep(over="angle", y_label="Holding torque [N·m]", lo=-90.0,
              hi_factor=1.0, hi_min=90.0,
              title="Torque vs arm angle - the cosine, flat-topped at "
                    "horizontal, which is why the worst case is a broad one"),
    ],
    checks=[
        Check(_servo_angle_check),
        Check(_servo_class_check),
        Check(_servo_factor_check),
    ],
    references=[
        Reference(
            title="Torque units on servo datasheets",
            columns=("1 of this", "in N·m", "in kgf·cm", "in oz·in"),
            rows=[
                ("N·m", "1", "10.197", "141.61"),
                ("kgf·cm (\"kg·cm\", \"kg\")", "0.0980665", "1", "13.887"),
                ("oz·in", "0.0070616", "0.072008", "1"),
                ("lbf·in", "0.11298", "1.1521", "16"),
                ("N·mm", "0.001", "0.010197", "0.14161"),
            ],
            note="Exact conversions, using g = 9.80665 m/s². 'kg·cm' on a "
                 "datasheet always means kgf·cm - kilogram-FORCE - and is a "
                 "torque, not a mass. The 16 oz·in per lbf·in is exact by "
                 "definition.",
        ),
        Reference(
            title="Stall torque by servo class",
            columns=("Class", "Typical stall torque", "Example"),
            rows=[
                ("Micro, 9 g plastic gear", "1.5 - 2.5 kgf·cm @ 4.8 V",
                 "SG90-type"),
                ("Standard, plastic gear", "3 - 4 kgf·cm @ 4.8 V",
                 "HS-422-type"),
                ("Standard, metal gear", "9 - 13 kgf·cm @ 4.8-6 V",
                 "MG996R-type"),
                ("High torque, metal gear", "20 - 35 kgf·cm @ 6-7.4 V",
                 "Large scale/digital"),
                ("Smart serial servo, small", "~15 kgf·cm (1.5 N·m) @ 12 V",
                 "Dynamixel AX-12A"),
                ("Smart serial servo, mid", "~25 kgf·cm (2.5 N·m) @ 12 V",
                 "Dynamixel MX-28"),
            ],
            note="Manufacturer STALL figures at the stated voltage, which is "
                 "the number on the box and the most optimistic one there is. "
                 "Continuous capability is roughly a third to a half of these, "
                 "and every figure drops with supply voltage. Check the actual "
                 "datasheet for the part you buy.",
        ),
    ],
    related=["robot.two_link_arm", "robot.reflected_inertia", "mech.torque",
             "rotational_mechanics.moment_of_inertia",
             "mech.mechanical_advantage"],
    variables=[
        ("$\\tau$", "Torque the actuator must hold", "N·m"),
        ("$m$", "Payload mass", "kg"),
        ("$g$", "Standard gravity, 9.80665", "m/s²"),
        ("$L$", "Distance from pivot to centre of mass", "m"),
        ("$\\theta$", "Arm angle above horizontal (0° = horizontal)", "°"),
    ],
    example=(
        "Picking a servo. Holding 500 g at 150 mm horizontally needs "
        "<b>0.7355 N·m</b>, which is 7.50 kgf·cm or 104 oz·in. With a 2.5x "
        "factor for stall-rated parts you want about 18.8 kgf·cm - so a 20 "
        "kgf·cm servo, not the 10 kgf·cm one the raw number suggests. Raise "
        "the arm to 60° and the requirement halves to 0.368 N·m (3.75 kgf·cm), "
        "which is exactly the trap: size at the angle you tested, and the "
        "first time the arm swings out level it stalls."),
    keywords=("servo", "torque", "arm", "holding", "kgcm", "kgf cm", "oz in",
              "actuator", "sizing", "stall torque", "gripper", "payload"),
)


def _encoder_rate_check(i, result):
    rate = encoder_count_rate(i.ppr, 1000.0)
    if rate <= 100_000.0:
        return None
    return ("warning",
            f"At 1000 rpm this encoder produces {rate:,.0f} counts per second. "
            "Software decoding on an interrupt typically tops out around "
            "10-50 kHz before it starves everything else; above that you need "
            "a hardware quadrature peripheral or a dedicated counter chip. A "
            "missed count is permanent - incremental encoders have no absolute "
            "reference to recover from.")


def _encoder_overdrive_check(i, result):
    if i.gear_ratio >= 1.0:
        return None
    return ("info",
            f"A ratio of {i.gear_ratio:g} means the output turns FASTER than "
            "the encoder, so resolution at the output gets worse, not better. "
            "Mounting the encoder on the fast side of a reduction is the "
            "cheapest resolution you will ever buy - and the reason motor-side "
            "encoders are the norm.")


def _encoder_slip_check(i, result):
    linear_mm = np.pi * i.wheel_diameter * 1000.0 / (i.ppr * 4 * i.gear_ratio)
    if linear_mm > 0.05:
        return None
    return ("info",
            f"One count is {linear_mm:.4g} mm of travel at the rim - far finer "
            "than any wheel actually holds. Tyre compression, wheel-radius "
            "tolerance and a few percent of slip all swamp this, so dead "
            "reckoning here is limited by traction, not by counting. Extra PPR "
            "buys smoother VELOCITY estimates, not a better position fix.")


_ENCODER = Calculator(
    slug="robot.encoder_resolution",
    name="Encoder resolution",
    latex=r"\Delta\theta = \frac{360°}{4 \times PPR \times N}",
    explanation=(
        "The smallest movement a robot can actually measure - the floor on "
        "position accuracy no amount of control tuning can beat. Quadrature "
        "decoding reads both edges of both channels, giving <b>four counts per "
        "pulse</b>, and a gearbox between encoder and output multiplies "
        "resolution by the ratio. The factor of four is the single most common "
        "off-by-4x error in robotics: it turns up as odometry that is exactly "
        "four times too far, or a PID loop tuned against gains four times too "
        "small."),
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
        Secondary("Counts per millimetre of travel", "counts/mm",
                  lambda i, r: (i.ppr * 4 * i.gear_ratio)
                  / (np.pi * i.wheel_diameter * 1000.0)),
        Secondary("In arcminutes", "arcmin", lambda i, r: r * 60.0),
        Secondary("In arcseconds", "arcsec", lambda i, r: r * 3600.0),
        Secondary("Count rate at 1000 rpm (encoder shaft)", "counts/s",
                  lambda i, r: encoder_count_rate(i.ppr, 1000.0)),
    ],
    assumptions=[
        "PPR, CPR, 'lines' and 'counts' are used inconsistently across "
        "datasheets. Quadrature gives 4 counts per pulse per channel pair; if a "
        "figure already includes that, do not multiply again. When in doubt, "
        "turn the shaft exactly one revolution by hand and print the count.",
        "Ideal decoding with no missed counts. At high speed a slow interrupt "
        "or polling loop drops counts and the error never comes back - an "
        "incremental encoder has no absolute reference to re-zero against.",
        "Resolution is not accuracy. Disc eccentricity, bearing play, "
        "quadrature phase error and above all GEARBOX BACKLASH add error far "
        "beyond this floor; a 0.018° resolution behind 0.5° of backlash is "
        "0.5° of real uncertainty.",
        "The gear ratio is assumed to be between the encoder and the point you "
        "care about. An encoder on the motor shaft measures the motor, so "
        "everything compliant or lost between there and the output - belt "
        "stretch, backlash, a slipping grub screw - is invisible to it.",
        "Measuring velocity by differencing position gives poor resolution at "
        "low speed: at one count per sample the velocity estimate is all "
        "quantisation noise. Timing the interval between counts instead is the "
        "usual fix.",
        "Index/Z channel is ignored. Without one, the zero is wherever the "
        "robot happened to be at power-up, and a homing routine is not "
        "optional.",
    ],
    graphs=[
        Sweep(over="gear_ratio", y_label="Angular resolution [°]",
              lo_factor=0.1, hi_factor=3.0, log_y=True,
              title="Resolution vs gear ratio (log scale) - gearing down "
                    "multiplies resolution"),
        Sweep(over="ppr", y_label="Angular resolution [°]",
              lo_factor=0.02, hi_factor=4.0, log_y=True,
              title="Resolution vs encoder PPR (log scale) - a straight line, "
                    "so buying 4x the PPR buys exactly 4x the resolution"),
    ],
    checks=[
        Check(_encoder_rate_check),
        Check(_encoder_overdrive_check),
        Check(_encoder_slip_check),
    ],
    references=[
        Reference(
            title="Common encoder resolutions (1:1, 80 mm wheel)",
            columns=("PPR", "Counts/rev (x4)", "Degrees per count",
                     "Arcsec per count", "mm at an 80 mm wheel"),
            rows=[
                ("8", "32", "11.25", "40,500", "7.85"),
                ("16", "64", "5.625", "20,250", "3.93"),
                ("64", "256", "1.406", "5,063", "0.982"),
                ("100", "400", "0.900", "3,240", "0.628"),
                ("250", "1000", "0.360", "1,296", "0.251"),
                ("256", "1024", "0.3516", "1,266", "0.245"),
                ("360", "1440", "0.250", "900", "0.175"),
                ("500", "2000", "0.180", "648", "0.126"),
                ("1000", "4000", "0.0900", "324", "0.0628"),
                ("2048", "8192", "0.0439", "158", "0.0307"),
                ("4096", "16384", "0.0220", "79.1", "0.0153"),
            ],
            note="Exact arithmetic from 360°/(4·PPR), with no gearbox. Add a "
                 "reduction and every figure divides by the ratio. The small "
                 "PPR values are typical of magnetic encoders moulded into "
                 "hobby gearmotors; 1000 and above are optical.",
        ),
        Reference(
            title="What the words on the datasheet mean",
            columns=("Term", "Usually means", "To get counts per rev"),
            rows=[
                ("PPR, pulses per revolution", "Cycles on ONE channel",
                 "x 4"),
                ("Lines, LPR", "Slots or magnetic poles on the disc", "x 4"),
                ("Cycles, CPR (cycles)", "Full A/B cycles", "x 4"),
                ("CPR (counts per revolution)", "Already post-quadrature",
                 "x 1"),
                ("Quadrature counts, edges", "Already post-quadrature", "x 1"),
                ("Steps (stepper motor)", "Full steps, not an encoder at all",
                 "no feedback"),
            ],
            note="CPR is the dangerous one: it is used for both 'cycles' and "
                 "'counts', which differ by exactly the factor of 4 this page "
                 "is about. The only safe reading is the one you verify by "
                 "turning the shaft one revolution and watching the counter.",
        ),
    ],
    related=["robot.differential_drive", "robot.reflected_inertia", "ctrl.pid",
             "ctrl.second_order", "mech.gear_ratio"],
    variables=[
        ("$\\Delta\\theta$", "Smallest measurable angle at the output", "°"),
        ("$PPR$", "Pulses per revolution, per channel", "-"),
        ("$N$", "Gear ratio between encoder and output", "-"),
        ("$4$", "Quadrature factor: both edges of both channels", "-"),
    ],
    example=(
        "Odometry accuracy. A 500 PPR encoder gives 2000 counts per motor turn; "
        "behind a 10:1 gearbox that is 20,000 per output turn, or <b>0.018°</b> "
        "per count - 1.08 arcminutes, 64.8 arcseconds. On an 80 mm wheel that "
        "is 0.0126 mm of travel, about 80 counts per millimetre, so wheel slip "
        "and tyre compression, not encoder resolution, are what limit dead "
        "reckoning. The same encoder spinning at 1000 rpm emits 33,333 counts "
        "per second, which a hardware quadrature timer handles easily and a "
        "naive interrupt handler does not."),
    keywords=("encoder", "quadrature", "ppr", "cpr", "resolution", "odometry",
              "counts", "arcminute", "lines", "incremental", "index"),
)


def _arm_note(i, result):
    theta1, theta2 = two_link_ik(i.l1, i.l2, i.x, i.y)
    hand_x, hand_y = two_link_forward(i.l1, i.l2, theta1, theta2)
    return (f"Check: driving the joints to θ₁ = {theta1:.2f}°, "
            f"θ₂ = {theta2:.2f}° puts the hand at "
            f"({hand_x:.4f}, {hand_y:.4f}) m - the target, to rounding.")


def _arm_extension_check(i, result):
    radius = float(np.hypot(i.x, i.y))
    _, outer = two_link_reach(i.l1, i.l2)
    if radius <= 0.98 * outer:
        return None
    return ("warning",
            f"The target is at {radius:.4g} m, which is "
            f"{100 * radius / outer:.1f}% of the {outer:.4g} m maximum reach - "
            "effectively full extension. This is a SINGULARITY: the arm has "
            "lost the ability to move radially at all, the Jacobian "
            "determinant l₁l₂sin θ₂ has gone to zero, and an inverse-kinematics "
            "controller will demand enormous joint rates for a millimetre of "
            "hand motion. Keep the working area inside about 90% of reach.")


def _arm_folded_check(i, result):
    radius = float(np.hypot(i.x, i.y))
    inner, _ = two_link_reach(i.l1, i.l2)
    if inner <= 0 or radius >= 1.05 * inner:
        return None
    return ("warning",
            f"The target is at {radius:.4g} m, just outside the {inner:.4g} m "
            "dead zone. The arm is folded back on itself here, which is the "
            "same singularity as full extension seen from the other side: "
            "sin θ₂ is near zero again, the two links are nearly collinear, "
            "and the elbow will also be close to colliding with the upper arm.")


def _arm_elbow_check(i, result):
    theta1, _ = two_link_ik(i.l1, i.l2, i.x, i.y, elbow_down=True)
    elbow_y = i.l1 * float(np.sin(np.radians(theta1)))
    if elbow_y >= 0.0:
        return None
    return ("info",
            f"The elbow-down solution puts the elbow {abs(elbow_y) * 1000:.0f} "
            "mm BELOW the shoulder. If this arm is bolted to a table at "
            "shoulder height, that solution drives the elbow through the "
            "table - use the elbow-up angles instead. Both are valid "
            "kinematically; only one is valid in the room.")


_TWO_LINK_ARM = Calculator(
    slug="robot.two_link_arm",
    name="Two-link arm: inverse kinematics",
    latex=(r"\cos\theta_2 = \frac{x^2 + y^2 - l_1^2 - l_2^2}{2\,l_1 l_2}, "
           r"\qquad \theta_1 = \mathrm{atan2}(y,x) - "
           r"\mathrm{atan2}\!\left(l_2\sin\theta_2,\; "
           r"l_1 + l_2\cos\theta_2\right)"),
    explanation=(
        "Forward kinematics - angles to position - is a substitution. Inverse "
        "kinematics is the hard direction and the one a robot actually needs: "
        "given a point, what must the joints do? For two links in a plane it "
        "closes in one line of trigonometry, and everything awkward about real "
        "manipulators is already visible here: the answer may not exist "
        "(outside the workspace), there may be <b>two</b> of them (elbow-up "
        "and elbow-down), and at the edges of reach it becomes infinitely "
        "sensitive."),
    inputs=[
        Field("l1", "Upper arm length l₁", "m", 0.25, min=0.0,
              help="Shoulder to elbow."),
        Field("l2", "Forearm length l₂", "m", 0.20, min=0.0,
              help="Elbow to hand."),
        Field("x", "Target x", "m", 0.30,
              help="Measured from the shoulder. May be negative."),
        Field("y", "Target y", "m", 0.10,
              help="Measured from the shoulder. Positive is up."),
    ],
    compute=lambda i: two_link_ik(i.l1, i.l2, i.x, i.y, elbow_down=True)[1],
    result=Output("Elbow angle θ₂ (elbow-down)", "°"),
    secondary=[
        Secondary("Shoulder angle θ₁ (elbow-down)", "°",
                  lambda i, r: two_link_ik(i.l1, i.l2, i.x, i.y, True)[0]),
        Secondary("Elbow angle θ₂ (elbow-up)", "°",
                  lambda i, r: two_link_ik(i.l1, i.l2, i.x, i.y, False)[1]),
        Secondary("Shoulder angle θ₁ (elbow-up)", "°",
                  lambda i, r: two_link_ik(i.l1, i.l2, i.x, i.y, False)[0]),
        Secondary("Distance to the target r", "m",
                  lambda i, r: float(np.hypot(i.x, i.y))),
        Secondary("Maximum reach l₁ + l₂", "m",
                  lambda i, r: two_link_reach(i.l1, i.l2)[1]),
        Secondary("Dead-zone radius |l₁ − l₂|", "m",
                  lambda i, r: two_link_reach(i.l1, i.l2)[0]),
        Secondary("Fraction of maximum reach used", "%",
                  lambda i, r: 100.0 * float(np.hypot(i.x, i.y))
                  / two_link_reach(i.l1, i.l2)[1]),
        Secondary("Manipulability l₁l₂|sin θ₂|", "m²",
                  lambda i, r: two_link_manipulability(i.l1, i.l2, r)),
    ],
    note=_arm_note,
    assumptions=[
        "<b>Reachability is checked before the arccos, not after.</b> Outside "
        "the workspace the cosine of the elbow angle leaves [-1, 1] and a bare "
        "arccos returns a domain error that tells you nothing; this page tests "
        "the radius first so it can say which boundary you crossed and by how "
        "much.",
        "BOTH solutions are correct. Elbow-up and elbow-down are mirror images "
        "about the line from shoulder to hand and put the hand in exactly the "
        "same place. Choosing between them is a question about the room - the "
        "table, the workpiece, the cable loom - not about the mathematics. A "
        "planner that switches between them mid-trajectory will make the arm "
        "flail through a large, fast, unplanned motion.",
        "At full extension (θ₂ = 0°) and fully folded (θ₂ = ±180°) the arm is "
        "SINGULAR: the two solutions merge, the Jacobian determinant "
        "l₁l₂sin θ₂ is zero, and hand motion along the radius becomes "
        "impossible while the joint rates required blow up. Keep the working "
        "envelope inside roughly 90% of reach.",
        "Unequal links leave a hole. The workspace is an annulus between "
        "|l₁ − l₂| and l₁ + l₂, so a short forearm buys reach at the cost of a "
        "dead disc around the shoulder that the hand cannot enter at all. "
        "Equal links remove the hole and, for a fixed total length, also give "
        "the largest workspace area (4π l₁l₂ is maximised when l₁ = l₂).",
        "Purely geometric, with no joint limits. A real shoulder and elbow "
        "have end stops, and roughly half of the mathematically valid "
        "solutions are usually unreachable because of them. Nothing here "
        "checks self-collision either.",
        "Planar and rigid. Gravity droop, link flex and gearbox backlash all "
        "move the real hand away from the computed point, and they do it most "
        "where the arm is most extended - exactly where the geometry is "
        "already worst behaved.",
        "θ₁ is measured from the +x axis and θ₂ from the upper arm's own "
        "direction (a relative, not absolute, elbow angle). Absolute elbow "
        "angle is θ₁ + θ₂. Mixing the two conventions is the classic sign "
        "bug in a hand-written IK routine.",
    ],
    graphs=[
        Sweep(over="x", y_label="Elbow angle θ₂ [°]", lo=0.0, hi_factor=1.6,
              title="Elbow angle vs target x - the curve simply stops where "
                    "the target leaves the workspace"),
        Sweep(over="y", y_label="Elbow angle θ₂ [°]", lo=0.0, hi_factor=3.0,
              title="Elbow angle vs target height y - reaching up folds the "
                    "elbow, because the distance to the shoulder falls first "
                    "and then rises"),
        Sweep(over="l2", y_label="Elbow angle θ₂ [°]", lo_factor=0.4,
              hi_factor=2.0,
              title="Elbow angle vs forearm length - a longer forearm reaches "
                    "the same point with a more folded elbow"),
    ],
    checks=[
        Check(_arm_extension_check),
        Check(_arm_folded_check),
        Check(_arm_elbow_check),
    ],
    references=[
        Reference(
            title="Workspace shape vs link ratio (for l₁ = 1)",
            columns=("l₂ / l₁", "Maximum reach", "Dead-zone radius",
                     "Workspace area (4π l₁l₂)", "Shape"),
            rows=[
                ("1.00", "2.00", "0.00", "12.57", "Full disc - no dead zone"),
                ("0.80", "1.80", "0.20", "10.05", "Annulus"),
                ("0.60", "1.60", "0.40", "7.54", "Annulus"),
                ("0.50", "1.50", "0.50", "6.28", "Annulus"),
                ("0.33", "1.33", "0.67", "4.15", "Annulus, large hole"),
            ],
            note="All in units of l₁ (and l₁² for area). Exact geometry, not "
                 "estimates. For a FIXED total length l₁ + l₂ the area 4π l₁l₂ "
                 "is largest when the links are equal - which is why most "
                 "two-link arms are drawn with a forearm close to the upper "
                 "arm in length. Real arms shorten the forearm anyway, to keep "
                 "the payload's moment on the shoulder down.",
        ),
        Reference(
            title="How well the arm moves at each elbow angle",
            columns=("Elbow angle θ₂", "|sin θ₂|", "Condition"),
            rows=[
                ("0° or 180°", "0.000", "Singular - fully extended or fully "
                                        "folded, no radial motion possible"),
                ("±15° / ±165°", "0.259", "Very poor - near a boundary"),
                ("±30° / ±150°", "0.500", "Usable, half the best case"),
                ("±45° / ±135°", "0.707", "Good"),
                ("±60° / ±120°", "0.866", "Very good"),
                ("±90°", "1.000", "Best conditioned - the arm moves equally "
                                  "well in every direction"),
            ],
            note="Manipulability w = l₁l₂|sin θ₂| is the determinant of this "
                 "arm's Jacobian (Yoshikawa's measure), so it is exact rather "
                 "than a rule of thumb. It says how much hand velocity you get "
                 "per unit of joint velocity in the worst direction - zero at "
                 "the boundaries, best at a right-angled elbow.",
        ),
    ],
    related=["robot.servo_torque", "robot.reflected_inertia",
             "robot.encoder_resolution", "mech.torque",
             "rotational_mechanics.moment_of_inertia"],
    variables=[
        ("$l_1$", "Upper arm length, shoulder to elbow", "m"),
        ("$l_2$", "Forearm length, elbow to hand", "m"),
        ("$x, y$", "Target position of the hand, measured from the shoulder",
         "m"),
        ("$r$", "Distance from shoulder to target, $\\sqrt{x^2+y^2}$", "m"),
        ("$\\theta_1$", "Shoulder angle, from the +x axis", "°"),
        ("$\\theta_2$", "Elbow angle, relative to the upper arm", "°"),
        ("$w$", "Manipulability, $l_1 l_2 |\\sin\\theta_2|$", "m²"),
    ],
    example=(
        "A small pick-and-place arm with a 250 mm upper arm and a 200 mm "
        "forearm, reaching for a part at (300, 100) mm. The target is 316.2 mm "
        "away - inside the 450 mm reach and outside the 50 mm dead zone, so it "
        "is reachable, at 70.3% of full extension. Elbow-down gives "
        "θ₁ = −20.78°, <b>θ₂ = +91.43°</b>; elbow-up gives θ₁ = +57.65°, "
        "θ₂ = −91.43°. Both put the hand on the part. The elbow-down solution "
        "puts the elbow 89 mm below the shoulder, so on a table-mounted arm "
        "you want elbow-up. The elbow is near 90°, so the arm is close to its "
        "best-conditioned posture - manipulability 0.0500 m² against a maximum "
        "of 0.0500 m²."),
    keywords=("inverse kinematics", "ik", "two link", "planar arm",
              "manipulator", "elbow up", "elbow down", "workspace", "reach",
              "singularity", "jacobian", "manipulability", "scara"),
)

CALCULATORS = [_DIFF_DRIVE, _GEAR_INERTIA, _SERVO_TORQUE, _ENCODER,
               _TWO_LINK_ARM]
