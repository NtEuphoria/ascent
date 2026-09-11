"""Materials and solid-mechanics calculators.

Areas and volumes are entered in whatever unit is convenient and converted to SI
immediately, because 1 MPa = 1 N/mm² is the single most common place to lose a
factor of a million.
"""
from __future__ import annotations

import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import G0

AREA_UNITS = {"mm²": 1e-6, "cm²": 1e-4, "m²": 1.0}
VOLUME_UNITS = {"mm³": 1e-9, "cm³ (= mL)": 1e-6, "litre": 1e-3, "m³": 1.0}

# ---------------------------------------------------------------------------
# Calculations  (all inputs and outputs in SI)
# ---------------------------------------------------------------------------


def normal_stress(force: float, area_m2: float) -> float:
    """σ = F / A   [Pa]. Tension positive, compression negative."""
    force = v.finite(force, "Force", "N")
    area_m2 = v.positive(area_m2, "Cross-sectional area", "m²")
    return force / area_m2


def strain(delta_length: float, original_length: float) -> float:
    """ε = dL / L0   [-] (dimensionless)"""
    delta_length = v.finite(delta_length, "Change in length", "m")
    original_length = v.positive(original_length, "Original length", "m")
    return delta_length / original_length


def youngs_modulus(stress_pa: float, strain_value: float) -> float:
    """E = σ / ε   [Pa]"""
    stress_pa = v.finite(stress_pa, "Stress", "Pa")
    strain_value = v.non_zero(strain_value, "Strain")
    return stress_pa / strain_value


def safety_factor(strength_pa: float, applied_stress_pa: float) -> float:
    """FoS = material strength / applied stress   [-]"""
    strength_pa = v.positive(strength_pa, "Material strength", "Pa")
    applied_stress_pa = v.positive(applied_stress_pa, "Applied stress", "Pa")
    return strength_pa / applied_stress_pa


def density(mass: float, volume_m3: float) -> float:
    """ρ = m / V   [kg/m³]"""
    mass = v.positive(mass, "Mass", "kg")
    volume_m3 = v.positive(volume_m3, "Volume", "m³")
    return mass / volume_m3


def specific_strength(strength_pa: float, density_kgm3: float) -> float:
    """Strength-to-weight: σ / ρ   [N·m/kg = J/kg]"""
    strength_pa = v.positive(strength_pa, "Strength", "Pa")
    density_kgm3 = v.positive(density_kgm3, "Density", "kg/m³")
    return strength_pa / density_kgm3


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


def _area_input(prefix: str, default_mm2: float = 78.54) -> float:
    """Area entry with a unit selector. Returns square metres."""
    unit = st.selectbox("Area unit", list(AREA_UNITS.keys()), index=0,
                        key=f"{prefix}_aunit")
    factor = AREA_UNITS[unit]
    shown_default = default_mm2 * 1e-6 / factor
    value = ui.number("Cross-sectional area A", unit, f"{prefix}_a_{unit}",
                      shown_default, min_value=0.0)
    return value * factor


def _volume_input(prefix: str, default_cm3: float = 1000.0) -> float:
    unit = st.selectbox("Volume unit", list(VOLUME_UNITS.keys()), index=1,
                        key=f"{prefix}_vunit")
    factor = VOLUME_UNITS[unit]
    shown_default = default_cm3 * 1e-6 / factor
    value = ui.number("Volume V", unit, f"{prefix}_v_{unit}", shown_default,
                      min_value=0.0)
    return value * factor


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def render_stress() -> None:
    p = "mat_stress"
    ui.page_header(
        "Normal stress",
        r"\sigma = \frac{F}{A}",
        "Force spread over the area carrying it. Two parts under the same load "
        "can be worlds apart in stress - which is why a thin bolt fails where a "
        "thick one does not. Note that 1 MPa is exactly 1 N/mm².",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        force = ui.number("Axial force F", "N", f"{p}_f", 5000.0,
                          help="Positive for tension, negative for compression.")
    with c2:
        area = _area_input(p, default_mm2=78.54)
        st.caption("78.54 mm² is the section of a 10 mm diameter round bar.")

    value = ui.compute(lambda: normal_stress(force, area))
    if value is not None:
        ui.result(
            "Normal stress σ", value / 1e6, "MPa",
            secondary=[
                ("In pascals", value, "Pa"),
                ("In pounds per square inch", value / 6894.757293168361, "psi"),
                ("Area used", area * 1e6, "mm²"),
            ],
        )
        if force < 0:
            st.caption("Negative stress is compression. Slender compression "
                       "members can buckle long before they reach this stress, so "
                       "check buckling separately.")
    ui.assumptions([
        "Uniform axial stress over the section: the load acts through the "
        "centroid and the section is far from holes, welds or sudden changes of "
        "shape.",
        "Stress concentrations around holes, fillets and notches can multiply the "
        "local stress by 2-3 times or more.",
        "This is the ENGINEERING stress, based on the original cross-section. "
        "True stress uses the instantaneous area and matters only near failure.",
        "Bending, shear and torsion produce their own stresses that are not "
        "included here.",
    ])
    ui.reference(
        variables=[
            ("$\\sigma$", "Normal stress", "Pa (N/m²)"),
            ("$F$", "Axial force", "N"),
            ("$A$", "Cross-sectional area", "m²"),
        ],
        example="Sizing a drone arm bolt. A 5 kN load through a 10 mm bolt "
                "(78.5 mm²) gives 63.7 MPa. Against a steel yield strength around "
                "640 MPa that is a safety factor of about 10 - comfortable, and "
                "typical for a joint that also sees vibration and fatigue.",
    )


def render_strain() -> None:
    p = "mat_strain"
    ui.page_header(
        "Strain",
        r"\varepsilon = \frac{\Delta L}{L_0}",
        "How much a material stretches, as a fraction of its original length. "
        "Strain is dimensionless, so it is usually quoted as a percentage or in "
        "microstrain - the unit strain gauges report.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        delta = ui.number("Change in length dL", "mm", f"{p}_dl", 1.2)
    with c2:
        length0 = ui.number("Original length L0", "mm", f"{p}_l0", 1000.0,
                            min_value=0.0)

    value = ui.compute(lambda: strain(delta / 1000.0, length0 / 1000.0))
    if value is not None:
        ui.result(
            "Strain ε", value, "-",
            secondary=[
                ("As a percentage", value * 100.0, "%"),
                ("In microstrain", value * 1e6, "με"),
                ("Final length", length0 + delta, "mm"),
            ],
        )
    ui.assumptions([
        "Engineering strain, referenced to the ORIGINAL length. True (logarithmic) "
        "strain differs once deformation becomes large.",
        "Uniform strain along the whole gauge length.",
        "Small-strain assumption: below about 5% the two definitions agree "
        "closely.",
        "Elastic strain is recovered when the load is removed; plastic strain is "
        "permanent. This equation does not distinguish between them.",
    ])
    ui.reference(
        variables=[
            ("$\\varepsilon$", "Strain (dimensionless)", "-"),
            ("$\\Delta L$", "Change in length", "m"),
            ("$L_0$", "Original (unloaded) length", "m"),
        ],
        example="Strain-gauge instrumentation on a test wing spar. A gauge reading "
                "1200 microstrain means the surface has stretched 0.12%. Multiply "
                "by the material's Young's modulus to get the stress at that point "
                "- the standard way of turning a test into a load figure.",
    )


def render_youngs_modulus() -> None:
    p = "mat_e"
    ui.page_header(
        "Young's modulus",
        r"E = \frac{\sigma}{\varepsilon}",
        "The stiffness of a material: how much stress it takes to produce a given "
        "strain. It is a property of the material, not the part - shape changes "
        "how stiff a component is, but not its Young's modulus.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        stress_mpa = ui.number("Stress σ", "MPa", f"{p}_s", 63.7)
    with c2:
        strain_pct = ui.number("Strain ε", "%", f"{p}_e", 0.0912,
                               help="0.0912% is 912 microstrain.")

    value = ui.compute(lambda: youngs_modulus(stress_mpa * 1e6, strain_pct / 100.0))
    if value is not None:
        ui.result(
            "Young's modulus E", value / 1e9, "GPa",
            secondary=[
                ("In megapascals", value / 1e6, "MPa"),
                ("In pascals", value, "Pa"),
                ("Strain in microstrain", strain_pct * 1e4, "με"),
            ],
        )
    ui.assumptions([
        "Valid only in the LINEAR ELASTIC region, below the proportional limit. "
        "Past yield, stress and strain are no longer proportional and this ratio "
        "stops being E.",
        "Isotropic material - the same in all directions. Carbon-fibre composites "
        "and 3D-printed parts are strongly direction-dependent, so E along the "
        "fibres or print lines is not E across them.",
        "Room temperature. Stiffness generally falls as temperature rises, and "
        "polymers change dramatically near their glass transition.",
        "Reference values: aluminium alloys about 69 GPa, steels about 200 GPa, "
        "titanium about 114 GPa, unidirectional carbon/epoxy 70-180 GPa along the "
        "fibres. Always check a datasheet for the exact alloy and temper.",
    ])
    ui.reference(
        variables=[
            ("$E$", "Young's modulus (elastic modulus)", "Pa"),
            ("$\\sigma$", "Normal stress", "Pa"),
            ("$\\varepsilon$", "Strain", "-"),
        ],
        example="Identifying a material from a tensile test. A specimen at 63.7 "
                "MPa showing 912 microstrain gives E = 69.8 GPa - consistent with "
                "an aluminium alloy, and far too low for steel.",
    )


def render_safety_factor() -> None:
    p = "mat_fos"
    basis = st.session_state.get(f"{p}_basis", "Yield strength")
    ui.page_header(
        "Factor of safety",
        r"FoS = \frac{\sigma_{" + ("yield" if basis.startswith("Yield")
                                   else "ultimate") + r"}}{\sigma_{applied}}",
        "How much margin there is between the stress in the part and the stress "
        "the material can take. <b>Which strength you divide by changes what the "
        "number means</b>: yield is where permanent deformation begins, ultimate "
        "is where it breaks.",
        p,
    )
    basis = st.radio("Strength basis", ["Yield strength", "Ultimate strength"],
                     key=f"{p}_basis", horizontal=True,
                     help="Yield: the part stops being reusable. Ultimate: the "
                          "part fails completely.")
    c1, c2 = st.columns(2)
    with c1:
        strength = ui.number(f"Material {basis.lower()}", "MPa", f"{p}_str", 276.0,
                             min_value=0.0,
                             help="6061-T6 aluminium: yield 276 MPa, ultimate "
                                  "310 MPa. Always confirm against a datasheet.")
    with c2:
        applied = ui.number("Applied stress", "MPa", f"{p}_app", 63.7, min_value=0.0)

    value = ui.compute(lambda: safety_factor(strength * 1e6, applied * 1e6))
    if value is not None:
        ui.result(
            f"Factor of safety ({basis.lower()})", value, "-",
            secondary=[
                ("Margin of safety (FoS - 1)", value - 1.0, "-"),
                ("Allowable stress at FoS = 1.5", strength / 1.5, "MPa"),
                ("Headroom left", strength - applied, "MPa"),
            ],
        )
        if value < 1.0:
            st.error(f"Applied stress exceeds the {basis.lower()}. The part would "
                     f"{'yield permanently' if basis.startswith('Yield') else 'fracture'}.")
        elif value < 1.5:
            st.caption("Below 1.5 is a thin margin for most airframe structure, "
                       "and leaves nothing for material variation, fatigue or "
                       "manufacturing tolerance.")
    ui.assumptions([
        f"Computed against {basis.lower()}. A factor of safety is only meaningful "
        "when you say which strength it is based on - they are different numbers.",
        "Static loading only. Parts under cyclic load fail by fatigue far below "
        "their static strength, and that needs an S-N curve, not this ratio.",
        "Uses the nominal material strength. Real batches vary; aerospace work "
        "uses statistically derived allowables (A-basis or B-basis), not typical "
        "values.",
        "Temperature, corrosion, stress concentrations and manufacturing defects "
        "all reduce real strength.",
        "Typical targets for orientation: aircraft structure 1.5 on ultimate, "
        "lifting equipment 4-6, pressure vessels 3-4. Your requirement comes from "
        "the applicable standard, not from this app.",
    ])
    ui.reference(
        variables=[
            ("$FoS$", "Factor of safety", "-"),
            ("$\\sigma_{yield}$", "Stress where permanent deformation starts", "Pa"),
            ("$\\sigma_{ultimate}$", "Stress at fracture", "Pa"),
            ("$\\sigma_{applied}$", "Stress actually in the part", "Pa"),
        ],
        example="Airframe bracket check. A bracket carrying 63.7 MPa made from "
                "6061-T6 (yield 276 MPa) has FoS 4.3 on yield. Aerospace practice "
                "usually demands 1.5 on ULTIMATE at limit load, so quoting a "
                "safety factor without naming the basis and the load case says "
                "very little.",
    )


def render_density() -> None:
    p = "mat_rho"
    ui.page_header(
        "Density",
        r"\rho = \frac{m}{V}",
        "Mass per unit volume. It converts a shape into a mass, which is how a "
        "CAD model becomes a mass budget - and mass budget is the currency of "
        "every aircraft and spacecraft design.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        mass = ui.number("Mass m", "kg", f"{p}_m", 2.7, min_value=0.0)
    with c2:
        volume = _volume_input(p, default_cm3=1000.0)

    value = ui.compute(lambda: density(mass, volume))
    if value is not None:
        ui.result(
            "Density ρ", value, "kg/m³",
            secondary=[
                ("In grams per cubic centimetre", value / 1000.0, "g/cm³"),
                ("Specific gravity (relative to water)", value / 1000.0, "-"),
                ("Weight of this sample", mass * G0, "N"),
            ],
        )
    ui.assumptions([
        "Uniform, solid material with no voids. Foams, honeycomb cores and "
        "3D-printed infill have a bulk density well below the solid material's.",
        "Density varies slightly with temperature; for solids the effect is small "
        "and usually ignored.",
        "Reference values: aluminium 2700 kg/m³, steel 7850, titanium 4500, "
        "carbon/epoxy laminate about 1600, water 1000 at 4 C.",
    ])
    ui.reference(
        variables=[
            ("$\\rho$", "Density", "kg/m³"),
            ("$m$", "Mass", "kg"),
            ("$V$", "Volume", "m³"),
        ],
        example="Mass budgeting from CAD. A 1000 cm³ aluminium bracket weighs "
                "2.7 kg. Switching to a carbon composite of density 1600 kg/m³ at "
                "the same volume saves 1.1 kg - before considering that the "
                "composite part probably needs a different shape to be as stiff.",
    )


def render_specific_strength() -> None:
    p = "mat_spec"
    ui.page_header(
        "Specific strength",
        r"\text{Specific strength} = \frac{\sigma}{\rho}",
        "Strength divided by density - the figure of merit for anything that has "
        "to fly. It is why aerospace uses aluminium and carbon fibre instead of "
        "steel: steel is stronger, but not stronger <b>per kilogram</b>.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        strength = ui.number("Strength σ", "MPa", f"{p}_s", 276.0, min_value=0.0)
    with c2:
        rho = ui.number("Density ρ", "kg/m³", f"{p}_r", 2700.0, min_value=0.0)

    value = ui.compute(lambda: specific_strength(strength * 1e6, rho))
    if value is not None:
        ui.result(
            "Specific strength", value / 1000.0, "kN·m/kg",
            secondary=[
                ("In N·m/kg (= J/kg)", value, "N·m/kg"),
                ("In MPa per (g/cm³)", strength / (rho / 1000.0), "MPa/(g/cm³)"),
                ("Breaking length (self-supporting column)", value / G0 / 1000.0,
                 "km"),
            ],
        )
    ui.assumptions([
        "Use the same strength basis on both sides of any comparison - yield "
        "against yield, or ultimate against ultimate.",
        "For composites, strength is direction-dependent: along the fibres the "
        "number is excellent, across them it is poor. A single figure hides that.",
        "Specific STIFFNESS (E/ρ) is a different figure of merit and often the "
        "one that actually drives aerospace structure, since most parts are "
        "stiffness-limited rather than strength-limited.",
        "Breaking length is the classic illustration: the length of a column of "
        "this material that would fail under its own weight.",
        "Orientation values (ultimate/density): 6061-T6 aluminium about 115 "
        "kN·m/kg, 4130 steel about 85, Ti-6Al-4V about 210, unidirectional "
        "carbon/epoxy 800-1500 along the fibres.",
    ])
    ui.reference(
        variables=[
            ("$\\sigma$", "Strength (yield or ultimate)", "Pa"),
            ("$\\rho$", "Density", "kg/m³"),
            ("$\\sigma/\\rho$", "Specific strength", "N·m/kg"),
        ],
        example="Material choice for a drone arm. Steel at 640 MPa and 7850 kg/m³ "
                "gives 82 kN·m/kg; 6061-T6 aluminium at 276 MPa and 2700 kg/m³ "
                "gives 102 kN·m/kg. The aluminium is weaker but better per "
                "kilogram - which is the number that matters when every gram costs "
                "flight time.",
    )


CALCULATORS = {
    "Normal stress": render_stress,
    "Strain": render_strain,
    "Young's modulus": render_youngs_modulus,
    "Factor of safety": render_safety_factor,
    "Density": render_density,
    "Specific strength": render_specific_strength,
}
