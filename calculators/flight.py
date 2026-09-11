"""Flight-performance calculators.

Only equations that are exact or have clearly stated assumptions are included.
Breguet range/endurance is deliberately left out of version 1 because its result
depends heavily on assumptions (specific fuel consumption, cruise schedule) that
deserve their own dedicated page rather than a hidden default.
"""
from __future__ import annotations

import numpy as np

from utils import validation as v
from utils.constants import G0, RHO_SL
from utils.spec import Calculator, Field, Output, Secondary, Sweep

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def weight_from_mass(mass: float) -> float:
    """W = m * g0   [N]. The single place mass becomes weight."""
    mass = v.non_negative(mass, "Mass", "kg")
    return mass * G0


def thrust_to_weight(thrust: float, weight: float) -> float:
    """TWR = T / W   [-]  (dimensionless: force divided by force)"""
    thrust = v.non_negative(thrust, "Thrust", "N")
    weight = v.positive(weight, "Weight", "N")
    return thrust / weight


def power_to_mass(power: float, mass: float) -> float:
    """P/m   [W/kg]. Commonly called 'power-to-weight', but the unit is per kg."""
    power = v.non_negative(power, "Power", "W")
    mass = v.positive(mass, "Mass", "kg")
    return power / mass


def stall_speed(weight: float, rho: float, area: float, cl_max: float) -> float:
    """V_stall = sqrt( 2W / (ρ * S * C_Lmax) )   [m/s]

    From L = W in steady 1 g level flight at the maximum usable C_L.
    """
    weight = v.non_negative(weight, "Weight", "N")
    rho = v.positive(rho, "Air density", "kg/m³")
    area = v.positive(area, "Wing area", "m²")
    cl_max = v.positive(cl_max, "Maximum lift coefficient")
    return float(np.sqrt(2.0 * weight / (rho * area * cl_max)))


def rate_of_climb(thrust: float, drag: float, velocity: float, weight: float) -> float:
    """RC = V * (T - D) / W   [m/s]

    Exact for a steady (unaccelerated) climb with thrust along the flight path:
    T - D - W sin(γ) = 0, and RC = V sin(γ).
    """
    thrust = v.non_negative(thrust, "Thrust", "N")
    drag = v.non_negative(drag, "Drag", "N")
    velocity = v.non_negative(velocity, "Airspeed", "m/s")
    weight = v.positive(weight, "Weight", "N")
    return velocity * (thrust - drag) / weight


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

_TWR = Calculator(
    slug="flight.twr",
    name="Thrust-to-weight ratio",
    latex=r"TWR = \frac{T}{W},\qquad W = m\,g",
    explanation=(
        "Thrust divided by weight - both forces, so the result is dimensionless. "
        "Below 1 the vehicle cannot accelerate vertically; above 1 it can climb "
        "straight up. Mixing mass (kg) with thrust (N) here is the classic error, "
        "so the input below converts for you and shows its working."
    ),
    inputs=[
        Field("thrust", "Total thrust T", "N", 1600.0, min=0.0),
        Field("weight", "Vehicle", "", 120.0, kind="weight"),
    ],
    compute=lambda i: thrust_to_weight(i.thrust, i.weight),
    result=Output("Thrust-to-weight ratio", "-"),
    secondary=[
        Secondary("Excess thrust (T - W)", "N", lambda i, r: i.thrust - i.weight),
        Secondary("Peak vertical acceleration (TWR - 1) × g", "m/s²",
                  lambda i, r: (r - 1.0) * G0),
        Secondary("Vehicle mass", "kg", lambda i, r: i.weight / G0),
    ],
    note=lambda i, r: ("TWR below 1: this vehicle cannot hover or climb vertically "
                       "on thrust alone. Fixed-wing aircraft are normally in this "
                       "range and use the wing to carry weight.") if r < 1.0 else None,
    assumptions=[
        "Thrust is the total static thrust available at this air density and "
        "battery/throttle state. Electric motor thrust falls as the battery sags; "
        "propeller thrust falls with altitude and forward speed.",
        "Weight is computed with standard gravity g = 9.80665 m/s².",
        "The vertical-acceleration figure assumes thrust points straight up and "
        "ignores aerodynamic drag, so it is an upper bound.",
        "Reference points: airliner at take-off 0.25-0.35, aerobatic aircraft "
        "around 1, a stable camera multirotor 1.8-2.2, a racing quad 8-14.",
    ],
    variables=[
        ("$T$", "Total thrust", "N"),
        ("$W$", "Weight (force)", "N"),
        ("$m$", "Mass", "kg"),
        ("$g$", "Standard gravity, 9.80665", "m/s²"),
    ],
    example=(
        "Multirotor design check. A 2.5 kg quadcopter weighs 24.5 N. Four motors "
        "each producing 12 N give 48 N total, a TWR of about 2.0 - the usual "
        "target, because hovering then sits near 50% throttle and leaves control "
        "authority in both directions."
    ),
    keywords=("twr", "thrust", "weight", "ratio"),
)

_PWR = Calculator(
    slug="flight.power_to_weight",
    name="Power-to-weight ratio",
    latex=(r"\frac{P}{m}\;\left[\mathrm{W/kg}\right], \qquad \frac{P}{W}\;"
           r"\left[\mathrm{W/N} = \mathrm{m/s}\right]"),
    explanation=(
        "Usually quoted as watts per kilogram, which is strictly a power-to-<b>mass"
        "</b> ratio. Both forms are shown: divide by mass for the industry-standard "
        "W/kg, or by weight for W/N, which has units of metres per second and is an "
        "absolute ceiling on climb rate."
    ),
    inputs=[
        Field("power", "Power P", "W", 1500.0, min=0.0),
        Field("mass", "Mass m", "kg", 2.5, min=0.0),
    ],
    compute=lambda i: power_to_mass(i.power, i.mass),
    result=Output("Power-to-mass ratio P/m", "W/kg"),
    secondary=[
        Secondary("Weight W = m g", "N", lambda i, r: i.mass * G0),
        Secondary("Power per unit weight P/W", "W/N  (= m/s)",
                  lambda i, r: i.power / (i.mass * G0)),
        Secondary("Absolute climb-rate ceiling (no drag, 100% efficient)", "m/s",
                  lambda i, r: i.power / (i.mass * G0)),
    ],
    assumptions=[
        "P is the power at the stated point in the chain. Electrical input power to "
        "the ESC, shaft power at the motor, and useful propulsive power delivered "
        "to the air are three different numbers - say which one you mean.",
        "The climb-rate ceiling assumes every watt becomes potential energy: no "
        "drag, no propeller loss, no motor loss. Real climb rate is a fraction of "
        "it. This is an upper bound, not a prediction.",
        "W/kg is a power-to-mass ratio. The term 'power-to-weight' is conventional "
        "but not dimensionally accurate.",
    ],
    variables=[
        ("$P$", "Power", "W"),
        ("$m$", "Mass", "kg"),
        ("$W$", "Weight, m g", "N"),
    ],
    example=(
        "Racing drone comparison. A 600 g quad pulling 1200 W has 2000 W/kg, "
        "roughly ten times a family car. That number, not thrust alone, is what "
        "makes the acceleration feel violent."
    ),
    keywords=("power", "weight", "pwr", "wkg"),
)

_STALL = Calculator(
    slug="flight.stall_speed",
    name="Stall speed",
    latex=r"V_{stall} = \sqrt{\frac{2W}{\rho\,S\,C_{L,max}}}",
    explanation=(
        "The slowest speed at which the wing can still carry the weight in level "
        "flight. It comes straight from setting lift equal to weight and using the "
        "largest lift coefficient the wing can reach before it stalls."
    ),
    inputs=[
        Field("weight", "Aircraft", "", 12.0, kind="weight"),
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0),
        Field("s", "Wing area S", "m²", 0.65, min=0.0),
        Field("cl_max", "Maximum lift coefficient C_Lmax", "-", 1.3, min=0.0,
              help="Clean wing typically 1.2-1.5; with flaps 1.8-2.5. Use "
                   "wind-tunnel or flight-test data if you have it."),
    ],
    compute=lambda i: stall_speed(i.weight, i.rho, i.s, i.cl_max),
    result=Output("Stall speed V_stall", "m/s"),
    secondary=[
        Secondary("In km/h", "km/h", lambda i, r: r * 3.6),
        Secondary("Recommended approach speed (1.3 × V_stall)", "m/s",
                  lambda i, r: r * 1.3),
        Secondary("Stall speed in a 45° banked turn (× 1.19)", "m/s",
                  lambda i, r: r * 1.1892),
    ],
    assumptions=[
        "Steady, wings-level, 1 g flight. In a banked turn the load factor n "
        "raises stall speed by sqrt(n) - a 60° bank means n = 2 and a 41% higher "
        "stall speed.",
        "C_Lmax is the single most uncertain input here and is Reynolds-dependent. "
        "A small slow aircraft will not reach the C_Lmax quoted for a full-size one.",
        "This is an estimate of aerodynamic stall only. Propeller slipstream, "
        "ground effect and centre-of-gravity position all shift real stall speed.",
        "The 1.3x approach-speed figure is a common convention, not a regulation.",
    ],
    graph=Sweep(over="weight", y_label="Stall speed [m/s]", lo_factor=0.3,
                hi_factor=1.7, x_label="Weight W [N]",
                title="Stall speed vs weight (square-root relationship)"),
    variables=[
        ("$V_{stall}$", "Stall speed (true airspeed)", "m/s"),
        ("$W$", "Weight", "N"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$S$", "Wing area", "m²"),
        ("$C_{L,max}$", "Maximum usable lift coefficient", "-"),
    ],
    example=(
        "Setting a safe launch speed for a fixed-wing UAV. Adding a 2 kg payload "
        "to a 10 kg airframe raises weight by 20%, so stall speed rises by "
        "sqrt(1.2) = 9.5%. Landing gear and airframe loads rise with the square of "
        "that speed."
    ),
    keywords=("stall", "vstall", "minimum speed", "clmax"),
)


def _climb_note(i, value):
    if i.thrust < i.drag_force:
        return ("Thrust is less than drag, so this is a descent: the negative rate "
                "of climb is the sink rate.")
    return None


_CLIMB = Calculator(
    slug="flight.rate_of_climb",
    name="Rate of climb",
    latex=r"RC = \frac{V\,(T - D)}{W} = V \sin\gamma",
    explanation=(
        "Climb comes from <b>excess thrust</b>. Whatever thrust is left after "
        "balancing drag gets converted into gaining height. Multiply that excess "
        "by airspeed and divide by weight and you have the vertical speed."
    ),
    inputs=[
        Field("thrust", "Thrust T", "N", 40.0, min=0.0),
        Field("drag_force", "Drag D at this speed", "N", 14.0, min=0.0),
        Field("velocity", "Airspeed V", "m/s", 22.0, min=0.0),
        Field("weight", "Aircraft", "", 12.0, kind="weight"),
    ],
    compute=lambda i: rate_of_climb(i.thrust, i.drag_force, i.velocity, i.weight),
    result=Output("Rate of climb", "m/s"),
    secondary=[
        Secondary("Climb angle γ", "°", lambda i, r: float(np.degrees(np.arcsin(
            max(min((i.thrust - i.drag_force) / i.weight, 1.0), -1.0))))),
        Secondary("Excess thrust (T - D)", "N",
                  lambda i, r: i.thrust - i.drag_force),
        Secondary("Excess power (T - D) × V", "W",
                  lambda i, r: (i.thrust - i.drag_force) * i.velocity),
        Secondary("Time to climb 100 m", "s",
                  lambda i, r: 100.0 / r if r > 0 else float("nan")),
    ],
    note=_climb_note,
    assumptions=[
        "Steady (unaccelerated) climb: airspeed is constant, so all excess power "
        "goes into height, none into acceleration.",
        "Thrust acts along the flight path. For a propeller aircraft climbing at a "
        "shallow angle this is a good approximation.",
        "D is the drag at this airspeed <b>in the climb</b>. Lift in a climb equals "
        "W cos(γ), slightly less than in level flight, so induced drag is slightly "
        "lower than the level-flight value.",
        "The climb angle uses sin(γ) = (T - D)/W, which is exact for a steady "
        "climb and is capped at plus/minus 90 degrees here.",
    ],
    variables=[
        ("$RC$", "Rate of climb (vertical speed)", "m/s"),
        ("$V$", "True airspeed along the flight path", "m/s"),
        ("$T$", "Thrust", "N"),
        ("$D$", "Drag", "N"),
        ("$W$", "Weight", "N"),
        ("$\\gamma$", "Climb angle relative to the horizon", "°"),
    ],
    example=(
        "Checking whether a UAV clears an obstacle after launch. A 12 kg aircraft "
        "weighs 117.7 N. With 40 N of thrust against 14 N of drag at 22 m/s, the "
        "climb rate is 4.9 m/s and the climb angle is 12.8 degrees - so a 30 m mast "
        "200 m down the runway is cleared with room to spare, but a 50 m one is not."
    ),
    keywords=("climb", "roc", "vertical speed", "excess thrust"),
)

CALCULATORS = [_TWR, _PWR, _STALL, _CLIMB]
