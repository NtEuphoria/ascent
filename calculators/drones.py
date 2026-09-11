"""Drone / multirotor calculators.

Motor manufacturers quote thrust in grams-force, which is a force, not a mass.
The helper below converts it to newtons on the way in so nothing downstream has
to guess which one it is holding.
"""
from __future__ import annotations

import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import G0, GRAM_FORCE_N
from utils.spec import Calculator, Field, Output, Secondary, Sweep

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


def _thrust_widget(key: str, field: Field) -> float:
    """Thrust entry in gf, kgf or N. Returns newtons.

    A compound input (unit selector plus value), so it is supplied as a custom
    widget rather than a plain numeric field. Each unit keeps its own widget
    key, so switching units shows that unit's default instead of silently
    reinterpreting the old number under a new label.
    """
    unit = st.radio("Thrust unit",
                    ["gram-force (gf)", "kilogram-force (kgf)", "newton (N)"],
                    key=f"{key}_unit", horizontal=True,
                    help="Datasheets almost always use grams-force. "
                         "1 gf = 0.00980665 N.")
    default_gf = float(field.default)
    if unit == "gram-force (gf)":
        return grams_force_to_newton(
            ui.number(field.label, "gf", f"{key}_gf", default_gf, min_value=0.0))
    if unit == "kilogram-force (kgf)":
        return grams_force_to_newton(
            ui.number(field.label, "kgf", f"{key}_kgf", default_gf / 1000.0,
                      min_value=0.0) * 1000.0)
    return ui.number(field.label, "N", f"{key}_n", default_gf * GRAM_FORCE_N,
                     min_value=0.0)


def _thrust_field(key: str, label: str, default_gf: float = 1200.0) -> Field:
    return Field(key, label, "", default_gf, widget=_thrust_widget)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

_TOTAL_THRUST = Calculator(
    slug="drone.total_thrust", name="Total thrust",
    latex=r"T_{total} = N_{motors} \times T_{motor}",
    explanation=(
        "Add up what the propulsion system can produce at full throttle. Motor "
        "datasheets quote thrust in grams-force; that is a <b>force</b>, and it is "
        "converted to newtons here so it can be compared with weight directly."),
    inputs=[
        Field("n_motors", "Number of motors", "", 4, min=1, max=32, kind="int"),
        _thrust_field("per_motor", "Thrust per motor at full throttle"),
    ],
    compute=lambda i: total_thrust(i.n_motors, i.per_motor),
    result=Output("Total thrust", "N"),
    secondary=[
        Secondary("In grams-force", "gf", lambda i, r: r / GRAM_FORCE_N),
        Secondary("In kilograms-force", "kgf",
                  lambda i, r: r / (GRAM_FORCE_N * 1000.0)),
        Secondary("Maximum mass it can lift at 1 g", "kg", lambda i, r: r / G0),
    ],
    assumptions=[
        "All motors produce their rated thrust at the same time. In practice the "
        "battery sags under full load, so total thrust is usually a few percent "
        "below the sum of individual bench figures.",
        "Bench thrust figures are measured static, at sea level, with a specified "
        "propeller and voltage. Change any of those and the number changes.",
        "Thrust in gf is converted with 1 gf = g × 0.001 kg = 0.00980665 N.",
        "No allowance is made for thrust lost to airframe download (the wash "
        "blowing onto arms and body), typically a few percent.",
    ],
    variables=[
        ("$T_{total}$", "Combined thrust of all motors", "N"),
        ("$N_{motors}$", "Number of motors", "-"),
        ("$T_{motor}$", "Thrust from one motor at full throttle", "N"),
    ],
    example=(
        "Component selection. Four motors rated 1200 gf each give 4800 gf = 47.1 N "
        "of thrust, which can lift 4.8 kg at 1 g. For a 2 kg aircraft that is a "
        "thrust-to-weight ratio of 2.4."),
    keywords=("thrust", "motors", "total"),
)

_DRONE_TWR = Calculator(
    slug="drone.twr", name="Thrust-to-weight ratio",
    latex=r"TWR = \frac{T_{total}}{W} = \frac{N_{motors}\,T_{motor}}{m\,g}",
    explanation=(
        "The headline number for multirotor performance. TWR of 1 means the "
        "aircraft can only just hold itself up at full throttle, with nothing left "
        "for control. Around 2 is the usual design target, so hover sits near "
        "half throttle with authority in both directions."),
    inputs=[
        Field("n_motors", "Number of motors", "", 4, min=1, max=32, kind="int"),
        _thrust_field("per_motor", "Thrust per motor"),
        Field("weight", "All-up", "", 2.0, kind="weight"),
    ],
    compute=lambda i: total_thrust(i.n_motors, i.per_motor) / v.positive(
        i.weight, "Weight", "N"),
    result=Output("Thrust-to-weight ratio", "-"),
    secondary=[
        Secondary("Total thrust", "N",
                  lambda i, r: total_thrust(i.n_motors, i.per_motor)),
        Secondary("All-up weight", "N", lambda i, r: i.weight),
        Secondary("Thrust used in hover", "% of maximum",
                  lambda i, r: 100.0 / r),
        Secondary("Peak vertical acceleration", "m/s²",
                  lambda i, r: (r - 1.0) * G0),
    ],
    note=lambda i, r: (
        "Below about 1.3 there is very little control authority left over after "
        "hovering; the aircraft will feel sluggish and may not recover from a "
        "descent." if r < 1.3 else
        "Very high TWR - typical of racing builds. Expect twitchy handling and "
        "short flight times." if r > 6 else None),
    assumptions=[
        "Weight uses W = m g with g = 9.80665 m/s², at the all-up mass including "
        "battery, payload and camera.",
        "The hover-throttle figure is simply the fraction of maximum thrust needed. "
        "Real throttle stick position is not linear with thrust.",
        "Static bench thrust: forward flight and descent through the rotor wash "
        "both change the real figure.",
    ],
    graph=Sweep(over="weight", y_label="Thrust-to-weight ratio [-]",
                x_label="All-up weight [N]", lo_factor=0.4, hi_factor=2.0,
                title="TWR vs weight at this propulsion system"),
    variables=[
        ("$T_{total}$", "Total thrust from all motors", "N"),
        ("$W$", "All-up weight", "N"), ("$m$", "All-up mass", "kg"),
    ],
    example=(
        "Deciding whether a new camera fits the budget. A 2.0 kg quad with 47 N of "
        "thrust has TWR 2.4. Add a 400 g gimbal and weight rises to 23.5 N, "
        "dropping TWR to 2.0 - still fine. Add another kilogram and TWR falls to "
        "1.4, where climb performance and gust rejection start to suffer "
        "noticeably."),
    keywords=("twr", "thrust weight", "multirotor"),
)

_HOVER = Calculator(
    slug="drone.hover_thrust", name="Hover thrust per motor",
    latex=r"T_{hover,motor} = \frac{W}{N_{motors}}",
    explanation=(
        "In a level hover the motors share the weight equally. Comparing that "
        "share with each motor's maximum thrust tells you how hard the propulsion "
        "system is working just to stay in the air."),
    inputs=[
        Field("weight", "All-up", "", 2.0, kind="weight"),
        Field("n_motors", "Number of motors", "", 4, min=1, max=32, kind="int"),
        _thrust_field("max_per_motor", "Maximum thrust per motor"),
    ],
    compute=lambda i: hover_thrust_per_motor(i.weight, i.n_motors),
    result=Output("Hover thrust per motor", "N"),
    secondary=[
        Secondary("In grams-force", "gf", lambda i, r: r / GRAM_FORCE_N),
        Secondary("Fraction of each motor's maximum", "%",
                  lambda i, r: r / i.max_per_motor * 100.0),
        Secondary("Remaining margin per motor", "N",
                  lambda i, r: i.max_per_motor - r),
    ],
    note=lambda i, r: (
        "Hovering above about 65% of maximum thrust leaves little headroom for "
        "manoeuvring, wind, or a failing cell - and motors run hot near their "
        "limit." if i.max_per_motor > 0 and r / i.max_per_motor > 0.65 else None),
    assumptions=[
        "Level hover, motors equally loaded, centre of gravity on the geometric "
        "centre. An off-centre CG makes some motors work harder than others.",
        "No wind and no vertical acceleration - a pure steady hover.",
        "Motor maximum thrust is the bench figure at the propeller and voltage the "
        "manufacturer tested with.",
    ],
    variables=[
        ("$T_{hover,motor}$", "Thrust each motor must make to hover", "N"),
        ("$W$", "All-up weight", "N"),
        ("$N_{motors}$", "Number of motors", "-"),
    ],
    example=(
        "Motor selection. A 2 kg quadcopter weighs 19.6 N, so each of four motors "
        "must produce 4.9 N (500 gf) to hover. Picking motors rated 1200 gf means "
        "hovering at about 42% of maximum - a healthy margin and a good efficiency "
        "point."),
    keywords=("hover", "per motor", "share"),
)

_FLIGHT_TIME = Calculator(
    slug="drone.flight_time", name="Flight time (estimate)",
    latex=(r"t_{min} = \frac{C_{Ah} \times \text{usable fraction}}{I_{avg}} "
           r"\times 60"),
    explanation=(
        "A first-order estimate of endurance. Usable capacity matters: discharging "
        "a lithium pack to empty damages it, so most pilots plan on using 70-85% "
        "of the rated capacity. This is an <b>estimate</b>, not a guarantee."),
    inputs=[
        Field("capacity", "Battery capacity", "Ah", 5.0, min=0.0,
              help="A 5000 mAh pack is 5.0 Ah."),
        Field("voltage", "Nominal pack voltage", "V", 22.2, min=0.0,
              help="3.7 V per cell nominal: 6S = 22.2 V."),
        Field("usable_pct", "Usable capacity", "%", 80.0, min=10.0, max=100.0,
              step=5.0, kind="slider",
              help="Fraction of rated capacity you are willing to draw before "
                   "landing."),
        Field("current", "Average current draw", "A", 25.0, min=0.0,
              help="Average over the whole flight, not the peak."),
    ],
    compute=lambda i: flight_time_minutes(i.capacity, i.usable_pct / 100.0,
                                          i.current),
    result=Output("Estimated flight time", "minutes"),
    secondary=[
        Secondary("Usable capacity", "Ah",
                  lambda i, r: i.capacity * i.usable_pct / 100.0),
        Secondary("Average electrical power", "W",
                  lambda i, r: i.voltage * i.current),
        Secondary("Energy used", "Wh",
                  lambda i, r: i.voltage * i.capacity * i.usable_pct / 100.0),
        Secondary("Discharge rate (C-rate)", "C",
                  lambda i, r: i.current / i.capacity),
    ],
    assumptions=[
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
    ],
    graph=Sweep(over="current", y_label="Flight time [min]", lo_factor=0.25,
                hi_factor=2.0,
                title="Flight time vs average current (inverse relationship)"),
    variables=[
        ("$C_{Ah}$", "Rated battery capacity", "Ah"),
        ("$I_{avg}$", "Average current draw", "A"),
        ("$t_{min}$", "Estimated flight time", "min"),
    ],
    example=(
        "Mission planning. A 5 Ah 6S pack flown to 80% depth of discharge at an "
        "average 25 A gives 9.6 minutes. Cutting average current to 20 A - by "
        "hovering more gently or shedding payload - buys another 2.4 minutes."),
    keywords=("flight time", "endurance", "battery", "duration"),
)

_POWER = Calculator(
    slug="drone.power", name="Electrical power",
    latex=r"P = V \times I",
    explanation=(
        "Instantaneous electrical power. On a drone this is what the battery is "
        "delivering to the ESCs right now - useful for sizing wiring, connectors "
        "and the battery's continuous discharge rating."),
    inputs=[
        Field("voltage", "Voltage V", "V", 22.2),
        Field("current", "Current I", "A", 60.0),
    ],
    compute=lambda i: electrical_power(i.voltage, i.current),
    result=Output("Electrical power P", "W"),
    secondary=[
        Secondary("In kilowatts", "kW", lambda i, r: r / 1000.0),
        Secondary("Mechanical equivalent", "hp",
                  lambda i, r: r / 745.6998715822702),
        Secondary("Energy in one minute at this power", "Wh",
                  lambda i, r: r / 60.0),
    ],
    assumptions=[
        "DC power. This form (P = V I) applies to direct current or to "
        "instantaneous values; AC systems also need a power factor.",
        "This is electrical input power. Motor and propeller losses mean the "
        "useful power reaching the air is typically 50-75% of it.",
        "Pack voltage sags under load, so the voltage while flying is lower than "
        "the resting voltage.",
    ],
    variables=[("$P$", "Electrical power", "W"), ("$V$", "Voltage", "V"),
               ("$I$", "Current", "A")],
    example=(
        "Wiring and connector sizing. A 6S pack at 22.2 V pulling 60 A is 1332 W. "
        "That current decides the wire gauge and connector type - an XT30 rated "
        "for 30 A would overheat and fail here."),
    keywords=("power", "watts", "vi"),
)

_BATTERY = Calculator(
    slug="drone.battery_energy", name="Battery energy",
    latex=r"E_{Wh} = V \times C_{Ah}",
    explanation=(
        "Capacity in amp-hours only tells half the story - it is charge, not "
        "energy. Multiply by voltage to get watt-hours, which is the number to "
        "compare packs of different cell counts and the one airlines regulate."),
    inputs=[
        Field("voltage", "Nominal pack voltage", "V", 22.2, min=0.0),
        Field("capacity", "Capacity", "Ah", 5.0, min=0.0),
    ],
    compute=lambda i: battery_energy_wh(i.voltage, i.capacity),
    result=Output("Stored energy", "Wh"),
    secondary=[
        Secondary("In kilojoules", "kJ", lambda i, r: r * 3.6),
        Secondary("Usable at 80% depth of discharge", "Wh", lambda i, r: r * 0.8),
        Secondary("Runtime at 500 W", "min", lambda i, r: r / 500.0 * 60.0),
    ],
    note=lambda i, r: ("Above 100 Wh, most airlines require prior approval to "
                       "carry a lithium pack, and above 160 Wh it is normally "
                       "banned from passenger aircraft.") if r > 100 else None,
    assumptions=[
        "Uses nominal voltage (3.7 V per LiPo cell). Real pack voltage runs from "
        "about 4.2 V per cell full to 3.5 V per cell under load, so stored energy "
        "is an average figure.",
        "Rated capacity assumes a healthy pack at a moderate discharge rate.",
        "Watt-hours measure energy; amp-hours measure charge. Comparing a 4S and a "
        "6S pack by mAh alone is misleading.",
    ],
    variables=[
        ("$E_{Wh}$", "Stored energy", "Wh"),
        ("$V$", "Nominal pack voltage", "V"),
        ("$C_{Ah}$", "Rated capacity (charge)", "Ah"),
    ],
    example=(
        "Comparing packs. A 4S 5000 mAh pack holds 14.8 × 5 = 74 Wh; a 6S "
        "5000 mAh pack holds 111 Wh. Same 'mAh' on the label, 50% more energy - "
        "and the 6S pack needs airline approval to fly with."),
    keywords=("battery", "energy", "wh", "capacity"),
)

CALCULATORS = [_TOTAL_THRUST, _DRONE_TWR, _HOVER, _FLIGHT_TIME, _POWER, _BATTERY]
