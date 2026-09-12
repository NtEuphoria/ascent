"""Electrical and robotics-electronics calculators.

Structure used by every calculator module in this project:
  1. Pure functions at the top - no Streamlit, fully unit-tested, self-validating.
  2. Calculator specs below - pure data describing each page.
  3. A CALCULATORS list at the bottom, which app.py turns into navigation.

Three pages here keep the `render=` escape hatch rather than becoming specs,
because a spec cannot express what they do:

  * **Ohm's law** changes which quantity is the headline - label, unit and
    formula all switch - and `Output` is one fixed label and one fixed unit.
  * **Resistors in series / parallel** take a variable-length list of
    resistors, and `Field` describes one scalar input.

Those three build the same explore block (graphs, reference tables, related
links) by hand through `_explore`, so staying imperative costs the reader
nothing.
"""
from __future__ import annotations

import math
from typing import NamedTuple, Optional, Sequence

import numpy as np
import streamlit as st

from utils import charts, navigate, settings, ui
from utils import validation as v
from utils.spec import (Calculator, Check, Field, Output, Reference, Secondary,
                        Sweep)

# ---------------------------------------------------------------------------
# Material and component constants
# ---------------------------------------------------------------------------

# Resistivity of annealed copper at 20 °C. 1.724e-8 Ω·m is the 100% IACS
# reference value, and it is the number that reproduces every published AWG
# resistance-per-metre table to three figures - see awg_area_mm2 below.
RHO_COPPER_20C = 1.724e-8       # Ω·m
RHO_ALUMINIUM_20C = 2.82e-8     # Ω·m

# IEC 60063 preferred values. One decade each; every real resistor value is one
# of these times a power of ten.
E12 = (1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2)
E24 = (1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
       3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1)
_SERIES = {"E12": E12, "E24": E24}

# Standard through-hole and chip resistor power ratings, in watts. 1/4 W is the
# default part in almost every parts bin, which is why it is exceeded so often.
STANDARD_POWER_RATINGS_W = (0.0625, 0.1, 0.125, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0)

# Typical continuous current for ONE insulated copper conductor in free air, by
# AWG. These are the long-standing "chassis wiring" figures; they assume a
# single conductor with room to shed heat, which is the case for drone and
# robot power leads and is NOT the case inside a loom, a conduit or a wall. See
# the note on _WIRE_TABLE for what changes them.
_FREE_AIR_AMPS = {8: 73.0, 10: 55.0, 12: 41.0, 14: 32.0, 16: 22.0,
                  18: 16.0, 20: 11.0, 22: 7.0, 24: 3.5}

# Nominal cell voltage by chemistry, used to name a pack from its voltage.
# Ordered so that a voltage two chemistries can both explain (12.0 V is both
# six lead-acid cells and ten NiMH cells) is named the way it is usually meant.
_CHEMISTRIES = (
    ("lead-acid", 2.0),
    ("lithium-polymer (LiPo)", 3.7),
    ("LiFePO4", 3.2),
    ("NiMH", 1.2),
)


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def ohms_law_voltage(current: float, resistance: float) -> float:
    """V = I * R   [V]"""
    current = v.finite(current, "Current", "A")
    resistance = v.non_negative(resistance, "Resistance", "Ω")
    return current * resistance


def ohms_law_current(voltage: float, resistance: float) -> float:
    """I = V / R   [A]"""
    voltage = v.finite(voltage, "Voltage", "V")
    resistance = v.positive(resistance, "Resistance", "Ω")
    return voltage / resistance


def ohms_law_resistance(voltage: float, current: float) -> float:
    """R = V / I   [Ω]"""
    voltage = v.finite(voltage, "Voltage", "V")
    current = v.non_zero(current, "Current", "A")
    return voltage / current


def power_vi(voltage: float, current: float) -> float:
    """P = V * I   [W]"""
    return v.finite(voltage, "Voltage", "V") * v.finite(current, "Current", "A")


def power_i2r(current: float, resistance: float) -> float:
    """P = I² * R   [W] - the form to use for resistive (heat) losses."""
    current = v.finite(current, "Current", "A")
    resistance = v.non_negative(resistance, "Resistance", "Ω")
    return current ** 2 * resistance


def power_v2r(voltage: float, resistance: float) -> float:
    """P = V² / R   [W]"""
    voltage = v.finite(voltage, "Voltage", "V")
    resistance = v.positive(resistance, "Resistance", "Ω")
    return voltage ** 2 / resistance


def series_resistance(resistances) -> float:
    """R_total = R1 + R2 + ...   [Ω]"""
    values = [v.non_negative(r, f"Resistor {i + 1}", "Ω")
              for i, r in enumerate(resistances)]
    if not values:
        raise v.ValidationError("Enter at least one resistor.")
    return float(sum(values))


def parallel_resistance(resistances) -> float:
    """1/R_total = 1/R1 + 1/R2 + ...   [Ω]"""
    values = [v.positive(r, f"Resistor {i + 1}", "Ω")
              for i, r in enumerate(resistances)]
    if not values:
        raise v.ValidationError("Enter at least one resistor.")
    return 1.0 / sum(1.0 / r for r in values)


def battery_energy_wh(voltage: float, capacity_ah: float) -> float:
    """E = V * Ah   [Wh]

    NOTE: calculators/drones.py defines an identical battery_energy_wh for its
    own "Battery energy" page. The duplication is deliberate for now - the two
    modules are owned separately - and both must stay V * Ah exactly. If they
    are ever merged, move this one into utils/ rather than importing across
    calculator modules.
    """
    voltage = v.non_negative(voltage, "Voltage", "V")
    capacity_ah = v.non_negative(capacity_ah, "Capacity", "Ah")
    return voltage * capacity_ah


def nearest_standard_resistor(value: float, series: str = "E24") -> float:
    """Closest catalogue resistor to `value`   [Ω]

    Chosen by ratio, not by difference, because the preferred-value series is
    geometric. 3.0 kΩ sits 300 Ω from 2.7 k and 300 Ω from 3.3 k, but the
    tolerance bands they were designed to cover are proportional, so the honest
    comparison is |ln(candidate / value)|.
    """
    value = v.positive(value, "Resistance", "Ω")
    if series not in _SERIES:
        raise v.ValidationError(
            f"Unknown series '{series}'. Use one of {', '.join(_SERIES)}.")
    decade = 10.0 ** math.floor(math.log10(value))
    candidates = [round(base * decade * step, 12)
                  for step in (0.1, 1.0, 10.0)
                  for base in _SERIES[series]]
    return min(candidates, key=lambda c: abs(math.log(c / value)))


def smallest_power_rating(dissipation: float, derating: float = 2.0
                          ) -> Optional[float]:
    """Smallest standard resistor rating with `derating`x headroom   [W]

    Returns None when even a 5 W part would be run harder than the derating
    allows - at that point the answer is a different component, not a bigger
    resistor of the same kind.
    """
    dissipation = v.non_negative(dissipation, "Power dissipated", "W")
    derating = v.positive(derating, "Derating factor", "-")
    needed = dissipation * derating
    for rating in STANDARD_POWER_RATINGS_W:
        if rating >= needed:
            return rating
    return None


def awg_area_mm2(awg: float) -> float:
    """Cross-sectional area of a solid AWG conductor   [mm²]

    The gauge is a geometric series by definition: 36 AWG is 0.127 mm across
    and each 6 gauges smaller doubles the diameter, so d = 0.127 * 92^((36-n)/39).
    Every third gauge roughly doubles the area, which is the rule of thumb worth
    remembering.
    """
    awg = v.in_range(awg, "Wire gauge", -3.0, 40.0, "AWG")
    diameter_mm = 0.127 * 92.0 ** ((36.0 - awg) / 39.0)
    return math.pi * diameter_mm ** 2 / 4.0


def wire_resistance(length_m: float, area_mm2: float,
                    resistivity: float = RHO_COPPER_20C) -> float:
    """R = ρ L / A   [Ω] for a single conductor of that length."""
    length_m = v.non_negative(length_m, "Conductor length", "m")
    area_mm2 = v.positive(area_mm2, "Conductor area", "mm²")
    resistivity = v.positive(resistivity, "Resistivity", "Ω·m")
    return resistivity * length_m / (area_mm2 * 1e-6)


def voltage_drop(current: float, length_m: float, area_mm2: float,
                 resistivity: float = RHO_COPPER_20C,
                 loop: bool = True) -> float:
    """ΔV = I * ρ * (2L) / A   [V]

    `length_m` is the ONE-WAY run. With loop=True (the default) the current has
    to come back too, so the resistance that matters is twice that length - the
    single most common mistake in cable sizing.
    """
    current = v.finite(current, "Current", "A")
    conductor = (2.0 if loop else 1.0) * length_m
    return current * wire_resistance(conductor, area_mm2, resistivity)


def free_air_current_limit(awg: float) -> Optional[float]:
    """Typical continuous current for one copper conductor in free air   [A]

    A lookup, not a formula, and only for 8-24 AWG. Returns None outside that
    range rather than extrapolating a number nobody measured.
    """
    return _FREE_AIR_AMPS.get(int(round(v.finite(awg, "Wire gauge", "AWG"))))


def identify_pack(voltage: float, tolerance: float = 0.015) -> Optional[str]:
    """Name a pack from its nominal voltage, e.g. 14.8 V -> "4S LiPo".

    Returns None when no whole number of cells of a common chemistry lands
    within `tolerance` (a fraction) of the voltage.
    """
    voltage = v.non_negative(voltage, "Voltage", "V")
    if voltage <= 0:
        return None
    for name, cell in _CHEMISTRIES:
        cells = round(voltage / cell)
        if cells < 1:
            continue
        if abs(voltage - cells * cell) <= tolerance * voltage:
            return f"{cells}S {name} ({cells} × {cell:g} V)"
    return None


# ---------------------------------------------------------------------------
# Reference tables shared by several pages
# ---------------------------------------------------------------------------

_E_SERIES_TABLE = Reference(
    title="Standard resistor values",
    columns=("Series", "Tolerance it was drawn for", "Values in one decade"),
    rows=[
        ("E6", "±20%", "1.0 1.5 2.2 3.3 4.7 6.8"),
        ("E12", "±10%", "1.0 1.2 1.5 1.8 2.2 2.7 3.3 3.9 4.7 5.6 6.8 8.2"),
        ("E24", "±5%", "E12 plus 1.1 1.3 1.6 2.0 2.4 3.0 3.6 4.3 5.1 6.2 7.5 9.1"),
        ("E96", "±1%", "96 values per decade, 2.3% apart"),
    ],
    note="IEC 60063 preferred values. Each row repeats every decade, so 4.7 "
         "means 0.47 Ω, 4.7 Ω, 47 Ω, 470 Ω, 4.7 kΩ and so on. The steps are "
         "geometric and sized so that consecutive parts at that tolerance just "
         "touch - which is why 'nearest value' means nearest ratio, not nearest "
         "difference.",
)

_POWER_RATING_TABLE = Reference(
    title="Resistor power ratings",
    columns=("Rating", "Typical package", "Run continuously at (50% derate)"),
    rows=[
        ("1/16 W (0.0625 W)", "0402 chip", "31 mW"),
        ("1/10 W (0.1 W)", "0603 chip", "50 mW"),
        ("1/8 W (0.125 W)", "0805 chip, small axial", "63 mW"),
        ("1/4 W (0.25 W)", "1206 chip, standard axial", "125 mW"),
        ("1/2 W (0.5 W)", "larger axial", "250 mW"),
        ("1 W", "axial, metal film / metal oxide", "500 mW"),
        ("2-5 W", "wirewound, ceramic body", "1-2.5 W"),
    ],
    note="The rating is the power at which the part reaches its maximum body "
         "temperature in free air at 25 °C - it is a destruction limit, not an "
         "operating point. Design to about half of it, less again inside a "
         "sealed box or next to other hot parts. 1/4 W is the default part in "
         "most parts bins and is the one most often exceeded by accident.",
)

_WIRE_TABLE = Reference(
    title="Copper wire by gauge",
    columns=("AWG", "Area [mm²]", "Resistance [mΩ/m]", "Free air [A]"),
    rows=[
        ("8", "8.37", "2.06", "73"),
        ("10", "5.26", "3.28", "55"),
        ("12", "3.31", "5.21", "41"),
        ("14", "2.08", "8.29", "32"),
        ("16", "1.31", "13.2", "22"),
        ("18", "0.823", "20.9", "16"),
        ("20", "0.518", "33.3", "11"),
        ("22", "0.326", "53.0", "7"),
        ("24", "0.205", "84.2", "3.5"),
    ],
    note="Area and resistance are exact for solid annealed copper at 20 °C "
         "(ρ = 1.724e-8 Ω·m) and are what stranded wire of the same gauge "
         "measures to within a few percent. The current column is a single "
         "insulated conductor in free air: inside a loom, a conduit or a wall "
         "it can be less than half that, and copper resistance itself rises "
         "about 0.4% per °C, so a hot wire loses more than a cold one.",
)


# ---------------------------------------------------------------------------
# Shared page furniture for the pages that stay imperative
# ---------------------------------------------------------------------------


class _Graph(NamedTuple):
    """One curve for `_explore`, already evaluated."""

    title: str
    x_label: str
    y_label: str
    xs: Sequence[float]
    ys: Sequence[float]
    point_x: Optional[float] = None
    point_y: Optional[float] = None


def _reference_table(table: Reference) -> None:
    header = "| " + " | ".join(table.columns) + " |"
    divider = "| " + " | ".join("---" for _ in table.columns) + " |"
    body = ["| " + " | ".join(str(cell) for cell in row) + " |"
            for row in table.rows]
    st.markdown("\n".join([header, divider] + body))
    if table.note:
        st.caption(table.note)


def _related_buttons(prefix: str, entries) -> None:
    """One-click jumps, addressed by slug the way utils/render.py does it."""
    st.markdown('<div class="a-note">These answer the question this page '
                'raises next.</div>', unsafe_allow_html=True)
    per_row = 3
    for start in range(0, len(entries), per_row):
        chunk = entries[start:start + per_row]
        for column, (slug, label) in zip(st.columns(per_row), chunk):
            with column:
                if st.button(label, key=f"rel_{prefix}_{slug}",
                             use_container_width=True):
                    navigate.request(slug)
                    st.rerun()


def _explore(prefix: str, graphs=(), tables=(), related=()) -> None:
    """The tabbed analysis block for the imperative pages.

    utils/render.py assembles this from a Calculator spec. The pages here that
    need imperative control assemble the same pieces by hand, so choosing the
    escape hatch never costs the reader a graph or a reference table.
    """
    labels, drawers = [], []
    for graph in graphs:
        labels.append(graph.title.split(" (")[0][:34])
        drawers.append(("graph", graph))
    for table in tables:
        labels.append(table.title[:34])
        drawers.append(("table", table))
    if related:
        labels.append("Related")
        drawers.append(("related", related))
    if not labels:
        return

    appearance = settings.load().get("appearance", "Follow system")
    st.markdown('<div class="a-label">Explore</div>', unsafe_allow_html=True)
    for tab, (kind, payload) in zip(st.tabs(labels), drawers):
        with tab:
            if kind == "graph":
                charts.sweep_chart(payload.xs, payload.ys,
                                   x_label=payload.x_label,
                                   y_label=payload.y_label,
                                   title=payload.title,
                                   point_x=payload.point_x,
                                   point_y=payload.point_y,
                                   appearance=appearance)
            elif kind == "table":
                _reference_table(payload)
            else:
                _related_buttons(prefix, payload)


_LEVELS = {"info": st.info, "warning": st.warning, "danger": st.error}


def _show_checks(verdicts) -> None:
    """Draw the regime warnings an imperative page worked out for itself."""
    for verdict in verdicts:
        if verdict:
            level, message = verdict
            _LEVELS.get(level, st.info)(message)


def _rating_check(dissipation: float, where: str = "This resistor"):
    """Warn when a part is being asked to dissipate more than a 1/4 W body."""
    if not math.isfinite(dissipation) or dissipation <= 0.25:
        return None
    rating = smallest_power_rating(dissipation)
    if rating is None:
        return ("warning",
                f"{where} dissipates {dissipation:.4g} W. That is past a 5 W "
                "wirewound part once you derate by half - at this power the "
                "answer is a different topology (a switching regulator, a "
                "current source, a heatsinked load), not a bigger resistor.")
    return ("warning",
            f"{where} dissipates {dissipation:.4g} W, so the usual 1/4 W part "
            f"will cook. Fit at least a {rating:g} W resistor - that is the "
            "smallest standard rating with the customary 2x derating - and "
            "give it air.")


def _current_check(current: float):
    """Point at the conductor once the current stops being a signal current."""
    if not math.isfinite(current) or abs(current) < 10.0:
        return None
    amps = abs(current)
    gauge = next((g for g in sorted(_FREE_AIR_AMPS)
                  if _FREE_AIR_AMPS[g] >= amps), None)
    need = (f"about {gauge} AWG or thicker" if gauge is not None
            else "heavier than 8 AWG - think busbar or multiple conductors")
    return ("info",
            f"{amps:.4g} A is a power current, not a signal current. In free "
            f"air that wants {need}, and connector and solder-joint resistance "
            "now matters as much as the wire does.")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def _resistor_inputs(prefix: str, default: float = 100.0):
    count = st.slider("Number of resistors", min_value=2, max_value=8, value=3,
                      key=f"{prefix}_n")
    values = []
    columns = st.columns(min(count, 4))
    for i in range(count):
        with columns[i % len(columns)]:
            values.append(ui.number(f"R{i + 1}", "Ω", f"{prefix}_r{i}",
                                    default * (i + 1), min_value=0.0))
    return values


# --- Ohm's law -------------------------------------------------------------

_OHM_RELATED = [
    ("elec.power", "Electrical power"),
    ("elec.series", "Resistors in series"),
    ("elec.parallel", "Resistors in parallel"),
    ("elec.voltage_drop", "Wire voltage drop"),
    ("elec.battery_energy", "Battery energy"),
]

_LED_TABLE = Reference(
    title="LED forward voltage",
    columns=("Colour / type", "Forward voltage at 20 mA [V]"),
    rows=[
        ("Infrared (GaAs)", "1.2 - 1.6"),
        ("Red", "1.8 - 2.2"),
        ("Amber / yellow", "2.0 - 2.2"),
        ("Green (older GaP)", "2.0 - 2.4"),
        ("Green, blue, white (InGaN)", "2.8 - 3.4"),
        ("Ultraviolet", "3.1 - 4.0"),
    ],
    note="Indicator LEDs, at the 10-20 mA they are usually run at. Forward "
         "voltage rises with current and falls as the die heats, which is why "
         "an LED must never be driven from a voltage source without a resistor "
         "or a current regulator: the drop sets itself, and the current runs "
         "away.",
)


def _ohm_graphs(solve_for: str, voltage, current, resistance, result):
    """Two sweeps for whichever quantity is being solved for."""
    def span(value, lo_factor=0.2, hi_factor=2.0):
        value = abs(float(value)) or 1.0
        return np.linspace(value * lo_factor, value * hi_factor, 200)

    if solve_for == "Voltage V":
        rs, is_ = span(resistance), span(current)
        return [
            _Graph("Voltage vs resistance", "Resistance R [Ω]", "Voltage V [V]",
                   rs, current * rs, resistance, result),
            _Graph("Voltage vs current", "Current I [A]", "Voltage V [V]",
                   is_, is_ * resistance, current, result),
            _Graph("Power dissipated vs current", "Current I [A]", "Power P [W]",
                   is_, is_ ** 2 * resistance, current,
                   power_i2r(current, resistance)),
        ]
    if solve_for == "Current I":
        rs, vs = span(resistance), span(voltage)
        return [
            _Graph("Current vs resistance", "Resistance R [Ω]", "Current I [A]",
                   rs, voltage / rs, resistance, result),
            _Graph("Current vs voltage", "Voltage V [V]", "Current I [A]",
                   vs, vs / resistance, voltage, result),
            _Graph("Power dissipated vs voltage", "Voltage V [V]",
                   "Power P [W]", vs, vs ** 2 / resistance, voltage,
                   power_v2r(voltage, resistance)),
        ]
    is_, vs = span(current), span(voltage)
    return [
        _Graph("Resistance vs current", "Current I [A]", "Resistance R [Ω]",
               is_, voltage / is_, current, result),
        _Graph("Resistance vs voltage", "Voltage V [V]", "Resistance R [Ω]",
               vs, vs / current, voltage, result),
        _Graph("Power dissipated vs voltage", "Voltage V [V]", "Power P [W]",
               vs, vs * current, voltage, power_vi(voltage, current)),
    ]


def render_ohms_law() -> None:
    p = "elec_ohm"
    solve_for = st.session_state.get(f"{p}_solve", "Voltage V")
    symbol = {"Voltage V": r"V = I\,R", "Current I": r"I = \frac{V}{R}",
              "Resistance R": r"R = \frac{V}{I}"}[solve_for]
    ui.page_header(
        "Ohm's law",
        symbol,
        "Voltage is what pushes, current is what flows, resistance is what "
        "opposes - and in a resistive circuit the three are locked together by "
        "one product. Pick which quantity you want and enter the other two. "
        "The relationship is <b>linear</b>, which is exactly what makes a "
        "resistor useful and exactly what a diode, an LED or a motor does not "
        "obey.",
        p,
    )
    solve_for = st.radio("Solve for", ["Voltage V", "Current I", "Resistance R"],
                         key=f"{p}_solve", horizontal=True)

    c1, c2 = st.columns(2)
    voltage = current = resistance = None
    if solve_for == "Voltage V":
        with c1:
            current = ui.number("Current I", "A", f"{p}_i", 0.5)
        with c2:
            resistance = ui.number("Resistance R", "Ω", f"{p}_r", 220.0,
                                   min_value=0.0)
        value = ui.compute(lambda: ohms_law_voltage(current, resistance))
        unit, label = "V", "Voltage V"
        dissipation = power_i2r(current, resistance)
        extras = ([("Power dissipated", dissipation, "W"),
                   ("Energy if held for an hour", dissipation, "Wh"),
                   ("In millivolts", value * 1000.0, "mV"),
                   ("Conductance G = 1/R", 1000.0 / resistance, "mS")]
                  if value is not None and resistance > 0 else
                  [("Power dissipated", dissipation, "W")])
        if value is not None:
            voltage = value
    elif solve_for == "Current I":
        with c1:
            voltage = ui.number("Voltage V", "V", f"{p}_v", 12.0)
        with c2:
            resistance = ui.number("Resistance R", "Ω", f"{p}_r", 220.0,
                                   min_value=0.0)
        value = ui.compute(lambda: ohms_law_current(voltage, resistance))
        unit, label = "A", "Current I"
        dissipation = power_v2r(voltage, resistance) if resistance > 0 else 0.0
        extras = ([("In milliamps", value * 1000.0, "mA"),
                   ("Power dissipated", dissipation, "W"),
                   ("Charge moved in a minute", value * 60.0, "coulomb"),
                   ("Nearest standard resistor (E24)",
                    nearest_standard_resistor(resistance), "Ω")]
                  if value is not None else [])
        if value is not None:
            current = value
    else:
        with c1:
            voltage = ui.number("Voltage V", "V", f"{p}_v", 12.0)
        with c2:
            current = ui.number("Current I", "A", f"{p}_i", 0.5)
        value = ui.compute(lambda: ohms_law_resistance(voltage, current))
        unit, label = "Ω", "Resistance R"
        dissipation = power_vi(voltage, current)
        # The nearest catalogue value is the number you actually order, and the
        # error it introduces is the number that decides whether you can.
        nearest = (nearest_standard_resistor(abs(value))
                   if value is not None and value != 0 else float("nan"))
        extras = ([("Power dissipated", dissipation, "W"),
                   ("In kilohms", value / 1000.0, "kΩ"),
                   ("Nearest standard resistor (E24)", nearest, "Ω"),
                   ("Error if you fit that one", 100.0 * (nearest - abs(value))
                    / abs(value), "%")]
                  if value is not None and value != 0 else [])
        if value is not None:
            resistance = value

    if value is not None:
        ui.result(label, value, unit, secondary=extras)
        _show_checks([
            _rating_check(dissipation),
            _current_check(current if current is not None else 0.0),
            ("warning",
             f"{resistance:.4g} Ω is the same order as the wiring: a soldered "
             "joint, a connector pair and a short lead are together tens of "
             "milliohms, so a large part of your 'resistor' is the circuit "
             "around it. Measure four-wire, or use a shunt designed for it.")
            if resistance is not None and 0 < resistance < 1.0 else None,
        ])

    ui.assumptions([
        "Ohmic (linear) component: resistance is constant and independent of "
        "voltage. Diodes, LEDs, motors and semiconductors are NOT ohmic - an "
        "LED fed 'the right voltage' draws whatever current it likes and dies.",
        "DC, or instantaneous values. AC circuits with capacitance or "
        "inductance need impedance, not plain resistance, and then current and "
        "voltage are no longer in phase.",
        "Resistance rises with temperature in metals - about 0.4% per °C for "
        "copper - so a resistor running hot is not quite the resistor on the "
        "label, and a hot motor winding draws less current than a cold one.",
        "Real resistors are 1% or 5% parts from the E24/E96 series. A computed "
        "value of 137 Ω is not a thing you can buy; the nearest standard value "
        "above is what you will actually fit.",
        "The resistor has to survive the power as well as carry the current. "
        "P = I²R sets the package size, and the usual practice is to run at "
        "half the rating or less.",
        "No source impedance: a real supply, a battery in particular, sags "
        "under load, so the voltage you set is not the voltage the resistor "
        "sees once current flows.",
    ])
    _explore(p,
             graphs=(_ohm_graphs(solve_for, voltage, current, resistance, value)
                     if value is not None and voltage is not None
                     and current is not None and resistance is not None
                     else ()),
             tables=(_E_SERIES_TABLE, _POWER_RATING_TABLE, _LED_TABLE),
             related=_OHM_RELATED)
    ui.reference(
        variables=[
            ("$V$", "Voltage (potential difference)", "V"),
            ("$I$", "Current", "A"),
            ("$R$", "Resistance", "Ω"),
            ("$P$", "Power dissipated, $P = I^2R$", "W"),
            ("$G$", "Conductance, $G = 1/R$", "S"),
        ],
        example="Sizing an LED series resistor. To run a red LED at 20 mA from "
                "5 V with a 2 V forward drop, the resistor must take the other "
                "3 V: R = 3 / 0.02 = 150 Ω exactly, which happens to be an E24 "
                "value, dissipating 3 × 0.02 = 60 mW. A 1/4 W part is fine. "
                "Drop the supply to 3.3 V and the resistor takes 1.3 V, so "
                "R = 65 Ω - fit 68 Ω and accept 19 mA.",
    )


# --- Electrical power ------------------------------------------------------


def _power_form(i) -> float:
    """Dispatch to whichever of the three identical laws the user picked."""
    if i.form == "P = I² × R":
        return power_i2r(i.i, i.r_wire)
    if i.form == "P = V² / R":
        return power_v2r(i.v, i.r_load)
    return power_vi(i.v, i.i)


def _power_uses_resistor(i) -> bool:
    return i.form in ("P = I² × R", "P = V² / R")


_POWER = Calculator(
    slug="elec.power",
    name="Electrical power",
    latex=r"P = V\,I = I^{2}R = \frac{V^{2}}{R}",
    explanation=(
        "Three forms of the same law, obtained by substituting Ohm's law into "
        "P = V × I. They are <b>not</b> interchangeable in practice, because "
        "each one is stated in terms of the quantity you can actually measure: "
        "use <code>I²R</code> when you care about heat in a wire or a motor "
        "winding, because that is where the loss physically happens and current "
        "is what you can clamp a meter around."
    ),
    inputs=[
        Field("form", "Form", "", 0, kind="choice",
              options=["P = V × I", "P = I² × R", "P = V² / R"],
              help="Which two quantities you know."),
        Field("v", "Voltage V", "V", 22.2,
              help="22.2 V is a 6S lithium pack at nominal charge."),
        Field("i", "Current I", "A", 60.0),
        Field("r_wire", "Wire / winding resistance R", "Ω", 0.005, min=0.0,
              help="Used by the I²R form. 5 milliohm is a realistic figure for "
                   "a short run of heavy drone wiring plus its connectors."),
        Field("r_load", "Load resistance R", "Ω", 10.0, min=0.0,
              help="Used by the V²/R form: the resistance the supply voltage "
                   "sits across."),
    ],
    compute=_power_form,
    result=Output("Power P", "W"),
    secondary=[
        Secondary("In kilowatts", "kW", lambda i, r: r / 1000.0),
        Secondary("In horsepower (mechanical)", "hp",
                  lambda i, r: r / 745.6998715822702),
        Secondary("Energy in one hour", "Wh", lambda i, r: r),
        Secondary("Energy over a 10-minute flight", "Wh", lambda i, r: r / 6.0),
        Secondary("Current this is at the entered voltage", "A",
                  lambda i, r: r / i.v),
        Secondary("Heat in the wiring at this current", "W",
                  lambda i, r: power_i2r(i.i, i.r_wire)),
    ],
    checks=[
        Check(lambda i, r: _rating_check(r, "The resistor")
              if _power_uses_resistor(i) else None),
        Check(lambda i, r: _current_check(i.i)
              if i.form in ("P = V × I", "P = I² × R") else None),
        Check(lambda i, r: ("warning",
                            f"{i.r_load:.4g} Ω across {i.v:.4g} V is a short "
                            "circuit, not a load - and the formula happily "
                            f"reports {r:,.0f} W because it has no idea the "
                            "supply cannot deliver it. Real sources sag, and "
                            "the current is then set by the source, not by "
                            "this resistance.")
              if i.form == "P = V² / R" and 0 < i.r_load < 0.1 else None),
    ],
    assumptions=[
        "All three forms are exactly equivalent FOR AN OHMIC COMPONENT with "
        "consistent V, I and R. They give different answers here on purpose: "
        "the three fields are three independent scenarios, not one circuit.",
        "DC or instantaneous power. Average AC power is V_rms × I_rms × cos φ - "
        "the power factor - and a motor drive or a switching supply can have a "
        "poor one, so volt-amps and watts stop being the same number.",
        "P = I²R applies to the resistance where the loss OCCURS - wire, "
        "connector, brush or winding resistance - not the load's nominal "
        "resistance. Putting the load resistance in here is the classic error.",
        "All of the power in a resistance becomes heat. Something has to carry "
        "it away, and the rating on a resistor assumes still air at 25 °C.",
        "Conductor resistance rises roughly 0.4% per °C, so I²R loss grows as "
        "the wire warms: a thermal runaway is possible in a badly sized loom.",
        "Electrical power in is not mechanical power out. A motor's shaft power "
        "is this number times its efficiency, typically 0.7-0.9 at its best "
        "point and far worse away from it.",
    ],
    graphs=[
        Sweep(over="i", y_label="Power P [W]", hi_factor=1.6, hi_min=1.0,
              title="Power vs current"),
        Sweep(over="v", y_label="Power P [W]", hi_factor=1.6, hi_min=1.0,
              title="Power vs voltage"),
        Sweep(over="r_wire", y_label="Power P [W]", hi_factor=2.0,
              hi_min=0.001, title="Power vs wire resistance"),
        Sweep(over="r_load", y_label="Power P [W]", lo_factor=0.2,
              hi_factor=2.0, hi_min=1.0, title="Power vs load resistance"),
    ],
    references=[_POWER_RATING_TABLE, _WIRE_TABLE],
    related=["elec.ohms_law", "elec.voltage_drop", "elec.battery_energy",
             "drone.power", "mech.power"],
    variables=[
        ("$P$", "Power", "W"),
        ("$V$", "Voltage", "V"),
        ("$I$", "Current", "A"),
        ("$R$", "Resistance where the loss occurs", "Ω"),
    ],
    example=(
        "Wiring loss in a drone. 60 A through 5 milliohm of wire and connectors "
        "burns 18 W as heat - lost flight time, a hot connector and a real fire "
        "risk. Halving the resistance (one gauge thicker, or a shorter run) "
        "halves the loss; halving the current quarters it, which is the real "
        "argument for a higher-voltage pack at the same power."
    ),
    keywords=("power", "watts", "joule heating", "i2r", "dissipation", "loss",
              "horsepower"),
)


# --- Resistors in series ---------------------------------------------------

_SERIES_RELATED = [
    ("elec.parallel", "Resistors in parallel"),
    ("elec.ohms_law", "Ohm's law"),
    ("elec.power", "Electrical power"),
    ("elec.voltage_drop", "Wire voltage drop"),
]


def render_series() -> None:
    p = "elec_series"
    ui.page_header(
        "Resistors in series",
        r"R_{total} = R_1 + R_2 + \cdots + R_n",
        "In series the same current flows through every resistor and the "
        "voltages add up, so the resistances add directly. The total is always "
        "larger than the largest single resistor - and because the current is "
        "shared, each resistor takes a share of the voltage <b>in proportion to "
        "its own value</b>. That is the voltage divider, and it is the reason "
        "this arrangement is used far more often for scaling a signal than for "
        "making an awkward resistance.",
        p,
    )
    values = _resistor_inputs(p, default=100.0)
    supply = ui.number("Supply voltage (optional)", "V", f"{p}_v", 12.0)
    total = ui.compute(lambda: series_resistance(values))

    if total is not None:
        current = supply / total if total > 0 else float("nan")
        powers = [current ** 2 * r for r in values]
        ui.result(
            "Total resistance", total, "Ω",
            secondary=[
                ("Largest single resistor", max(values), "Ω"),
                ("Current from the supply", current, "A"),
                ("Total power dissipated", supply * current, "W"),
                ("Nearest standard value (E24)",
                 nearest_standard_resistor(total) if total > 0 else float("nan"),
                 "Ω"),
                ("Hottest resistor takes", max(powers) if powers else 0.0, "W"),
                ("Divider ratio of R1", values[0] / total if total else 0.0, "-"),
            ],
        )
        st.caption("Voltage across each resistor (a voltage divider): " +
                   ",  ".join(f"R{i + 1} = {supply * r / total:.3g} V"
                              for i, r in enumerate(values)))
        hottest = int(np.argmax(powers)) if powers else 0
        _show_checks([
            _rating_check(max(powers) if powers else 0.0,
                          f"R{hottest + 1} (the largest resistor)"),
            _current_check(current),
            ("info",
             "Every resistor here is the same value, so the string is just "
             f"n × R and each one takes exactly {supply / len(values):.3g} V. "
             "That is the cheapest way to get a precise ratio: matched parts "
             "drift together.")
            if len(set(values)) == 1 and len(values) > 1 else None,
        ])

    ui.assumptions([
        "Ideal resistors: tolerance, temperature drift and lead resistance are "
        "ignored. Real parts are 1% or 5%, and the tolerances add in the same "
        "way the values do - three 5% parts give a total that is 5% out, not "
        "15%, but a divider RATIO can be out by nearly the sum of the two.",
        "The same current flows through all of them - that is the definition of "
        "a series connection. If anything else is connected to a mid-point, "
        "that is no longer true and the divider maths changes.",
        "A divider that feeds a real input is loaded by it. The rule of thumb "
        "is to make the divider current at least ten times the current the load "
        "takes, or the output sags below the ratio you designed.",
        "Each resistor must dissipate its own share of the power, and in a "
        "series string the LARGEST resistor gets the most - it has the same "
        "current and the biggest voltage across it.",
        "Low-value strings are dominated by what you did not model: a solder "
        "joint, a connector or 10 cm of 22 AWG wire is tens of milliohms.",
        "This is exact for DC. At high frequency every resistor has series "
        "inductance and parallel capacitance, and a long string stops behaving "
        "like a single resistance.",
    ])

    if total is not None and total > 0:
        r1 = values[0]
        r1s = np.linspace(max(r1 * 0.05, 1e-6), r1 * 2.5, 200)
        rest = total - r1
        totals = r1s + rest
        supplies = np.linspace(0.0, max(abs(supply) * 2.0, 1.0), 200)
        graphs = [
            _Graph("Total resistance vs R1", "R1 [Ω]", "Total resistance [Ω]",
                   r1s, totals, r1, total),
            _Graph("Voltage across R1 vs R1", "R1 [Ω]", "Voltage across R1 [V]",
                   r1s, supply * r1s / totals, r1, supply * r1 / total),
            _Graph("Supply current vs supply voltage", "Supply voltage [V]",
                   "Current [A]", supplies, supplies / total, supply,
                   supply / total),
        ]
    else:
        graphs = ()
    _explore(p, graphs=graphs,
             tables=(_E_SERIES_TABLE, _POWER_RATING_TABLE),
             related=_SERIES_RELATED)

    ui.reference(
        variables=[
            ("$R_{total}$", "Equivalent resistance of the string", "Ω"),
            ("$R_i$", "Each individual resistance", "Ω"),
            ("$V_i$", "Voltage across resistor i, $V R_i / R_{total}$", "V"),
            ("$I$", "The single current through all of them", "A"),
        ],
        example="Voltage dividers for sensor scaling. To read a 22.2 V battery "
                "with a 3.3 V microcontroller input you need to divide by at "
                "least 6.7, so a 10 kΩ over 2 kΩ pair gives 22.2 × 2/12 = "
                "3.7 V - still too high, whereas 47 kΩ over 8.2 kΩ gives "
                "22.2 × 8.2/55.2 = 3.30 V. That string draws only 0.4 mA and "
                "wastes 9 mW, which matters when it sits across the pack for "
                "the whole flight.",
    )


# --- Resistors in parallel -------------------------------------------------

_PARALLEL_RELATED = [
    ("elec.series", "Resistors in series"),
    ("elec.ohms_law", "Ohm's law"),
    ("elec.power", "Electrical power"),
    ("elec.voltage_drop", "Wire voltage drop"),
]


def render_parallel() -> None:
    p = "elec_parallel"
    ui.page_header(
        "Resistors in parallel",
        r"\frac{1}{R_{total}} = \frac{1}{R_1} + \frac{1}{R_2} + \cdots + "
        r"\frac{1}{R_n}",
        "In parallel every resistor sees the same voltage and the currents add, "
        "so it is the <b>conductances</b> that add. The total is always SMALLER "
        "than the smallest single resistor - adding a path can only make it "
        "easier for current to flow. The practical consequence is that a "
        "parallel bank is dominated by its smallest member, and that putting "
        "parts in parallel is how you get a resistance, a power rating or a "
        "current capability that no single part can give you.",
        p,
    )
    values = _resistor_inputs(p, default=100.0)
    supply = ui.number("Supply voltage (optional)", "V", f"{p}_v", 12.0)
    total = ui.compute(lambda: parallel_resistance(values))

    if total is not None:
        currents = [supply / r for r in values]
        powers = [supply ** 2 / r for r in values]
        ui.result(
            "Total resistance", total, "Ω",
            secondary=[
                ("Smallest single resistor", min(values), "Ω"),
                ("Total current from the supply", supply / total, "A"),
                ("Total power dissipated", supply ** 2 / total, "W"),
                ("Nearest standard value (E24)",
                 nearest_standard_resistor(total), "Ω"),
                ("Hottest resistor takes", max(powers), "W"),
                ("Share of the current in R1",
                 100.0 * currents[0] / sum(currents) if sum(currents) else 0.0,
                 "%"),
            ],
        )
        st.caption("Current through each resistor: " +
                   ",  ".join(f"R{i + 1} = {supply / r:.3g} A"
                              for i, r in enumerate(values)))
        hottest = int(np.argmax(powers))
        _show_checks([
            _rating_check(max(powers), f"R{hottest + 1} (the smallest resistor)"),
            _current_check(supply / total),
            ("info",
             f"All {len(values)} resistors are equal, so the total is exactly "
             f"R/n = {values[0]:.4g}/{len(values)} and each carries the same "
             f"{currents[0]:.3g} A. This is the standard way to build a shunt: "
             "n identical parts share the heat n ways and the tolerances "
             "average out.")
            if len(set(values)) == 1 and len(values) > 1 else None,
        ])

    ui.assumptions([
        "Ideal resistors and ideal (zero-resistance) wiring between them. In a "
        "parallel bank the wiring is in series with each branch, so uneven lead "
        "lengths make the branches share unevenly - which matters most in "
        "exactly the low-resistance banks people build for current sharing.",
        "Every resistor must be greater than zero. A zero-Ω path is a short "
        "circuit: the formula has no meaning and the bank has no resistance.",
        "Two equal resistors in parallel give exactly half the value; n equal "
        "resistors give R/n. Two very unequal ones give almost the smaller one, "
        "so a 1 MΩ across a 100 Ω changes nothing you can measure.",
        "The SMALLEST resistor dissipates the MOST, because they all share the "
        "same voltage - the opposite of a series string. Size the package for "
        "that one.",
        "Parallel parts do not share current perfectly if they are not matched. "
        "For power sharing use identical parts from the same batch, and give "
        "each one its own identical connection.",
        "This is exact for DC. At high frequency the parasitic inductance of "
        "the loop between the parts stops them behaving as one resistance.",
    ])

    if total is not None:
        r1 = values[0]
        r1s = np.linspace(max(r1 * 0.05, 1e-6), r1 * 2.5, 200)
        # 1/R_total = 1/R1 + (1/R_total_now - 1/R1): hold the rest of the bank
        # fixed and vary only R1, which is what the user is actually choosing.
        rest_conductance = sum(1.0 / r for r in values[1:])
        totals = 1.0 / (1.0 / r1s + rest_conductance)
        supplies = np.linspace(0.0, max(abs(supply) * 2.0, 1.0), 200)
        graphs = [
            _Graph("Total resistance vs R1", "R1 [Ω]", "Total resistance [Ω]",
                   r1s, totals, r1, total),
            _Graph("Current through R1 vs R1", "R1 [Ω]", "Current in R1 [A]",
                   r1s, supply / r1s, r1, supply / r1),
            _Graph("Total current vs supply voltage", "Supply voltage [V]",
                   "Total current [A]", supplies, supplies / total, supply,
                   supply / total),
        ]
    else:
        graphs = ()
    _explore(p, graphs=graphs,
             tables=(_E_SERIES_TABLE, _POWER_RATING_TABLE),
             related=_PARALLEL_RELATED)

    ui.reference(
        variables=[
            ("$R_{total}$", "Equivalent resistance", "Ω"),
            ("$R_i$", "Each individual resistance", "Ω"),
            ("$G$", "Conductance $1/R$ - the thing that actually adds", "S"),
            ("$I_i$", "Current in branch i, $V / R_i$", "A"),
        ],
        example="Current sensing and load sharing. Putting shunt resistors in "
                "parallel spreads the heat and lowers the resistance: four "
                "0.02 Ω shunts in parallel give 0.005 Ω, each carries a quarter "
                "of the current and each dissipates a sixteenth of the power a "
                "single 0.005 Ω part would have to. At 60 A that is 18 W total, "
                "4.5 W each - still a serious part, but a buyable one.",
    )


# --- Battery energy --------------------------------------------------------

_CELL_TABLE = Reference(
    title="Cell voltages by chemistry",
    columns=("Chemistry", "Nominal [V]", "Fully charged [V]", "Empty [V]"),
    rows=[
        ("Li-ion (NMC / LCO)", "3.6 - 3.7", "4.2", "3.0"),
        ("Lithium-polymer (LiPo)", "3.7", "4.2", "3.5 resting, 3.0 absolute"),
        ("LiFePO4", "3.2", "3.65", "2.5"),
        ("NiMH", "1.2", "1.4 - 1.45", "1.0"),
        ("NiCd", "1.2", "1.4", "1.0"),
        ("Lead-acid (per cell)", "2.0", "2.4 charging, 2.12 rested", "1.75"),
        ("Alkaline (primary)", "1.5", "1.6", "0.9"),
    ],
    note="Multiply by the cell count for the pack: 3S LiPo is 11.1 V nominal "
         "and 12.6 V charged, 6S is 22.2 V and 25.2 V, and a 12 V lead-acid "
         "battery is six cells reading about 12.7 V rested and full. Nominal "
         "voltage is an average over the discharge, which is why watt-hours "
         "computed from it are an estimate even when the amp-hours are exact.",
)

_ENERGY_DENSITY_TABLE = Reference(
    title="Practical energy density",
    columns=("Chemistry", "Specific energy [Wh/kg]", "Notes"),
    rows=[
        ("Li-ion cylindrical (18650/21700)", "200 - 260",
         "Best mass energy; modest discharge rate"),
        ("Lithium-polymer, high-C hobby pack", "130 - 180",
         "Thick collectors and tabs cost energy to gain current"),
        ("LiFePO4", "90 - 160", "Long cycle life, very tolerant of abuse"),
        ("NiMH", "60 - 120", "Robust, self-discharges, no protection needed"),
        ("Lead-acid", "30 - 50", "Cheap, heavy, hates deep discharge"),
        ("Alkaline (primary)", "100 - 150", "High energy, very low current"),
    ],
    note="Cell-level figures for healthy parts at a moderate rate. A finished "
         "pack loses 10-25% of these to the case, wiring, balance leads and "
         "protection electronics, and everything falls off in the cold. Compare "
         "against roughly 12,000 Wh/kg for petrol to see why electric aircraft "
         "endurance is hard.",
)


def _battery_c_rate(i, r: float) -> float:
    """Discharge rate as a multiple of capacity - 'C' on every pack label."""
    return (i.load / i.voltage) / i.capacity


_BATTERY = Calculator(
    slug="elec.battery_energy",
    name="Battery energy",
    latex=r"E_{Wh} = V \times C_{Ah}",
    explanation=(
        "Charge in amp-hours times voltage gives energy in watt-hours. This is "
        "the one number that can be compared across packs: two batteries with "
        "the same mAh rating but different cell counts hold completely "
        "different amounts of energy, and it is energy - not charge - that "
        "buys you flight time. A 5000 mAh 3S and a 5000 mAh 6S are not the "
        "same battery in any sense that matters."
    ),
    inputs=[
        Field("voltage", "Nominal voltage", "V", 14.8, min=0.0,
              help="Cell count times nominal cell voltage: 4 × 3.7 V here."),
        Field("capacity", "Capacity", "Ah", 5.0, min=0.0,
              help="5000 mAh is 5 Ah. Divide a mAh rating by 1000."),
        Field("load", "Average load power", "W", 100.0, min=0.0,
              help="Average, not peak - the runtime figures use this."),
        Field("dod", "Usable depth of discharge", "%", 80.0, min=0.0, max=100.0,
              help="How much of the pack you are willing to use. 80% is the "
                   "usual limit for lithium if you want the pack to last."),
    ],
    compute=lambda i: battery_energy_wh(i.voltage, i.capacity),
    result=Output("Stored energy", "Wh"),
    secondary=[
        Secondary("In kilojoules", "kJ", lambda i, r: r * 3.6),
        Secondary("Usable at this depth of discharge", "Wh",
                  lambda i, r: r * i.dod / 100.0),
        Secondary("Runtime at this load, full capacity", "h",
                  lambda i, r: r / i.load),
        Secondary("Runtime at this load, usable only", "min",
                  lambda i, r: 60.0 * r * i.dod / 100.0 / i.load),
        Secondary("Average current at this load", "A",
                  lambda i, r: i.load / i.voltage),
        Secondary("Discharge rate", "C", _battery_c_rate),
    ],
    checks=[
        Check(lambda i, r: ("info", f"{i.voltage:g} V is {identify_pack(i.voltage)}.")
              if identify_pack(i.voltage) else None),
        Check(lambda i, r: ("warning",
                            f"That load is {_battery_c_rate(i, r):.1f}C. Above "
                            "about 10C only a pack sold for it will hold its "
                            "voltage: internal resistance turns the difference "
                            "into heat, the pack sags, the capacity you "
                            "actually get falls, and cycle life goes with it.")
              if _battery_c_rate(i, r) > 10.0 else None),
        Check(lambda i, r: ("warning",
                            f"{r:,.0f} Wh is over the 100 Wh airline limit. "
                            "Between 100 and 160 Wh a lithium battery needs "
                            "airline approval and must travel in the cabin; "
                            "above 160 Wh it cannot go on a passenger aircraft "
                            "at all.")
              if r > 100.0 else None),
    ],
    assumptions=[
        "Nominal voltage is an AVERAGE over the discharge, not a constant. A "
        "LiPo cell is 4.2 V charged, 3.7 V nominal and 3.0 V empty, so the real "
        "energy delivered depends on where you stop and on how hard you pull.",
        "The amp-hour rating is measured at a gentle rate, often 0.2C or 1C. "
        "Pull 20C and you will get noticeably fewer amp-hours out - the "
        "Peukert effect - as well as fewer volts.",
        "Capacity falls with age, with cold and with high current. A pack at "
        "0 °C can deliver a third less than the same pack at 25 °C, and it "
        "comes back when it warms up, so a cold-morning test is not a verdict.",
        "Amp-hours measure CHARGE; watt-hours measure ENERGY. Only watt-hours "
        "can be compared across different voltages, and only watt-hours divide "
        "by watts to give a time.",
        "Running a lithium pack to zero destroys it. Depth of discharge above "
        "is the honest number to plan with - 80% is generous for a pack you "
        "want to keep, and aircraft reserves are usually stricter still.",
        "This is stored energy, not delivered energy. Internal resistance, the "
        "ESC, the wiring and the motor each take their cut before anything "
        "turns a propeller.",
    ],
    graphs=[
        Sweep(over="capacity", y_label="Stored energy [Wh]", hi_factor=2.0,
              hi_min=1.0, title="Energy vs capacity"),
        Sweep(over="voltage", y_label="Stored energy [Wh]", hi_factor=2.0,
              hi_min=5.0, title="Energy vs pack voltage"),
    ],
    references=[_CELL_TABLE, _ENERGY_DENSITY_TABLE],
    related=["drone.flight_time", "drone.battery_energy", "elec.power",
             "elec.voltage_drop", "prop.hover_endurance"],
    variables=[
        ("$E_{Wh}$", "Energy stored", "Wh"),
        ("$V$", "Nominal pack voltage", "V"),
        ("$C_{Ah}$", "Capacity (charge)", "Ah"),
        ("$C$", "Discharge rate as a multiple of capacity", "-"),
        ("$DoD$", "Depth of discharge actually used", "%"),
    ],
    example=(
        "Power budget for a rover. A 14.8 V 5 Ah pack holds 74 Wh. At an "
        "average 100 W that is 0.74 h of run time on paper, but planning to use "
        "only 80% of the pack leaves 59.2 Wh and about 36 minutes - and that is "
        "before allowing for cold weather or for the pack ageing. The load is "
        "6.76 A, a gentle 1.35C, so this pack will hold its voltage well."
    ),
    keywords=("battery", "energy", "watt hour", "wh", "amp hour", "ah", "mah",
              "lipo", "capacity", "runtime", "c rate"),
)


# --- Wire voltage drop (new) ----------------------------------------------

_RESISTIVITY = {"Copper": RHO_COPPER_20C, "Aluminium": RHO_ALUMINIUM_20C}


def _drop_area(i) -> float:
    return awg_area_mm2(i.awg)


def _drop(i) -> float:
    return voltage_drop(i.current, i.length, _drop_area(i),
                        _RESISTIVITY[i.material])


def _drop_fraction(i, r: float) -> float:
    """Drop as a percentage of the supply - the number the rules are written in."""
    return 100.0 * r / i.supply


_VOLTAGE_DROP = Calculator(
    slug="elec.voltage_drop",
    name="Wire voltage drop",
    latex=r"\Delta V = I\,\frac{\rho\,(2L)}{A}",
    explanation=(
        "Cable is a resistor you did not mean to fit. The voltage that arrives "
        "at the load is the supply minus I×R of the wiring, and the factor that "
        "catches people is the <b>2</b>: current has to come back, so a 2 m run "
        "is 4 m of conductor. Because the loss is I²R, it is the current - not "
        "the power - that decides how thick the wire has to be, which is the "
        "whole argument for higher-voltage distribution."
    ),
    inputs=[
        Field("current", "Current I", "A", 20.0, min=0.0),
        Field("awg", "Wire gauge", "AWG", 14.0, min=-3.0, max=40.0, step=1.0,
              help="American Wire Gauge. Smaller number means thicker wire; "
                   "three gauges thinner roughly halves the area."),
        Field("length", "Run length (one way)", "m", 2.0, min=0.0,
              help="Battery to load. The return path is counted automatically."),
        Field("supply", "Supply voltage", "V", 24.0, min=0.0,
              help="Only used to express the drop as a percentage."),
        Field("material", "Conductor", "", 0, kind="choice",
              options=["Copper", "Aluminium"]),
    ],
    compute=_drop,
    result=Output("Voltage lost in the cable", "V"),
    secondary=[
        Secondary("Drop as a fraction of the supply", "%", _drop_fraction),
        Secondary("Voltage that reaches the load", "V",
                  lambda i, r: i.supply - r),
        Secondary("Loop resistance (out and back)", "mΩ",
                  lambda i, r: 1000.0 * wire_resistance(
                      2.0 * i.length, _drop_area(i), _RESISTIVITY[i.material])),
        Secondary("Power lost as heat in the cable", "W",
                  lambda i, r: r * i.current),
        Secondary("Conductor cross-section", "mm²", lambda i, r: _drop_area(i)),
        Secondary("Current density", "A/mm²",
                  lambda i, r: i.current / _drop_area(i)),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            f"The cable is eating {_drop_fraction(i, r):.1f}% "
                            "of the supply. The usual wiring guideline is to "
                            "keep a feeder under 3%; past that the load sees a "
                            "noticeably lower voltage, a motor draws more "
                            "current to make the same power, and the loss grows "
                            "again. Go thicker, go shorter, or raise the "
                            "voltage.")
              if 3.0 < _drop_fraction(i, r) <= 10.0 else None),
        Check(lambda i, r: ("warning",
                            f"{_drop_fraction(i, r):.0f}% of the supply is "
                            "being dropped in the wiring, and "
                            f"{r * i.current:.0f} W is being turned into heat "
                            "inside the insulation. This is not a sizing "
                            "question any more - the cable is the load.")
              if _drop_fraction(i, r) > 10.0 else None),
        Check(lambda i, r: ("warning",
                            f"{i.current:.4g} A is more than the "
                            f"{free_air_current_limit(i.awg):g} A that "
                            f"{int(round(i.awg))} AWG is usually taken to carry "
                            "as a single conductor in free air. Bundled or in "
                            "a conduit it is worse. Use thicker wire, or split "
                            "the current across several conductors.")
              if (free_air_current_limit(i.awg) is not None
                  and i.current > free_air_current_limit(i.awg)) else None),
    ],
    assumptions=[
        "DC or low-frequency AC. Above a few kilohertz the skin effect pushes "
        "current to the outside of the conductor and the effective resistance "
        "rises, so a thick wire stops being as good as its area suggests.",
        "Copper at 20 °C unless you pick aluminium. Resistance rises about "
        "0.4% per °C, so a loom at 70 °C has roughly 20% more resistance than "
        "this - and the hotter it gets, the more it loses.",
        "The area is the nominal solid-conductor area for that gauge. Stranded "
        "wire of the same gauge is within a few percent; cheap 'copper-clad "
        "aluminium' sold at a gauge number is not, and can be 60% worse.",
        "Connectors, solder joints, fuses and switches are NOT included and "
        "often dominate a short run. A mediocre connector pair is worth tens of "
        "milliohms - the same as metres of the wire it joins.",
        "The return path is assumed to be the same wire size and length. A "
        "chassis or ground-plane return can be much better, or, if it goes "
        "through a hinge or a bearing, far worse.",
        "Free-air current figures assume one conductor with room to shed heat. "
        "Inside a loom, a conduit or a sealed arm the same wire carries much "
        "less before its insulation is in danger.",
    ],
    graphs=[
        Sweep(over="current", y_label="Voltage drop [V]", hi_factor=2.0,
              hi_min=5.0, title="Drop vs current"),
        Sweep(over="length", y_label="Voltage drop [V]", hi_factor=2.0,
              hi_min=1.0, title="Drop vs run length"),
        Sweep(over="awg", y_label="Voltage drop [V]", lo=6.0, hi_factor=1.8,
              hi_min=24.0, title="Drop vs wire gauge"),
    ],
    references=[_WIRE_TABLE, _POWER_RATING_TABLE],
    related=["elec.power", "elec.ohms_law", "elec.battery_energy",
             "elec.parallel", "drone.power"],
    variables=[
        ("$\\Delta V$", "Voltage lost in the cable", "V"),
        ("$I$", "Current carried", "A"),
        ("$\\rho$", "Resistivity of the conductor", "Ω·m"),
        ("$L$", "One-way run length", "m"),
        ("$A$", "Conductor cross-sectional area", "m²"),
    ],
    example=(
        "Battery to speed controller in a small rover. 20 A down a 2 m run of "
        "14 AWG copper is 4 m of conductor at 8.29 mΩ/m, so 33.1 mΩ and 0.663 V "
        "lost - 2.8% of a 24 V supply, and 13.3 W turned into heat inside the "
        "loom. Going two gauges thicker to 12 AWG cuts both by a third, to "
        "0.417 V and 8.3 W."
    ),
    keywords=("voltage drop", "wire", "cable", "gauge", "awg", "wiring loss",
              "ampacity", "conductor", "copper"),
)


# --- Registry --------------------------------------------------------------

_OHMS_LAW = Calculator(
    slug="elec.ohms_law", name="Ohm's law", latex="", explanation="",
    render=render_ohms_law,
    keywords=("ohm", "ohms law", "voltage", "current", "resistance", "volt",
              "amp", "resistor"),
)

_SERIES_PAGE = Calculator(
    slug="elec.series", name="Resistors in series", latex="", explanation="",
    render=render_series,
    keywords=("series", "resistor", "voltage divider", "divider", "string",
              "add resistance"),
)

_PARALLEL_PAGE = Calculator(
    slug="elec.parallel", name="Resistors in parallel", latex="",
    explanation="", render=render_parallel,
    keywords=("parallel", "resistor", "shunt", "conductance", "current sharing"),
)

CALCULATORS = [_OHMS_LAW, _POWER, _SERIES_PAGE, _PARALLEL_PAGE, _BATTERY,
               _VOLTAGE_DROP]
