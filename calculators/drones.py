"""Drone / multirotor calculators.

Motor manufacturers quote thrust in grams-force, which is a force, not a mass.
The helper below converts it to newtons on the way in so nothing downstream has
to guess which one it is holding.
"""
from __future__ import annotations

import numpy as np
import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import G0, GRAM_FORCE_N
from utils.plotting import ACCENT, PRIMARY, mark_point, new_figure, show

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def grams_force_to_newton(gram_force: float) -> float:
    """1 gf = 0.00980665 N. A gram-force is a force, not a mass."""
    return v.non_negative(gram_force, "Thrust", "gf") * GRAM_FORCE_N


def total_thrust(n_motors: int, thrust_per_motor: float) -> float:
    """Total thrust = number of motors × thrust per motor   [N]"""
    n_motors = v.positive_int(n_motors, "Number of motors")
    thrust_per_motor = v.non_negative(thrust_per_motor, "Thrust per motor", "N")
    return n_motors * thrust_per_motor


def hover_thrust_per_motor(weight: float, n_motors: int) -> float:
    """Each motor carries an equal share of the weight in a level hover   [N]"""
    weight = v.non_negative(weight, "Weight", "N")
    n_motors = v.positive_int(n_motors, "Number of motors")
    return weight / n_motors


def flight_time_minutes(capacity_ah: float, usable_fraction: float,
                        average_current_a: float) -> float:
    """t = (usable capacity [Ah] / average current [A]) * 60   [minutes]"""
    capacity_ah = v.positive(capacity_ah, "Battery capacity", "Ah")
    usable_fraction = v.in_range(usable_fraction, "Usable capacity", 0.0, 1.0, "-")
    if usable_fraction == 0:
        raise v.ValidationError("Usable capacity cannot be 0% - there would be no "
                                "energy available.")
    average_current_a = v.positive(average_current_a, "Average current", "A")
    return (capacity_ah * usable_fraction / average_current_a) * 60.0


def electrical_power(voltage: float, current: float) -> float:
    """P = V * I   [W]"""
    voltage = v.finite(voltage, "Voltage", "V")
    current = v.finite(current, "Current", "A")
    return voltage * current


def battery_energy_wh(voltage: float, capacity_ah: float) -> float:
    """E = V * Ah   [Wh]"""
    voltage = v.non_negative(voltage, "Voltage", "V")
    capacity_ah = v.non_negative(capacity_ah, "Capacity", "Ah")
    return voltage * capacity_ah


# ---------------------------------------------------------------------------
# Shared input helper
# ---------------------------------------------------------------------------


def _thrust_input(prefix: str, label: str, default_gf: float) -> float:
    """Thrust entry in gf, kgf or N. Returns newtons."""
    unit = st.radio("Thrust unit", ["gram-force (gf)", "kilogram-force (kgf)",
                                    "newton (N)"],
                    key=f"{prefix}_tunit", horizontal=True,
                    help="Datasheets almost always use grams-force. "
                         "1 gf = 0.00980665 N.")
    if unit == "gram-force (gf)":
        gf = ui.number(label, "gf", f"{prefix}_tgf", default_gf, min_value=0.0)
        return grams_force_to_newton(gf)
    if unit == "kilogram-force (kgf)":
        kgf = ui.number(label, "kgf", f"{prefix}_tkgf", default_gf / 1000.0,
                        min_value=0.0)
        return grams_force_to_newton(kgf * 1000.0)
    return ui.number(label, "N", f"{prefix}_tn", default_gf * GRAM_FORCE_N,
                     min_value=0.0)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def render_total_thrust() -> None:
    p = "drone_total"
    ui.page_header(
        "Total thrust",
        r"T_{total} = N_{motors} \times T_{motor}",
        "Add up what the propulsion system can produce at full throttle. Motor "
        "datasheets quote thrust in grams-force; that is a <b>force</b>, and it is "
        "converted to newtons here so it can be compared with weight directly.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        n_motors = ui.integer("Number of motors", f"{p}_n", 4, min_value=1,
                              max_value=32)
    with c2:
        per_motor = _thrust_input(p, "Thrust per motor at full throttle", 1200.0)

    value = ui.compute(lambda: total_thrust(n_motors, per_motor))
    if value is not None:
        ui.result(
            "Total thrust", value, "N",
            secondary=[
                ("In grams-force", value / GRAM_FORCE_N, "gf"),
                ("In kilograms-force", value / (GRAM_FORCE_N * 1000.0), "kgf"),
                ("Maximum mass it can lift at 1 g", value / G0, "kg"),
            ],
        )
    ui.assumptions([
        "All motors produce their rated thrust at the same time. In practice the "
        "battery sags under full load, so total thrust is usually a few percent "
        "below the sum of individual bench figures.",
        "Bench thrust figures are measured static, at sea level, with a specified "
        "propeller and voltage. Change any of those and the number changes.",
        "Thrust in gf is converted with 1 gf = g × 0.001 kg = 0.00980665 N.",
        "No allowance is made for thrust lost to airframe download (the wash "
        "blowing onto arms and body), typically a few percent.",
    ])
    ui.reference(
        variables=[
            ("$T_{total}$", "Combined thrust of all motors", "N"),
            ("$N_{motors}$", "Number of motors", "-"),
            ("$T_{motor}$", "Thrust from one motor at full throttle", "N"),
        ],
        example="Component selection. Four motors rated 1200 gf each give 4800 gf "
                "= 47.1 N of thrust, which can lift 4.8 kg at 1 g. For a 2 kg "
                "aircraft that is a thrust-to-weight ratio of 2.4.",
    )


def render_drone_twr() -> None:
    p = "drone_twr"
    ui.page_header(
        "Drone thrust-to-weight ratio",
        r"TWR = \frac{T_{total}}{W} = \frac{N_{motors}\,T_{motor}}{m\,g}",
        "The headline number for multirotor performance. TWR of 1 means the "
        "aircraft can only just hold itself up at full throttle, with nothing left "
        "for control. Around 2 is the usual design target, so hover sits near "
        "half throttle with authority in both directions.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        n_motors = ui.integer("Number of motors", f"{p}_n", 4, min_value=1,
                              max_value=32)
    with c2:
        per_motor = _thrust_input(p, "Thrust per motor", 1200.0)
    with c3:
        weight = ui.weight_inputs(p, default_mass=2.0, label="All-up")

    value = ui.compute(
        lambda: total_thrust(n_motors, per_motor) / v.positive(weight, "Weight", "N"))
    if value is not None:
        thrust = total_thrust(n_motors, per_motor)
        hover_fraction = weight / thrust if thrust > 0 else float("nan")
        ui.result(
            "Thrust-to-weight ratio", value, "-",
            secondary=[
                ("Total thrust", thrust, "N"),
                ("All-up weight", weight, "N"),
                ("Thrust used in hover", hover_fraction * 100.0, "% of maximum"),
                ("Peak vertical acceleration", (value - 1.0) * G0, "m/s²"),
            ],
        )
        if value < 1.3:
            st.caption("Below about 1.3 there is very little control authority "
                       "left over after hovering; the aircraft will feel sluggish "
                       "and may not recover from a descent.")
        elif value > 6:
            st.caption("Very high TWR - typical of racing builds. Expect twitchy "
                       "handling and short flight times.")
    ui.assumptions([
        "Weight uses W = m g with g = 9.80665 m/s², at the all-up mass including "
        "battery, payload and camera.",
        "The hover-throttle figure assumes thrust is proportional to nothing in "
        "particular - it is simply the fraction of maximum thrust needed. Real "
        "throttle stick position is not linear with thrust.",
        "Static bench thrust: forward flight and descent through the rotor wash "
        "both change the real figure.",
    ])

    if ui.graph_toggle(p):
        thrust = total_thrust(n_motors, per_motor)
        sweep = np.linspace(0.1, max(thrust * 1.6, weight * 2.5), 200)
        fig, (ax,) = new_figure()
        ax.plot(sweep, sweep / weight, color=PRIMARY, linewidth=2)
        ax.axhline(1.0, color=ACCENT, linewidth=1, linestyle="--")
        ax.annotate("TWR = 1 (just hovers)", xy=(sweep[0], 1.0),
                    xytext=(4, 6), textcoords="offset points", fontsize=9,
                    color=ACCENT)
        ax.axhline(2.0, color="#8a94a6", linewidth=1, linestyle=":")
        ax.annotate("TWR = 2 (common target)", xy=(sweep[0], 2.0),
                    xytext=(4, 6), textcoords="offset points", fontsize=9,
                    color="#8a94a6")
        mark_point(ax, thrust, thrust / weight, "current")
        ax.set_xlabel("Total thrust [N]")
        ax.set_ylabel("Thrust-to-weight ratio [-]")
        ax.set_title(f"TWR vs total thrust at a fixed weight of "
                     f"{weight:.1f} N", fontsize=10, loc="left")
        show(fig)

    ui.reference(
        variables=[
            ("$T_{total}$", "Total thrust from all motors", "N"),
            ("$W$", "All-up weight", "N"),
            ("$m$", "All-up mass", "kg"),
        ],
        example="Deciding whether a new camera fits the budget. A 2.0 kg quad with "
                "47 N of thrust has TWR 2.4. Add a 400 g gimbal and weight rises to "
                "23.5 N, dropping TWR to 2.0 - still fine. Add another kilogram and "
                "TWR falls to 1.4, where climb performance and gust rejection start "
                "to suffer noticeably.",
    )


def render_hover_thrust() -> None:
    p = "drone_hover"
    ui.page_header(
        "Hover thrust per motor",
        r"T_{hover,motor} = \frac{W}{N_{motors}}",
        "In a level hover the motors share the weight equally. Comparing that "
        "share with each motor's maximum thrust tells you how hard the propulsion "
        "system is working just to stay in the air.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        weight = ui.weight_inputs(p, default_mass=2.0, label="All-up")
    with c2:
        n_motors = ui.integer("Number of motors", f"{p}_n", 4, min_value=1,
                              max_value=32)
    with c3:
        max_per_motor = _thrust_input(p, "Maximum thrust per motor", 1200.0)

    value = ui.compute(lambda: hover_thrust_per_motor(weight, n_motors))
    if value is not None:
        load = value / max_per_motor if max_per_motor > 0 else float("nan")
        ui.result(
            "Hover thrust per motor", value, "N",
            secondary=[
                ("In grams-force", value / GRAM_FORCE_N, "gf"),
                ("Fraction of each motor's maximum", load * 100.0, "%"),
                ("Remaining margin per motor", max_per_motor - value, "N"),
            ],
        )
        if np.isfinite(load) and load > 0.65:
            st.caption("Hovering above about 65% of maximum thrust leaves little "
                       "headroom for manoeuvring, wind, or a failing cell - and "
                       "motors run hot near their limit.")
    ui.assumptions([
        "Level hover, motors equally loaded, centre of gravity on the geometric "
        "centre. An off-centre CG makes some motors work harder than others.",
        "No wind and no vertical acceleration - a pure steady hover.",
        "Motor maximum thrust is the bench figure at the propeller and voltage the "
        "manufacturer tested with.",
    ])
    ui.reference(
        variables=[
            ("$T_{hover,motor}$", "Thrust each motor must make to hover", "N"),
            ("$W$", "All-up weight", "N"),
            ("$N_{motors}$", "Number of motors", "-"),
        ],
        example="Motor selection. A 2 kg quadcopter weighs 19.6 N, so each of four "
                "motors must produce 4.9 N (500 gf) to hover. Picking motors rated "
                "1200 gf means hovering at about 42% of maximum - a healthy margin "
                "and a good efficiency point.",
    )


def render_flight_time() -> None:
    p = "drone_time"
    ui.page_header(
        "Flight time (estimate)",
        r"t_{min} = \frac{C_{Ah} \times \text{usable fraction}}{I_{avg}} \times 60",
        "A first-order estimate of endurance. Usable capacity matters: discharging "
        "a lithium pack to empty damages it, so most pilots plan on using 70-85% "
        "of the rated capacity. This is an <b>estimate</b>, not a guarantee.",
        p,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        capacity = ui.number("Battery capacity", "Ah", f"{p}_cap", 5.0,
                             min_value=0.0,
                             help="A 5000 mAh pack is 5.0 Ah.")
        voltage = ui.number("Nominal pack voltage", "V", f"{p}_v", 22.2,
                            min_value=0.0,
                            help="3.7 V per cell nominal: 6S = 22.2 V.")
    with c2:
        usable_pct = st.slider("Usable capacity [%]", min_value=10, max_value=100,
                               value=80, step=5, key=f"{p}_usable",
                               help="Fraction of rated capacity you are willing to "
                                    "draw before landing.")
    with c3:
        current = ui.number("Average current draw", "A", f"{p}_i", 25.0,
                            min_value=0.0,
                            help="Average over the whole flight, not the peak.")

    value = ui.compute(
        lambda: flight_time_minutes(capacity, usable_pct / 100.0, current))
    if value is not None:
        usable_ah = capacity * usable_pct / 100.0
        ui.result(
            "Estimated flight time", value, "minutes",
            secondary=[
                ("Usable capacity", usable_ah, "Ah"),
                ("Average electrical power", voltage * current, "W"),
                ("Energy used", voltage * usable_ah, "Wh"),
                ("Discharge rate (C-rate)", current / capacity, "C"),
            ],
        )
    ui.assumptions([
        "ESTIMATE, not an exact relationship. Real endurance depends on wind, "
        "flying style, temperature and payload.",
        "Current is assumed constant at the average value. A multirotor draws far "
        "more while climbing or fighting wind than while hovering.",
        "Rated capacity is measured at a low, steady discharge rate. At high "
        "C-rates a pack delivers less than its label (the Peukert effect), so a "
        "hard-flown pack gives less than this number.",
        "Voltage sag, cell ageing and cold weather all reduce usable energy.",
        "Always land with a reserve. Planning to 100% usable capacity is how packs "
        "get destroyed and aircraft fall out of the sky.",
    ])

    if ui.graph_toggle(p):
        currents = np.linspace(max(current * 0.25, 0.5), current * 2.0, 200)
        fig, (ax,) = new_figure()
        ax.plot(currents, (capacity * usable_pct / 100.0 / currents) * 60.0,
                color=PRIMARY, linewidth=2)
        mark_point(ax, current, value if value else 0.0, "current")
        ax.set_xlabel("Average current draw [A]")
        ax.set_ylabel("Flight time [min]")
        ax.set_title("Flight time vs average current (inverse relationship)",
                     fontsize=10, loc="left")
        show(fig)

    ui.reference(
        variables=[
            ("$C_{Ah}$", "Rated battery capacity", "Ah"),
            ("$I_{avg}$", "Average current draw", "A"),
            ("$t_{min}$", "Estimated flight time", "min"),
        ],
        example="Mission planning. A 5 Ah 6S pack flown to 80% depth of discharge "
                "at an average 25 A gives 9.6 minutes. Cutting average current to "
                "20 A - by hovering more gently or shedding payload - buys another "
                "2.4 minutes.",
    )


def render_power() -> None:
    p = "drone_power"
    ui.page_header(
        "Electrical power",
        r"P = V \times I",
        "Instantaneous electrical power. On a drone this is what the battery is "
        "delivering to the ESCs right now - useful for sizing wiring, connectors "
        "and the battery's continuous discharge rating.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        voltage = ui.number("Voltage V", "V", f"{p}_v", 22.2)
    with c2:
        current = ui.number("Current I", "A", f"{p}_i", 60.0)

    value = ui.compute(lambda: electrical_power(voltage, current))
    if value is not None:
        ui.result(
            "Electrical power P", value, "W",
            secondary=[
                ("In kilowatts", value / 1000.0, "kW"),
                ("Mechanical equivalent", value / 745.6998715822702, "hp"),
                ("Energy in one minute at this power", value / 60.0, "Wh"),
            ],
        )
    ui.assumptions([
        "DC power. This form (P = V I) applies to direct current or to "
        "instantaneous values; AC systems also need a power factor.",
        "This is electrical input power. Motor and propeller losses mean the "
        "useful power reaching the air is typically 50-75% of it.",
        "Pack voltage sags under load, so the voltage while flying is lower than "
        "the resting voltage.",
    ])
    ui.reference(
        variables=[
            ("$P$", "Electrical power", "W"),
            ("$V$", "Voltage", "V"),
            ("$I$", "Current", "A"),
        ],
        example="Wiring and connector sizing. A 6S pack at 22.2 V pulling 60 A is "
                "1332 W. That current decides the wire gauge and connector type - "
                "an XT30 rated for 30 A would overheat and fail here.",
    )


def render_battery_energy() -> None:
    p = "drone_energy"
    ui.page_header(
        "Battery energy",
        r"E_{Wh} = V \times C_{Ah}",
        "Capacity in amp-hours only tells half the story - it is charge, not "
        "energy. Multiply by voltage to get watt-hours, which is the number to "
        "compare packs of different cell counts and the one airlines regulate.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        voltage = ui.number("Nominal pack voltage", "V", f"{p}_v", 22.2,
                            min_value=0.0)
    with c2:
        capacity = ui.number("Capacity", "Ah", f"{p}_c", 5.0, min_value=0.0)

    value = ui.compute(lambda: battery_energy_wh(voltage, capacity))
    if value is not None:
        ui.result(
            "Stored energy", value, "Wh",
            secondary=[
                ("In kilojoules", value * 3.6, "kJ"),
                ("Usable at 80% depth of discharge", value * 0.8, "Wh"),
                ("Runtime at 500 W", value / 500.0 * 60.0, "min"),
            ],
        )
        if value > 100:
            st.caption("Above 100 Wh, most airlines require prior approval to "
                       "carry a lithium pack, and above 160 Wh it is normally "
                       "banned from passenger aircraft.")
    ui.assumptions([
        "Uses nominal voltage (3.7 V per LiPo cell). Real pack voltage runs from "
        "about 4.2 V per cell full to 3.5 V per cell under load, so stored energy "
        "is an average figure.",
        "Rated capacity assumes a healthy pack at a moderate discharge rate.",
        "Watt-hours measure energy; amp-hours measure charge. Comparing a 4S and a "
        "6S pack by mAh alone is misleading.",
    ])
    ui.reference(
        variables=[
            ("$E_{Wh}$", "Stored energy", "Wh"),
            ("$V$", "Nominal pack voltage", "V"),
            ("$C_{Ah}$", "Rated capacity (charge)", "Ah"),
        ],
        example="Comparing packs. A 4S 5000 mAh pack holds 14.8 × 5 = 74 Wh; a 6S "
                "5000 mAh pack holds 111 Wh. Same 'mAh' on the label, 50% more "
                "energy - and the 6S pack needs airline approval to fly with.",
    )


CALCULATORS = {
    "Total thrust": render_total_thrust,
    "Thrust-to-weight ratio": render_drone_twr,
    "Hover thrust per motor": render_hover_thrust,
    "Flight time (estimate)": render_flight_time,
    "Electrical power": render_power,
    "Battery energy": render_battery_energy,
}
