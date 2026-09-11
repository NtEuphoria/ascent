"""Constants and reference data.

The ISA page computes atmospheric properties from the model equations rather
than reading them from a copied table, so every number shown is internally
consistent with the others.
"""
from __future__ import annotations

import numpy as np
import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import (A_SL, GAMMA_AIR, G0, MU_AIR_SL, NU_AIR_SL, P_SL,
                             RHO_SL, R_AIR, T_SL_K)
from utils.formatting import format_number
from utils.plotting import PRIMARY, mark_point, new_figure, show

LAPSE_RATE = 0.0065          # K/m, ISA troposphere
TROPOPAUSE_M = 11000.0       # geopotential altitude
STRATOSPHERE_TOP_M = 20000.0
T_TROPOPAUSE = T_SL_K - LAPSE_RATE * TROPOPAUSE_M      # 216.65 K


def isa_properties(altitude_m: float) -> dict:
    """International Standard Atmosphere, 0 to 20 km geopotential altitude.

    Troposphere (0-11 km):   T = T0 - L*h,  p = p0 (T/T0)^(g/(R L))
    Stratosphere (11-20 km): T constant,    p = p11 exp(-g (h-11000)/(R T11))
    """
    altitude_m = v.in_range(altitude_m, "Altitude", 0.0, STRATOSPHERE_TOP_M, "m")
    exponent = G0 / (R_AIR * LAPSE_RATE)
    if altitude_m <= TROPOPAUSE_M:
        temperature = T_SL_K - LAPSE_RATE * altitude_m
        pressure = P_SL * (temperature / T_SL_K) ** exponent
    else:
        p_tropopause = P_SL * (T_TROPOPAUSE / T_SL_K) ** exponent
        temperature = T_TROPOPAUSE
        pressure = p_tropopause * float(np.exp(
            -G0 * (altitude_m - TROPOPAUSE_M) / (R_AIR * T_TROPOPAUSE)))
    density = pressure / (R_AIR * temperature)
    speed_of_sound = float(np.sqrt(GAMMA_AIR * R_AIR * temperature))
    return {
        "temperature_k": temperature,
        "temperature_c": temperature - 273.15,
        "pressure_pa": pressure,
        "density_kgm3": density,
        "speed_of_sound_ms": speed_of_sound,
        "density_ratio": density / RHO_SL,
    }


CONSTANTS = [
    ("Standard gravity", "g", G0, "m/s²",
     "Exact by definition. Used everywhere in this app to convert mass to "
     "weight: W = m g."),
    ("Sea-level air density (ISA)", "rho_0", RHO_SL, "kg/m³",
     "At 15 C and 101325 Pa. Falls with altitude, rises in cold weather, and "
     "drops slightly with humidity."),
    ("Speed of sound at sea level (ISA)", "a_0", A_SL, "m/s",
     "a = sqrt(γ R T). Depends on temperature only, not on pressure or "
     "altitude directly."),
    ("Standard atmospheric pressure", "p_0", P_SL, "Pa",
     "Exact by definition. Equals 1013.25 hPa, 14.696 psi, or 29.92 inHg."),
    ("Sea-level temperature (ISA)", "T_0", T_SL_K, "K",
     "Exact by definition: 15 degrees C."),
    ("Dynamic viscosity of air at 15 C", "μ", MU_AIR_SL, "Pa·s",
     "From Sutherland's law. Depends on temperature, barely on pressure."),
    ("Kinematic viscosity of air at sea level", "ν", NU_AIR_SL, "m²/s",
     "ν = μ / ρ. This is the form used in Re = V L / ν."),
    ("Specific gas constant, dry air", "R", R_AIR, "J/(kg·K)",
     "Used in the ideal gas law p = ρ R T."),
    ("Ratio of specific heats, air", "γ", GAMMA_AIR, "-",
     "1.4 for diatomic gases at ordinary temperatures. Appears in the speed of "
     "sound and in compressible flow."),
]


def render_constants() -> None:
    p = "ref_constants"
    ui.page_header(
        "Engineering constants",
        r"g = 9.80665\ \mathrm{m/s^2}, \quad \rho_0 = 1.225\ \mathrm{kg/m^3},"
        r"\quad p_0 = 101325\ \mathrm{Pa}",
        "The reference values this app uses. Some are exact by definition; the "
        "rest describe a <b>standard</b> atmosphere that the real one rarely "
        "matches exactly.",
        p,
    )
    rows = ["| Constant | Symbol | Value | Unit |", "| --- | --- | --- | --- |"]
    for name, symbol, value, unit, _ in CONSTANTS:
        rows.append(f"| {name} | {symbol} | {format_number(value, 7)} | {unit} |")
    st.markdown("\n".join(rows))

    st.markdown('<div class="small-head">Notes on each value</div>',
                unsafe_allow_html=True)
    notes = "".join(f"<li><b>{symbol}</b> - {note}</li>"
                    for _, symbol, _, _, note in CONSTANTS)
    st.markdown(f'<ul class="tight">{notes}</ul>', unsafe_allow_html=True)

    st.info(
        "**Atmospheric properties are not constants.** Air density, pressure, "
        "temperature and the speed of sound all change with altitude, weather, "
        "season and humidity. A hot day at a high-altitude airfield can easily "
        "give 20% less density than the sea-level standard - which costs you 20% "
        "of your lift and thrust at the same speed and RPM. Use the standard "
        "atmosphere page for altitude effects, and measured data when it matters."
    )

    ui.assumptions([
        "Values marked exact (g, p_0, T_0) are fixed by international agreement; "
        "they are definitions, not measurements.",
        "ISA values describe a modelled average atmosphere, not today's weather.",
        "Air is treated as dry. Humid air is slightly LESS dense than dry air at "
        "the same pressure and temperature, because water vapour is lighter than "
        "the nitrogen and oxygen it displaces.",
    ])
    ui.reference(
        variables=[(f"${symbol}$", name, unit)
                   for name, symbol, _, unit, _ in CONSTANTS],
        example="Every calculator in this app uses these values as defaults. "
                "Changing the air density input on the lift page from 1.225 to "
                "the real value at your flying site is one of the quickest ways "
                "to make a prediction match reality.",
    )


def render_isa() -> None:
    p = "ref_isa"
    ui.page_header(
        "Standard atmosphere (ISA)",
        r"T = T_0 - L h, \qquad p = p_0\left(\frac{T}{T_0}\right)^{g/(RL)},"
        r"\qquad \rho = \frac{p}{R\,T}",
        "The International Standard Atmosphere: an agreed model of how air "
        "properties change with height, used so that aircraft performance figures "
        "can be compared. Valid here from sea level to 20 km.",
        p,
    )
    altitude = ui.number("Altitude (geopotential)", "m", f"{p}_h", 0.0,
                         min_value=0.0, max_value=STRATOSPHERE_TOP_M, step=100.0,
                         help="0 to 20,000 m. Above 11 km the model is isothermal.")

    props = ui.compute(lambda: isa_properties(altitude))
    if props is not None:
        ui.result(
            "Air density at this altitude", props["density_kgm3"], "kg/m³",
            secondary=[
                ("Density relative to sea level", props["density_ratio"], "-"),
                ("Temperature", props["temperature_c"], "°C"),
                ("Pressure", props["pressure_pa"] / 1000.0, "kPa"),
                ("Speed of sound", props["speed_of_sound_ms"], "m/s"),
            ],
        )
        st.caption(
            f"At this altitude, lift and drag at a given true airspeed are "
            f"{props['density_ratio'] * 100:.1f}% of their sea-level values, and a "
            f"propeller or rotor produces correspondingly less thrust."
        )

    if ui.graph_toggle(p):
        altitudes = np.linspace(0.0, STRATOSPHERE_TOP_M, 200)
        densities = [isa_properties(h)["density_kgm3"] for h in altitudes]
        temperatures = [isa_properties(h)["temperature_c"] for h in altitudes]
        fig, (ax_rho, ax_t) = new_figure(rows=2, height=2.4)
        ax_rho.plot(altitudes / 1000.0, densities, color=PRIMARY, linewidth=2)
        if props is not None:
            mark_point(ax_rho, altitude / 1000.0, props["density_kgm3"], "current")
        ax_rho.set_ylabel("Density [kg/m³]")
        ax_rho.set_title("ISA density and temperature vs altitude", fontsize=10,
                         loc="left")
        ax_t.plot(altitudes / 1000.0, temperatures, color=PRIMARY, linewidth=2)
        ax_t.axvline(TROPOPAUSE_M / 1000.0, color="#8a94a6", linestyle=":",
                     linewidth=1)
        ax_t.annotate("tropopause (11 km)", xy=(TROPOPAUSE_M / 1000.0, 0),
                      xytext=(6, 0), textcoords="offset points", fontsize=9,
                      color="#8a94a6")
        ax_t.set_ylabel("Temperature [°C]")
        ax_t.set_xlabel("Altitude [km]")
        show(fig)

    ui.assumptions([
        "ISA is a MODEL of an average atmosphere. Real conditions differ daily; "
        "'ISA +15' means 15 C hotter than standard at that altitude.",
        "Geopotential altitude is used (the altitude the model is defined in). "
        "Below 20 km it differs from geometric altitude by less than 0.4%.",
        "Troposphere lapse rate is 6.5 C per km up to 11 km; above that the model "
        "holds temperature constant at -56.5 C to 20 km.",
        "Dry air, treated as an ideal gas.",
        "Values here are computed from the model equations, so they are "
        "self-consistent - they may differ in the last digit from printed tables "
        "that use geometric altitude.",
    ])
    ui.reference(
        variables=[
            ("$h$", "Geopotential altitude", "m"),
            ("$T$", "Temperature", "K"),
            ("$p$", "Static pressure", "Pa"),
            ("$\\rho$", "Density", "kg/m³"),
            ("$L$", "Lapse rate, 0.0065", "K/m"),
            ("$R$", "Specific gas constant for air, 287.05", "J/(kg·K)"),
        ],
        example="Density altitude and performance. At 2000 m, density is 82% of "
                "sea level, so a drone must spin its propellers faster for the "
                "same thrust and a fixed-wing aircraft must fly faster for the "
                "same lift - which is why hot-and-high take-offs need more runway.",
    )


CALCULATORS = {
    "Engineering constants": render_constants,
    "Standard atmosphere (ISA)": render_isa,
}
