"""Electrical and robotics-electronics calculators."""
from __future__ import annotations

import streamlit as st

from utils import ui
from utils import validation as v

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
    """E = V * Ah   [Wh]"""
    voltage = v.non_negative(voltage, "Voltage", "V")
    capacity_ah = v.non_negative(capacity_ah, "Capacity", "Ah")
    return voltage * capacity_ah


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


def render_ohms_law() -> None:
    p = "elec_ohm"
    solve_for = st.session_state.get(f"{p}_solve", "Voltage V")
    symbol = {"Voltage V": r"V = I\,R", "Current I": r"I = \frac{V}{R}",
              "Resistance R": r"R = \frac{V}{I}"}[solve_for]
    ui.page_header(
        "Ohm's law",
        symbol,
        "The relationship between voltage, current and resistance in a resistive "
        "circuit. Pick which quantity you want and enter the other two.",
        p,
    )
    solve_for = st.radio("Solve for", ["Voltage V", "Current I", "Resistance R"],
                         key=f"{p}_solve", horizontal=True)

    c1, c2 = st.columns(2)
    if solve_for == "Voltage V":
        with c1:
            current = ui.number("Current I", "A", f"{p}_i", 0.5)
        with c2:
            resistance = ui.number("Resistance R", "Ω", f"{p}_r", 220.0,
                                   min_value=0.0)
        value = ui.compute(lambda: ohms_law_voltage(current, resistance))
        unit, label = "V", "Voltage V"
        extras = [("Power dissipated", power_i2r(current, resistance), "W"),
                  ("Current", current, "A"), ("Resistance", resistance, "Ω")]
    elif solve_for == "Current I":
        with c1:
            voltage = ui.number("Voltage V", "V", f"{p}_v", 12.0)
        with c2:
            resistance = ui.number("Resistance R", "Ω", f"{p}_r", 220.0,
                                   min_value=0.0)
        value = ui.compute(lambda: ohms_law_current(voltage, resistance))
        unit, label = "A", "Current I"
        extras = ([("In milliamps", value * 1000.0, "mA"),
                   ("Power dissipated", power_v2r(voltage, resistance), "W")]
                  if value is not None else [])
    else:
        with c1:
            voltage = ui.number("Voltage V", "V", f"{p}_v", 12.0)
        with c2:
            current = ui.number("Current I", "A", f"{p}_i", 0.5)
        value = ui.compute(lambda: ohms_law_resistance(voltage, current))
        unit, label = "Ω", "Resistance R"
        extras = [("Power dissipated", power_vi(voltage, current), "W"),
                  ("In kilohms", value / 1000.0, "kΩ")] if value is not None else []

    if value is not None:
        ui.result(label, value, unit, secondary=extras)
    ui.assumptions([
        "Ohmic (linear) component: resistance is constant and independent of "
        "voltage. Diodes, LEDs, motors and semiconductors are NOT ohmic.",
        "DC, or instantaneous values. AC circuits with capacitance or inductance "
        "need impedance, not plain resistance.",
        "Resistance rises with temperature in metals, so a resistor running hot "
        "is not quite the resistor on the label.",
        "This is an exact relationship for an ideal resistor, not an estimate.",
    ])
    ui.reference(
        variables=[
            ("$V$", "Voltage (potential difference)", "V"),
            ("$I$", "Current", "A"),
            ("$R$", "Resistance", "Ω"),
        ],
        example="Sizing an LED series resistor. To run an LED at 20 mA from 5 V "
                "with a 2 V forward drop, the resistor must take 3 V: "
                "R = 3 / 0.02 = 150 Ω, dissipating 60 mW.",
    )


def render_power_forms() -> None:
    p = "elec_power"
    form = st.session_state.get(f"{p}_form", "P = V × I")
    latex = {"P = V × I": r"P = V\,I", "P = I² × R": r"P = I^{2}R",
             "P = V² / R": r"P = \frac{V^{2}}{R}"}[form]
    ui.page_header(
        "Electrical power",
        latex,
        "Three forms of the same law, obtained by substituting Ohm's law into "
        "P = V × I. Use I² R when you care about heat in a wire or a motor "
        "winding, because that is where the loss actually happens.",
        p,
    )
    form = st.radio("Form", ["P = V × I", "P = I² × R", "P = V² / R"],
                    key=f"{p}_form", horizontal=True)

    c1, c2 = st.columns(2)
    if form == "P = V × I":
        with c1:
            voltage = ui.number("Voltage V", "V", f"{p}_v", 22.2)
        with c2:
            current = ui.number("Current I", "A", f"{p}_i", 60.0)
        value = ui.compute(lambda: power_vi(voltage, current))
    elif form == "P = I² × R":
        with c1:
            current = ui.number("Current I", "A", f"{p}_i", 60.0)
        with c2:
            resistance = ui.number("Resistance R", "Ω", f"{p}_r", 0.005,
                                   min_value=0.0,
                                   help="5 milliohm is a realistic figure for a "
                                        "short run of heavy drone wiring.")
        value = ui.compute(lambda: power_i2r(current, resistance))
    else:
        with c1:
            voltage = ui.number("Voltage V", "V", f"{p}_v", 22.2)
        with c2:
            resistance = ui.number("Resistance R", "Ω", f"{p}_r", 10.0,
                                   min_value=0.0)
        value = ui.compute(lambda: power_v2r(voltage, resistance))

    if value is not None:
        ui.result(
            "Power P", value, "W",
            secondary=[
                ("In kilowatts", value / 1000.0, "kW"),
                ("In horsepower (mechanical)", value / 745.6998715822702, "hp"),
                ("Energy in one hour", value, "Wh"),
            ],
        )
    ui.assumptions([
        "All three forms are exactly equivalent for an ohmic component. They give "
        "different answers only if the component is not ohmic.",
        "DC or instantaneous power. Average AC power needs a power factor.",
        "P = I² R applies to the resistance where the loss occurs - wire, "
        "connector or winding resistance, not the load's nominal resistance.",
    ])
    ui.reference(
        variables=[
            ("$P$", "Power", "W"),
            ("$V$", "Voltage", "V"),
            ("$I$", "Current", "A"),
            ("$R$", "Resistance", "Ω"),
        ],
        example="Wiring loss in a drone. 60 A through 5 milliohm of wire and "
                "connectors burns 18 W as heat - lost flight time and a real fire "
                "risk. Halving the resistance halves the loss; halving the current "
                "quarters it.",
    )


def render_series() -> None:
    p = "elec_series"
    ui.page_header(
        "Resistors in series",
        r"R_{total} = R_1 + R_2 + \cdots + R_n",
        "In series the same current flows through every resistor and the voltages "
        "add up, so the resistances add directly. The total is always larger than "
        "the largest single resistor.",
        p,
    )
    values = _resistor_inputs(p, default=100.0)
    total = ui.compute(lambda: series_resistance(values))
    if total is not None:
        supply = ui.number("Supply voltage (optional)", "V", f"{p}_v", 12.0)
        current = supply / total if total > 0 else float("nan")
        ui.result(
            "Total resistance", total, "Ω",
            secondary=[
                ("Largest single resistor", max(values), "Ω"),
                ("Current from the supply", current, "A"),
                ("Total power dissipated", supply * current, "W"),
            ],
        )
        st.caption("Voltage across each resistor (a voltage divider): " +
                   ",  ".join(f"R{i + 1} = {supply * r / total:.3g} V"
                              for i, r in enumerate(values)))
    ui.assumptions([
        "Ideal resistors: tolerance, temperature drift and lead resistance are "
        "ignored. Real resistors are typically 1% or 5% parts.",
        "The same current flows through all of them - that is the definition of a "
        "series connection.",
        "Each resistor must be able to dissipate its share of the power; in a "
        "series string the largest resistor gets the most.",
    ])
    ui.reference(
        variables=[
            ("$R_{total}$", "Equivalent resistance of the string", "Ω"),
            ("$R_i$", "Each individual resistance", "Ω"),
        ],
        example="Voltage dividers for sensor scaling. To read a 22 V battery with "
                "a 3.3 V microcontroller input, a series pair scales the voltage "
                "down - the divider ratio is just each resistor over the total.",
    )


def render_parallel() -> None:
    p = "elec_parallel"
    ui.page_header(
        "Resistors in parallel",
        r"\frac{1}{R_{total}} = \frac{1}{R_1} + \frac{1}{R_2} + \cdots + "
        r"\frac{1}{R_n}",
        "In parallel every resistor sees the same voltage and the currents add, so "
        "the conductances add. The total is always SMALLER than the smallest "
        "single resistor - adding paths makes it easier for current to flow.",
        p,
    )
    values = _resistor_inputs(p, default=100.0)
    total = ui.compute(lambda: parallel_resistance(values))
    if total is not None:
        supply = ui.number("Supply voltage (optional)", "V", f"{p}_v", 12.0)
        ui.result(
            "Total resistance", total, "Ω",
            secondary=[
                ("Smallest single resistor", min(values), "Ω"),
                ("Total current from the supply", supply / total, "A"),
                ("Total power dissipated", supply ** 2 / total, "W"),
            ],
        )
        st.caption("Current through each resistor: " +
                   ",  ".join(f"R{i + 1} = {supply / r:.3g} A"
                              for i, r in enumerate(values)))
    ui.assumptions([
        "Ideal resistors and ideal (zero-resistance) wiring between them.",
        "Every resistor must be greater than zero - a zero-Ω path is a short "
        "circuit and the formula has no meaning.",
        "Two equal resistors in parallel give exactly half the value; n equal "
        "resistors give R/n.",
    ])
    ui.reference(
        variables=[
            ("$R_{total}$", "Equivalent resistance", "Ω"),
            ("$R_i$", "Each individual resistance", "Ω"),
        ],
        example="Current sensing and load sharing. Putting shunt resistors in "
                "parallel spreads the heat and lowers the resistance: four 0.02 "
                "Ω shunts in parallel give 0.005 Ω, and each carries a quarter "
                "of the current.",
    )


def render_battery_energy() -> None:
    p = "elec_batt"
    ui.page_header(
        "Battery energy",
        r"E_{Wh} = V \times C_{Ah}",
        "Charge in amp-hours times voltage gives energy in watt-hours. Two packs "
        "with the same mAh rating but different cell counts hold very different "
        "amounts of energy.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        voltage = ui.number("Nominal voltage", "V", f"{p}_v", 14.8, min_value=0.0)
    with c2:
        capacity = ui.number("Capacity", "Ah", f"{p}_c", 5.0, min_value=0.0)

    value = ui.compute(lambda: battery_energy_wh(voltage, capacity))
    if value is not None:
        ui.result(
            "Stored energy", value, "Wh",
            secondary=[
                ("In kilojoules", value * 3.6, "kJ"),
                ("In joules", value * 3600.0, "J"),
                ("Runtime at 100 W", value / 100.0, "h"),
                ("Charge stored", capacity * 3600.0, "coulomb"),
            ],
        )
    ui.assumptions([
        "Nominal voltage is an average over the discharge. A LiPo cell is 4.2 V "
        "charged, 3.7 V nominal and 3.0 V empty, so real energy delivered depends "
        "on the load.",
        "Assumes a healthy pack at a moderate discharge rate. Capacity falls with "
        "age, cold and high current.",
        "Amp-hours measure charge; watt-hours measure energy. Only watt-hours can "
        "be compared across different voltages.",
    ])
    ui.reference(
        variables=[
            ("$E_{Wh}$", "Energy stored", "Wh"),
            ("$V$", "Nominal voltage", "V"),
            ("$C_{Ah}$", "Capacity (charge)", "Ah"),
        ],
        example="Power budget for a rover. A 14.8 V 5 Ah pack holds 74 Wh. A "
                "rover drawing an average 30 W runs for about 2.5 hours - before "
                "allowing for a reserve and for cold-weather losses.",
    )


CALCULATORS = {
    "Ohm's law": render_ohms_law,
    "Electrical power": render_power_forms,
    "Resistors in series": render_series,
    "Resistors in parallel": render_parallel,
    "Battery energy": render_battery_energy,
}
