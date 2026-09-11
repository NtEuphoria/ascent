"""Unit-conversion tables and helpers.

Each table maps a display label to "how many SI base units is one of these".
Conversion is therefore always: value * factor(from) / factor(to), with the SI
base unit as the single intermediate representation. Nothing converts directly
between two non-SI units, which is where rounding drift usually creeps in.

Factors marked "exact" are exact by international definition.
"""
from __future__ import annotations

from collections import OrderedDict

from .validation import ValidationError, finite

LENGTH = OrderedDict([          # -> metre
    ("Millimetre (mm)", 1e-3),
    ("Centimetre (cm)", 1e-2),
    ("Metre (m)", 1.0),
    ("Kilometre (km)", 1e3),
    ("Inch (in)", 0.0254),                 # exact
    ("Foot (ft)", 0.3048),                 # exact
    ("Mile (mi)", 1609.344),               # exact
])

VELOCITY = OrderedDict([        # -> metre per second
    ("Metre per second (m/s)", 1.0),
    ("Kilometre per hour (km/h)", 1.0 / 3.6),
    ("Mile per hour (mph)", 0.44704),      # exact
    ("Knot (kn)", 1852.0 / 3600.0),        # exact (1 nautical mile = 1852 m)
])

MASS = OrderedDict([            # -> kilogram
    ("Gram (g)", 1e-3),
    ("Kilogram (kg)", 1.0),
    ("Pound-mass (lb)", 0.45359237),       # exact
])

FORCE = OrderedDict([           # -> newton
    ("Newton (N)", 1.0),
    ("Kilonewton (kN)", 1e3),
    ("Pound-force (lbf)", 4.4482216152605),  # exact
])

PRESSURE = OrderedDict([        # -> pascal
    ("Pascal (Pa)", 1.0),
    ("Kilopascal (kPa)", 1e3),
    ("Megapascal (MPa)", 1e6),
    ("Pound per square inch (psi)", 4.4482216152605 / (0.0254 ** 2)),  # exact
    ("Bar (bar)", 1e5),                    # exact
])

ENERGY = OrderedDict([          # -> joule
    ("Joule (J)", 1.0),
    ("Kilojoule (kJ)", 1e3),
    ("Watt-hour (Wh)", 3600.0),            # exact
    ("Kilowatt-hour (kWh)", 3.6e6),        # exact
])

POWER = OrderedDict([           # -> watt
    ("Watt (W)", 1.0),
    ("Kilowatt (kW)", 1e3),
    ("Horsepower, mechanical (hp)", 745.6998715822702),  # 550 ft*lbf/s, exact
    ("Horsepower, metric (PS)", 735.49875),              # 75 kgf*m/s, exact
])

TABLES = OrderedDict([
    ("Length", (LENGTH, "m")),
    ("Velocity", (VELOCITY, "m/s")),
    ("Mass", (MASS, "kg")),
    ("Force", (FORCE, "N")),
    ("Pressure", (PRESSURE, "Pa")),
    ("Energy", (ENERGY, "J")),
    ("Power", (POWER, "W")),
])

TEMPERATURE_UNITS = ["Celsius (°C)", "Fahrenheit (°F)", "Kelvin (K)"]

ABSOLUTE_ZERO = {
    "Celsius (°C)": -273.15,
    "Fahrenheit (°F)": -459.67,
    "Kelvin (K)": 0.0,
}


def convert(value: float, from_unit: str, to_unit: str, table) -> float:
    """Convert between two units of the same physical quantity."""
    value = finite(value, "Value")
    if from_unit not in table:
        raise ValidationError(f"Unknown source unit: {from_unit}")
    if to_unit not in table:
        raise ValidationError(f"Unknown target unit: {to_unit}")
    return value * table[from_unit] / table[to_unit]


def to_kelvin(value: float, unit: str) -> float:
    """Convert a temperature to kelvin, rejecting values below absolute zero."""
    value = finite(value, "Temperature")
    if value < ABSOLUTE_ZERO[unit] - 1e-9:
        raise ValidationError(
            f"{value:g} {unit} is below absolute zero ({ABSOLUTE_ZERO[unit]:g}) "
            "and cannot exist."
        )
    if unit == "Kelvin (K)":
        return value
    if unit == "Celsius (°C)":
        return value + 273.15
    if unit == "Fahrenheit (°F)":
        return (value - 32.0) * 5.0 / 9.0 + 273.15
    raise ValidationError(f"Unknown temperature unit: {unit}")


def from_kelvin(kelvin: float, unit: str) -> float:
    """Convert kelvin to the requested temperature unit."""
    if unit == "Kelvin (K)":
        return kelvin
    if unit == "Celsius (°C)":
        return kelvin - 273.15
    if unit == "Fahrenheit (°F)":
        return (kelvin - 273.15) * 9.0 / 5.0 + 32.0
    raise ValidationError(f"Unknown temperature unit: {unit}")


def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Temperature needs offsets as well as scaling, so it gets its own path."""
    return from_kelvin(to_kelvin(value, from_unit), to_unit)
