"""Drone / multirotor calculators.

Motor manufacturers quote thrust in grams-force, which is a force, not a mass.
The helper below converts it to newtons on the way in so nothing downstream has
to guess which one it is holding.

Two pages here exist to explain the optimism of the others. `drone.battery_sag`
shows why the flight-time estimate is generous (V = V_oc - I R_int, and the ESC
answers a voltage drop by drawing more current), and `drone.range_endurance`
separates the two questions a fixed-wing electric aircraft is really asked: how
far, and how long. They are not the same question and they do not have the same
answer.
"""
from __future__ import annotations

import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import G0, GRAM_FORCE_N, LBF_PER_N
from utils.spec import (Calculator, Check, Field, Output, Reference, Secondary,
                        Sweep)

# Lithium-polymer cell landmarks, used by several checks and tables. These are
# the figures the whole hobby works to; a cell is "full" at 4.20 V and is being
# damaged below 3.0 V, whatever the label on the pack says.
LIPO_NOMINAL_V = 3.7
LIPO_FULL_V = 4.2
LIPO_CUTOFF_V = 3.0
LI_ION_NOMINAL_V = 3.6

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


# --- Battery internal resistance and voltage sag ---------------------------


def pack_internal_resistance(cells: int, milliohm_per_cell: float) -> float:
    """R_pack = N * r_cell   [ohm]

    Cells in series add their resistances, exactly like any other series
    circuit. Chargers report per-cell internal resistance in MILLIohms, which
    is why this takes mOhm and returns ohms.
    """
    cells = v.positive_int(cells, "Cells in series")
    milliohm_per_cell = v.non_negative(milliohm_per_cell,
                                       "Internal resistance per cell", "mOhm")
    return cells * milliohm_per_cell / 1000.0


def voltage_sag(current: float, resistance: float) -> float:
    """dV = I * R   [V] - Ohm's law applied inside the battery."""
    current = v.non_negative(current, "Load current", "A")
    resistance = v.non_negative(resistance, "Internal resistance", "ohm")
    return current * resistance


def loaded_pack_voltage(cells: int, volts_per_cell: float,
                        milliohm_per_cell: float, current: float) -> float:
    """V = V_oc - I * R_int   [V]

    The single equation behind every "my quad browned out on a punch-out". A
    cell is a voltage source with a resistor in series with it; the resistor is
    small but the current is not, and the product is volts.

    If the drop would exceed the resting voltage the load is impossible rather
    than merely bad, so this raises instead of returning a nonsense number.
    """
    cells = v.positive_int(cells, "Cells in series")
    volts_per_cell = v.positive(volts_per_cell, "Resting voltage per cell", "V")
    open_circuit = cells * volts_per_cell
    sag = voltage_sag(current, pack_internal_resistance(cells, milliohm_per_cell))
    if sag >= open_circuit:
        raise v.ValidationError(
            f"At {current:g} A this pack would drop {sag:.1f} V, more than its "
            f"{open_circuit:.1f} V resting voltage. No such current can flow - "
            "the pack collapses first. Lower the current, or the internal "
            "resistance.")
    return open_circuit - sag


# --- Electric range and endurance (constant-weight Breguet) ----------------


def cruise_drag(weight: float, lift_to_drag: float) -> float:
    """D = W / (L/D)   [N]

    In steady level flight lift equals weight, so the drag an aircraft must
    push through is fixed entirely by its weight and its L/D.
    """
    weight = v.positive(weight, "All-up weight", "N")
    lift_to_drag = v.positive(lift_to_drag, "Lift-to-drag ratio", "-")
    return weight / lift_to_drag


def cruise_electrical_power(weight: float, speed: float, lift_to_drag: float,
                            efficiency: float) -> float:
    """P = D * V / eta = W V / ((L/D) eta)   [W] - electrical, not shaft."""
    speed = v.non_negative(speed, "Cruise speed", "m/s")
    efficiency = v.in_range(efficiency, "Total efficiency", 0.01, 1.0, "-")
    return cruise_drag(weight, lift_to_drag) * speed / efficiency


def electric_range_km(energy_wh: float, usable_fraction: float,
                      efficiency: float, lift_to_drag: float,
                      weight: float) -> float:
    """R = eta * E * DoD * (L/D) / W   [km]

    The electric (constant-weight) Breguet range equation. A battery aircraft
    does not get lighter as it flies, so the logarithm of the fuel-burning
    version collapses to a straight division.

    Note what is NOT in it: speed. Energy per unit distance is just drag, and
    at a fixed L/D drag is fixed by weight - so flying faster gets you there
    sooner on the same energy, not further.
    """
    energy_wh = v.non_negative(energy_wh, "Battery energy", "Wh")
    usable_fraction = v.in_range(usable_fraction, "Usable fraction", 0.01, 1.0, "-")
    efficiency = v.in_range(efficiency, "Total efficiency", 0.01, 1.0, "-")
    propulsive_joules = energy_wh * 3600.0 * usable_fraction * efficiency
    return propulsive_joules / cruise_drag(weight, lift_to_drag) / 1000.0


def electric_endurance_minutes(energy_wh: float, usable_fraction: float,
                               efficiency: float, lift_to_drag: float,
                               weight: float, speed: float) -> float:
    """t = R / V   [minutes] - and this one does care about speed."""
    speed = v.positive(speed, "Cruise speed", "m/s")
    range_m = electric_range_km(energy_wh, usable_fraction, efficiency,
                                lift_to_drag, weight) * 1000.0
    return range_m / speed / 60.0


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
# Shared checks and reference tables
# ---------------------------------------------------------------------------


def _pack_voltage_check(i, result):
    """Catch the two voltage mistakes that make every battery page wrong.

    Entering 25.2 V (a full 6S) where the nominal 22.2 V belongs overstates
    energy by 13%, and entering a Li-ion pack's voltage looks like a typo
    unless you know 3.6 V is its nominal figure.
    """
    volts = float(i.voltage)
    if volts <= 0:
        return None
    lipo = volts / LIPO_NOMINAL_V
    if round(lipo) >= 1 and abs(lipo - round(lipo)) <= 0.02:
        return None
    li_ion = volts / LI_ION_NOMINAL_V
    if round(li_ion) >= 1 and abs(li_ion - round(li_ion)) <= 0.02:
        return ("info",
                f"{volts:g} V is {round(li_ion):.0f} cells at 3.6 V, the nominal "
                "figure for Li-ion (18650 / 21700). That is the right voltage to "
                "use here. Li-ion holds far more energy per gram than LiPo but "
                "delivers much less current - typically 1-3 C continuous.")
    full = volts / LIPO_FULL_V
    if round(full) >= 1 and abs(full - round(full)) <= 0.02:
        return ("warning",
                f"{volts:g} V is {round(full):.0f} cells at 4.20 V - that is the "
                "FULLY CHARGED voltage, not the nominal one. A pack spends most "
                "of a flight near 3.7 V per cell, so using the full figure "
                "overstates energy and power by about 13%. Enter "
                f"{round(full) * LIPO_NOMINAL_V:.1f} V instead.")
    return ("info",
            f"{volts:g} V is {lipo:.2f} LiPo cells at 3.7 V each, which is not a "
            "whole cell count. Packs come in whole cells - check the figure "
            "against the pack label.")


_CELL_VOLTAGE_TABLE = Reference(
    title="LiPo cell voltages",
    columns=("State", "Per cell", "3S", "4S", "6S", "12S"),
    rows=[
        ("Full charge", "4.20 V", "12.6 V", "16.8 V", "25.2 V", "50.4 V"),
        ("Storage (weeks+)", "3.80 V", "11.4 V", "15.2 V", "22.8 V", "45.6 V"),
        ("Nominal (label)", "3.70 V", "11.1 V", "14.8 V", "22.2 V", "44.4 V"),
        ("Land now (resting)", "3.50 V", "10.5 V", "14.0 V", "21.0 V", "42.0 V"),
        ("Typical ESC cutoff", "3.30 V", "9.9 V", "13.2 V", "19.8 V", "39.6 V"),
        ("Damage below", "3.00 V", "9.0 V", "12.0 V", "18.0 V", "36.0 V"),
    ],
    note="Lithium-polymer. Li-ion cells are 3.6 V nominal and 4.2 V full; LiHV "
         "charges to 4.35 V. The cutoff row is voltage UNDER LOAD - a pack that "
         "sags to 3.3 V in a climb may rest back at 3.7 V, which is why "
         "telemetry alarms and post-flight checks disagree.",
)

_C_RATING_TABLE = Reference(
    title="Typical C ratings",
    columns=("Pack type", "Honest continuous C", "Typical use"),
    rows=[
        ("Li-ion 18650, energy cell", "1 - 3 C", "Long-endurance survey, VTOL"),
        ("Li-ion 21700, power cell", "3 - 8 C", "Endurance with some climb"),
        ("LiPo, endurance / cinema", "5 - 15 C", "Camera multirotors"),
        ("LiPo, high discharge", "20 - 40 C", "Freestyle, racing, punch-outs"),
        ("LiPo, printed on the label", "75 - 150 C", "Marketing"),
    ],
    note="C-rate is current divided by capacity in amp-hours: 50 A from a 5 Ah "
         "pack is 10 C. Printed ratings are burst figures measured generously; "
         "the continuous column is what a pack sustains without heating, sagging "
         "and losing cycle life. Capacity itself falls at high C (the Peukert "
         "effect), so a hard-flown pack delivers less than its label.",
)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def _rotor_count_check(i, result):
    """Yaw is controlled by torque pairs, and pairs need an even number."""
    n = int(i.n_motors)
    if n <= 2:
        return ("info",
                "One or two rotors cannot control pitch, roll and yaw on their "
                "own. A single rotor needs a swashplate and a tail rotor; a "
                "bicopter needs both motors on tilt servos. The sum above is "
                "still the thrust available - it is the control that is missing.")
    if n % 2 == 1:
        return ("info",
                f"{n} rotors is an odd number, so clockwise and counter-clockwise "
                "rotors cannot be paired evenly and their reaction torques do not "
                "cancel. A tricopter fixes this with a tilting tail motor; larger "
                "odd counts hold heading with a permanent speed imbalance, which "
                "costs a little of the thrust above.")
    return None


def _stacked_rotor_check(i, result):
    n = int(i.n_motors)
    if n >= 8:
        kgf = result / (GRAM_FORCE_N * 1000.0)
        return ("info",
                f"{n} rotors are often mounted as {n // 2} coaxial pairs (an X8). "
                "The lower rotor of a pair works in the wash of the upper one, so "
                "a stacked pair makes roughly 75-85% of what two isolated rotors "
                f"make. If this is a stacked layout, budget nearer "
                f"{kgf * 0.8:.1f} kgf than {kgf:.1f} kgf.")
    return None


def _micro_scale_check(i, result):
    if 0 < result < 1000.0 * GRAM_FORCE_N:
        return ("info",
                "Under 1 kgf of total thrust is the micro class. Small, fast "
                "propellers run at low Reynolds number, where the blade sections "
                "are less efficient and figure of merit sits at the bottom of the "
                "0.4-0.6 band - so thrust per watt is far worse than a large "
                "rotor's, however good the motor is.")
    return None


_TOTAL_THRUST = Calculator(
    slug="drone.total_thrust", name="Total thrust",
    latex=r"T_{total} = N_{motors} \times T_{motor}",
    explanation=(
        "Add up what the propulsion system can produce at full throttle. Motor "
        "datasheets quote thrust in grams-force; that is a <b>force</b>, and it is "
        "converted to newtons here so it can be compared with weight directly. "
        "The sum is an upper bound: it assumes every motor makes its bench figure "
        "at the same instant, on a full pack, with clean air into every disk."),
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
        Secondary("In pound-force", "lbf", lambda i, r: r * LBF_PER_N),
        Secondary("Maximum mass it can lift at 1 g", "kg", lambda i, r: r / G0),
        Secondary("All-up mass for a thrust-to-weight of 2", "kg",
                  lambda i, r: r / G0 / 2.0),
    ],
    checks=[
        Check(_rotor_count_check),
        Check(_stacked_rotor_check),
        Check(_micro_scale_check),
    ],
    assumptions=[
        "All motors produce their rated thrust at the same time. In practice the "
        "battery sags under full load, so total thrust is usually a few percent "
        "below the sum of individual bench figures.",
        "Bench thrust figures are measured static, at sea level, with a specified "
        "propeller and voltage. Change any of those and the number changes.",
        "Datasheet thrust is measured on a fully charged pack. Halfway through a "
        "flight the pack sits a volt or more lower and every motor makes less "
        "thrust - a 10% voltage drop typically costs 15-20% of thrust.",
        "Thrust in gf is converted with 1 gf = g × 0.001 kg = 0.00980665 N.",
        "Rotors are assumed to be separate and in clean air. Overlapping or "
        "coaxial rotors interfere, and a coaxial pair loses 15-25%.",
        "No allowance is made for thrust lost to airframe download (the wash "
        "blowing onto arms and body), typically a few percent.",
        "Static thrust is a propeller's maximum. In forward flight the same motor "
        "and propeller make less, because the blades see a higher advance ratio.",
    ],
    graphs=[
        Sweep(over="per_motor", y_label="Total thrust [N]",
              x_label="Thrust per motor [N]", hi_factor=2.0, hi_min=5.0,
              title="Total thrust vs thrust per motor"),
        Sweep(over="n_motors", y_label="Total thrust [N]",
              x_label="Number of motors [-]", lo=1.0, hi_factor=3.0, hi_min=8.0,
              title="Total thrust vs motor count (a staircase - motors come "
                    "whole)"),
    ],
    references=[
        Reference(
            title="Force units on a datasheet",
            columns=("Unit", "In newtons", "Where it appears"),
            rows=[
                ("1 gram-force (gf)", "0.00980665 N", "Motor thrust tables"),
                ("1 kilogram-force (kgf)", "9.80665 N", "Large motor datasheets"),
                ("1 ounce-force (ozf)", "0.278014 N", "US hobby listings"),
                ("1 pound-force (lbf)", "4.448222 N", "Heavy lift, full scale"),
                ("1 newton (N)", "1 N", "Every equation in this app"),
            ],
            note="A datasheet reading '1.2 kg thrust' means 1.2 kgf = 11.8 N; it "
                 "is a force wearing a mass label. The same trap runs through "
                 "servo torque quoted in kg·cm, which is really kgf·cm = "
                 "0.0980665 N·m - so a '20 kg' servo makes 1.96 N·m, not 20.",
        ),
        Reference(
            title="Multirotor layouts",
            columns=("Rotors", "Yaw control", "After one motor fails"),
            rows=[
                ("3 (tricopter)", "Tilting tail motor", "Not controllable"),
                ("4 (quad)", "Paired CW / CCW", "Not controllable"),
                ("6 (hex)", "Paired CW / CCW", "Usually survivable with margin"),
                ("8 (octo, flat)", "Paired CW / CCW", "Survivable"),
                ("8 (X8, coaxial)", "Paired CW / CCW",
                 "Survivable; the pair's partner covers it"),
            ],
            note="Surviving a failure needs thrust margin as well as rotors: the "
                 "remaining motors must hold the whole weight, and the rotor "
                 "opposite the dead one is usually throttled back to keep the "
                 "aircraft level. Specialist firmware can land a quad by letting "
                 "it spin, but it is not controlled flight.",
        ),
    ],
    related=["drone.twr", "drone.hover_thrust", "prop.momentum_theory",
             "drone.battery_sag", "robot.servo_torque"],
    variables=[
        ("$T_{total}$", "Combined thrust of all motors", "N"),
        ("$N_{motors}$", "Number of motors", "-"),
        ("$T_{motor}$", "Thrust from one motor at full throttle", "N"),
    ],
    example=(
        "Component selection. Four motors rated 1200 gf each give 4800 gf = "
        "47.07 N of thrust, which can lift 4.80 kg at 1 g. Held to the usual "
        "thrust-to-weight target of 2, that is a 2.40 kg aircraft - battery, "
        "camera and all - which is why a 1200 gf motor and a 2 kg quadcopter "
        "keep turning up together."),
    keywords=("thrust", "motors", "total", "gram force", "gf", "kgf",
              "quadcopter", "octocopter", "static thrust", "propulsion"),
)


def _twr_regime_check(i, result):
    """TWR is the one number that decides whether an aircraft is flyable."""
    if result < 1.0:
        return ("danger",
                f"Thrust-to-weight {result:.2f} is below 1. At full throttle the "
                "motors cannot hold this weight up: the aircraft will not leave "
                f"the ground. It is {(1.0 - result) * 100:.0f}% short.")
    if result < 1.3:
        return ("danger",
                f"Thrust-to-weight {result:.2f} leaves almost nothing for "
                f"control. Hovering already needs {100.0 / result:.0f}% throttle, "
                "so a gust, a turn or a descent has no thrust left to answer "
                "with. This will not recover from its own wake.")
    if result < 1.5:
        return ("warning",
                f"Thrust-to-weight {result:.2f} means "
                f"{100.0 / result:.0f}% throttle to hover and only "
                f"{(result - 1.0) * G0:.1f} m/s² of spare vertical acceleration. "
                "Wind, a heavy camera or one tired cell will make this feel "
                "sluggish and unsafe. 1.5 is the usual floor, 2.0 the target.")
    if result > 6.0:
        return ("info",
                f"Thrust-to-weight {result:.2f} is racing territory - hover sits "
                f"near {100.0 / result:.0f}% throttle. Expect twitchy handling, "
                "very high peak currents and short flights; the motors spend "
                "their lives far from their efficient point.")
    return None


def _mass_class_check(i, result):
    """The two mass thresholds that change which rules you fly under."""
    mass = i.weight / G0
    if mass > 25.0:
        return ("info",
                f"{mass:.1f} kg all-up is above 25 kg (55 lb). That is outside "
                "the EU 'open' category and above the FAA Part 107 small-UAS "
                "limit, so this aircraft needs a specific authorisation or an "
                "exemption rather than ordinary drone rules. Check the current "
                "rules where you fly - they move.")
    if 0 < mass < 0.25:
        return ("info",
                f"{mass * 1000:.0f} g all-up is under the 250 g line that many "
                "countries use as the threshold for registration. It is also "
                "light enough that wind, not thrust, will be the limit on when "
                "you can fly.")
    return None


def _payload_cost_check(i, result):
    if result < 2.0:
        return ("info",
                "Payload costs power faster than it costs thrust. Thrust needed "
                "rises in proportion to mass, but hover power goes as mass^1.5 - "
                "10% more mass needs 10% more thrust and about 15% more power, so "
                f"endurance falls faster than this ratio does. At {result:.2f} "
                "there is not much of either left.")
    return None


_DRONE_TWR = Calculator(
    slug="drone.twr", name="Thrust-to-weight ratio",
    latex=r"TWR = \frac{T_{total}}{W} = \frac{N_{motors}\,T_{motor}}{m\,g}",
    explanation=(
        "The headline number for multirotor performance. TWR of 1 means the "
        "aircraft can only just hold itself up at full throttle, with nothing left "
        "for control. Around 2 is the usual design target, so hover sits near "
        "half throttle with authority in both directions. The reciprocal is just "
        "as useful: <code>1/TWR</code> is the fraction of maximum thrust a hover "
        "costs, and thrust left over is the only thing an aircraft has to answer "
        "a gust with."),
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
        Secondary("All-up mass", "kg", lambda i, r: i.weight / G0),
        Secondary("Thrust used in hover", "% of maximum",
                  lambda i, r: 100.0 / r),
        Secondary("Thrust left over", "N",
                  lambda i, r: total_thrust(i.n_motors, i.per_motor) - i.weight),
        Secondary("Peak vertical acceleration", "m/s²",
                  lambda i, r: (r - 1.0) * G0),
    ],
    note=lambda i, r: (
        "Below about 1.3 there is very little control authority left over after "
        "hovering; the aircraft will feel sluggish and may not recover from a "
        "descent." if r < 1.3 else
        "Very high TWR - typical of racing builds. Expect twitchy handling and "
        "short flight times." if r > 6 else None),
    checks=[
        Check(_twr_regime_check),
        Check(_mass_class_check),
        Check(_payload_cost_check),
    ],
    assumptions=[
        "Weight uses W = m g with g = 9.80665 m/s², at the all-up mass including "
        "battery, payload and camera.",
        "The hover-throttle figure is simply the fraction of maximum thrust needed. "
        "Real throttle stick position is not linear with thrust.",
        "Static bench thrust: forward flight and descent through the rotor wash "
        "both change the real figure.",
        "Bench thrust is measured on a full pack. The TWR you actually fly with is "
        "lower and falls through the flight as the pack sags - so size the ratio "
        "for the end of the flight, not the start.",
        "Peak vertical acceleration is (TWR - 1) g and assumes every motor is at "
        "maximum. A real controller keeps thrust in reserve for attitude control, "
        "so climb acceleration is lower than this.",
        "Equal loading on every motor: a centre of gravity off the geometric "
        "centre makes some motors saturate before others, and the aircraft runs "
        "out of control authority before TWR says it should.",
    ],
    graphs=[
        Sweep(over="weight", y_label="Thrust-to-weight ratio [-]",
              x_label="All-up weight [N]", lo_factor=0.4, hi_factor=2.0,
              title="TWR vs weight at this propulsion system"),
        Sweep(over="per_motor", y_label="Thrust-to-weight ratio [-]",
              x_label="Thrust per motor [N]", hi_factor=2.0, hi_min=5.0,
              title="TWR vs motor choice (what a bigger motor buys)"),
        Sweep(over="n_motors", y_label="Thrust-to-weight ratio [-]",
              x_label="Number of motors [-]", lo=1.0, hi_factor=3.0, hi_min=8.0,
              title="TWR vs motor count (before the extra arms and ESCs are "
                    "weighed)"),
    ],
    references=[
        Reference(
            title="TWR design targets",
            columns=("Aircraft", "Typical TWR", "What it feels like"),
            rows=[
                ("Heavy lift, survey, mapping", "1.7 - 2.0",
                 "Stable, efficient, no spare"),
                ("Camera / cinema multirotor", "2.0 - 2.5",
                 "Smooth, holds position in wind"),
                ("General sport and freestyle", "3 - 5", "Lively, forgiving"),
                ("Racing", "6 - 12", "Violent; hover near idle"),
                ("Below 1.5", "-", "Unsafe in anything but still air"),
            ],
            note="Community rules of thumb rather than standards, and all "
                 "computed from static bench thrust on a full pack. Endurance "
                 "aircraft sit at the low end deliberately: a motor hovering at "
                 "50% of its maximum is near its efficient point, while one "
                 "hovering at 20% is carrying metal it never uses.",
        ),
        Reference(
            title="What TWR buys",
            columns=("TWR", "Hover throttle", "Peak climb acceleration"),
            rows=[
                ("1.25", "80%", "2.5 m/s²  (0.25 g)"),
                ("1.5", "67%", "4.9 m/s²  (0.5 g)"),
                ("2.0", "50%", "9.8 m/s²  (1.0 g)"),
                ("3.0", "33%", "19.6 m/s²  (2.0 g)"),
                ("4.0", "25%", "29.4 m/s²  (3.0 g)"),
                ("6.0", "17%", "49.0 m/s²  (5.0 g)"),
            ],
            note="Hover throttle is exactly 1/TWR of maximum thrust; peak "
                 "acceleration is (TWR - 1) g with every motor saturated and "
                 "nothing held back for attitude control.",
        ),
    ],
    related=["drone.total_thrust", "drone.hover_thrust",
             "prop.hover_endurance", "flight.twr", "drone.battery_sag"],
    variables=[
        ("$T_{total}$", "Total thrust from all motors", "N"),
        ("$W$", "All-up weight", "N"), ("$m$", "All-up mass", "kg"),
        ("$g$", "Standard gravity, 9.80665", "m/s²"),
        ("$TWR$", "Thrust-to-weight ratio (dimensionless)", "-"),
    ],
    example=(
        "Deciding whether a new camera fits the budget. A 2.0 kg quad with 47.07 N "
        "of thrust has TWR 2.40, hovering at 42% throttle. Add a 400 g gimbal and "
        "weight rises to 23.54 N, dropping TWR to 2.00 - still fine, hover now "
        "50%. Add another kilogram and TWR falls to 1.41, where hover takes 71% of "
        "everything the motors have and gust rejection starts to suffer badly."),
    keywords=("twr", "thrust weight", "multirotor", "hover throttle", "margin",
              "payload", "racing"),
)


def _hover_margin_check(i, result):
    share = result / i.max_per_motor
    if share > 1.0:
        return ("danger",
                f"Each motor must make {result / GRAM_FORCE_N:.0f} gf to hover but "
                f"is rated {i.max_per_motor / GRAM_FORCE_N:.0f} gf. This aircraft "
                "cannot hover at all - it is over its maximum take-off mass.")
    if share > 0.85:
        return ("danger",
                f"Hovering takes {share * 100:.0f}% of every motor's maximum. "
                "There is no margin for wind, a turn or a failing cell, motors "
                "and ESCs will run hot enough to lose magnets or de-solder, and "
                "the aircraft is one weak motor away from descending.")
    if share < 0.25:
        return ("info",
                f"Hovering takes only {share * 100:.0f}% of each motor's maximum. "
                "That is a lot of motor and propeller mass being carried and "
                "never used - and a motor loafing this far below its design point "
                "is not at its efficient one either.")
    return None


def _motor_out_check(i, result):
    """What happens when one of them stops - the question that decides layout."""
    n = int(i.n_motors)
    if n < 4:
        return None
    remaining = v.positive_int(n - 1, "Remaining motors")
    share = i.weight / remaining
    fraction = share / i.max_per_motor
    if n == 4:
        return ("info",
                "A quadcopter cannot survive a motor failure: with three rotors "
                "left there is no way to balance both attitude and yaw torque. "
                f"The three would each need {share / GRAM_FORCE_N:.0f} gf "
                f"({fraction * 100:.0f}% of maximum) even if they could. Six "
                "rotors or more is the first layout that can be flown home.")
    if fraction > 1.0:
        return ("warning",
                f"Lose one motor and the remaining {remaining} would each need "
                f"{share / GRAM_FORCE_N:.0f} gf - more than their "
                f"{i.max_per_motor / GRAM_FORCE_N:.0f} gf maximum. The extra "
                "rotors buy no redundancy at this weight; they only share the "
                "load.")
    return ("info",
            f"Lose one motor and the remaining {remaining} each need "
            f"{share / GRAM_FORCE_N:.0f} gf, {fraction * 100:.0f}% of maximum. "
            "Below about 85% that is a survivable failure, though the autopilot "
            "will also throttle back the rotor opposite the dead one to stay "
            "level, so plan on landing rather than continuing.")


_HOVER = Calculator(
    slug="drone.hover_thrust", name="Hover thrust per motor",
    latex=r"T_{hover,motor} = \frac{W}{N_{motors}}",
    explanation=(
        "In a level hover the motors share the weight equally. Comparing that "
        "share with each motor's maximum thrust tells you how hard the propulsion "
        "system is working just to stay in the air. Thrust is <b>linear</b> in "
        "mass, which makes this page look forgiving - but the power to make that "
        "thrust goes as <b>mass^1.5</b>, so 10% more mass needs 10% more thrust "
        "and about 15% more power. Endurance always falls faster than this number "
        "rises."),
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
        Secondary("All-up mass", "kg", lambda i, r: i.weight / G0),
        Secondary("Per motor if one fails", "N",
                  lambda i, r: i.weight / v.positive_int(int(i.n_motors) - 1,
                                                         "Remaining motors")),
        Secondary("Spare thrust, whole aircraft", "N",
                  lambda i, r: i.n_motors * i.max_per_motor - i.weight),
    ],
    note=lambda i, r: (
        "Hovering above about 65% of maximum thrust leaves little headroom for "
        "manoeuvring, wind, or a failing cell - and motors run hot near their "
        "limit." if i.max_per_motor > 0 and r / i.max_per_motor > 0.65 else None),
    checks=[
        Check(_hover_margin_check),
        Check(_motor_out_check),
    ],
    assumptions=[
        "Level hover, motors equally loaded, centre of gravity on the geometric "
        "centre. An off-centre CG makes some motors work harder than others, and "
        "the hardest-working one is the one that saturates.",
        "No wind and no vertical acceleration - a pure steady hover.",
        "Motor maximum thrust is the bench figure at the propeller and voltage the "
        "manufacturer tested with. On a half-empty pack it is lower, so hover "
        "share rises through the flight.",
        "Thrust shares out linearly with mass, but hover POWER does not: momentum "
        "theory gives P proportional to T^1.5, so 10% more mass costs about 15% "
        "more power. A design that looks comfortable here can still be out of "
        "battery.",
        "More rotors share the load but do not create disk area on their own. Four "
        "10-inch rotors have more disk area, and so need less power, than eight "
        "5-inch ones lifting the same weight.",
        "Nothing here accounts for a motor failure - see the check above for what "
        "the survivors would have to make.",
    ],
    graphs=[
        Sweep(over="weight", y_label="Hover thrust per motor [N]",
              x_label="All-up weight [N]", lo_factor=0.3, hi_factor=2.0,
              title="Hover thrust per motor vs weight (linear here - but the "
                    "power to make it goes as weight^1.5)"),
        Sweep(over="n_motors", y_label="Hover thrust per motor [N]",
              x_label="Number of motors [-]", lo=1.0, hi_factor=3.0, hi_min=8.0,
              title="Hover thrust per motor vs rotor count (each extra rotor "
                    "helps less than the last)"),
    ],
    references=[
        Reference(
            title="Typical hover share",
            columns=("Aircraft", "Hover, % of maximum thrust", "Why"),
            rows=[
                ("Racing / freestyle", "20 - 30%", "Everything spent on margin"),
                ("Camera multirotor", "35 - 45%", "Smooth, still responsive"),
                ("Survey / long endurance", "45 - 55%",
                 "Motors near their efficient point"),
                ("Heavy lift at full payload", "55 - 65%", "Margin traded for mass"),
                ("Above 70%", "-", "No wind margin, no failure margin, hot motors"),
            ],
            note="Hover share is 1/TWR. The efficient point of a motor and "
                 "propeller pair is usually somewhere near 40-60% of maximum "
                 "thrust, which is why endurance designs sit there rather than "
                 "carrying oversized motors.",
        ),
        Reference(
            title="Motor-out load",
            columns=("Rotors", "Each survivor must make", "Increase"),
            rows=[
                ("4", "W / 3", "+33%  (and yaw is uncontrollable)"),
                ("6", "W / 5", "+20%"),
                ("8", "W / 7", "+14%"),
                ("12", "W / 11", "+9%"),
            ],
            note="Exact arithmetic for the thrust share; whether the aircraft "
                 "survives also depends on having that margin available and on "
                 "the autopilot supporting a motor-out mode. In practice the "
                 "rotor opposite the failed one is throttled back to keep the "
                 "aircraft level, so the real demand is higher than this.",
        ),
    ],
    related=["drone.twr", "prop.momentum_theory", "prop.hover_endurance",
             "drone.flight_time", "drone.total_thrust"],
    variables=[
        ("$T_{hover,motor}$", "Thrust each motor must make to hover", "N"),
        ("$W$", "All-up weight", "N"),
        ("$N_{motors}$", "Number of motors", "-"),
    ],
    example=(
        "Motor selection. A 2 kg quadcopter weighs 19.61 N, so each of four motors "
        "must produce 4.903 N (500 gf) to hover. Picking motors rated 1200 gf "
        "means hovering at 41.7% of maximum - a healthy margin and a good "
        "efficiency point. Lose one motor and the other three would each need "
        "6.54 N (667 gf, 55.6%): the thrust is there, but three rotors cannot "
        "balance yaw, which is the real reason survey aircraft have six."),
    keywords=("hover", "per motor", "share", "motor out", "redundancy",
              "margin", "throttle"),
)


def _depth_of_discharge_check(i, result):
    pct = float(i.usable_pct)
    if pct >= 95.0:
        return ("danger",
                f"Planning on {pct:.0f}% of rated capacity means landing at or "
                "below 3.0 V per cell under load. That is past the damage "
                "threshold: the pack loses capacity permanently, may puff, and "
                "the ESC's low-voltage cutoff can fire while you are still in the "
                "air. There is no reserve here at all.")
    if pct > 85.0:
        return ("warning",
                f"{pct:.0f}% depth of discharge is beyond the usual planning "
                "limit. Cycle life falls steeply above about 80%, and the last "
                "10% of a lithium pack is where voltage collapses fastest - so "
                "the final minutes of this estimate are the least trustworthy "
                "part of it.")
    if 0 < pct <= 50.0:
        return ("info",
                f"Using only {pct:.0f}% of the pack is kind to cycle life, but "
                "you are carrying roughly half a battery you never spend. On a "
                "multirotor that unused mass costs power on every flight.")
    return None


def _c_rate_check(i, result):
    rate = i.current / i.capacity
    if rate > 30.0:
        return ("warning",
                f"{rate:.0f} C continuous. Printed ratings of 100 C and above are "
                "burst figures: a genuine high-discharge LiPo sustains roughly "
                "20-40 C, and both delivered capacity and voltage fall away well "
                "before the label does. Expect noticeably less than the flight "
                "time above.")
    if rate > 10.0:
        return ("info",
                f"{rate:.1f} C is high-discharge LiPo territory. A Li-ion "
                "endurance pack (18650 or 21700 cells, 1-3 C continuous) cannot "
                "supply this: it would sag hard, heat up and deliver well under "
                "its rated capacity.")
    return None


_FLIGHT_TIME = Calculator(
    slug="drone.flight_time", name="Flight time (estimate)",
    latex=(r"t_{min} = \frac{C_{Ah} \times \text{usable fraction}}{I_{avg}} "
           r"\times 60"),
    explanation=(
        "A first-order estimate of endurance. Usable capacity matters: discharging "
        "a lithium pack to empty damages it, so most pilots plan on using 70-85% "
        "of the rated capacity. This is an <b>estimate</b>, not a guarantee - and "
        "it is an optimistic one, because it assumes the pack delivers its rated "
        "amp-hours at whatever current you ask for. It does not; see "
        "<i>Battery sag &amp; internal resistance</i> for why."),
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
        Secondary("Reserve left at landing", "Ah",
                  lambda i, r: i.capacity * (1.0 - i.usable_pct / 100.0)),
        Secondary("Average electrical power", "W",
                  lambda i, r: i.voltage * i.current),
        Secondary("Energy used", "Wh",
                  lambda i, r: i.voltage * i.capacity * i.usable_pct / 100.0),
        Secondary("Discharge rate (C-rate)", "C",
                  lambda i, r: i.current / i.capacity),
        Secondary("Cells in series at 3.7 V nominal", "S",
                  lambda i, r: i.voltage / LIPO_NOMINAL_V),
    ],
    checks=[
        Check(_depth_of_discharge_check),
        Check(_c_rate_check),
        Check(_pack_voltage_check),
    ],
    assumptions=[
        "ESTIMATE, not an exact relationship. Real endurance depends on wind, "
        "flying style, temperature and payload.",
        "Current is assumed constant at the average value. A multirotor draws far "
        "more while climbing or fighting wind than while hovering.",
        "Rated capacity is measured at a low, steady discharge rate. At high "
        "C-rates a pack delivers less than its label (the Peukert effect), so a "
        "hard-flown pack gives less than this number.",
        "Voltage sag, cell ageing and cold weather all reduce usable energy. A "
        "pack at 0 °C can have double the internal resistance it has at 25 °C, "
        "and the extra loss comes straight out of this flight time.",
        "The usable fraction is a charge target, not a voltage. 80% depth of "
        "discharge lands a healthy LiPo at roughly 3.7-3.8 V per cell resting - "
        "if your telemetry says 3.5 V resting, you used more than you planned.",
        "Capacity fades with cycles. A pack 200 cycles old may hold 80% of its "
        "label, so enter the capacity it actually has rather than the one printed "
        "on it.",
        "Always land with a reserve. Planning to 100% usable capacity is how packs "
        "get destroyed and aircraft fall out of the sky.",
    ],
    graphs=[
        Sweep(over="current", y_label="Flight time [min]", lo_factor=0.25,
              hi_factor=2.0,
              title="Flight time vs average current (inverse relationship)"),
        Sweep(over="capacity", y_label="Flight time [min]", lo_factor=0.2,
              hi_factor=2.5,
              title="Flight time vs capacity (linear here - but a bigger pack "
                    "is heavier, and a heavier aircraft draws more)"),
        Sweep(over="usable_pct", y_label="Flight time [min]", lo=10.0,
              hi_factor=1.25, hi_min=100.0,
              title="Flight time vs depth of discharge (the last stretch is "
                    "bought with cycle life)"),
    ],
    references=[_CELL_VOLTAGE_TABLE, _C_RATING_TABLE],
    related=["drone.battery_sag", "drone.battery_energy", "drone.power",
             "prop.hover_endurance", "drone.range_endurance"],
    variables=[
        ("$C_{Ah}$", "Rated battery capacity", "Ah"),
        ("$I_{avg}$", "Average current draw", "A"),
        ("$t_{min}$", "Estimated flight time", "min"),
        ("$V$", "Nominal pack voltage", "V"),
    ],
    example=(
        "Mission planning. A 5 Ah 6S pack flown to 80% depth of discharge at an "
        "average 25 A gives 9.6 minutes, using 4.0 Ah - 88.8 Wh - at an easy 5 C. "
        "Cutting average current to 20 A, by hovering more gently or shedding "
        "payload, buys another 2.4 minutes for 12.0 in total. Pushing depth of "
        "discharge from 80% to 95% would add only 1.8 minutes, and would cost far "
        "more than that in pack life."),
    keywords=("flight time", "endurance", "battery", "duration", "c rate",
              "depth of discharge", "lipo", "reserve"),
)


_CONNECTORS = ((30.0, "XT30"), (60.0, "XT60"), (90.0, "XT90"),
               (150.0, "AS150 or 8 mm bullets"))


def _connector_check(i, result):
    """Wire and connectors are sized by current, never by power."""
    amps = abs(float(i.current))
    if amps < 1.0:
        return None
    for rating, name in _CONNECTORS:
        if rating >= amps * 1.15:
            return ("info",
                    f"{amps:g} A continuous. The smallest common connector with a "
                    f"sensible margin is the {name} (rated {rating:g} A). Ratings "
                    "are continuous figures in free air - a taped harness inside a "
                    "closed frame runs hotter, and a connector at exactly its "
                    "rating has no margin at all.")
    return ("warning",
            f"{amps:g} A is beyond the usual hobby connectors, which stop around "
            "150 A. At this current the wire and the joints, not the battery, "
            "decide whether the aircraft catches fire: 8 AWG or larger, properly "
            "soldered, and check every joint before every flight.")


def _regen_check(i, result):
    if result < 0:
        return ("info",
                "Negative power means energy flowing back INTO the pack - a "
                "descending propeller driving its motor as a generator, or simply "
                "a sign error. ESCs with active braking do regenerate, but a full "
                "pack has nowhere to put the energy and the bus voltage rises "
                "until something gives.")
    return None


def _i2r_check(i, result):
    amps = abs(float(i.current))
    if amps >= 40.0:
        loss = amps ** 2 * 0.010
        return ("info",
                f"At {amps:g} A, every 10 mΩ in the path - wire, connectors, ESC "
                f"FETs, the pack's own internal resistance - burns {loss:.0f} W as "
                "heat. Loss goes as current SQUARED, so the same power taken from "
                "a pack of twice the voltage at half the current would waste a "
                f"quarter as much: {loss / 4:.0f} W. That is the whole argument "
                "for 6S and 12S.")
    return None


_POWER = Calculator(
    slug="drone.power", name="Electrical power",
    latex=r"P = V \times I",
    explanation=(
        "Instantaneous electrical power. On a drone this is what the battery is "
        "delivering to the ESCs right now - useful for sizing wiring, connectors "
        "and the battery's continuous discharge rating. Power decides how fast you "
        "empty the pack; <b>current</b> decides whether the wire, the connectors "
        "and the battery survive doing it, and the two are not the same "
        "constraint."),
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
        Secondary("Energy for a ten-minute flight", "Wh",
                  lambda i, r: r / 6.0),
        Secondary("Current per motor on a quad", "A", lambda i, r: i.current / 4.0),
        Secondary("Loss in 10 mΩ of wire and connectors", "W",
                  lambda i, r: i.current ** 2 * 0.010),
    ],
    checks=[
        Check(_connector_check),
        Check(_i2r_check),
        Check(_regen_check),
    ],
    assumptions=[
        "DC power. This form (P = V I) applies to direct current or to "
        "instantaneous values; AC systems also need a power factor.",
        "This is electrical input power. Motor and propeller losses mean the "
        "useful power reaching the air is typically 50-75% of it.",
        "Pack voltage sags under load, so the voltage while flying is lower than "
        "the resting voltage. Use the loaded figure here, not the one on a "
        "charger, or this overstates power.",
        "An ESC holds POWER roughly constant for a given throttle, not current. "
        "When voltage sags, current rises to compensate - which sags the pack "
        "further. That feedback is why real currents exceed the ones planned.",
        "The I²R figure uses an illustrative 10 mΩ of total path resistance. Real "
        "builds run from about 5 mΩ (short, thick, few joints) to 30 mΩ or more "
        "(long thin leads, cheap connectors, a tired pack).",
        "Continuous power, not burst. A motor or ESC rated 1 kW continuous will "
        "take much more for a second or two; thermal mass, not the equation, is "
        "what decides.",
    ],
    graphs=[
        Sweep(over="current", y_label="Electrical power [W]", hi_factor=2.0,
              hi_min=20.0, title="Power vs current at this voltage"),
        Sweep(over="voltage", y_label="Electrical power [W]", hi_factor=2.0,
              hi_min=10.0,
              title="Power vs voltage at this current (raise voltage and the "
                    "same power costs less current, so less heat)"),
    ],
    references=[
        Reference(
            title="Wire gauge by current",
            columns=("AWG", "Continuous current", "Typical use"),
            rows=[
                ("20", "11 A", "Signal, small ESC leads, 5 in motor leads"),
                ("18", "16 A", "Micro and 5 in ESC to motor"),
                ("16", "22 A", "5 in quad main leads"),
                ("14", "32 A", "7 in and small heavy-lift arms"),
                ("12", "41 A", "Main battery leads, 6S builds"),
                ("10", "55 A", "Heavy lift main leads"),
                ("8", "73 A", "High-current mains, AS150 class"),
            ],
            note="Chassis-wiring figures for short runs in free air, which is how "
                 "drone wiring is used. The same wire in a bundle, in a sealed "
                 "frame, or in a long run must be de-rated. Silicone-insulated "
                 "wire tolerates more heat than PVC but the copper is the same.",
        ),
        Reference(
            title="Connector ratings",
            columns=("Connector", "Continuous current", "Notes"),
            rows=[
                ("JST-PH / BT2.0", "2 - 6 A", "Whoops and micros"),
                ("XT30", "30 A", "3-4 in quads, small packs"),
                ("XT60", "60 A", "The 5 in standard"),
                ("XT90", "90 A", "7 in, 6S heavy, anti-spark version common"),
                ("AS150 / 8 mm bullet", "150 A", "Heavy lift, 12S"),
            ],
            note="Manufacturer continuous figures with adequate wire and airflow. "
                 "A connector run at its rating gets hot; pick the next size up "
                 "if the current is sustained or the frame is enclosed. "
                 "Anti-spark versions matter above about 6S, where the inrush "
                 "into the ESC capacitors pits plain contacts.",
        ),
    ],
    related=["drone.battery_sag", "drone.battery_energy", "drone.flight_time",
             "elec.ohms_law", "prop.motor_constants"],
    variables=[("$P$", "Electrical power", "W"), ("$V$", "Voltage", "V"),
               ("$I$", "Current", "A")],
    example=(
        "Wiring and connector sizing. A 6S pack at 22.2 V pulling 60 A is 1332 W. "
        "That current decides the wire gauge and connector type - an XT30 rated "
        "for 30 A would overheat and fail here, and even an XT60 is at exactly its "
        "limit. The same 60 A also wastes 36 W in only 10 mΩ of wiring and pack "
        "resistance; on a 12S pack the same 1332 W would need 30 A and waste a "
        "quarter as much."),
    keywords=("power", "watts", "vi", "current", "wire gauge", "awg",
              "connector", "xt60"),
)


def _air_transport_check(i, result):
    if result > 160.0:
        return ("warning",
                f"{result:.0f} Wh is above 160 Wh. Lithium batteries over 160 Wh "
                "are normally forbidden on passenger aircraft, in the cabin and "
                "in the hold, and move as dangerous goods on cargo aircraft "
                "instead.")
    if result > 100.0:
        return ("info",
                f"{result:.0f} Wh falls in the 100-160 Wh band. That needs the "
                "operator's prior approval, carry-on only, terminals protected "
                "against short circuits, and normally at most two spare packs per "
                "passenger.")
    return None


_BATTERY = Calculator(
    slug="drone.battery_energy", name="Battery energy",
    latex=r"E_{Wh} = V \times C_{Ah}",
    explanation=(
        "Capacity in amp-hours only tells half the story - it is charge, not "
        "energy. Multiply by voltage to get watt-hours, which is the number to "
        "compare packs of different cell counts and the one airlines regulate. "
        "Two packs with the same mAh on the label can differ by a factor of three "
        "in the energy they actually hold."),
    inputs=[
        Field("voltage", "Nominal pack voltage", "V", 22.2, min=0.0),
        Field("capacity", "Capacity", "Ah", 5.0, min=0.0),
    ],
    compute=lambda i: battery_energy_wh(i.voltage, i.capacity),
    result=Output("Stored energy", "Wh"),
    secondary=[
        Secondary("In kilojoules", "kJ", lambda i, r: r * 3.6),
        Secondary("Usable at 80% depth of discharge", "Wh", lambda i, r: r * 0.8),
        Secondary("Charge stored", "mAh", lambda i, r: i.capacity * 1000.0),
        Secondary("Cells in series at 3.7 V nominal", "S",
                  lambda i, r: i.voltage / LIPO_NOMINAL_V),
        Secondary("Runtime at 500 W", "min", lambda i, r: r / 500.0 * 60.0),
        Secondary("Hover time, 2 kg quad at 280 W, 80% usable", "min",
                  lambda i, r: r * 0.8 / 280.0 * 60.0),
    ],
    checks=[
        Check(_air_transport_check),
        Check(_pack_voltage_check),
    ],
    assumptions=[
        "Uses nominal voltage (3.7 V per LiPo cell). Real pack voltage runs from "
        "about 4.2 V per cell full to 3.5 V per cell under load, so stored energy "
        "is an average figure.",
        "Rated capacity assumes a healthy pack at a moderate discharge rate.",
        "Watt-hours measure energy; amp-hours measure charge. Comparing a 4S and a "
        "6S pack by mAh alone is misleading.",
        "This is the energy in the pack, not the energy you can use. Plan on 70-85% "
        "of it, and less again in the cold.",
        "Capacity fades with cycles and with storage at full charge. A pack stored "
        "full for a month loses capacity it never gets back.",
        "The hover-time figure assumes the 280 W a 2 kg quadcopter on 10-inch "
        "propellers takes to hover; a different aircraft has a different number. "
        "See Hover power & endurance to compute your own.",
    ],
    graphs=[
        Sweep(over="capacity", y_label="Stored energy [Wh]", hi_factor=2.0,
              hi_min=2.0, title="Energy vs capacity at this pack voltage"),
        Sweep(over="voltage", y_label="Stored energy [Wh]", hi_factor=2.0,
              hi_min=12.6,
              title="Energy vs pack voltage (same mAh, more cells, more energy)"),
    ],
    references=[
        Reference(
            title="Common packs",
            columns=("Pack", "Nominal", "Capacity", "Energy"),
            rows=[
                ("3S 2200 mAh", "11.1 V", "2.2 Ah", "24.4 Wh"),
                ("4S 1300 mAh (race)", "14.8 V", "1.3 Ah", "19.2 Wh"),
                ("4S 5000 mAh", "14.8 V", "5.0 Ah", "74.0 Wh"),
                ("6S 1300 mAh (race)", "22.2 V", "1.3 Ah", "28.9 Wh"),
                ("6S 5000 mAh", "22.2 V", "5.0 Ah", "111.0 Wh"),
                ("12S 22000 mAh (heavy lift)", "44.4 V", "22.0 Ah", "976.8 Wh"),
            ],
            note="Energy is simply the product of the two columns before it. Note "
                 "the 4S and 6S 5000 mAh rows: identical labels in mAh, 50% more "
                 "energy in the 6S pack, and it is the 6S one that needs airline "
                 "approval to travel.",
        ),
        Reference(
            title="Specific energy by chemistry",
            columns=("Chemistry", "Pack level", "Character"),
            rows=[
                ("NiMH", "60 - 100 Wh/kg", "Obsolete for flight"),
                ("LiPo, high discharge", "130 - 170 Wh/kg", "Current, not energy"),
                ("LiPo, standard", "150 - 190 Wh/kg", "The usual compromise"),
                ("Li-ion 18650 pack", "180 - 230 Wh/kg", "Endurance, low current"),
                ("Li-ion 21700 pack", "200 - 260 Wh/kg", "Endurance with margin"),
                ("Petrol (for scale)", "~12,800 Wh/kg", "Fuel only; ~25% reaches "
                                                        "the shaft"),
            ],
            note="Pack level, after wiring, case and BMS - bare cells are 10-25% "
                 "better than this. The petrol row is why fuel-burning aircraft "
                 "still out-endure electric ones by an order of magnitude: even "
                 "after a poor engine efficiency, the fuel carries roughly "
                 "fifteen times the useful energy per kilogram.",
        ),
    ],
    related=["drone.flight_time", "drone.battery_sag", "drone.power",
             "prop.hover_endurance", "elec.battery_energy"],
    variables=[
        ("$E_{Wh}$", "Stored energy", "Wh"),
        ("$V$", "Nominal pack voltage", "V"),
        ("$C_{Ah}$", "Rated capacity (charge)", "Ah"),
    ],
    example=(
        "Comparing packs. A 4S 5000 mAh pack holds 14.8 × 5 = 74 Wh; a 6S "
        "5000 mAh pack holds 111 Wh. Same 'mAh' on the label, 50% more energy - "
        "and the 6S pack needs airline approval to fly with. At 80% usable, that "
        "111 Wh is 88.8 Wh, which hovers a 2 kg quadcopter drawing 280 W for "
        "about 19 minutes."),
    keywords=("battery", "energy", "wh", "capacity", "mah", "watt hours",
              "airline", "specific energy"),
)


# ---------------------------------------------------------------------------
# Battery internal resistance and voltage sag
# ---------------------------------------------------------------------------


def _loaded_cell_check(i, result):
    per_cell = result / int(i.cells)
    if per_cell < LIPO_CUTOFF_V:
        return ("danger",
                f"{per_cell:.2f} V per cell under load is below the 3.0 V damage "
                "threshold. The ESC's low-voltage cutoff will fire, thrust will "
                "drop while you are still flying, and the pack loses capacity "
                "permanently. Reduce the current, use a bigger pack, or land "
                "earlier.")
    if per_cell < 3.3:
        return ("warning",
                f"{per_cell:.2f} V per cell under load is at or below the usual "
                "ESC cutoff of 3.3 V. Expect the flight controller to start "
                "limiting throttle; the pack will rest back higher than this, "
                "which is how a 'sudden' brownout looks fine after landing.")
    if per_cell < 3.5:
        return ("info",
                f"{per_cell:.2f} V per cell under load is in the land-soon band. "
                "There is usable charge left, but very little voltage margin for "
                "a climb or a punch-out at this current.")
    return None


def _sag_fraction_check(i, result):
    open_circuit = int(i.cells) * float(i.v_cell)
    fraction = (open_circuit - result) / open_circuit
    resistance = pack_internal_resistance(i.cells, i.r_cell)
    heat = i.current ** 2 * resistance
    if fraction > 0.20:
        return ("danger",
                f"{fraction * 100:.0f}% of the pack's voltage is being lost inside "
                f"the pack itself, {heat:.0f} W of it as heat in the cells. This "
                "pack is badly undersized for this current: it will get hot, age "
                "fast, and deliver far less than its rated capacity.")
    if fraction > 0.10:
        return ("warning",
                f"{fraction * 100:.0f}% of the pack's voltage is dropped across "
                f"its own internal resistance, heating the cells with {heat:.0f} "
                "W. Above about 10% you are paying for the pack twice - once in "
                "wasted energy, once in shortened life.")
    if fraction > 0.05:
        return ("info",
                f"{fraction * 100:.1f}% of the pack's voltage is lost internally, "
                f"{heat:.0f} W as heat in the cells. That is normal for a "
                "multirotor at power, and it is the direct reason a flight-time "
                "estimate based on rated capacity comes out optimistic.")
    return None


def _internal_resistance_check(i, result):
    r_cell = float(i.r_cell)
    if r_cell < 1.0:
        return ("info",
                f"{r_cell:g} mΩ per cell is lower than any small lithium cell "
                "measures. Chargers report internal resistance in MILLIohms - "
                "check you have not entered ohms, which would be a thousand times "
                "too small.")
    if r_cell > 25.0:
        return ("info",
                f"{r_cell:g} mΩ per cell is Li-ion territory (18650 energy cells "
                "measure 30-60 mΩ) or a badly aged LiPo. It is fine for a "
                "low-current endurance aircraft and hopeless for a high-current "
                "one - the sag above is the whole story.")
    if r_cell > 10.0:
        return ("info",
                f"{r_cell:g} mΩ per cell is high for a LiPo. A healthy "
                "high-discharge pack measures 2-6 mΩ per cell at room "
                "temperature. Resistance rises with age, with damage, and steeply "
                "as the pack gets cold - a winter flight can start with double "
                "the resistance of a summer one.")
    return None


_BATTERY_SAG = Calculator(
    slug="drone.battery_sag", name="Battery sag & internal resistance",
    latex=(r"V_{load} = V_{oc} - I\,R_{int}, \qquad "
           r"R_{int} = N_{cells}\,r_{cell}"),
    explanation=(
        "A battery is a voltage source with a resistor in series with it, and this "
        "is the equation for that resistor. The resistance is tiny - a few "
        "milliohms per cell - but the current is not, and the product is volts you "
        "never see at the ESC. Worse, it is a feedback loop: the ESC holds power "
        "roughly constant, so when voltage sags it draws <b>more</b> current, "
        "which sags the pack further. This is why the flight-time page is "
        "optimistic and why a pack that reads 3.8 V per cell on the bench can hit "
        "the low-voltage cutoff in a climb."),
    inputs=[
        Field("cells", "Cells in series", "S", 6, min=1, max=24, kind="int",
              help="6S means six cells in series: six times the voltage, and six "
                   "times the internal resistance."),
        Field("v_cell", "Resting voltage per cell", "V", 3.8, min=2.5, max=4.4,
              help="4.20 V full, 3.80 V about half, 3.50 V nearly empty."),
        Field("r_cell", "Internal resistance per cell", "mΩ", 4.0, min=0.0,
              help="What a charger's IR test reports. 2-6 mΩ for a healthy "
                   "high-discharge LiPo; 30-60 mΩ for an 18650 Li-ion cell."),
        Field("current", "Load current", "A", 60.0, min=0.0,
              help="The instantaneous draw you care about - usually a climb or a "
                   "punch-out, not the flight average."),
    ],
    compute=lambda i: loaded_pack_voltage(i.cells, i.v_cell, i.r_cell, i.current),
    result=Output("Pack voltage under load", "V"),
    secondary=[
        Secondary("Voltage sag", "V",
                  lambda i, r: i.cells * i.v_cell - r),
        Secondary("Under load, per cell", "V", lambda i, r: r / int(i.cells)),
        Secondary("Pack internal resistance", "mΩ",
                  lambda i, r: pack_internal_resistance(i.cells, i.r_cell) * 1000.0),
        Secondary("Heat generated inside the pack", "W",
                  lambda i, r: i.current ** 2
                  * pack_internal_resistance(i.cells, i.r_cell)),
        Secondary("Share of pack power lost as heat", "%",
                  lambda i, r: (i.cells * i.v_cell - r) / (i.cells * i.v_cell)
                  * 100.0),
        Secondary("Power reaching the ESCs", "W", lambda i, r: r * i.current),
    ],
    checks=[
        Check(_loaded_cell_check),
        Check(_sag_fraction_check),
        Check(_internal_resistance_check),
    ],
    assumptions=[
        "Internal resistance is treated as a constant. It is not: it rises as the "
        "pack empties, rises steeply as it gets cold, and rises permanently with "
        "age and abuse. A cold, old pack can have several times the resistance of "
        "the number you entered.",
        "Cells in series add resistance, so a 6S pack of 4 mΩ cells is a 24 mΩ "
        "pack. Cells in PARALLEL divide it - a 2P pack of the same cells is half "
        "the resistance, which is the main reason parallel packs punch harder.",
        "This is the pack alone. Wiring, connectors, the ESC's FETs and every "
        "solder joint add their own milliohms in series, often as much again as "
        "the battery.",
        "Open-circuit voltage is the RESTED voltage. A pack measured immediately "
        "after a hard flight reads low and recovers over minutes - that recovery "
        "is the difference between this equation and a discharged cell.",
        "The heat computed here is deposited inside the cells, where it is hardest "
        "to remove. A pack that comes down warm was working; one that comes down "
        "hot is being damaged.",
        "An ESC is a roughly constant-POWER load at a given throttle, not a "
        "constant-current one. The real operating point is where the sag line and "
        "the power demand meet, so the true current is higher than a fixed-current "
        "calculation suggests.",
    ],
    graphs=[
        Sweep(over="current", y_label="Pack voltage under load [V]", lo=0.0,
              hi_factor=2.5, hi_min=60.0,
              title="Voltage vs current (the sag line - its slope IS the pack's "
                    "internal resistance)"),
        Sweep(over="r_cell", y_label="Pack voltage under load [V]", lo=0.0,
              hi_factor=4.0, hi_min=10.0,
              title="Voltage vs cell resistance (ageing and cold move you right "
                    "along this line)"),
        Sweep(over="v_cell", y_label="Pack voltage under load [V]", lo=3.0,
              hi_factor=1.11, hi_min=4.2,
              title="Voltage vs state of charge (sag is the same size at every "
                    "state of charge, so it bites hardest when nearly empty)"),
        Sweep(over="cells", y_label="Pack voltage under load [V]", lo=1.0,
              hi_factor=2.0, hi_min=12.0,
              title="Voltage vs cell count (more cells add resistance too - the "
                    "sag per cell is unchanged)"),
    ],
    references=[
        Reference(
            title="Typical internal resistance",
            columns=("Cell", "Per cell", "Notes"),
            rows=[
                ("High-discharge LiPo, new", "2 - 6 mΩ",
                 "Lower for larger capacity"),
                ("LiPo after heavy use", "8 - 15 mΩ", "Sags noticeably more"),
                ("LiPo, puffed or damaged", "20 mΩ+", "Retire it"),
                ("Li-ion 21700, power cell", "15 - 25 mΩ", "Endurance with punch"),
                ("Li-ion 18650, energy cell", "30 - 60 mΩ",
                 "Long flights, gentle currents"),
            ],
            note="Measured at room temperature by a charger's IR function, per "
                 "cell, for a single cell in series. Values vary with capacity "
                 "(a bigger cell has lower resistance), with temperature, and "
                 "between measuring methods - use them for comparison between "
                 "your own packs rather than as absolutes.",
        ),
        _CELL_VOLTAGE_TABLE,
    ],
    related=["drone.flight_time", "drone.power", "drone.battery_energy",
             "elec.ohms_law", "prop.motor_constants"],
    variables=[
        ("$V_{load}$", "Pack voltage while the load is applied", "V"),
        ("$V_{oc}$", "Open-circuit (rested) pack voltage", "V"),
        ("$I$", "Load current", "A"),
        ("$R_{int}$", "Pack internal resistance", "Ω"),
        ("$N_{cells}$", "Cells in series", "-"),
        ("$r_{cell}$", "Internal resistance of one cell", "Ω"),
    ],
    example=(
        "Why the punch-out browns out. A 6S pack of healthy 4 mΩ cells, half "
        "discharged at 3.80 V per cell, rests at 22.80 V and has 24 mΩ of internal "
        "resistance. Pull 60 A and it drops 1.44 V to 21.36 V - 3.56 V per cell, "
        "still comfortable, with 86 W heating the cells. Pull 100 A and it drops "
        "2.40 V to 20.40 V, or 3.40 V per cell, and 240 W is now going into the "
        "pack instead of the propellers. Do the same on a tired pack at 10 mΩ per "
        "cell and 60 A alone takes it to 19.20 V - 3.20 V per cell, below the "
        "usual ESC cutoff, and the aircraft drops out of the sky on a full-looking "
        "battery."),
    keywords=("sag", "internal resistance", "voltage drop", "brownout", "ir",
              "milliohm", "lipo", "punch out", "peukert", "battery"),
)


# ---------------------------------------------------------------------------
# Electric range and endurance
# ---------------------------------------------------------------------------


def _efficiency_check(i, result):
    eta = float(i.eta)
    if eta > 0.75:
        return ("warning",
                f"A total efficiency of {eta:.2f} is not achievable by a complete "
                "electric drivetrain. Multiply it out: propeller 0.70-0.80, motor "
                "0.85-0.90, ESC 0.95, wiring and battery losses a few percent - "
                "the product lands between 0.45 and 0.65. Above 0.75 this page "
                "is telling you a fairy tale about range.")
    if eta < 0.35:
        return ("info",
                f"A total efficiency of {eta:.2f} is low even for a small, "
                "heavily loaded propeller. If you meant motor efficiency alone, "
                "this field wants propeller × motor × ESC together.")
    return None


def _lift_to_drag_check(i, result):
    ld = float(i.ld)
    if ld > 25.0:
        return ("info",
                f"L/D of {ld:.0f} is sailplane territory. Powered UAVs run 8-16, "
                "and only a clean, high-aspect-ratio wing flown at its best speed "
                "gets past 20. Check the number against the reference table "
                "before trusting the range.")
    if ld < 6.0:
        return ("info",
                f"L/D of {ld:.1f} describes a multirotor or a very draggy "
                "airframe. The equation still holds - a quadcopter in forward "
                "flight has an effective L/D of 3-6 - but 'cruise' is then "
                "whatever speed minimises power, and there is no clean best-range "
                "speed to fly.")
    return None


def _headwind_check(i, result):
    speed = float(i.speed)
    if 0 < speed < 15.0:
        loss = 5.0 / speed
        return ("info",
                f"At {speed:g} m/s cruise, wind is a first-order effect. A 5 m/s "
                "headwind - a light breeze - removes "
                f"{loss * 100:.0f}% of the ground range above, because the "
                "equation computes distance through the AIR, not over the ground. "
                "Slow aircraft plan their legs around the wind.")
    return None


def _range_note(i, result):
    endurance = electric_endurance_minutes(i.energy, i.dod, i.eta, i.ld,
                                           i.weight, i.speed)
    return (f"At {i.speed:g} m/s that is {endurance:.1f} minutes in the air. Fly "
            f"20% slower, at {i.speed * 0.8:g} m/s, and the range stays "
            f"{result:.1f} km while endurance stretches to "
            f"{endurance / 0.8:.1f} minutes - provided you re-trim to the same "
            "L/D. Range and endurance are different questions with different "
            "answers.")


_RANGE_ENDURANCE = Calculator(
    slug="drone.range_endurance", name="Electric range & endurance",
    latex=(r"R = \frac{\eta\,E\,DoD\,(L/D)}{W}, \qquad "
           r"t = \frac{R}{V} = \frac{\eta\,E\,DoD\,(L/D)}{W\,V}"),
    explanation=(
        "The Breguet range equation for a battery aircraft. A fuel-burning "
        "aeroplane gets lighter as it flies, which is where the logarithm in the "
        "classic form comes from; a battery aircraft does not, so the logarithm "
        "collapses to a division. Read what is <b>missing</b> from the range "
        "equation: speed. Energy per unit distance is just drag, and at a fixed "
        "L/D drag is set by weight alone - so flying faster gets you there sooner "
        "on the same energy, not further. Endurance is the opposite: it is range "
        "divided by speed, so every knot of extra cruise costs you time aloft."),
    inputs=[
        Field("energy", "Battery energy", "Wh", 111.0, min=0.0,
              help="Pack voltage × capacity. A 6S 5 Ah LiPo is 111 Wh."),
        Field("dod", "Usable fraction (depth of discharge)", "-", 0.8,
              min=0.05, max=1.0),
        Field("eta", "Propeller × motor × ESC efficiency", "-", 0.6,
              min=0.05, max=1.0,
              help="The whole chain from watt-hours to thrust power. 0.45-0.65 "
                   "is realistic; 0.6 is a good clean installation."),
        Field("ld", "Lift-to-drag ratio L/D", "-", 10.0, min=0.5,
              help="8-16 for a small electric UAV, 3-6 for a multirotor in "
                   "forward flight, 40+ for a sailplane."),
        Field("weight", "All-up", "", 3.0, kind="weight"),
        Field("speed", "Cruise speed V", "m/s", 18.0, min=0.0,
              help="True airspeed. Range barely cares; endurance cares a lot."),
    ],
    compute=lambda i: electric_range_km(i.energy, i.dod, i.eta, i.ld, i.weight),
    result=Output("Still-air range", "km"),
    secondary=[
        Secondary("Endurance", "minutes",
                  lambda i, r: electric_endurance_minutes(i.energy, i.dod, i.eta,
                                                          i.ld, i.weight,
                                                          i.speed)),
        Secondary("Cruise electrical power", "W",
                  lambda i, r: cruise_electrical_power(i.weight, i.speed, i.ld,
                                                       i.eta)),
        Secondary("Cruise drag (= thrust needed)", "N",
                  lambda i, r: cruise_drag(i.weight, i.ld)),
        Secondary("Usable energy", "Wh", lambda i, r: i.energy * i.dod),
        Secondary("Energy per kilometre", "Wh/km",
                  lambda i, r: i.energy * i.dod / r),
        Secondary("In statute miles", "miles", lambda i, r: r * 0.621371),
    ],
    note=_range_note,
    checks=[
        Check(_efficiency_check),
        Check(_lift_to_drag_check),
        Check(_headwind_check),
    ],
    assumptions=[
        "CONSTANT WEIGHT. This is the whole difference from the fuel-burning "
        "Breguet equation: a battery weighs the same empty as full, so there is "
        "no logarithm and no benefit from burning off mass.",
        "Steady level cruise at a fixed L/D. Climb, loiter, turns and the descent "
        "are not included, and on a short flight the climb alone can be a fifth of "
        "the energy.",
        "L/D is the value at the speed you are actually flying, not the aircraft's "
        "best. Fly faster or slower than the best-L/D speed and L/D falls, which "
        "is the real reason range is not perfectly flat with speed.",
        "Efficiency is the whole chain - propeller, motor, ESC, wiring - and is "
        "assumed constant. A propeller sized for cruise is poor in the climb, and "
        "vice versa.",
        "Still air. Range here is distance through the air mass; a headwind of a "
        "third of your cruise speed costs a third of your ground range, and there "
        "is no way to get it back.",
        "Battery energy is the pack's rated energy. Voltage sag, the Peukert "
        "effect, cold and age all reduce what you actually get - see Battery sag "
        "& internal resistance.",
        "No reserve beyond the depth-of-discharge figure. Aviation practice is to "
        "plan a diversion and a hold on top of the mission, not to fly to the "
        "last watt-hour.",
    ],
    graphs=[
        Sweep(over="ld", y_label="Range [km]", lo=1.0, hi_factor=2.5, hi_min=20.0,
              title="Range vs lift-to-drag ratio (aerodynamic cleanliness is "
                    "bought once and paid for on every flight)"),
        Sweep(over="energy", y_label="Range [km]", hi_factor=2.5, hi_min=100.0,
              title="Range vs battery energy (linear - but a bigger pack is "
                    "heavier, and the weight graph pushes back)"),
        Sweep(over="weight", y_label="Range [km]", x_label="All-up weight [N]",
              lo_factor=0.4, hi_factor=2.0,
              title="Range vs weight (inverse - every gram costs range in "
                    "proportion)"),
        Sweep(over="speed", y_label="Range [km]", lo_factor=0.3, hi_factor=2.0,
              title="Range vs cruise speed (flat - at a fixed L/D, range does "
                    "not depend on speed; endurance does)"),
    ],
    references=[
        Reference(
            title="Typical lift-to-drag ratios",
            columns=("Aircraft", "L/D", "Comment"),
            rows=[
                ("Competition sailplane", "40 - 60", "The whole point of it"),
                ("Airliner in cruise", "15 - 19", "Efficient at its design point"),
                ("Small electric UAV, clean", "12 - 16", "High aspect ratio wing"),
                ("Foam FPV wing", "6 - 10", "Draggy, but forgiving"),
                ("Light aircraft", "8 - 12", "Struts, wheels, cooling drag"),
                ("Multirotor in forward flight", "3 - 6",
                 "Effective value; it has no wing"),
            ],
            note="At the aircraft's best-L/D speed. Fly faster or slower than "
                 "that and L/D falls off on both sides, which is why the "
                 "speed-independence of range holds only near the design point.",
        ),
        Reference(
            title="Pack energy for this equation",
            columns=("Pack", "Energy", "Range at L/D 10, 3 kg, 60% efficient"),
            rows=[
                ("4S 5000 mAh LiPo", "74 Wh", "43 km"),
                ("6S 5000 mAh LiPo", "111 Wh", "65 km"),
                ("6S 10000 mAh Li-ion", "222 Wh", "130 km"),
                ("12S 22000 mAh", "977 Wh", "574 km"),
            ],
            note="Computed straight from this page at 80% depth of discharge and "
                 "3 kg all-up, which the larger packs would not be - the point of "
                 "the column is the proportionality, not the aircraft. Doubling "
                 "energy doubles range only if the extra pack is free, and it "
                 "never is.",
        ),
    ],
    related=["drone.flight_time", "drone.battery_energy", "aero.lift_to_drag",
             "flight.glide", "prop.hover_endurance"],
    variables=[
        ("$R$", "Still-air range", "km"),
        ("$t$", "Endurance", "min"),
        ("$E$", "Battery energy", "Wh"),
        ("$DoD$", "Usable fraction of the pack", "-"),
        ("$\\eta$", "Propeller × motor × ESC efficiency", "-"),
        ("$L/D$", "Lift-to-drag ratio at cruise", "-"),
        ("$W$", "All-up weight", "N"),
        ("$V$", "Cruise true airspeed", "m/s"),
    ],
    example=(
        "Sizing a survey aircraft. A 3 kg fixed-wing UAV (29.42 N) with L/D 10 "
        "carries a 111 Wh pack, flown to 80% and driven at 60% total efficiency. "
        "Cruise drag is 2.94 N, cruise power 88.3 W, and the still-air range is "
        "65.2 km - 60.4 minutes at 18 m/s. Fly at 14.4 m/s instead and the range "
        "is still 65.2 km but the endurance becomes 75.5 minutes, which is the "
        "right trade for a camera and the wrong one for a delivery. Add 500 g of "
        "payload and range falls to 55.9 km: weight is the only input that costs "
        "you both at once."),
    keywords=("range", "endurance", "breguet", "fixed wing", "cruise",
              "lift to drag", "mission", "loiter", "electric"),
)


CALCULATORS = [_TOTAL_THRUST, _DRONE_TWR, _HOVER, _FLIGHT_TIME, _POWER, _BATTERY,
               _BATTERY_SAG, _RANGE_ENDURANCE]
