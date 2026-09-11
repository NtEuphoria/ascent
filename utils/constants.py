"""Physical constants and reference values.

All values are SI unless the name says otherwise. Every constant carries a note
about where it comes from, because a "standard" value is only standard under a
stated set of conditions.
"""

# --- Exact by definition ---------------------------------------------------
G0 = 9.80665
"""Standard gravity [m/s²]. Exact by definition (CGPM 1901). This is the value
used to convert mass to weight everywhere in this app: W = m * g."""

P_SL = 101325.0
"""ISA sea-level static pressure [Pa]. Exact by definition."""

T_SL_K = 288.15
"""ISA sea-level temperature [K] (15 degrees C). Exact by definition."""

# --- Derived / measured ----------------------------------------------------
RHO_SL = 1.225
"""ISA sea-level air density [kg/m³] at 15 C and 101325 Pa. Real air density
changes with altitude, temperature, humidity and weather."""

A_SL = 340.29
"""Speed of sound at ISA sea level [m/s], a = sqrt(γ * R * T)."""

MU_AIR_SL = 1.789e-5
"""Dynamic viscosity of air at 15 C [Pa·s], from Sutherland's law."""

NU_AIR_SL = MU_AIR_SL / RHO_SL
"""Kinematic viscosity of air at ISA sea level [m²/s]."""

R_AIR = 287.0528
"""Specific gas constant for dry air [J/(kg·K)]."""

GAMMA_AIR = 1.4
"""Ratio of specific heats for air at ordinary temperatures [-]."""

# --- Unit-conversion constants used inside calculators ---------------------
LBF_PER_N = 0.224808943
"""1 newton in pound-force."""

GRAM_FORCE_N = G0 / 1000.0
"""1 gram-force in newtons (0.00980665 N). Drone motor thrust is usually
quoted in grams-force, which is a force, not a mass."""
