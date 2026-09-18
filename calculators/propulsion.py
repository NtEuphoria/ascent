"""Propulsion: momentum theory, hover power, propellers, motors, rockets.

Everything hover-related in v1.0.0 was bookkeeping - thrust sums, watt-hours.
Momentum theory is the first physics here that explains *why* hovering costs
what it costs, and it is the foundation the rest of rotor performance sits on.

Two conventions run through this module and are easy to confuse, so both are
stated explicitly on the pages that use them:

  * Propeller coefficients use *n* in **revolutions per second** and the
    propeller diameter D. Helicopter coefficients use the blade tip speed
    (omega R) and the disk area A. The two C_T values differ by 4/pi^3.
  * g0 in the rocket equation is a unit conversion between seconds of specific
    impulse and metres per second of exhaust velocity. It is not local gravity.

Structure: pure functions first (self-validating, unit-tested), then Calculator
specs. See calculators/aerodynamics.py for the worked example.
"""
from __future__ import annotations

import numpy as np

from utils import validation as v
from utils.constants import A_SL, G0, RHO_SL
from utils.spec import (Calculator, Check, Field, Output, Reference, Secondary,
                        Sweep)

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def disk_area(radius: float) -> float:
    """A = pi * R^2   [m^2] - the swept circle, not the blade area."""
    radius = v.positive(radius, "Rotor radius", "m")
    return float(np.pi * radius ** 2)


def disk_loading(thrust: float, area: float) -> float:
    """DL = T / A   [N/m^2]. The single best predictor of hover efficiency."""
    thrust = v.non_negative(thrust, "Thrust", "N")
    area = v.positive(area, "Disk area", "m^2")
    return thrust / area


def induced_velocity_hover(thrust: float, area: float,
                           rho: float = RHO_SL) -> float:
    """v_h = sqrt( T / (2 rho A) )   [m/s]

    The speed the rotor must accelerate air downward to hold up the thrust.
    """
    thrust = v.non_negative(thrust, "Thrust", "N")
    area = v.positive(area, "Disk area", "m^2")
    rho = v.positive(rho, "Air density", "kg/m^3")
    return float(np.sqrt(thrust / (2.0 * rho * area)))


def ideal_hover_power(thrust: float, area: float, rho: float = RHO_SL) -> float:
    """P_ideal = T * v_h = T^1.5 / sqrt(2 rho A)   [W]

    A LOWER BOUND. Real rotors also pay profile power; total hover power is
    roughly P_ideal / FM.
    """
    return thrust * induced_velocity_hover(thrust, area, rho)


def axial_flow_regime(climb_speed: float, hover_induced_velocity: float) -> str:
    """Which branch of momentum theory applies at this axial speed.

    Returns "climb" (includes hover), "vortex ring" or "windmill brake".

    The classification is the ratio V_c / v_h. Above zero the rotor pushes a
    single downward slipstream and the theory holds. Below -2 the rotor is
    descending faster than it can push air down, the flow is upward through the
    disk everywhere, and the theory holds again with the other root. Between
    them the wake recirculates: there is no steady one-directional slipstream
    to apply conservation of momentum to, and the equations have no physical
    solution even though the arithmetic still produces one.
    """
    climb_speed = v.finite(climb_speed, "Axial climb speed", "m/s")
    hover_induced_velocity = v.non_negative(
        hover_induced_velocity, "Hover induced velocity", "m/s")
    if climb_speed >= 0.0:
        return "climb"
    if hover_induced_velocity == 0.0:
        return "windmill brake"
    ratio = climb_speed / hover_induced_velocity
    return "vortex ring" if ratio > -2.0 else "windmill brake"


def induced_velocity_axial(thrust: float, area: float, climb_speed: float,
                           rho: float = RHO_SL) -> float:
    """Induced velocity in axial climb or fast descent   [m/s]

    Climb:            v_i = -V_c/2 + sqrt( (V_c/2)^2 + v_h^2 )
    Windmill brake:   v_i = -V_c/2 - sqrt( (V_c/2)^2 - v_h^2 )

    REFUSES to answer in the vortex ring state (-2 v_h < V_c < 0), because
    momentum theory has no valid solution there. Returning a number would be
    worse than raising: the arithmetic is happy and the answer is fiction.
    """
    v_h = induced_velocity_hover(thrust, area, rho)
    climb_speed = v.finite(climb_speed, "Axial climb speed", "m/s")
    regime = axial_flow_regime(climb_speed, v_h)
    half = climb_speed / 2.0
    if regime == "climb":
        return float(-half + np.sqrt(half ** 2 + v_h ** 2))
    if regime == "windmill brake":
        return float(-half - np.sqrt(max(half ** 2 - v_h ** 2, 0.0)))
    raise v.ValidationError(
        f"Descending at {climb_speed:.2f} m/s is inside the vortex ring state "
        f"(between 0 and {-2.0 * v_h:.2f} m/s for this rotor). Momentum theory "
        "has no valid solution there - the rotor is recirculating its own "
        "wake, so there is no steady slipstream to conserve momentum in.")


def axial_ideal_power(thrust: float, area: float, climb_speed: float,
                      rho: float = RHO_SL) -> float:
    """P = T (V_c + v_i)   [W] - ideal power in axial climb or descent.

    Reduces to T * v_h in hover. In the windmill brake state it is negative:
    the rotor is extracting energy from the air, which is autorotation.
    """
    return thrust * (climb_speed
                     + induced_velocity_axial(thrust, area, climb_speed, rho))


def figure_of_merit(ideal_power: float, actual_power: float) -> float:
    """FM = P_ideal / P_actual   [-]. Hover only; meaningless in forward flight."""
    ideal_power = v.non_negative(ideal_power, "Ideal power", "W")
    actual_power = v.positive(actual_power, "Measured shaft power", "W")
    return ideal_power / actual_power


def power_loading(thrust: float, power: float) -> float:
    """PL = T / P   [N/W]. Quoted as g/W in the drone community."""
    thrust = v.non_negative(thrust, "Thrust", "N")
    power = v.positive(power, "Power", "W")
    return thrust / power


def hover_electrical_power(weight: float, n_rotors: int, radius: float,
                           figure_of_merit_value: float, efficiency: float,
                           rho: float = RHO_SL) -> float:
    """Electrical power to hover   [W].

    Each rotor carries W/N, so P_elec = N * P_ideal(per rotor) / (FM * eta).
    """
    weight = v.non_negative(weight, "Weight", "N")
    n_rotors = v.positive_int(n_rotors, "Number of rotors")
    figure_of_merit_value = v.in_range(figure_of_merit_value,
                                       "Figure of merit", 0.05, 1.0)
    efficiency = v.in_range(efficiency, "Drivetrain efficiency", 0.05, 1.0)
    area = disk_area(radius)
    per_rotor = weight / n_rotors
    return (n_rotors * ideal_hover_power(per_rotor, area, rho)
            / (figure_of_merit_value * efficiency))


def hover_endurance_minutes(energy_wh: float, depth_of_discharge: float,
                            power_w: float) -> float:
    """t = E * DoD / P   [minutes]"""
    energy_wh = v.positive(energy_wh, "Battery energy", "Wh")
    depth_of_discharge = v.in_range(depth_of_discharge, "Usable fraction",
                                    0.05, 1.0)
    power_w = v.positive(power_w, "Hover power", "W")
    return energy_wh * depth_of_discharge / power_w * 60.0


# --- Propeller coefficients ------------------------------------------------
# Everything below uses the PROPELLER convention: n in revolutions per second
# and the diameter D. See rotor_thrust_coefficient for the helicopter one.


def advance_ratio(velocity: float, rps: float, diameter: float) -> float:
    """J = V / (n D)   [-]

    How far the aircraft travels per revolution, divided by the diameter. n is
    in REVOLUTIONS PER SECOND: using RPM here gives an answer 60x too small.
    """
    velocity = v.non_negative(velocity, "Airspeed", "m/s")
    rps = v.positive(rps, "Rotational speed", "rev/s")
    diameter = v.positive(diameter, "Propeller diameter", "m")
    return velocity / (rps * diameter)


def thrust_coefficient(thrust: float, rho: float, rps: float,
                       diameter: float) -> float:
    """C_T = T / (rho n^2 D^4)   [-], propeller convention.

    Thrust may be negative: past the zero-thrust advance ratio a fixed-pitch
    propeller drags rather than pushes.
    """
    thrust = v.finite(thrust, "Thrust", "N")
    rho = v.positive(rho, "Air density", "kg/m^3")
    rps = v.positive(rps, "Rotational speed", "rev/s")
    diameter = v.positive(diameter, "Propeller diameter", "m")
    return thrust / (rho * rps ** 2 * diameter ** 4)


def power_coefficient(power: float, rho: float, rps: float,
                      diameter: float) -> float:
    """C_P = P / (rho n^3 D^5)   [-], propeller convention."""
    power = v.positive(power, "Shaft power", "W")
    rho = v.positive(rho, "Air density", "kg/m^3")
    rps = v.positive(rps, "Rotational speed", "rev/s")
    diameter = v.positive(diameter, "Propeller diameter", "m")
    return power / (rho * rps ** 3 * diameter ** 5)


def propeller_efficiency(advance_ratio_value: float, ct: float,
                         cp: float) -> float:
    """eta = J C_T / C_P   [-], identical to T V / P.

    Zero in the hover, by definition, because the aircraft is going nowhere.
    That is not a statement about how good the rotor is - use the figure of
    merit for that.
    """
    advance_ratio_value = v.non_negative(advance_ratio_value, "Advance ratio")
    ct = v.finite(ct, "Thrust coefficient")
    cp = v.positive(cp, "Power coefficient")
    return advance_ratio_value * ct / cp


def rotor_thrust_coefficient(thrust: float, rho: float, area: float,
                             tip_speed_value: float) -> float:
    """C_T = T / (rho A (omega R)^2)   [-], HELICOPTER convention.

    Numerically 4/pi^3 = 0.129 times the propeller C_T for the same rotor.
    Quoting one where the other is expected is a factor-of-eight error.
    """
    thrust = v.finite(thrust, "Thrust", "N")
    rho = v.positive(rho, "Air density", "kg/m^3")
    area = v.positive(area, "Disk area", "m^2")
    tip_speed_value = v.positive(tip_speed_value, "Tip speed", "m/s")
    return thrust / (rho * area * tip_speed_value ** 2)


def tip_speed(rps: float, diameter: float) -> float:
    """V_tip = pi n D   [m/s] - the rotational component only."""
    rps = v.positive(rps, "Rotational speed", "rev/s")
    diameter = v.positive(diameter, "Propeller diameter", "m")
    return float(np.pi * rps * diameter)


def helical_tip_speed(rps: float, diameter: float, velocity: float) -> float:
    """The speed the tip section actually sees: sqrt(V_tip^2 + V^2)   [m/s].

    This, not the rotational tip speed alone, is what sets the tip Mach number.
    """
    velocity = v.non_negative(velocity, "Airspeed", "m/s")
    return float(np.hypot(tip_speed(rps, diameter), velocity))


def froude_efficiency(thrust: float, area: float, velocity: float,
                      rho: float = RHO_SL) -> float:
    """Ideal propulsive efficiency of any actuator disk   [-]

        eta_ideal = 2 V / ( V + sqrt( V^2 + 2T/(rho A) ) )

    The ceiling no propeller of this diameter can beat at this thrust and
    speed, however perfect its blades. Measured efficiency above it means an
    input is wrong, not that a remarkable propeller has been built.
    """
    thrust = v.non_negative(thrust, "Thrust", "N")
    area = v.positive(area, "Disk area", "m^2")
    velocity = v.non_negative(velocity, "Airspeed", "m/s")
    rho = v.positive(rho, "Air density", "kg/m^3")
    if velocity == 0.0:
        return 0.0
    return float(2.0 * velocity
                 / (velocity + np.sqrt(velocity ** 2
                                       + 2.0 * thrust / (rho * area))))


# --- Rockets ---------------------------------------------------------------


def delta_v(specific_impulse: float, mass_initial: float,
            mass_final: float) -> float:
    """dv = Isp * g0 * ln(m0 / mf)   [m/s]

    g0 here is a unit-conversion constant tying seconds to exhaust velocity,
    NOT local gravity.
    """
    specific_impulse = v.positive(specific_impulse, "Specific impulse", "s")
    mass_initial = v.positive(mass_initial, "Initial mass", "kg")
    mass_final = v.positive(mass_final, "Final mass", "kg")
    if mass_final > mass_initial:
        raise v.ValidationError(
            "Final mass cannot exceed initial mass - a rocket loses propellant, "
            "it does not gain it.")
    return specific_impulse * G0 * float(np.log(mass_initial / mass_final))


def mass_ratio_for_delta_v(delta_v_value: float,
                           specific_impulse: float) -> float:
    """m0/mf = exp( dv / (Isp g0) )   [-] - the rocket equation, inverted.

    The number that explains staging: the mass ratio grows exponentially with
    the delta-v you ask for.
    """
    delta_v_value = v.non_negative(delta_v_value, "Delta-v", "m/s")
    specific_impulse = v.positive(specific_impulse, "Specific impulse", "s")
    return float(np.exp(delta_v_value / (specific_impulse * G0)))


def propellant_mass_fraction(mass_initial: float, mass_final: float) -> float:
    """(m0 - mf) / m0   [-] - propellant as a fraction of the whole vehicle."""
    mass_initial = v.positive(mass_initial, "Initial mass", "kg")
    mass_final = v.non_negative(mass_final, "Final mass", "kg")
    if mass_final > mass_initial:
        raise v.ValidationError(
            "Final mass cannot exceed initial mass.")
    return (mass_initial - mass_final) / mass_initial


def thrust_from_mass_flow(mass_flow: float, specific_impulse: float) -> float:
    """F = mdot * Isp * g0 = mdot * v_e   [N]

    Specific impulse and mass flow set thrust; they say nothing about how long
    it lasts. Thrust is a flow rate of momentum, not a store of anything.
    """
    mass_flow = v.non_negative(mass_flow, "Propellant mass flow", "kg/s")
    specific_impulse = v.positive(specific_impulse, "Specific impulse", "s")
    return mass_flow * specific_impulse * G0


def burn_time(propellant_mass: float, mass_flow: float) -> float:
    """t_b = m_prop / mdot   [s] at constant mass flow."""
    propellant_mass = v.non_negative(propellant_mass, "Propellant mass", "kg")
    mass_flow = v.positive(mass_flow, "Propellant mass flow", "kg/s")
    return propellant_mass / mass_flow


def total_impulse(thrust: float, duration: float) -> float:
    """I_total = F t   [N*s]. Equals Isp * g0 * m_prop, so it is really a
    measure of how much propellant you have and how good it is."""
    thrust = v.non_negative(thrust, "Thrust", "N")
    duration = v.non_negative(duration, "Burn time", "s")
    return thrust * duration


# --- Electric motors -------------------------------------------------------


def torque_constant(kv_rpm_per_volt: float) -> float:
    """Kt = 60 / (2 pi Kv) = 9.5493 / Kv   [N*m/A]

    Ke in V*s/rad is numerically identical to Kt in SI units. That is a
    consequence of energy conservation, not a coincidence - and it breaks the
    moment RPM is mixed into the units.
    """
    kv = v.positive(kv_rpm_per_volt, "Kv", "rpm/V")
    return 60.0 / (2.0 * np.pi * kv)


def motor_torque(kv_rpm_per_volt: float, current: float,
                 no_load_current: float) -> float:
    """tau = Kt (I - I0)   [N*m]. Current below I0 produces no useful torque."""
    current = v.non_negative(current, "Current", "A")
    no_load_current = v.non_negative(no_load_current, "No-load current", "A")
    return torque_constant(kv_rpm_per_volt) * (current - no_load_current)


def motor_speed_rpm(kv_rpm_per_volt: float, voltage: float, current: float,
                    resistance: float) -> float:
    """n = (V - I R) * Kv   [rpm] - back-EMF sets the speed, not Kv * V alone."""
    voltage = v.non_negative(voltage, "Voltage", "V")
    current = v.non_negative(current, "Current", "A")
    resistance = v.non_negative(resistance, "Winding resistance", "ohm")
    kv = v.positive(kv_rpm_per_volt, "Kv", "rpm/V")
    return max(voltage - current * resistance, 0.0) * kv


def motor_efficiency(kv_rpm_per_volt: float, voltage: float, current: float,
                     resistance: float, no_load_current: float) -> float:
    """eta = shaft power / electrical power   [-]"""
    current = v.positive(current, "Current", "A")
    voltage = v.positive(voltage, "Voltage", "V")
    torque = motor_torque(kv_rpm_per_volt, current, no_load_current)
    omega = motor_speed_rpm(kv_rpm_per_volt, voltage, current,
                            resistance) * 2.0 * np.pi / 60.0
    return max(torque * omega, 0.0) / (voltage * current)


def peak_efficiency_current(voltage: float, no_load_current: float,
                            resistance: float) -> float:
    """I_opt = sqrt( V I0 / R )   [A] - the current of maximum efficiency.

    Falls straight out of the model above: eta = (1 - I0/I)(1 - IR/V), whose
    only maximum sits at this current. Iron losses pull the real peak slightly
    lower, but the point stands - peak efficiency is nowhere near peak power.
    """
    voltage = v.positive(voltage, "Voltage", "V")
    no_load_current = v.positive(no_load_current, "No-load current", "A")
    resistance = v.positive(resistance, "Winding resistance", "ohm")
    return float(np.sqrt(voltage * no_load_current / resistance))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

# --- Momentum theory -------------------------------------------------------


def _momentum_note(i, value):
    """What the ideal number becomes once a real rotor is put under it."""
    return (f"That is the floor. A well-built rotor at FM = 0.6 would need "
            f"about {value / 0.6:.0f} W of shaft power for the same thrust, a "
            f"small hobby propeller at FM = 0.45 about {value / 0.45:.0f} W. "
            "No rotor beats the number above.")


def _vortex_ring_check(i, r):
    """The one warning on this page that is not about accuracy but about
    whether the equation is describing reality at all."""
    v_h = induced_velocity_hover(i.thrust, disk_area(i.radius), i.rho)
    if i.climb_speed >= 0.0 or v_h <= 0.0:
        return None
    ratio = i.climb_speed / v_h
    if ratio <= -2.0:
        return ("info",
                f"WINDMILL BRAKE STATE. Descending at {abs(ratio):.1f} times "
                f"the hover induced velocity ({v_h:.1f} m/s), air passes "
                "upward through the disk everywhere and momentum theory has a "
                "valid solution again - this is the autorotation regime, where "
                "the rotor extracts energy from the airflow instead of adding "
                "it. The hover power above does not describe this condition.")
    if -1.5 <= ratio <= -0.5:
        return ("danger",
                f"VORTEX RING STATE. Descending at {abs(ratio):.2f} times the "
                f"hover induced velocity ({v_h:.1f} m/s) puts the rotor inside "
                "its own recirculating wake. Momentum theory assumes one "
                "steady slipstream in one direction; here there is none, so "
                "the number above is not an approximation - it is fiction. "
                "Real aircraft in this band lose thrust unpredictably, sink "
                "faster the more collective is pulled, and recover only by "
                "flying out sideways or forward.")
    return ("warning",
            f"Descending at {abs(ratio):.2f} times the hover induced velocity "
            f"({v_h:.1f} m/s). Anywhere between 0 and -2 v_h "
            f"(0 to {-2.0 * v_h:.1f} m/s here) momentum theory has no valid "
            "solution, and the worst of it - the vortex ring state proper - "
            "runs from -0.5 to -1.5 v_h. Treat the number above as a hover "
            "figure that happens to be on screen, not as a descent answer.")


def _disk_loading_check(i, r):
    area = disk_area(i.radius)
    dl = disk_loading(i.thrust, area)
    v_h = induced_velocity_hover(i.thrust, area, i.rho)
    if dl > 500.0:
        return ("warning",
                f"Disk loading is {dl:.0f} N/m², which throws air down at "
                f"{v_h:.0f} m/s. That is transport-helicopter and tiltrotor "
                "territory: the equation still holds, but at this loading the "
                "downwash erodes ground, raises debris and makes induced power "
                "the dominant cost of the whole aircraft. Efficient hover "
                "means a bigger disk, not a better blade.")
    if dl < 25.0:
        return ("info",
                f"Disk loading is only {dl:.0f} N/m² ({v_h:.1f} m/s of "
                "downwash). Very lightly loaded rotors like this hover "
                "cheaply, but they are large, structurally heavy, slow to "
                "respond and easily upset by wind - which is why the trade "
                "stops somewhere short of 'as big as possible'.")
    return None


def _density_check(i, r):
    if i.rho >= 1.10:
        return None
    factor = float(np.sqrt(RHO_SL / i.rho))
    return ("info",
            f"At ρ = {i.rho:.3f} kg/m³ the same thrust costs {factor:.2f}x the "
            "sea-level ideal power, because induced power goes as 1/sqrt(ρ). "
            "Hot and high is expensive twice over: thinner air also cuts the "
            "thrust a propeller makes at a given RPM, so the motor must work "
            "harder to produce the thrust in the first place.")


def _axial_power_curve(i, climb_speeds):
    """Ideal power against axial climb speed, for the graph."""
    area = disk_area(i.radius)
    out = []
    for speed in climb_speeds:
        try:
            out.append(axial_ideal_power(i.thrust, area, float(speed), i.rho))
        except v.ValidationError:
            out.append(np.nan)
    return np.array(out, dtype=float)


_MOMENTUM = Calculator(
    slug="prop.momentum_theory",
    name="Momentum theory (hover)",
    latex=(r"v_h = \sqrt{\frac{T}{2\rho A}}, \qquad "
           r"P_{ideal} = T\,v_h = \frac{T^{3/2}}{\sqrt{2\rho A}}"),
    explanation=(
        "Why hovering costs what it costs. A rotor holds an aircraft up by "
        "throwing air downwards, and the power needed is the thrust times the "
        "speed it must throw that air. Because power goes as <b>T^1.5</b> and "
        "as <b>1/R</b>, 10% more mass costs about 15% more power while a "
        "doubling of rotor radius halves it - the two most important "
        "non-linearities in rotorcraft design, both of them in one equation."),
    inputs=[
        Field("thrust", "Thrust per rotor T", "N", 4.9, min=0.0,
              help="For a multirotor, total weight divided by rotor count."),
        Field("radius", "Rotor radius R", "m", 0.127, min=0.0,
              help="A 10-inch propeller has a 5-inch (0.127 m) radius."),
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0),
        Field("climb_speed", "Axial climb speed V_c", "m/s", 0.0,
              help="0 for hover. Negative is descent - and momentum theory "
                   "breaks down in part of that range."),
    ],
    compute=lambda i: ideal_hover_power(i.thrust, disk_area(i.radius), i.rho),
    result=Output("Ideal hover power (per rotor)", "W"),
    secondary=[
        Secondary("Disk loading T/A", "N/m²",
                  lambda i, r: disk_loading(i.thrust, disk_area(i.radius))),
        Secondary("Induced velocity v_h", "m/s",
                  lambda i, r: induced_velocity_hover(i.thrust,
                                                      disk_area(i.radius), i.rho)),
        Secondary("Slipstream velocity far below (2 v_h)", "m/s",
                  lambda i, r: 2.0 * induced_velocity_hover(
                      i.thrust, disk_area(i.radius), i.rho)),
        Secondary("Ideal power loading", "g/W",
                  lambda i, r: i.thrust / r / G0 * 1000.0),
        Secondary("Shaft power at FM = 0.6", "W", lambda i, r: r / 0.6),
        Secondary("Mass held up at 1 g", "kg", lambda i, r: i.thrust / G0),
        Secondary("Disk area", "m²", lambda i, r: disk_area(i.radius)),
        Secondary("Ideal power at this axial speed", "W",
                  lambda i, r: axial_ideal_power(i.thrust, disk_area(i.radius),
                                                 i.climb_speed, i.rho)),
    ],
    note=_momentum_note,
    checks=[
        Check(_vortex_ring_check),
        Check(_disk_loading_check),
        Check(_density_check),
    ],
    assumptions=[
        "IDEAL ROTOR: uniform inflow through an infinitely thin disk, "
        "incompressible, inviscid, no swirl, no blade count, no tip losses and "
        "no profile drag. Every one of those costs power in a real rotor, "
        "which is what the figure of merit collects: real total power is "
        "roughly this divided by FM.",
        "This is a LOWER BOUND. Nothing that pushes air through a disk of this "
        "size can hover for less, so a measured power below it means the area, "
        "the thrust or the instrument is wrong.",
        "Use the swept DISK area, pi R squared - not blade area. Using blade "
        "area instead typically understates the disk by a factor of ten and "
        "overstates the power by about three.",
        "For a multirotor, enter thrust per rotor and multiply the answer by "
        "the rotor count. Entering total thrust with one rotor's area "
        "overstates power by N^1.5 - a factor of 8 on a quadcopter.",
        "Valid in hover and axial climb. In descent between 0 and -2 v_h the "
        "rotor enters the vortex ring state, where the theory does not merely "
        "lose accuracy, it stops applying: see the warning above.",
        "Overlapping or closely spaced rotors do not each get their own clean "
        "disk. Coaxial pairs need roughly 1.2-1.3x the power of two isolated "
        "rotors; a tightly packed multirotor frame pays a few percent.",
        "No ground effect. Within about one rotor radius of the ground the "
        "same thrust costs materially less power - a real effect this equation "
        "cannot see, and one reason a hover test at 30 cm flatters the design.",
        "Typical figure of merit: 0.4-0.6 small multirotor props, 0.6-0.7 good "
        "UAV rotors, 0.7-0.8 full-scale helicopters. Above 0.8 means a "
        "measurement error, not a breakthrough.",
    ],
    graphs=[
        Sweep(over="radius", y_label="Ideal hover power [W]",
              lo_factor=0.35, hi_factor=2.2,
              title="Power vs rotor radius (bigger, slower rotors always win)"),
        Sweep(over="thrust", y_label="Ideal hover power [W]", lo=0.0,
              hi_factor=2.0, hi_min=2.0,
              title="Power vs thrust (the three-halves power law)"),
        Sweep(over="rho", y_label="Ideal hover power [W]", lo=0.35,
              hi_factor=1.05, hi_min=1.30,
              title="Power vs air density (hot and high costs power)"),
        Sweep(over="climb_speed", y_label="Ideal power [W]", lo=0.0,
              hi_factor=1.6, hi_min=10.0, fn=_axial_power_curve,
              x_label="Axial climb speed V_c [m/s]",
              title="Power vs axial climb speed (descent is not plotted - "
                    "the theory fails there)"),
    ],
    references=[
        Reference(
            title="Figure of merit by rotor quality",
            columns=("Rotor", "Figure of merit"),
            rows=[
                ("Perfect rotor (this page's answer)", "1.00"),
                ("Well-designed full-scale helicopter rotor", "0.70 - 0.80"),
                ("Purpose-designed large UAV rotor", "0.60 - 0.70"),
                ("Typical multirotor propeller, 10-15 in", "0.50 - 0.65"),
                ("Small hobby propeller, 5 in, low Reynolds", "0.40 - 0.55"),
                ("Propeller run well off its design RPM", "0.30 - 0.45"),
            ],
            note="FM is a HOVER figure only and is meaningless in forward "
                 "flight. It compares a rotor against the ideal rotor of the "
                 "same disk area, so it rewards blade design, not size - a "
                 "large rotor with a poor FM still beats a small rotor with a "
                 "good one. A measured FM above 0.8 on a small rotor almost "
                 "always means the disk area or the power measurement is wrong.",
        ),
        Reference(
            title="Typical disk loadings",
            columns=("Aircraft", "Disk loading [N/m²]", "Downwash v_h [m/s]"),
            rows=[
                ("Small multirotor, 5-15 in props", "50 - 150", "4.5 - 7.8"),
                ("Light helicopter (R22, Bell 206 class)", "130 - 200",
                 "7.3 - 9.0"),
                ("Transport helicopter (UH-60, CH-47)", "400 - 500",
                 "12.8 - 14.3"),
                ("Tiltrotor (V-22 class)", "≈ 1000", "≈ 20"),
                ("Ducted lift fan / lift jet", "> 2000", "> 29"),
            ],
            note="Downwash is the hover induced velocity at sea level, "
                 "v_h = sqrt(DL / 2ρ); the slipstream reaches twice that "
                 "further downstream. Disk loading, not power or weight, is "
                 "what decides whether an aircraft can hover efficiently: "
                 "power per unit thrust goes as sqrt(DL).",
        ),
    ],
    related=["prop.hover_endurance", "prop.advance_ratio",
             "drone.hover_thrust", "drone.flight_time", "drone.power"],
    variables=[
        ("$T$", "Thrust produced by one rotor", "N"),
        ("$A$", "Swept disk area, pi R squared", "m²"),
        ("$R$", "Rotor radius", "m"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$v_h$", "Induced velocity in hover", "m/s"),
        ("$v_i$", "Induced velocity at the disk in axial flight", "m/s"),
        ("$V_c$", "Axial climb speed, negative in descent", "m/s"),
        ("$P_{ideal}$", "Ideal (induced) hover power", "W"),
        ("$FM$", "Figure of merit, P_ideal / P_actual", "-"),
    ],
    example=(
        "Why big props win. A 2 kg quadcopter needs 4.9 N per rotor. On 5-inch "
        "props (0.0635 m radius) the ideal power is 61.6 W per rotor; on "
        "10-inch props (0.127 m) it is 30.8 W - half, for the same thrust, "
        "because halving the disk loading cuts induced velocity by sqrt(2). "
        "The real gap is wider still: small props also have a worse figure of "
        "merit, so at FM = 0.45 the 5-inch rotor needs about 137 W of shaft "
        "power while the 10-inch at FM = 0.55 needs about 56 W - 2.4x, not 2x. "
        "That is the whole argument for large, slow-turning rotors on "
        "endurance aircraft."),
    keywords=("momentum", "actuator disk", "hover", "disk loading", "induced",
              "figure of merit", "rotor", "vortex ring", "vrs", "downwash",
              "settling with power", "autorotation", "slipstream"),
)


# --- Hover power and endurance ---------------------------------------------


def _hover_power_loading(i, r):
    """Grams of lift per watt of electrical power - the drone yardstick."""
    return i.weight / G0 * 1000.0 / r


def _figure_of_merit_check(i, r):
    if i.fm > 0.75:
        return ("warning",
                f"A figure of merit of {i.fm:.2f} is above what small rotors "
                "achieve. 0.70-0.80 belongs to well-designed full-scale "
                "helicopter rotors; a multirotor propeller is 0.4-0.65. The "
                "power below is therefore an optimistic floor, and the "
                "endurance an overestimate - by about "
                f"{(i.fm / 0.55 - 1.0) * 100:.0f}% against a realistic 0.55.")
    if i.fm < 0.35:
        return ("info",
                f"FM = {i.fm:.2f} is pessimistic even for a small propeller "
                "run off its design point. If this came from a bench test, "
                "check that the disk area used the full swept circle and that "
                "the power was shaft power, not electrical.")
    return None


def _power_loading_check(i, r):
    grams_per_watt = _hover_power_loading(i, r)
    if grams_per_watt < 4.0:
        return ("warning",
                f"{grams_per_watt:.1f} g/W is poor: a racing quad manages "
                "4-6 g/W, a camera drone 7-9, an endurance airframe 10-14. "
                "At this power loading the aircraft is either heavily loaded "
                "on a small disk or losing most of its energy in the "
                "drivetrain. Rotor size is the lever with the most left in it.")
    if grams_per_watt > 15.0:
        return ("info",
                f"{grams_per_watt:.1f} g/W is better than production "
                "multirotors achieve (7-12 g/W). That is plausible only with a "
                "very large, very lightly loaded disk - worth double-checking "
                "the rotor radius and the figure of merit before trusting the "
                "endurance.")
    return None


def _discharge_rate_check(i, r):
    """Hover current as a multiple of pack capacity, at the assumed 22.2 V."""
    capacity_ah = i.energy / 22.2
    if capacity_ah <= 0:
        return None
    c_rate = (r / 22.2) / capacity_ah
    if c_rate > 8.0:
        return ("warning",
                f"Hovering at roughly {c_rate:.0f}C (assuming a 6S, 22.2 V "
                "pack). Above about 8C, voltage sag and internal heating mean "
                "the pack will not deliver its rated watt-hours, so the real "
                "endurance falls short of the figure below - and repeated "
                "flights at this rate shorten pack life sharply.")
    if c_rate < 0.5:
        return ("info",
                f"Hovering at only {c_rate:.1f}C. The pack is barely working, "
                "so it will deliver close to its full rated energy - but it is "
                "also probably heavier than this aircraft needs, and mass is "
                "the thing endurance is most sensitive to.")
    return None


_HOVER_ENDURANCE = Calculator(
    slug="prop.hover_endurance",
    name="Hover power & endurance",
    latex=(r"P_{elec} = \frac{N\,(W/N)^{3/2}}{\sqrt{2\rho A}\;FM\;\eta}, "
           r"\qquad t = \frac{E\,DoD}{P_{elec}}"),
    explanation=(
        "Chains momentum theory to the battery: how long can this aircraft "
        "actually hover? Because power scales as mass^1.5 while battery energy "
        "scales only linearly with pack mass, every gram costs more than "
        "linearly - which is why adding battery eventually stops helping, as "
        "the pack starts spending its own energy carrying itself."),
    inputs=[
        Field("weight", "All-up", "", 2.0, kind="weight"),
        Field("n_rotors", "Number of rotors", "", 4, min=1, max=32, kind="int"),
        Field("radius", "Rotor radius R", "m", 0.127, min=0.0),
        Field("fm", "Figure of merit FM", "-", 0.55, min=0.05, max=1.0,
              help="0.4-0.6 for small multirotor props. Above 0.8 is not real."),
        Field("efficiency", "Motor × ESC efficiency", "-", 0.80,
              min=0.05, max=1.0),
        Field("energy", "Battery energy", "Wh", 111.0, min=0.0),
        Field("dod", "Usable fraction (depth of discharge)", "-", 0.8,
              min=0.05, max=1.0),
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0),
    ],
    compute=lambda i: hover_electrical_power(i.weight, i.n_rotors, i.radius,
                                             i.fm, i.efficiency, i.rho),
    result=Output("Electrical power to hover", "W"),
    secondary=[
        Secondary("Hover endurance", "minutes",
                  lambda i, r: hover_endurance_minutes(i.energy, i.dod, r)),
        Secondary("Thrust per rotor", "N", lambda i, r: i.weight / i.n_rotors),
        Secondary("Disk loading", "N/m²",
                  lambda i, r: disk_loading(i.weight / i.n_rotors,
                                            disk_area(i.radius))),
        Secondary("Power loading", "g/W", _hover_power_loading),
        Secondary("Ideal power (FM = 1, η = 1)", "W",
                  lambda i, r: i.n_rotors * ideal_hover_power(
                      i.weight / i.n_rotors, disk_area(i.radius), i.rho)),
        Secondary("Power per rotor", "W", lambda i, r: r / i.n_rotors),
        Secondary("Total disk area", "m²",
                  lambda i, r: i.n_rotors * disk_area(i.radius)),
        Secondary("Average current at 22.2 V", "A", lambda i, r: r / 22.2),
    ],
    checks=[
        Check(_figure_of_merit_check),
        Check(_power_loading_check),
        Check(_discharge_rate_check),
    ],
    assumptions=[
        "HOVER ONLY, and hover is the expensive case. A multirotor in "
        "efficient forward flight typically uses 20-30% less power, so this is "
        "a conservative floor rather than a mission time. It is also the right "
        "number for the worst case: station-keeping in wind.",
        "Constant power for the whole flight: no climb, no wind, no "
        "manoeuvring, no reserve. Holding position in a 5 m/s wind can cost "
        "10-20% more, and landing with a flat pack is how packs are destroyed.",
        "Figure of merit and drivetrain efficiency are both assumed constant. "
        "Both fall away from their design point, and both fall as the battery "
        "sags and the ESC has to push more current for the same power.",
        "Battery energy is at pack level, not cell level. Modern cells reach "
        "250-300 Wh/kg, but a finished pack is 150-220 Wh/kg after BMS, "
        "wiring, connectors and case - use the pack figure or endurance comes "
        "out 20-40% optimistic.",
        "Ignores voltage sag and the Peukert effect. A pack delivers "
        "noticeably less than its rated watt-hours at high discharge rates, "
        "which is exactly when you need them.",
        "The current reading assumes a 6S, 22.2 V nominal pack. At another "
        "voltage the power is unchanged but the current scales inversely - "
        "which is the whole argument for higher-voltage systems: half the "
        "current is a quarter of the I²R loss in wiring and ESCs.",
        "Weight is the all-up flying weight including the battery. The "
        "circularity is the point: sizing a pack means solving for a mass that "
        "appears on both sides.",
        "Assumes every rotor carries an equal share. A payload mounted off "
        "centre makes some motors work harder, and the aircraft's endurance is "
        "set by the hardest-working one.",
    ],
    graphs=[
        Sweep(over="weight", y_label="Hover power [W]",
              x_label="All-up weight [N]", lo_factor=0.4, hi_factor=2.0,
              title="Power vs all-up weight (a curve, not a line: P goes as "
                    "W^1.5)"),
        Sweep(over="radius", y_label="Hover power [W]", lo_factor=0.4,
              hi_factor=2.0, title="Power vs rotor radius"),
        Sweep(over="fm", y_label="Hover power [W]", lo=0.2, hi_factor=1.6,
              hi_min=1.0, title="Power vs figure of merit"),
        Sweep(over="rho", y_label="Hover power [W]", lo=0.35, hi_factor=1.05,
              hi_min=1.30, title="Power vs air density (density altitude)"),
    ],
    references=[
        Reference(
            title="Measured hover power loading",
            columns=("Aircraft", "Power loading [g/W]"),
            rows=[
                ("5 in racing / freestyle quad", "4 - 6"),
                ("Consumer camera drone, 8-9 in props", "7 - 9"),
                ("Survey / mapping multirotor, 13-15 in", "9 - 12"),
                ("Endurance airframe, large slow rotors", "10 - 14"),
            ],
            note="Whole-aircraft ELECTRICAL power in the hover, which is what "
                 "this page computes: it already includes figure of merit and "
                 "drivetrain efficiency. Divide the all-up mass in grams by "
                 "this to get hover power in watts, or use it the other way as "
                 "a sanity check on the answer above. Forward flight is "
                 "better; wind and manoeuvring are worse.",
        ),
        Reference(
            title="Battery energy density, pack level",
            columns=("Chemistry", "Cell [Wh/kg]", "Finished pack [Wh/kg]"),
            rows=[
                ("LiPo, high discharge (RC packs)", "180 - 250", "130 - 180"),
                ("Li-ion NMC, 18650 / 21700 cells", "250 - 300", "180 - 240"),
                ("LiFePO4", "120 - 160", "90 - 120"),
                ("Li-ion, semi-solid (emerging)", "350 - 450", "250 - 350"),
            ],
            note="Pack-level figures are what belong in the Battery energy "
                 "field, after BMS, wiring, connectors and case - typically "
                 "70-80% of the cell figure. High-discharge LiPo trades energy "
                 "density for the ability to deliver it: the cell that lasts "
                 "longest in the hover is rarely the one that survives a "
                 "10C burst.",
        ),
    ],
    related=["prop.momentum_theory", "drone.flight_time",
             "drone.battery_energy", "drone.power", "prop.motor_constants"],
    variables=[
        ("$W$", "All-up weight", "N"),
        ("$N$", "Number of rotors", "-"),
        ("$A$", "Disk area of one rotor", "m²"),
        ("$FM$", "Figure of merit", "-"),
        ("$\\eta$", "Motor and ESC efficiency", "-"),
        ("$E$", "Battery energy at pack level", "Wh"),
        ("$DoD$", "Usable fraction of the battery", "-"),
        ("$P_{elec}$", "Electrical power to hover", "W"),
        ("$t$", "Hover endurance", "minutes"),
    ],
    example=(
        "The payload question. A 2 kg quad on 10-inch props at FM = 0.55 and "
        "80% drivetrain efficiency draws 280 W and hovers for 19.0 minutes on "
        "a 111 Wh pack at 80% depth of discharge - a power loading of "
        "7.1 g/W. The ideal rotor would need only 123 W, so 56% of the "
        "electrical power is lost in the blades and the drivetrain. Now add a "
        "400 g camera: power rises to 368 W and endurance falls to 14.5 "
        "minutes. A 20% mass increase cost 31% more power and 24% of the "
        "flight time, because power follows mass^1.5."),
    keywords=("hover", "endurance", "payload", "power", "battery",
              "flight time", "power loading", "g/w", "multirotor", "disk"),
)


# --- Propeller advance ratio ------------------------------------------------


def _prop_rps(i):
    return i.rpm / 60.0


def _prop_ct(i, r=None):
    return thrust_coefficient(i.thrust, i.rho, _prop_rps(i), i.diameter)


def _prop_cp(i, r=None):
    return power_coefficient(i.power, i.rho, _prop_rps(i), i.diameter)


def _prop_disk_area(i):
    return disk_area(i.diameter / 2.0)


def _advance_ratio_check(i, r):
    if r < 0.05:
        return ("info",
                f"J = {r:.3f} is effectively static. Efficiency as defined "
                "here (η = T V / P) goes to zero in the hover no matter how "
                "good the propeller is, because the aircraft is going "
                "nowhere - the useful power really is zero. Judge a static or "
                "hovering rotor by its figure of merit instead. (If you meant "
                "to enter revolutions per second, note that this page takes "
                "RPM and divides by 60 for you.)")
    if r > 1.2:
        return ("warning",
                f"J = {r:.2f} is beyond the useful range of most fixed-pitch "
                "propellers. As J rises the blade sections see a smaller angle "
                "of attack, and past the zero-thrust advance ratio - typically "
                "J of 0.8 to 1.2 for a model propeller, higher for a "
                "coarse-pitch one - the propeller produces drag and drives the "
                "motor rather than the other way round. Check the airspeed and "
                "RPM before trusting C_T.")
    return None


def _tip_mach_check(i, r):
    helical = helical_tip_speed(_prop_rps(i), i.diameter, i.velocity)
    mach = helical / A_SL
    if mach > 0.85:
        return ("danger",
                f"Helical tip Mach {mach:.2f} ({helical:.0f} m/s). Above about "
                "0.85 the tip sections go transonic: drag rises steeply, "
                "thrust falls off, efficiency collapses and the noise becomes "
                "severe. C_T and C_P measured at low speed no longer apply, "
                "and neither does anything on this page.")
    if mach > 0.70:
        return ("warning",
                f"Helical tip Mach {mach:.2f} ({helical:.0f} m/s). "
                "Compressibility is starting to cost measurable efficiency and "
                "a great deal of noise. Most propellers are designed to stay "
                "below about 0.75; full-scale helicopters hold the tip near "
                "0.6-0.65 in hover for exactly this reason.")
    return None


def _froude_limit_check(i, r):
    """The hardest constraint on this page: no disk beats the ideal one."""
    area = _prop_disk_area(i)
    ideal = froude_efficiency(max(i.thrust, 0.0), area, i.velocity, i.rho)
    measured = propeller_efficiency(r, _prop_ct(i), _prop_cp(i))
    if measured > 1.0:
        return ("danger",
                f"Efficiency comes out at {measured * 100:.0f}%, which is "
                "impossible: a propeller cannot deliver more useful power "
                "(T × V) than the shaft supplies. Check the units - thrust in "
                "newtons not grams, power in watts not amps - and check that "
                "the thrust and power belong to the same operating point.")
    if ideal > 0.0 and measured > ideal:
        return ("danger",
                f"Efficiency of {measured * 100:.0f}% exceeds the ideal "
                f"actuator-disk limit of {ideal * 100:.0f}% for this thrust, "
                "diameter and airspeed. Even a perfect propeller loses that "
                "much energy to the kinetic energy left in the slipstream, so "
                "one of the four inputs is wrong.")
    if ideal > 0.0 and measured > 0.9 * ideal:
        return ("info",
                f"Efficiency is {measured * 100:.0f}% against an ideal ceiling "
                f"of {ideal * 100:.0f}% - within 10% of the theoretical best "
                "for this disk. Little is left to win from the blades; the "
                "remaining gain is in a larger diameter, which lowers the "
                "ceiling's cost by pushing more air more slowly.")
    return None


def _froude_vs_thrust(i, thrusts):
    area = _prop_disk_area(i)
    return np.array([froude_efficiency(max(float(t), 0.0), area, i.velocity,
                                       i.rho) * 100.0
                     for t in thrusts], dtype=float)


_PROPELLER = Calculator(
    slug="prop.advance_ratio",
    name="Propeller advance ratio",
    latex=(r"J = \frac{V}{n D}, \qquad C_T = \frac{T}{\rho n^{2} D^{4}}, "
           r"\qquad C_P = \frac{P}{\rho n^{3} D^{5}}, \qquad "
           r"\eta = \frac{J\,C_T}{C_P}"),
    explanation=(
        "The advance ratio is how far the aircraft moves forward per "
        "revolution, measured in diameters. It is the propeller's angle of "
        "attack in disguise: at a given J every blade section sees the same "
        "relative flow angle regardless of size or speed, so a propeller's "
        "whole performance map collapses onto curves of C_T, C_P and η "
        "against J. <b>n is revolutions per second, not RPM</b> - the single "
        "most common error on this page."),
    inputs=[
        Field("velocity", "Airspeed V", "m/s", 20.0, min=0.0,
              help="True airspeed. Zero is the static (hover) case, where J "
                   "and efficiency are both zero by definition."),
        Field("rpm", "Shaft speed", "rpm", 9000.0, min=0.0,
              help="Revolutions per MINUTE, as a tachometer reads. The "
                   "equation uses rev/s and the conversion is done for you."),
        Field("diameter", "Propeller diameter D", "m", 0.254, min=0.0,
              help="Diameter, not radius. A 10-inch propeller is 0.254 m."),
        Field("thrust", "Thrust T", "N", 8.0,
              help="At this airspeed and RPM. May be negative if the "
                   "propeller is windmilling."),
        Field("power", "Shaft power P", "W", 250.0, min=0.0,
              help="Mechanical power into the propeller, after motor losses."),
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0),
    ],
    compute=lambda i: advance_ratio(i.velocity, _prop_rps(i), i.diameter),
    result=Output("Advance ratio J", "-"),
    secondary=[
        Secondary("Rotational speed n", "rev/s", lambda i, r: _prop_rps(i)),
        Secondary("Thrust coefficient C_T (propeller)", "-", _prop_ct),
        Secondary("Power coefficient C_P (propeller)", "-", _prop_cp),
        Secondary("Propeller efficiency η", "-",
                  lambda i, r: propeller_efficiency(r, _prop_ct(i),
                                                    _prop_cp(i))),
        Secondary("C_T in the helicopter convention", "-",
                  lambda i, r: rotor_thrust_coefficient(
                      i.thrust, i.rho, _prop_disk_area(i),
                      tip_speed(_prop_rps(i), i.diameter))),
        Secondary("Helical tip speed", "m/s",
                  lambda i, r: helical_tip_speed(_prop_rps(i), i.diameter,
                                                 i.velocity)),
        Secondary("Helical tip Mach at sea level", "-",
                  lambda i, r: helical_tip_speed(_prop_rps(i), i.diameter,
                                                 i.velocity) / A_SL),
        Secondary("Ideal (Froude) efficiency ceiling", "-",
                  lambda i, r: froude_efficiency(max(i.thrust, 0.0),
                                                 _prop_disk_area(i),
                                                 i.velocity, i.rho)),
        Secondary("Useful power T × V", "W",
                  lambda i, r: i.thrust * i.velocity),
    ],
    checks=[
        Check(_advance_ratio_check),
        Check(_tip_mach_check),
        Check(_froude_limit_check),
    ],
    assumptions=[
        "n IS REVOLUTIONS PER SECOND in every one of these equations. This "
        "page takes RPM and divides by 60 for you; feeding RPM straight into "
        "J = V/(nD) makes the advance ratio 60x too small, C_T 3600x too small "
        "and C_P 216,000x too small.",
        "D IS THE DIAMETER, not the radius - a factor of 16 in C_T and 32 in "
        "C_P. Propeller work is done in diameters; rotor work is done in radii, "
        "and the two conventions meet on this page.",
        "The helicopter convention is different and not interchangeable: it "
        "references thrust to the disk area and the tip speed rather than to "
        "D^4 and n^2, so C_T,rotor = (4/pi^3) C_T,prop = 0.129 C_T,prop. Both "
        "are shown above; always state which one a number is.",
        "C_T and C_P are only constant at a fixed J. They also drift with "
        "Reynolds number, which matters for small propellers: blade-section Re "
        "below about 100,000 costs several points of efficiency that no "
        "coefficient table will show you.",
        "η = J C_T / C_P is identical to T V / P. It is the propeller's "
        "efficiency alone - motor, ESC and gearbox losses are not in it, so "
        "the electrical figure is lower.",
        "Efficiency is zero in the hover by definition, and that says nothing "
        "about the rotor. Use the figure of merit for static thrust, and note "
        "that the two measures disagree about which propeller is better.",
        "Thrust and power must come from the SAME operating point. Pairing a "
        "static thrust figure from a datasheet with a cruise power figure "
        "produces an efficiency that is simply invented.",
        "Compressibility is not modelled. The helical tip speed - rotation and "
        "flight combined - is what goes transonic, and above about Mach 0.85 "
        "measured coefficients stop transferring between conditions.",
    ],
    graphs=[
        Sweep(over="velocity", y_label="Advance ratio J [-]", lo=0.0,
              hi_factor=2.0, hi_min=10.0,
              title="Advance ratio vs airspeed"),
        Sweep(over="rpm", y_label="Advance ratio J [-]", lo_factor=0.3,
              hi_factor=1.8, title="Advance ratio vs shaft RPM"),
        Sweep(over="diameter", y_label="Advance ratio J [-]", lo_factor=0.4,
              hi_factor=2.0, title="Advance ratio vs diameter"),
        Sweep(over="thrust", y_label="Ideal efficiency [%]", lo=0.0,
              hi_factor=2.5, hi_min=4.0, fn=_froude_vs_thrust,
              x_label="Thrust T [N]",
              title="Froude efficiency limit vs thrust (more thrust from the "
                    "same disk costs efficiency)"),
    ],
    references=[
        Reference(
            title="Typical advance ratio and efficiency",
            columns=("Condition", "J", "Propeller η"),
            rows=[
                ("Static / hovering rotor", "0", "0 by definition"),
                ("Model or UAV propeller in cruise", "0.4 - 0.8", "0.55 - 0.75"),
                ("Light aircraft, fixed pitch, cruise", "0.6 - 0.9",
                 "0.75 - 0.85"),
                ("Constant-speed propeller, cruise", "0.8 - 1.4", "0.80 - 0.88"),
                ("Large, slow, well-matched propeller", "0.8 - 1.2",
                 "up to ≈ 0.90"),
                ("Windmilling (driving the shaft)", "> 1.0 - 1.4", "negative"),
            ],
            note="η here is shaft-to-thrust only; multiply by motor and ESC "
                 "efficiency for the electrical figure. A fixed-pitch "
                 "propeller peaks at one J and falls away either side, which "
                 "is why an aircraft that must climb and cruise well ends up "
                 "with a constant-speed propeller.",
        ),
        Reference(
            title="Propeller vs helicopter conventions",
            columns=("Quantity", "Propeller convention", "Rotor convention"),
            rows=[
                ("Reference speed", "n D  (n in rev/s)", "ΩR  (tip speed, m/s)"),
                ("Thrust coefficient", "C_T = T / (ρ n² D⁴)",
                 "C_T = T / (ρ A (ΩR)²)"),
                ("Power coefficient", "C_P = P / (ρ n³ D⁵)",
                 "C_P = P / (ρ A (ΩR)³)"),
                ("Speed parameter", "J = V / (nD)", "μ = V / (ΩR)"),
                ("Typical magnitude", "C_T ≈ 0.05 - 0.15",
                 "C_T ≈ 0.004 - 0.010"),
                ("Conversion", "—", "C_T,rotor = (4/π³) C_T,prop"),
            ],
            note="Both describe the same rotor and neither is wrong, but "
                 "mixing them is a factor-of-eight error in thrust "
                 "coefficient. The conversions follow from A = πD²/4 and "
                 "ΩR = πnD: C_T,rotor = 0.1290 C_T,prop and "
                 "C_P,rotor = (4/π⁴) C_P,prop = 0.0411 C_P,prop.",
        ),
    ],
    related=["prop.momentum_theory", "prop.motor_constants",
             "rotational_mechanics.rotational_power", "drone.power",
             "aero.reynolds"],
    variables=[
        ("$J$", "Advance ratio", "-"),
        ("$V$", "True airspeed", "m/s"),
        ("$n$", "Rotational speed, REVOLUTIONS PER SECOND", "rev/s"),
        ("$D$", "Propeller diameter", "m"),
        ("$T$", "Thrust", "N"),
        ("$P$", "Shaft power into the propeller", "W"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$C_T$", "Thrust coefficient, propeller convention", "-"),
        ("$C_P$", "Power coefficient, propeller convention", "-"),
        ("$\\eta$", "Propeller efficiency, J C_T / C_P = T V / P", "-"),
    ],
    example=(
        "Reading a propeller test. A 10-inch (0.254 m) propeller at 9000 rpm "
        "on a UAV flying 20 m/s makes 8 N of thrust for 250 W at the shaft. "
        "n is 150 rev/s, so J = 0.525, C_T = 0.0697, C_P = 0.0572 and "
        "η = 0.640 - which is exactly T V / P = 160/250. The same rotor in the "
        "helicopter convention has C_T = 0.0090, a normal rotor value from a "
        "number that looked eight times larger. The ideal actuator disk of "
        "this diameter would reach 87.6% at this thrust and speed, so the "
        "blades are giving up a quarter of what the disk allows, and the "
        "helical tip Mach of 0.36 says compressibility is not the reason."),
    keywords=("advance ratio", "propeller", "prop", "ct", "cp", "coefficient",
              "efficiency", "pitch speed", "tip speed", "j", "windmilling",
              "froude", "thrust coefficient"),
)


# --- Motor constants -------------------------------------------------------


def _efficiency_curve(i, currents):
    """Efficiency across the current range, for the graph."""
    return np.array([
        motor_efficiency(i.kv, i.voltage, max(float(c), 1e-6), i.resistance,
                         i.no_load_current) * 100.0
        for c in currents])


def _efficiency_vs_resistance(i, resistances):
    return np.array([
        motor_efficiency(i.kv, i.voltage, i.current, max(float(x), 0.0),
                         i.no_load_current) * 100.0
        for x in resistances])


def _speed_vs_voltage(i, voltages):
    return np.array([
        motor_speed_rpm(i.kv, max(float(x), 0.0), i.current, i.resistance)
        for x in voltages])


def _no_useful_torque_check(i, r):
    if i.current <= i.no_load_current:
        return ("danger",
                f"At {i.current:g} A the motor is drawing no more than its "
                f"no-load current of {i.no_load_current:g} A, so it produces "
                "no useful shaft torque at all - every watt going in is "
                "becoming iron loss, friction and windage. Torque only starts "
                "above I₀.")
    return None


def _peak_efficiency_check(i, r):
    optimum = peak_efficiency_current(i.voltage, i.no_load_current,
                                      i.resistance)
    best = (1.0 - float(np.sqrt(i.no_load_current * i.resistance
                                / i.voltage))) ** 2
    here = motor_efficiency(i.kv, i.voltage, i.current, i.resistance,
                            i.no_load_current)
    if i.current > 1.5 * optimum:
        return ("warning",
                f"Running at {i.current:g} A, well past the peak-efficiency "
                f"current of {optimum:.1f} A where this motor would reach "
                f"{best * 100:.1f}%. Efficiency here is {here * 100:.1f}%, and "
                f"{i.current ** 2 * i.resistance:.0f} W is being turned into "
                "heat in the windings alone - copper loss goes as the square "
                "of current, so the last amp is always the most expensive.")
    if i.current < 0.4 * optimum:
        return ("info",
                f"Running at {i.current:g} A, well below the peak-efficiency "
                f"current of {optimum:.1f} A. Down here the fixed no-load "
                "losses dominate: the motor is oversized for the load, which "
                "costs efficiency and mass but not heat.")
    return None


def _winding_drop_check(i, r):
    drop = i.current * i.resistance
    if i.voltage <= 0:
        return None
    fraction = drop / i.voltage
    if fraction > 0.5:
        return ("danger",
                f"{drop:.1f} V of the {i.voltage:g} V supply is being dropped "
                f"across the winding - {fraction * 100:.0f}% of it. The motor "
                "is close to stall, converting most of the input to heat, and "
                "the Kv × V speed figure is meaningless here. Sustained "
                "operation in this region destroys motors.")
    if fraction > 0.2:
        return ("warning",
                f"{drop:.1f} V ({fraction * 100:.0f}%) is lost across the "
                f"winding resistance, so the motor turns at "
                f"{motor_speed_rpm(i.kv, i.voltage, i.current, i.resistance):,.0f}"
                f" rpm rather than the {i.kv * i.voltage:,.0f} rpm that Kv × V "
                "suggests. Expect this gap to widen sharply with load.")
    return None


_MOTOR = Calculator(
    slug="prop.motor_constants",
    name="Motor constants (Kv, Kt, back-EMF)",
    latex=(r"K_t = \frac{60}{2\pi K_v}, \qquad \tau = K_t (I - I_0), "
           r"\qquad n = (V - I R)\,K_v"),
    explanation=(
        "What a motor's Kv rating actually tells you. Kv fixes the torque "
        "constant, the torque constant fixes torque per amp, and the voltage "
        "left after the winding drop fixes speed. A high-Kv motor is not "
        "'more powerful' - it trades torque for speed at the same power. The "
        "two knobs an aircraft designer really has are current, which buys "
        "torque and costs heat, and voltage, which buys RPM almost for free."),
    inputs=[
        Field("kv", "Motor Kv", "rpm/V", 920.0, min=0.0,
              help="Lowercase k, unrelated to kilo. RPM per volt, unloaded."),
        Field("voltage", "Applied voltage V", "V", 22.2, min=0.0),
        Field("current", "Current I", "A", 20.0, min=0.0),
        Field("resistance", "Winding resistance R", "Ω", 0.08, min=0.0),
        Field("no_load_current", "No-load current I₀", "A", 0.7, min=0.0,
              help="Current drawn spinning free - iron, friction and windage."),
    ],
    compute=lambda i: motor_torque(i.kv, i.current, i.no_load_current),
    result=Output("Shaft torque", "N·m"),
    secondary=[
        Secondary("Torque constant Kt", "N·m/A",
                  lambda i, r: torque_constant(i.kv)),
        Secondary("Speed under this load", "rpm",
                  lambda i, r: motor_speed_rpm(i.kv, i.voltage, i.current,
                                               i.resistance)),
        Secondary("Shaft power", "W",
                  lambda i, r: r * motor_speed_rpm(i.kv, i.voltage, i.current,
                                                   i.resistance)
                  * 2.0 * np.pi / 60.0),
        Secondary("Electrical power", "W", lambda i, r: i.voltage * i.current),
        Secondary("Efficiency", "%",
                  lambda i, r: motor_efficiency(i.kv, i.voltage, i.current,
                                                i.resistance,
                                                i.no_load_current) * 100.0),
        Secondary("Winding loss I²R", "W",
                  lambda i, r: i.current ** 2 * i.resistance),
        Secondary("Current for peak efficiency", "A",
                  lambda i, r: peak_efficiency_current(i.voltage,
                                                       i.no_load_current,
                                                       i.resistance)),
        Secondary("No-load speed (Kv × V)", "rpm",
                  lambda i, r: i.kv * i.voltage),
    ],
    checks=[
        Check(_no_useful_torque_check),
        Check(_peak_efficiency_check),
        Check(_winding_drop_check),
    ],
    assumptions=[
        "Kv is measured UNLOADED and ignores winding resistance, so real speed "
        "under load is always below Kv × V. The (V - I R) term is that "
        "difference, and it grows linearly with current.",
        "Kt = 9.5493/Kv is exact for an ideal DC machine. For a three-phase "
        "BLDC it additionally depends on whether Kv is quoted line-to-line or "
        "per phase, and on sinusoidal (FOC) versus trapezoidal commutation - "
        "factors of sqrt(3) appear in the literature. Treat this as a good "
        "first-order estimate and check the convention.",
        "Ke in V·s/rad equals Kt in N·m/A in SI units. That identity follows "
        "from energy conservation and breaks the moment RPM enters the units.",
        "I₀ is not constant: it rises with speed, so torque at high RPM is "
        "slightly below Kt(I - I₀), and the efficiency figure here is "
        "correspondingly optimistic at the top of the range.",
        "R is not constant either. Copper gains about 0.4% resistance per "
        "kelvin, so a winding that starts at 0.08 Ω cold is nearer 0.10 Ω at "
        "80 °C - and that extra resistance makes more heat, which is the "
        "runaway that cooks motors.",
        "Maximum power and maximum efficiency occur at DIFFERENT operating "
        "points. Peak efficiency sits at I = sqrt(V I₀ / R); peak power sits "
        "near half the stall current, far higher. Sizing to peak power runs a "
        "motor hot and wasteful.",
        "Nothing here models heat. A motor's real limit is almost always "
        "thermal, not electrical: the current it can hold for thirty seconds "
        "is not the current it can hold for ten minutes, and airflow over the "
        "can changes the answer more than any constant on this page.",
        "The ESC is not modelled. Its switching and conduction losses sit "
        "between the battery and these numbers, typically 3-8%.",
    ],
    graphs=[
        Sweep(over="current", y_label="Efficiency [%]", lo_factor=0.05,
              hi_factor=4.0, fn=_efficiency_curve,
              title="Efficiency vs current (peaks well below maximum power)"),
        Sweep(over="kv", y_label="Shaft torque [N·m]", lo_factor=0.2,
              hi_factor=2.0,
              title="Torque vs Kv (the trade: torque for speed)"),
        Sweep(over="resistance", y_label="Efficiency [%]", lo=0.0,
              hi_factor=1.6, hi_min=0.3, fn=_efficiency_vs_resistance,
              title="Efficiency vs winding resistance"),
        Sweep(over="voltage", y_label="Speed under load [rpm]", lo_factor=0.2,
              hi_factor=2.0, fn=_speed_vs_voltage,
              title="Speed vs bus voltage (the line misses the origin by I R)"),
    ],
    references=[
        Reference(
            title="Kv, Kt and no-load speed",
            columns=("Kv [rpm/V]", "Kt [N·m/A]", "No-load rpm at 22.2 V"),
            rows=[
                ("100", "0.09549", "2,220"),
                ("400", "0.02387", "8,880"),
                ("920", "0.01038", "20,424"),
                ("1500", "0.00637", "33,300"),
                ("2400", "0.00398", "53,280"),
            ],
            note="Exact arithmetic: Kt = 9.5493 / Kv for an ideal machine, and "
                 "the speed column is simply Kv × 22.2 with no load and no "
                 "winding drop. Every real motor turns slower than the third "
                 "column and makes slightly less torque than the second.",
        ),
        Reference(
            title="Typical Kv by propeller size",
            columns=("Aircraft", "Battery", "Kv [rpm/V]"),
            rows=[
                ("5 in racing / freestyle", "4S (14.8 V)", "2200 - 2700"),
                ("5 in freestyle", "6S (22.2 V)", "1600 - 1900"),
                ("7 in long range", "6S (22.2 V)", "1200 - 1500"),
                ("9-10 in camera drone", "4S - 6S", "800 - 1100"),
                ("15-18 in heavy lift", "12S (44.4 V)", "100 - 200"),
            ],
            note="Kv is chosen backwards from the propeller: the prop wants a "
                 "particular RPM, and Kv × V must land near it. That is why Kv "
                 "falls roughly in proportion as cell count rises for the same "
                 "airframe, and why swapping a 4S pack for 6S without changing "
                 "the motor overspeeds the propeller by 50%.",
        ),
    ],
    related=["prop.hover_endurance", "prop.advance_ratio", "drone.power",
             "elec.power", "rotational_mechanics.rotational_power"],
    variables=[
        ("$K_v$", "Speed constant, unloaded", "rpm/V"),
        ("$K_t$", "Torque constant", "N·m/A"),
        ("$K_e$", "Back-EMF constant, numerically equal to Kt", "V·s/rad"),
        ("$I$", "Current drawn", "A"),
        ("$I_0$", "No-load current", "A"),
        ("$V$", "Applied terminal voltage", "V"),
        ("$R$", "Winding resistance", "Ω"),
        ("$\\tau$", "Shaft torque", "N·m"),
        ("$n$", "Shaft speed under load", "rpm"),
    ],
    example=(
        "Reading a datasheet. A 920 kv motor has Kt = 0.01038 N·m/A, so at "
        "20 A with a 0.7 A no-load current it makes 0.2003 N·m. On 6S it would "
        "spin 20,424 rpm unloaded, but the 1.6 V lost across 0.08 Ω at 20 A "
        "drops that to 18,952 rpm, and the motor runs at 89.5% efficiency for "
        "398 W at the shaft. Its best point is 13.9 A, where it would reach "
        "90.2%. Push it to 40 A instead and efficiency falls to 84.1% while "
        "the windings alone dissipate 128 W - four times the heat for twice "
        "the current."),
    keywords=("motor", "kv", "kt", "back emf", "bldc", "torque constant",
              "efficiency", "winding", "esc", "copper loss", "no-load"),
)


# --- Rocket equation -------------------------------------------------------


def _isp_check(i, r):
    if i.isp >= 1200.0:
        ratio = mass_ratio_for_delta_v(r, i.isp)
        return ("info",
                f"I_sp = {i.isp:g} s is electric propulsion. The delta-v is "
                f"real and the mass ratio needed is only {ratio:.2f}, but the "
                "thrust is milli-newtons: the burn takes weeks to months, so "
                "it is nothing like the instantaneous impulse this equation "
                "assumes. A slow spiral out of a gravity well also loses "
                "meaningfully more than an impulsive burn of the same delta-v.")
    if i.isp < 150.0:
        return ("warning",
                f"I_sp = {i.isp:g} s is below any practical chemical rocket. "
                "Cold gas thrusters run 50-75 s and are used for attitude "
                "control, not translation; monopropellant hydrazine is about "
                "230 s. Check the number before sizing anything around it.")
    return None


def _mass_ratio_check(i, r):
    ratio = i.m0 / i.mf
    if ratio > 20.0:
        return ("warning",
                f"A mass ratio of {ratio:.1f} means the vehicle is "
                f"{propellant_mass_fraction(i.m0, i.mf) * 100:.1f}% propellant "
                "by mass, leaving everything else - tanks, engines, "
                "structure, avionics, payload - inside the remainder. Real "
                "single stages top out near 20, and only with pressure-"
                "stabilised tanks. Above that the answer is staging, not a "
                "lighter tank.")
    if ratio < 1.05:
        return ("info",
                f"A mass ratio of {ratio:.3f} is a small trim or "
                "station-keeping burn. In this region the logarithm is nearly "
                "linear, so delta-v is very close to v_e times the propellant "
                "fraction and the intuition that 'twice the propellant is "
                "twice the delta-v' briefly holds.")
    return None


def _mission_check(i, r):
    if r < 500.0:
        return None
    if r < 9400.0:
        return ("info",
                f"{r / 1000.0:.2f} km/s is {r / 9400.0 * 100:.0f}% of the "
                "≈9.4 km/s an expendable launcher needs to reach low Earth "
                "orbit from the pad. Note that orbital velocity is only "
                "7.8 km/s - the other 1.6 km/s is gravity, drag and steering "
                "losses, none of which appear in this equation.")
    return ("info",
            f"{r / 1000.0:.2f} km/s exceeds the ≈9.4 km/s budget for low Earth "
            "orbit, which is the realistic figure including the roughly "
            "1.6 km/s of gravity, drag and steering losses this equation "
            "cannot see. Beyond that: 2.4 km/s more to a transfer orbit, "
            "3.1 km/s from LEO for trans-lunar injection.")


_ROCKET = Calculator(
    slug="prop.rocket_equation",
    name="Rocket equation",
    latex=r"\Delta v = I_{sp}\,g_0 \ln\!\left(\frac{m_0}{m_f}\right)",
    explanation=(
        "Tsiolkovsky's equation: the velocity change a rocket can produce "
        "depends only on its exhaust velocity and the <b>ratio</b> of its wet "
        "to dry mass. The logarithm is brutal - each extra km/s costs "
        "exponentially more propellant, which is why rockets are almost "
        "entirely fuel and why shaving structural mass pays far better than "
        "adding tank."),
    inputs=[
        Field("isp", "Specific impulse I_sp", "s", 300.0, min=0.0,
              help="Solid ~250 s, kerolox ~300 s (sea level) to 340 s (vacuum), "
                   "hydrolox ~450 s, ion 3000+ s."),
        Field("m0", "Initial (wet) mass m₀", "kg", 1000.0, min=0.0),
        Field("mf", "Final (dry) mass m_f", "kg", 300.0, min=0.0),
    ],
    compute=lambda i: delta_v(i.isp, i.m0, i.mf),
    result=Output("Delta-v", "m/s"),
    secondary=[
        Secondary("In km/s", "km/s", lambda i, r: r / 1000.0),
        Secondary("Exhaust velocity v_e = I_sp g₀", "m/s",
                  lambda i, r: i.isp * G0),
        Secondary("Mass ratio m₀/m_f", "-", lambda i, r: i.m0 / i.mf),
        Secondary("Propellant mass", "kg", lambda i, r: i.m0 - i.mf),
        Secondary("Propellant mass fraction", "-",
                  lambda i, r: propellant_mass_fraction(i.m0, i.mf)),
        Secondary("Structural coefficient m_f/m₀", "-",
                  lambda i, r: i.mf / i.m0),
        Secondary("Fraction of the 9.4 km/s LEO budget", "-",
                  lambda i, r: r / 9400.0),
        Secondary("Mass ratio this I_sp needs for LEO", "-",
                  lambda i, r: mass_ratio_for_delta_v(9400.0, i.isp)),
    ],
    checks=[
        Check(_isp_check),
        Check(_mass_ratio_check),
        Check(_mission_check),
    ],
    assumptions=[
        "NO EXTERNAL FORCES: no gravity, no atmospheric drag, no steering "
        "losses. Reaching low Earth orbit needs about 9.4 km/s of delta-v even "
        "though orbital velocity is only 7.8 km/s - that 1.6 km/s gap is the "
        "losses this equation does not contain.",
        "g₀ = 9.80665 m/s² is a UNIT CONVERSION between specific impulse in "
        "seconds and exhaust velocity in metres per second. It is not local "
        "gravity: using Mars gravity here because the rocket is on Mars is a "
        "classic and expensive mistake. The physical quantity is v_e = I_sp g₀, "
        "and the seconds only exist because the imperial and metric camps "
        "wanted one number they could agree on.",
        "Constant exhaust velocity, one burn, one direction. Throttling or "
        "changing mixture ratio changes I_sp mid-burn and the simple form "
        "no longer applies.",
        "I_sp differs between sea level and vacuum for the same engine, "
        "because nozzle expansion depends on ambient pressure - typically 10 "
        "to 15% for a first-stage engine. Use the value for where the burn "
        "actually happens.",
        "The answer depends only on the RATIO of the masses, so the units "
        "cancel: kilograms, tonnes or pounds all give the same delta-v as long "
        "as both masses use the same one.",
        "m_f is everything left at the end: structure, engines, avionics, "
        "residual propellant AND payload. Sizing a stage means splitting that "
        "remainder between the parts that fly and the part that pays.",
        "Nothing here says the burn is possible. A vehicle with the right mass "
        "ratio but a thrust-to-weight below 1 never leaves the pad, and one "
        "that burns for hours in low orbit loses much of its delta-v to "
        "gravity.",
    ],
    graphs=[
        Sweep(over="mf", y_label="Delta-v [m/s]", lo_factor=0.15,
              hi_factor=1.6, x_label="Final (dry) mass [kg]",
              title="Delta-v vs dry mass (the logarithm punishes structure)"),
        Sweep(over="isp", y_label="Delta-v [m/s]", lo=0.0, hi_factor=1.8,
              hi_min=500.0, title="Delta-v vs specific impulse (linear)"),
        Sweep(over="m0", y_label="Delta-v [m/s]", lo_factor=1.0,
              hi_factor=3.0, x_label="Initial (wet) mass [kg]",
              title="Delta-v vs wet mass (diminishing returns from more fuel)"),
    ],
    references=[
        Reference(
            title="Typical specific impulse",
            columns=("Propulsion", "I_sp [s]", "v_e [m/s]"),
            rows=[
                ("Cold gas (nitrogen)", "60 - 75", "590 - 740"),
                ("Monopropellant hydrazine", "≈ 230", "≈ 2,260"),
                ("Solid motor", "240 - 265", "2,350 - 2,600"),
                ("Hypergolic (NTO / MMH), vacuum", "300 - 320",
                 "2,940 - 3,140"),
                ("Kerolox, sea level", "≈ 300", "≈ 2,940"),
                ("Kerolox, vacuum", "330 - 350", "3,240 - 3,430"),
                ("Hydrolox, vacuum", "440 - 465", "4,310 - 4,560"),
                ("Hall thruster / gridded ion", "1,500 - 4,000",
                 "14,700 - 39,200"),
            ],
            note="v_e = I_sp × 9.80665, exactly. Vacuum figures are quoted "
                 "where an engine is used in vacuum. The electric numbers buy "
                 "their I_sp with electrical power and give up thrust: a Hall "
                 "thruster produces tens to hundreds of millinewtons, so it "
                 "cannot lift anything and works only where there is time.",
        ),
        Reference(
            title="Delta-v budgets",
            columns=("Manoeuvre", "Delta-v [km/s]"),
            rows=[
                ("Earth surface to low Earth orbit", "9.3 - 9.5"),
                ("LEO to geostationary transfer orbit", "≈ 2.4"),
                ("GTO to geostationary orbit", "≈ 1.5"),
                ("LEO to trans-lunar injection", "≈ 3.1"),
                ("Low lunar orbit to lunar surface", "≈ 1.9"),
                ("LEO to Mars transfer injection", "≈ 3.6"),
                ("Geostationary station-keeping", "≈ 0.05 per year"),
            ],
            note="The surface-to-LEO figure already includes roughly 1.6 km/s "
                 "of gravity, drag and steering losses on top of the 7.8 km/s "
                 "of orbital velocity; every other line is a near-impulsive "
                 "manoeuvre in vacuum where this equation applies cleanly. "
                 "Budgets vary with launch site, trajectory and how much "
                 "aerobraking is used.",
        ),
    ],
    related=["prop.rocket_thrust", "mech.momentum", "flight.twr",
             "mech.kinetic_energy",
             "constants___reference.engineering_constants"],
    variables=[
        ("$\\Delta v$", "Achievable velocity change", "m/s"),
        ("$I_{sp}$", "Specific impulse", "s"),
        ("$g_0$", "Standard gravity, 9.80665 (a unit conversion)", "m/s²"),
        ("$v_e$", "Effective exhaust velocity, I_sp g₀", "m/s"),
        ("$m_0$", "Initial mass, including propellant", "kg"),
        ("$m_f$", "Final mass, after the burn", "kg"),
    ],
    example=(
        "Staging maths. A vehicle with I_sp = 300 s burning from 1000 kg to "
        "300 kg gets 3.54 km/s - well short of orbit. Shedding dry mass to "
        "200 kg raises it to 4.73 km/s. Now ask the question the other way: to "
        "reach 9.4 km/s in one stage at 300 s you need a mass ratio of 24.4, "
        "which is 95.9% propellant, leaving 4.1% for tanks, engines, structure "
        "and payload together. Switch to hydrolox at 450 s and the required "
        "ratio falls to 8.4, or 88.1% propellant. That sensitivity is why "
        "rockets stage and why every kilogram of tank is fought over."),
    keywords=("rocket", "tsiolkovsky", "delta-v", "isp", "specific impulse",
              "space", "mass ratio", "staging", "exhaust velocity",
              "propellant fraction"),
)


# --- Rocket thrust and mass flow --------------------------------------------


def _liftoff_twr(i, r=None):
    thrust = thrust_from_mass_flow(i.mdot, i.isp)
    mass = v.positive(i.m_lift, "Liftoff mass", "kg")
    return thrust / (mass * G0)


def _twr_check(i, r):
    twr = _liftoff_twr(i)
    if i.isp >= 1200.0:
        return None                  # electric propulsion: see the I_sp check
    if twr < 1.0:
        return ("danger",
                f"Thrust-to-weight at liftoff is {twr:.2f}. This vehicle "
                "cannot leave the ground: the engine produces less force than "
                "the vehicle weighs. It is a perfectly good upper stage, where "
                "T/W below 1 is normal, but it is not a first stage.")
    if twr < 1.2:
        return ("warning",
                f"Thrust-to-weight at liftoff is only {twr:.2f}. It will rise, "
                "but slowly, and every second spent fighting gravity at low "
                "speed is delta-v lost - gravity losses go as g times the time "
                "of flight. Launch vehicles are normally designed for 1.2-1.6 "
                "at liftoff.")
    if twr > 8.0:
        return ("info",
                f"Thrust-to-weight of {twr:.1f} is sounding-rocket or "
                "solid-booster territory. Gravity losses are small, but the "
                "vehicle reaches high dynamic pressure low in the atmosphere, "
                "so drag losses and airframe loads become the constraint "
                "instead.")
    return None


def _mass_flow_isp_check(i, r):
    if i.isp >= 1200.0:
        return ("info",
                f"At I_sp = {i.isp:g} s this is electric propulsion, and the "
                f"thrust of {r:.3g} N is correct but tiny - thrust-to-weight "
                "is far below 1 and that is fine, because the vehicle is "
                "already in orbit and has months to spend. The limit here is "
                "electrical power, roughly 20 kW per newton at this exhaust "
                "velocity, not propellant.")
    return None


def _propellant_fraction_check(i, r):
    if i.m_prop >= i.m_lift:
        return ("danger",
                f"Propellant mass ({i.m_prop:g} kg) is at least the whole "
                f"liftoff mass ({i.m_lift:g} kg), which leaves nothing for "
                "tanks, engine, structure or payload. No delta-v can be "
                "computed from that. Real stages are 85-95% propellant, never "
                "100%.")
    fraction = i.m_prop / i.m_lift
    if fraction > 0.96:
        return ("warning",
                f"Propellant is {fraction * 100:.1f}% of liftoff mass, leaving "
                f"{i.m_lift - i.m_prop:g} kg for everything else. A structural "
                "coefficient that good has only been achieved with "
                "pressure-stabilised balloon tanks; 0.05-0.12 dry is the "
                "normal range.")
    return None


def _twr_vs_mass(i, masses):
    thrust = thrust_from_mass_flow(i.mdot, i.isp)
    out = []
    for mass in masses:
        mass = float(mass)
        out.append(thrust / (mass * G0) if mass > 0 else np.nan)
    return np.array(out, dtype=float)


def _burn_time_vs_propellant(i, propellants):
    return np.array([burn_time(max(float(m), 0.0), i.mdot)
                     for m in propellants], dtype=float)


_ROCKET_THRUST = Calculator(
    slug="prop.rocket_thrust",
    name="Rocket thrust & mass flow",
    latex=(r"F = \dot{m}\,I_{sp}\,g_0 = \dot{m}\,v_e, \qquad "
           r"t_b = \frac{m_p}{\dot{m}}, \qquad I_{tot} = F\,t_b"),
    explanation=(
        "The other half of rocket sizing. The rocket equation says how much "
        "velocity a given propellant load can buy; this says how hard and for "
        "how long it can push. Thrust is a <b>flow rate</b> of momentum - "
        "mass per second times the speed it leaves at - so it depends on how "
        "fast you burn propellant, while delta-v depends only on how much of "
        "it there is. Burning twice as fast doubles thrust and halves the "
        "burn, leaving delta-v untouched."),
    inputs=[
        Field("mdot", "Propellant mass flow ṁ", "kg/s", 8.0, min=0.0),
        Field("isp", "Specific impulse I_sp", "s", 300.0, min=0.0,
              help="Use the value for where the burn happens: sea level for a "
                   "first stage, vacuum for an upper stage."),
        Field("m_prop", "Propellant mass", "kg", 1200.0, min=0.0),
        Field("m_lift", "Liftoff (wet) mass", "kg", 1600.0, min=0.0,
              help="Everything at ignition: propellant, structure and "
                   "payload."),
    ],
    compute=lambda i: thrust_from_mass_flow(i.mdot, i.isp),
    result=Output("Thrust", "N"),
    secondary=[
        Secondary("In kilonewtons", "kN", lambda i, r: r / 1000.0),
        Secondary("Exhaust velocity v_e", "m/s", lambda i, r: i.isp * G0),
        Secondary("Burn time", "s", lambda i, r: burn_time(i.m_prop, i.mdot)),
        Secondary("Total impulse", "N·s",
                  lambda i, r: total_impulse(r, burn_time(i.m_prop, i.mdot))),
        Secondary("Thrust-to-weight at liftoff", "-", _liftoff_twr),
        Secondary("Delta-v from this burn", "m/s",
                  lambda i, r: delta_v(i.isp, i.m_lift, i.m_lift - i.m_prop)),
        Secondary("Initial acceleration, net of gravity", "m/s²",
                  lambda i, r: r / i.m_lift - G0),
    ],
    checks=[
        Check(_twr_check),
        Check(_mass_flow_isp_check),
        Check(_propellant_fraction_check),
    ],
    assumptions=[
        "CONSTANT MASS FLOW and constant I_sp for the whole burn. Real engines "
        "throttle, and solid motors have a thrust curve set by the grain "
        "geometry - progressive, neutral or regressive - so burn time and peak "
        "thrust both differ from the average this computes.",
        "F = ṁ v_e is the momentum term only. The full thrust equation adds a "
        "pressure term, (p_e - p_a) A_e, which is why an engine makes 10-15% "
        "more thrust in vacuum than at sea level. Using an I_sp measured at "
        "the right ambient pressure folds that term back in.",
        "g₀ is the same unit conversion as in the rocket equation, not local "
        "gravity. The weight in thrust-to-weight, however, IS local gravity - "
        "this page assumes Earth's surface, so a Mars lander's T/W is 2.6x "
        "what is shown.",
        "Thrust-to-weight is evaluated at ignition, when the vehicle is "
        "heaviest. It rises through the burn as propellant leaves: a stage "
        "starting at 1.5 finishes near 6 if it is 90% propellant, which is "
        "what limits acceleration at the end rather than the start.",
        "Total impulse equals I_sp g₀ m_prop regardless of mass flow, so it is "
        "really a measure of how much propellant there is and how good it is. "
        "It is the right number for comparing motors of different burn times.",
        "Nothing here models the trajectory. Gravity losses (roughly g times "
        "burn time for a vertical climb) and drag losses are what separate "
        "this ideal delta-v from what the vehicle actually gains.",
        "The delta-v shown assumes the whole propellant load is spent in this "
        "one burn with no residuals and no ullage left behind.",
    ],
    graphs=[
        Sweep(over="mdot", y_label="Thrust [N]", lo=0.0, hi_factor=2.0,
              hi_min=2.0, title="Thrust vs propellant mass flow"),
        Sweep(over="isp", y_label="Thrust [N]", lo=0.0, hi_factor=1.6,
              hi_min=500.0, title="Thrust vs specific impulse"),
        Sweep(over="m_lift", y_label="Liftoff thrust-to-weight [-]",
              lo_factor=0.4, hi_factor=2.0, fn=_twr_vs_mass,
              x_label="Liftoff mass [kg]",
              title="Thrust-to-weight vs liftoff mass"),
        Sweep(over="m_prop", y_label="Burn time [s]", lo=0.0, hi_factor=2.0,
              fn=_burn_time_vs_propellant, x_label="Propellant mass [kg]",
              title="Burn time vs propellant mass"),
    ],
    references=[
        Reference(
            title="Typical liftoff thrust-to-weight",
            columns=("Stage", "T/W at ignition"),
            rows=[
                ("Launch vehicle first stage", "1.2 - 1.6"),
                ("Solid booster / sounding rocket", "3 - 10"),
                ("Upper stage, ignited in vacuum", "0.3 - 0.9"),
                ("Lunar / planetary lander, powered descent", "0.3 - 0.6"),
                ("Orbital manoeuvring and RCS", "0.01 - 0.1"),
                ("Electric propulsion", "10⁻⁵ - 10⁻⁴"),
            ],
            note="Measured against EARTH weight at ignition, which is the "
                 "convention even for stages that never see Earth's surface. "
                 "Below 1 a vehicle cannot lift off but can still accelerate "
                 "perfectly well in orbit; the penalty of a low T/W in a "
                 "gravity well is the delta-v lost to gravity during a long "
                 "burn, not an inability to move.",
        ),
        Reference(
            title="What one kilogram per second buys",
            columns=("Propulsion", "I_sp [s]", "Thrust per kg/s [N]"),
            rows=[
                ("Cold gas (nitrogen)", "70", "686"),
                ("Monopropellant hydrazine", "230", "2,255"),
                ("Solid motor", "250", "2,452"),
                ("Kerolox, sea level", "300", "2,942"),
                ("Kerolox, vacuum", "340", "3,334"),
                ("Hydrolox, vacuum", "450", "4,413"),
                ("Hall thruster", "1,800", "17,652"),
            ],
            note="Exactly I_sp × 9.80665, since F/ṁ = v_e. It shows what "
                 "specific impulse really means: the thrust you get for each "
                 "kilogram per second you are willing to throw away. The Hall "
                 "thruster row is arithmetically true and practically "
                 "irrelevant - no electric thruster can be fed anywhere near "
                 "a kilogram per second, because the electrical power needed "
                 "would be gigawatts.",
        ),
    ],
    related=["prop.rocket_equation", "flight.twr", "mech.force",
             "mech.momentum", "mech.power"],
    variables=[
        ("$F$", "Thrust", "N"),
        ("$\\dot{m}$", "Propellant mass flow rate", "kg/s"),
        ("$I_{sp}$", "Specific impulse", "s"),
        ("$g_0$", "Standard gravity, 9.80665 (a unit conversion)", "m/s²"),
        ("$v_e$", "Effective exhaust velocity, I_sp g₀", "m/s"),
        ("$m_p$", "Propellant mass", "kg"),
        ("$t_b$", "Burn time at constant mass flow", "s"),
        ("$I_{tot}$", "Total impulse, F t_b", "N·s"),
    ],
    example=(
        "Sizing a small stage. Burning 8 kg/s at I_sp = 300 s gives 23.54 kN "
        "of thrust. With 1200 kg of propellant the burn lasts 150 s and "
        "delivers 3.53 MN·s of total impulse. On a 1600 kg vehicle that is a "
        "liftoff thrust-to-weight of 1.50, so it accelerates upward at "
        "4.90 m/s² to begin with - and the rocket equation gives the same "
        "stage 4.08 km/s of ideal delta-v. Halve the mass flow to 4 kg/s and "
        "thrust halves to 11.77 kN: the delta-v is unchanged at 4.08 km/s, but "
        "thrust-to-weight falls to 0.75 and the vehicle never leaves the pad."),
    keywords=("thrust", "mass flow", "mdot", "burn time", "total impulse",
              "rocket", "specific impulse", "twr", "thrust to weight",
              "engine", "staging"),
)


CALCULATORS = [_MOMENTUM, _HOVER_ENDURANCE, _PROPELLER, _MOTOR, _ROCKET,
               _ROCKET_THRUST]
