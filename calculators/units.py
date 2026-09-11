"""Unit converter.

One generic renderer drives every quantity, so adding a new one means adding a
table to utils/conversions.py and a single line to CALCULATORS below.
Temperature gets its own renderer because it needs offsets, not just scaling.
"""
from __future__ import annotations

from functools import partial

import streamlit as st

from utils import ui
from utils import conversions as cv
from utils.formatting import format_number

_NOTES = {
    "Length": ("Inch, foot and mile are defined exactly in terms of the metre "
               "(1 in = 25.4 mm exactly), so these conversions are exact.",
               "CAD work, wingspans, and reading US datasheets that mix inches "
               "into an otherwise metric design."),
    "Velocity": ("The knot is one nautical mile (exactly 1852 m) per hour. "
                 "Aviation uses knots; scientific work uses m/s.",
                 "Converting an airspeed limit given in knots into the m/s that "
                 "the lift and drag equations need."),
    "Mass": ("The pound here is pound-MASS (0.45359237 kg exactly). Pound-force "
             "is a unit of force and lives in the Force table.",
             "Weighing a payload against a maximum take-off mass quoted in "
             "pounds."),
    "Force": ("Pound-force is the weight of one pound-mass under standard "
              "gravity: 1 lbf = 0.45359237 × 9.80665 = 4.448222 N exactly.",
              "Converting a published thrust figure in lbf into newtons before "
              "computing a thrust-to-weight ratio."),
    "Pressure": ("1 psi = 1 lbf/in². 1 bar = 100,000 Pa exactly, which is close "
                 "to, but not the same as, one standard atmosphere (101,325 Pa).",
                 "Tyre and pneumatic pressures, hydraulic systems, and reading "
                 "material strengths quoted in ksi."),
    "Energy": ("1 Wh = 3600 J exactly. Battery capacity in mAh is CHARGE, not "
               "energy - multiply by voltage first to get watt-hours.",
               "Comparing battery packs, or converting a stored-energy figure "
               "into the joules used in mechanics equations."),
    "Power": ("Two different horsepowers are in use: mechanical (550 ft·lbf/s = "
              "745.700 W) and metric (75 kgf·m/s = 735.499 W). They differ by "
              "1.4%, so always say which one.",
              "Comparing an electric motor rated in watts against an engine "
              "rated in horsepower."),
}


# Sensible starting pair for each quantity, by index into its unit table, so the
# converter opens on a conversion someone would actually make.
_DEFAULT_PAIR = {
    "Length": (2, 5),        # metre -> foot
    "Velocity": (0, 1),      # m/s -> km/h
    "Mass": (1, 2),          # kilogram -> pound-mass
    "Force": (0, 2),         # newton -> pound-force
    "Pressure": (2, 3),      # megapascal -> psi
    "Energy": (2, 0),        # watt-hour -> joule
    "Power": (0, 2),         # watt -> horsepower
}


def _render_table_converter(name: str) -> None:
    table, si_unit = cv.TABLES[name]
    p = f"units_{name.lower()}"
    note, example = _NOTES[name]
    units = list(table.keys())

    ui.page_header(
        f"{name} converter",
        r"\text{value}_{to} = \text{value}_{from} \times "
        r"\frac{\text{factor}_{from}}{\text{factor}_{to}}",
        f"Convert between {name.lower()} units. Every conversion goes through the "
        f"SI base unit ({si_unit}), so no rounding error accumulates between two "
        f"non-SI units. {note}",
        p,
    )
    from_index, to_index = _DEFAULT_PAIR.get(name, (0, min(1, len(units) - 1)))
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        value = ui.number("Value", "", f"{p}_val", 1.0)
    with c2:
        from_unit = st.selectbox("From", units, index=from_index, key=f"{p}_from")
    with c3:
        to_unit = st.selectbox("To", units, index=to_index, key=f"{p}_to")

    result = ui.compute(lambda: cv.convert(value, from_unit, to_unit, table))
    if result is not None:
        ui.result(f"{format_number(value, 6)} {from_unit} equals", result,
                  to_unit.split("(")[-1].rstrip(")"), sig=6)
        rows = ["| Unit | Value |", "| --- | --- |"]
        for unit in units:
            converted = cv.convert(value, from_unit, unit, table)
            marker = " **<-**" if unit == to_unit else ""
            rows.append(f"| {unit} | {format_number(converted, 6)}{marker} |")
        st.markdown('<div class="small-head">Same value in every unit</div>',
                    unsafe_allow_html=True)
        st.markdown("\n".join(rows))

    ui.assumptions([
        "Conversion factors marked exact are exact by international definition; "
        "the rest are given to full double precision.",
        "Converting does not change the physical quantity - only how it is "
        "expressed. Rounding the displayed result does not change the stored "
        "value used in the table above.",
        "Mass and force are different quantities and are kept in separate tables. "
        "Converting kilograms to newtons requires gravity (W = m g), not a unit "
        "conversion.",
    ])
    ui.reference(
        variables=[(f"${si_unit}$", f"SI base unit for {name.lower()} used "
                    f"internally", si_unit)],
        example=example,
    )


def render_temperature() -> None:
    p = "units_temperature"
    ui.page_header(
        "Temperature converter",
        r"K = {}^{\circ}C + 273.15, \qquad "
        r"{}^{\circ}C = ({}^{\circ}F - 32)\times\tfrac{5}{9}",
        "Temperature is the one conversion that needs an offset as well as a "
        "scale factor, because the scales have different zero points. Kelvin and "
        "Celsius share a degree size; Fahrenheit does not.",
        p,
    )
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        value = ui.number("Value", "", f"{p}_val", 15.0)
    with c2:
        from_unit = st.selectbox("From", cv.TEMPERATURE_UNITS, index=0,
                                 key=f"{p}_from")
    with c3:
        to_unit = st.selectbox("To", cv.TEMPERATURE_UNITS, index=2, key=f"{p}_to")

    result = ui.compute(lambda: cv.convert_temperature(value, from_unit, to_unit))
    if result is not None:
        rows = ["| Unit | Value |", "| --- | --- |"]
        for unit in cv.TEMPERATURE_UNITS:
            converted = cv.convert_temperature(value, from_unit, unit)
            marker = " **<-**" if unit == to_unit else ""
            rows.append(f"| {unit} | {format_number(converted, 6)}{marker} |")
        ui.result(f"{format_number(value, 6)} {from_unit} equals", result,
                  to_unit.split("(")[-1].rstrip(")"), sig=6)
        st.markdown('<div class="small-head">Same temperature in every scale</div>',
                    unsafe_allow_html=True)
        st.markdown("\n".join(rows))

    ui.assumptions([
        "Values below absolute zero (-273.15 C, -459.67 F, 0 K) are rejected: they "
        "cannot exist.",
        "These convert a TEMPERATURE. A temperature DIFFERENCE converts "
        "differently - a change of 1 K equals a change of 1 C, but 1.8 F.",
        "Kelvin has no degree symbol and is never written as 'degrees kelvin'.",
    ])
    ui.reference(
        variables=[
            ("$K$", "Absolute temperature (kelvin)", "K"),
            ("$^{\\circ}C$", "Celsius", "°C"),
            ("$^{\\circ}F$", "Fahrenheit", "°F"),
        ],
        example="Air-density calculations. The ideal gas law needs absolute "
                "temperature: a 15 C day is 288.15 K. Using 15 instead of 288.15 "
                "would give a density nearly 20 times too high.",
    )


CALCULATORS = {name: partial(_render_table_converter, name) for name in cv.TABLES}
CALCULATORS["Temperature"] = render_temperature
