"""Flight-performance calculators.

Only equations that are exact or have clearly stated assumptions are included.
Breguet range/endurance is deliberately left out of version 1 because its result
depends heavily on assumptions (specific fuel consumption, cruise schedule) that
deserve their own dedicated page rather than a hidden default.
"""
from __future__ import annotations

import numpy as np
import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import G0, RHO_SL
from utils.plotting import PRIMARY, mark_point, new_figure, show

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


def render_twr() -> None:
    p = "flight_twr"
    ui.page_header(
        "Thrust-to-weight ratio",
        r"TWR = \frac{T}{W},\qquad W = m\,g",
        "Thrust divided by weight - both forces, so the result is dimensionless. "
        "Below 1 the vehicle cannot accelerate vertically; above 1 it can climb "
        "straight up. Mixing mass (kg) with thrust (N) here is the classic error, "
        "so the input below converts for you and shows its working.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        thrust = ui.number("Total thrust T", "N", f"{p}_t", 1600.0, min_value=0.0)
    with c2:
        weight = ui.weight_inputs(p, default_mass=120.0, label="Vehicle")

    value = ui.compute(lambda: thrust_to_weight(thrust, weight))
    if value is not None:
        excess = thrust - weight
        ui.result(
            "Thrust-to-weight ratio", value, "-",
            secondary=[
                ("Excess thrust (T - W)", excess, "N"),
                ("Peak vertical acceleration (TWR - 1) × g", (value - 1.0) * G0,
                 "m/s²"),
                ("Vehicle mass", weight / G0, "kg"),
            ],
        )
        if value < 1.0:
            st.caption("TWR below 1: this vehicle cannot hover or climb vertically "
                       "on thrust alone. Fixed-wing aircraft are normally in this "
                       "range and use the wing to carry weight.")
    ui.assumptions([
        "Thrust is the total static thrust available at this air density and "
        "battery/throttle state. Electric motor thrust falls as the battery sags; "
        "propeller thrust falls with altitude and forward speed.",
        "Weight is computed with standard gravity g = 9.80665 m/s².",
        "The vertical-acceleration figure assumes thrust points straight up and "
        "ignores aerodynamic drag, so it is an upper bound.",
        "Reference points: airliner at take-off 0.25-0.35, aerobatic aircraft "
        "around 1, a stable camera multirotor 1.8-2.2, a racing quad 8-14.",
    ])
    ui.reference(
        variables=[
            ("$T$", "Total thrust", "N"),
            ("$W$", "Weight (force)", "N"),
            ("$m$", "Mass", "kg"),
            ("$g$", "Standard gravity, 9.80665", "m/s²"),
        ],
        example="Multirotor design check. A 2.5 kg quadcopter weighs 24.5 N. Four "
                "motors each producing 12 N give 48 N total, a TWR of about 2.0 - "
                "the usual target, because hovering then sits near 50% throttle and "
                "leaves control authority in both directions.",
    )


def render_pwr() -> None:
    p = "flight_pwr"
    ui.page_header(
        "Power-to-weight ratio",
        r"\frac{P}{m}\;\left[\mathrm{W/kg}\right], \qquad \frac{P}{W}\;"
        r"\left[\mathrm{W/N} = \mathrm{m/s}\right]",
        "Usually quoted as watts per kilogram, which is strictly a power-to-<b>mass"
        "</b> ratio. Both forms are shown: divide by mass for the industry-standard "
        "W/kg, or by weight for W/N, which has units of metres per second and is an "
        "absolute ceiling on climb rate.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        power = ui.number("Power P", "W", f"{p}_p", 1500.0, min_value=0.0)
    with c2:
        mass = ui.number("Mass m", "kg", f"{p}_m", 2.5, min_value=0.0)

    value = ui.compute(lambda: power_to_mass(power, mass))
    if value is not None:
        weight = mass * G0
        ui.result(
            "Power-to-mass ratio P/m", value, "W/kg",
            secondary=[
                ("Weight W = m g", weight, "N"),
                ("Power per unit weight P/W", power / weight, "W/N  (= m/s)"),
                ("Absolute climb-rate ceiling (no drag, 100% efficient)",
                 power / weight, "m/s"),
            ],
        )
    ui.assumptions([
        "P is the power at the stated point in the chain. Electrical input power to "
        "the ESC, shaft power at the motor, and useful propulsive power delivered "
        "to the air are three different numbers - say which one you mean.",
        "The climb-rate ceiling assumes every watt becomes potential energy: no "
        "drag, no propeller loss, no motor loss. Real climb rate is a fraction of "
        "it. This is an upper bound, not a prediction.",
        "W/kg is a power-to-mass ratio. The term 'power-to-weight' is conventional "
        "but not dimensionally accurate.",
    ])
    ui.reference(
        variables=[
            ("$P$", "Power", "W"),
            ("$m$", "Mass", "kg"),
            ("$W$", "Weight, m g", "N"),
        ],
        example="Racing drone comparison. A 600 g quad pulling 1200 W has 2000 W/kg, "
                "roughly ten times a family car. That number, not thrust alone, is "
                "what makes the acceleration feel violent.",
    )


def render_stall_speed() -> None:
    p = "flight_vs"
    ui.page_header(
        "Stall speed",
        r"V_{stall} = \sqrt{\frac{2W}{\rho\,S\,C_{L,max}}}",
        "The slowest speed at which the wing can still carry the weight in level "
        "flight. It comes straight from setting lift equal to weight and using the "
        "largest lift coefficient the wing can reach before it stalls.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        weight = ui.weight_inputs(p, default_mass=12.0, label="Aircraft")
    with c2:
        rho = ui.number("Air density ρ", "kg/m³", f"{p}_rho", RHO_SL,
                        min_value=0.0)
        area = ui.number("Wing area S", "m²", f"{p}_s", 0.65, min_value=0.0)
    with c3:
        cl_max = ui.number("Maximum lift coefficient C_Lmax", "-", f"{p}_clmax", 1.3,
                           min_value=0.0,
                           help="Clean wing typically 1.2-1.5; with flaps 1.8-2.5. "
                                "Use wind-tunnel or flight-test data if you have it.")

    value = ui.compute(lambda: stall_speed(weight, rho, area, cl_max))
    if value is not None:
        ui.result(
            "Stall speed V_stall", value, "m/s",
            secondary=[
                ("In km/h", value * 3.6, "km/h"),
                ("Recommended approach speed (1.3 × V_stall)", value * 1.3, "m/s"),
                ("Stall speed in a 45 ° banked turn (x 1.19)", value * 1.1892,
                 "m/s"),
            ],
        )
    ui.assumptions([
        "Steady, wings-level, 1 g flight. In a banked turn the load factor n "
        "raises stall speed by sqrt(n) - a 60 ° bank means n = 2 and a 41% "
        "higher stall speed.",
        "C_Lmax is the single most uncertain input here and is Reynolds-dependent. "
        "A small slow aircraft will not reach the C_Lmax quoted for a full-size one.",
        "This is an estimate of aerodynamic stall only. Propeller slipstream, "
        "ground effect and centre-of-gravity position all shift real stall speed.",
        "The 1.3x approach-speed figure is a common convention, not a regulation.",
    ])

    if ui.graph_toggle(p):
        weights = np.linspace(max(weight * 0.3, 1.0), weight * 1.7, 200)
        fig, (ax,) = new_figure()
        ax.plot(weights, np.sqrt(2.0 * weights / (rho * area * cl_max)),
                color=PRIMARY, linewidth=2)
        mark_point(ax, weight, stall_speed(weight, rho, area, cl_max), "current")
        ax.set_xlabel("Weight W [N]")
        ax.set_ylabel("Stall speed [m/s]")
        ax.set_title("Stall speed vs weight (square-root relationship)",
                     fontsize=10, loc="left")
        show(fig)

    ui.reference(
        variables=[
            ("$V_{stall}$", "Stall speed (true airspeed)", "m/s"),
            ("$W$", "Weight", "N"),
            ("$\\rho$", "Air density", "kg/m³"),
            ("$S$", "Wing area", "m²"),
            ("$C_{L,max}$", "Maximum usable lift coefficient", "-"),
        ],
        example="Setting a safe launch speed for a fixed-wing UAV. Adding a 2 kg "
                "payload to a 10 kg airframe raises weight by 20%, so stall speed "
                "rises by sqrt(1.2) = 9.5%. Landing gear and airframe loads rise "
                "with the square of that speed.",
    )


def render_climb() -> None:
    p = "flight_roc"
    ui.page_header(
        "Rate of climb (steady climb)",
        r"RC = \frac{V\,(T - D)}{W} = V \sin\gamma",
        "Climb comes from <b>excess thrust</b>. Whatever thrust is left after "
        "balancing drag gets converted into gaining height. Multiply that excess "
        "by airspeed and divide by weight and you have the vertical speed.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        thrust = ui.number("Thrust T", "N", f"{p}_t", 40.0, min_value=0.0)
        drag_force = ui.number("Drag D at this speed", "N", f"{p}_d", 14.0,
                               min_value=0.0)
    with c2:
        velocity = ui.number("Airspeed V", "m/s", f"{p}_v", 22.0, min_value=0.0)
    with c3:
        weight = ui.weight_inputs(p, default_mass=12.0, label="Aircraft")

    value = ui.compute(lambda: rate_of_climb(thrust, drag_force, velocity, weight))
    if value is not None:
        ratio = max(min((thrust - drag_force) / weight, 1.0), -1.0)
        ui.result(
            "Rate of climb", value, "m/s",
            secondary=[
                ("Climb angle γ", float(np.degrees(np.arcsin(ratio))), "°"),
                ("Excess thrust (T - D)", thrust - drag_force, "N"),
                ("Excess power (T - D) × V", (thrust - drag_force) * velocity, "W"),
                ("Time to climb 100 m", 100.0 / value if value > 0
                 else float("nan"), "s"),
            ],
        )
        if thrust < drag_force:
            st.caption("Thrust is less than drag, so this is a descent: the "
                       "negative rate of climb is the sink rate.")
    ui.assumptions([
        "Steady (unaccelerated) climb: airspeed is constant, so all excess power "
        "goes into height, none into acceleration.",
        "Thrust acts along the flight path. For a propeller aircraft climbing at a "
        "shallow angle this is a good approximation.",
        "D is the drag at this airspeed <b>in the climb</b>. Lift in a climb equals "
        "W cos(γ), slightly less than in level flight, so induced drag is "
        "slightly lower than the level-flight value.",
        "The climb angle uses sin(γ) = (T - D)/W, which is exact for a steady "
        "climb and is capped at plus/minus 90 degrees here.",
    ])
    ui.reference(
        variables=[
            ("$RC$", "Rate of climb (vertical speed)", "m/s"),
            ("$V$", "True airspeed along the flight path", "m/s"),
            ("$T$", "Thrust", "N"),
            ("$D$", "Drag", "N"),
            ("$W$", "Weight", "N"),
            ("$\\gamma$", "Climb angle relative to the horizon", "°"),
        ],
        example="Checking whether a UAV clears an obstacle after launch. A 12 kg "
                "aircraft weighs 117.7 N. With 40 N of thrust against 14 N of drag "
                "at 22 m/s, the climb rate is 4.9 m/s and the climb angle is 12.8 "
                "degrees - so a 30 m mast 200 m down the runway is cleared with "
                "room to spare, but a 50 m one is not.",
    )


CALCULATORS = {
    "Thrust-to-weight ratio": render_twr,
    "Power-to-weight ratio": render_pwr,
    "Stall speed": render_stall_speed,
    "Rate of climb": render_climb,
}
