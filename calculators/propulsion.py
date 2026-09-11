"""Propulsion: momentum theory, hover power, and the rocket equation.

Everything hover-related in v1.0.0 was bookkeeping - thrust sums, watt-hours.
Momentum theory is the first physics here that explains *why* hovering costs
what it costs, and it is the foundation the rest of rotor performance sits on.

Structure: pure functions first (self-validating, unit-tested), then Calculator
specs. See calculators/aerodynamics.py for the worked example.
"""
from __future__ import annotations

import numpy as np

from utils import validation as v
from utils.constants import G0, RHO_SL
from utils.spec import Calculator, Field, Output, Secondary, Sweep

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


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def _momentum_note(i, value):
    if i.climb_speed < 0 and i.climb_speed > -2.0 * induced_velocity_hover(
            i.thrust, disk_area(i.radius), i.rho):
        return ("DESCENT INSIDE THE VORTEX RING STATE. Momentum theory does not "
                "apply here - the rotor is descending into its own wake and the "
                "equations return a confident but meaningless answer. Real "
                "aircraft lose lift unpredictably in this region.")
    return None


_MOMENTUM = Calculator(
    slug="prop.momentum_theory",
    name="Momentum theory (hover)",
    latex=(r"v_h = \sqrt{\frac{T}{2\rho A}}, \qquad "
           r"P_{ideal} = T\,v_h = \frac{T^{3/2}}{\sqrt{2\rho A}}"),
    explanation=(
        "Why hovering costs what it costs. A rotor holds an aircraft up by "
        "throwing air downwards, and the power needed is the thrust times the "
        "speed it must throw that air. Because power goes as <b>T^1.5</b>, 10% "
        "more mass costs about 15% more power - the single most important "
        "non-linearity in multirotor design."),
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
        Secondary("Ideal power loading", "g/W",
                  lambda i, r: i.thrust / r / G0 * 1000.0),
        Secondary("Disk area", "m²", lambda i, r: disk_area(i.radius)),
    ],
    note=_momentum_note,
    assumptions=[
        "IDEAL ROTOR: uniform inflow through an infinitely thin disk, "
        "incompressible, inviscid, no swirl, no blade count, no tip losses and "
        "no profile drag. Real total power is roughly this divided by the "
        "figure of merit.",
        "This is a LOWER BOUND on power. Nothing can hover for less.",
        "Use the swept DISK area, pi R squared - not blade area. For a "
        "multirotor use thrust per rotor and multiply the power by the rotor "
        "count.",
        "Valid in hover and axial climb. In descent between roughly 0 and "
        "-2 v_h the rotor enters the vortex ring state, where momentum theory "
        "fails completely.",
        "Typical figure of merit: 0.4-0.6 small multirotor props, 0.6-0.7 good "
        "UAV rotors, 0.7-0.8 full-scale helicopters. Above 0.8 means a "
        "measurement error, not a breakthrough.",
    ],
    graph=Sweep(over="radius", y_label="Ideal hover power [W]",
                lo_factor=0.35, hi_factor=2.2,
                title="Bigger, slower rotors always win: power vs rotor radius "
                      "at constant thrust"),
    variables=[
        ("$T$", "Thrust produced by one rotor", "N"),
        ("$A$", "Swept disk area, pi R squared", "m²"),
        ("$R$", "Rotor radius", "m"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$v_h$", "Induced velocity in hover", "m/s"),
        ("$P_{ideal}$", "Ideal (induced) hover power", "W"),
    ],
    example=(
        "Why big props win. A 2 kg quadcopter needs 4.9 N per rotor. On 5-inch "
        "props (0.0635 m radius) the ideal power is 62 W per rotor; on 10-inch "
        "props (0.127 m) it is 31 W - half, for the same thrust. Halving disk "
        "loading cuts induced power by 1/sqrt(2). That is the whole argument "
        "for large, slow-turning rotors on endurance aircraft."),
    keywords=("momentum", "actuator disk", "hover", "disk loading", "induced",
              "figure of merit", "rotor"),
)

_HOVER_ENDURANCE = Calculator(
    slug="prop.hover_endurance",
    name="Hover power & endurance",
    latex=(r"P_{elec} = \frac{N\,(W/N)^{3/2}}{\sqrt{2\rho A}\;FM\;\eta}, "
           r"\qquad t = \frac{E\,DoD}{P_{elec}}"),
    explanation=(
        "Chains momentum theory to the battery: how long can this aircraft "
        "actually hover? Because power scales as mass^1.5, every gram costs "
        "more than linearly - which is why adding a battery eventually stops "
        "helping, as the pack starts carrying itself."),
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
        Secondary("Average current at 22.2 V", "A", lambda i, r: r / 22.2),
    ],
    assumptions=[
        "HOVER ONLY, and hover is the expensive case. A multirotor in efficient "
        "forward flight typically uses 20-30% less power, so this is a "
        "conservative floor rather than a mission time.",
        "Constant power for the whole flight: no climb, no wind, no manoeuvring.",
        "Figure of merit and drivetrain efficiency are both assumed constant. "
        "Both fall away from their design point.",
        "Battery energy is at pack level, not cell level. Modern cells reach "
        "250-300 Wh/kg, but a finished pack is 150-220 Wh/kg after BMS, wiring "
        "and case.",
        "Ignores voltage sag and the Peukert effect, both of which reduce real "
        "delivered energy at high current.",
    ],
    graph=Sweep(over="weight", y_label="Hover power [W]",
                x_label="All-up weight [N]", lo_factor=0.4, hi_factor=2.0,
                title="Power vs weight - note the curve, not a straight line "
                      "(P is proportional to W^1.5)"),
    variables=[
        ("$W$", "All-up weight", "N"),
        ("$N$", "Number of rotors", "-"),
        ("$FM$", "Figure of merit", "-"),
        ("$\\eta$", "Motor and ESC efficiency", "-"),
        ("$E$", "Battery energy", "Wh"),
        ("$DoD$", "Usable fraction of the battery", "-"),
    ],
    example=(
        "The payload question. A 2 kg quad on 10-inch props hovering at 55% "
        "figure of merit draws about 280 W and lasts roughly 19 minutes on a "
        "111 Wh pack. Add a 400 g camera and power rises to about 368 W - a 20% "
        "mass increase costing 31% more power, and cutting endurance to about "
        "14.5 minutes."),
    keywords=("hover", "endurance", "payload", "power", "battery", "flight time"),
)

_ROCKET = Calculator(
    slug="prop.rocket_equation",
    name="Rocket equation",
    latex=r"\Delta v = I_{sp}\,g_0 \ln\!\left(\frac{m_0}{m_f}\right)",
    explanation=(
        "Tsiolkovsky's equation: the velocity change a rocket can produce "
        "depends only on its exhaust velocity and the <b>ratio</b> of its wet "
        "to dry mass. The logarithm is brutal - each extra km/s costs "
        "exponentially more propellant, which is why rockets are almost "
        "entirely fuel."),
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
    ],
    assumptions=[
        "NO EXTERNAL FORCES: no gravity, no atmospheric drag, no steering "
        "losses. Reaching low Earth orbit needs about 9.4 km/s of delta-v even "
        "though orbital velocity is only 7.8 km/s - that 1.6 km/s gap is the "
        "losses this equation does not contain.",
        "g₀ = 9.80665 m/s² is a UNIT CONVERSION between specific impulse in "
        "seconds and exhaust velocity. It is not local gravity - using Mars "
        "gravity here is a classic mistake.",
        "Constant exhaust velocity and a single burn in one direction.",
        "I_sp differs between sea level and vacuum for the same engine, because "
        "nozzle expansion depends on ambient pressure.",
    ],
    graph=Sweep(over="mf", y_label="Delta-v [m/s]", lo_factor=0.15,
                hi_factor=1.6, x_label="Final (dry) mass [kg]",
                title="Delta-v vs dry mass - the logarithm punishes heavy "
                      "structure severely"),
    variables=[
        ("$\\Delta v$", "Achievable velocity change", "m/s"),
        ("$I_{sp}$", "Specific impulse", "s"),
        ("$g_0$", "Standard gravity, 9.80665 (a unit conversion)", "m/s²"),
        ("$m_0$", "Initial mass, including propellant", "kg"),
        ("$m_f$", "Final mass, after the burn", "kg"),
    ],
    example=(
        "Staging maths. A vehicle with I_sp = 300 s burning from 1000 kg to "
        "300 kg gets 3.54 km/s - well short of orbit. Shedding dry mass to "
        "200 kg raises it to 4.73 km/s. That sensitivity to structural mass is "
        "why rockets stage, and why every kilogram of tank is fought over."),
    keywords=("rocket", "tsiolkovsky", "delta-v", "isp", "specific impulse",
              "space"),
)

CALCULATORS = [_MOMENTUM, _HOVER_ENDURANCE, _ROCKET]
