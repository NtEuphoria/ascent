"""Materials and solid-mechanics calculators.

Areas and volumes are entered in whatever unit is convenient and converted to SI
immediately, because 1 MPa = 1 N/mm² is the single most common place to lose a
factor of a million.

These were the last plain equations in the app still drawing their own pages,
which cost them everything the shared renderer provides for nothing: the
influence table, first-order uncertainty propagation, binding an input to a
project parameter, and a sweep graph.

Uncertainty matters more here than anywhere else in the app. A yield strength is
a distribution, not a number - batch to batch scatter of 5-10% is ordinary - so
a factor of safety worked out from a typical value is a point estimate wearing a
lab coat. Give the strength a sigma and the page will tell you what the factor
of safety is actually worth.

The unit selectors that kept these pages imperative are `widget=` fields now,
which is exactly what that escape hatch is for.
"""
from __future__ import annotations

import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import G0
from utils.spec import (Calculator, Check, Field, Output, Reference, Secondary,
                        Sweep)

AREA_UNITS = {"mm²": 1e-6, "cm²": 1e-4, "m²": 1.0}
VOLUME_UNITS = {"mm³": 1e-9, "cm³ (= mL)": 1e-6, "litre": 1e-3, "m³": 1.0}
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
# Compound inputs
#
# A value plus a unit selector is one logical input drawn with two controls,
# which is the case Field(widget=...) exists for. Both return SI.
# ---------------------------------------------------------------------------


def _scaled_widget(key: str, field: Field, units, label: str, index: int):
    """A number box with a unit selector beside it, returning the SI value.

    Each unit keeps its own widget key, so switching from mm² to m² shows that
    unit's own default rather than silently reinterpreting 78.54 as square
    metres - which would be a factor of a million, in the one module where a
    factor of a million is the standing hazard.
    """
    unit = st.selectbox(label, list(units.keys()), index=index,
                        key=f"{key}_unit")
    factor = units[unit]
    return ui.number(field.label, unit, f"{key}_{unit}",
                     float(field.default) / factor, min_value=0.0) * factor


def _area_widget(key: str, field: Field) -> float:
    return _scaled_widget(key, field, AREA_UNITS, "Area unit", 0)


def _volume_widget(key: str, field: Field) -> float:
    return _scaled_widget(key, field, VOLUME_UNITS, "Volume unit", 1)


# ---------------------------------------------------------------------------
# Shared reference data
# ---------------------------------------------------------------------------

MATERIALS_TABLE = Reference(
    title="Typical material properties",
    columns=("Material", "ρ [kg/m³]", "Yield [MPa]", "Ultimate [MPa]", "E [GPa]"),
    rows=[
        ("6061-T6 aluminium", "2700", "276", "310", "68.9"),
        ("7075-T6 aluminium", "2810", "503", "572", "71.7"),
        ("4130 steel, normalised", "7850", "435", "670", "205"),
        ("304 stainless, annealed", "8000", "215", "505", "193"),
        ("Ti-6Al-4V (Grade 5)", "4430", "880", "950", "114"),
        ("Carbon/epoxy UD, along fibres", "1600", "—", "1500", "135"),
        ("PLA, 3D printed", "1240", "50", "50", "3.5"),
    ],
    note="Typical room-temperature values, for orientation only. Real batches "
         "vary, and aerospace work uses statistically derived allowables "
         "(A-basis or B-basis) rather than typical values. Carbon/epoxy is "
         "quoted along the fibres and is far weaker across them; a laminate's "
         "properties depend on its layup, not just its material. Brittle "
         "materials have no meaningful yield point. Always confirm against the "
         "datasheet for your exact alloy, temper and product form.",
)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

NORMAL_STRESS = Calculator(
    slug="materials.normal_stress",
    name="Normal stress",
    latex=r"\sigma = \frac{F}{A}",
    explanation=(
        "Force spread over the area carrying it. Two parts under the same load "
        "can be worlds apart in stress - which is why a thin bolt fails where a "
        "thick one does not. Note that 1 MPa is exactly 1 N/mm²."
    ),
    inputs=[
        Field("force", "Axial force F", "N", 5000.0,
              help="Positive for tension, negative for compression."),
        Field("area", "Cross-sectional area A", "m²", 78.54e-6,
              widget=_area_widget,
              help="78.54 mm² is the section of a 10 mm diameter round bar."),
    ],
    compute=lambda i: normal_stress(i.force, i.area) / 1e6,
    result=Output("Normal stress σ", "MPa"),
    secondary=[
        Secondary("In pascals", "Pa", lambda i, r: r * 1e6),
        Secondary("In pounds per square inch", "psi",
                  lambda i, r: r * 1e6 / 6894.757293168361),
        Secondary("Area used", "mm²", lambda i, r: i.area * 1e6),
        Secondary("Load at which 6061-T6 would yield (276 MPa)", "N",
                  lambda i, r: 276e6 * i.area),
    ],
    assumptions=[
        "Uniform axial stress over the section: the load acts through the "
        "centroid and the section is far from holes, welds or sudden changes of "
        "shape.",
        "Stress concentrations around holes, fillets and notches can multiply the "
        "local stress by 2-3 times or more.",
        "This is the ENGINEERING stress, based on the original cross-section. "
        "True stress uses the instantaneous area and matters only near failure.",
        "Bending, shear and torsion produce their own stresses that are not "
        "included here.",
    ],
    variables=[
        ("$\\sigma$", "Normal stress", "Pa (N/m²)"),
        ("$F$", "Axial force", "N"),
        ("$A$", "Cross-sectional area", "m²"),
    ],
    example="Sizing a drone arm bolt. A 5 kN load through a 10 mm bolt "
            "(78.5 mm²) gives 63.7 MPa. Against a steel yield strength around "
            "640 MPa that is a safety factor of about 10 - comfortable, and "
            "typical for a joint that also sees vibration and fatigue.",
    graphs=[
        Sweep(over="force", y_label="Normal stress σ [MPa]",
              title="Stress against applied load", hi_factor=2.0),
    ],
    checks=[
        Check(lambda i, r: ("info",
                            "Negative stress is compression. Slender compression "
                            "members can buckle long before they reach this "
                            "stress, so check buckling separately.")
              if i.force < 0 else None),
    ],
    references=[MATERIALS_TABLE],
    related=["materials.factor_of_safety", "materials.strain",
             "struct.buckling", "struct.second_moment"],
    keywords=("sigma", "axial", "tension", "compression", "bolt", "MPa"),
)


STRAIN = Calculator(
    slug="materials.strain",
    name="Strain",
    latex=r"\varepsilon = \frac{\Delta L}{L_0}",
    explanation=(
        "How much a material stretches, as a fraction of its original length. "
        "Strain is dimensionless, so it is usually quoted as a percentage or in "
        "microstrain - the unit strain gauges report."
    ),
    inputs=[
        Field("delta", "Change in length dL", "mm", 1.2),
        Field("length0", "Original length L0", "mm", 1000.0, min=0.0),
    ],
    compute=lambda i: strain(i.delta / 1000.0, i.length0 / 1000.0),
    result=Output("Strain ε", "-"),
    secondary=[
        Secondary("As a percentage", "%", lambda i, r: r * 100.0),
        Secondary("In microstrain", "με", lambda i, r: r * 1e6),
        Secondary("Final length", "mm", lambda i, r: i.length0 + i.delta),
        Secondary("Stress if this were 6061-T6 (E = 68.9 GPa)", "MPa",
                  lambda i, r: r * 68.9e3),
    ],
    assumptions=[
        "Engineering strain, referenced to the ORIGINAL length. True "
        "(logarithmic) strain differs once deformation becomes large.",
        "Uniform strain along the whole gauge length.",
        "Small-strain assumption: below about 5% the two definitions agree "
        "closely.",
        "Elastic strain is recovered when the load is removed; plastic strain is "
        "permanent. This equation does not distinguish between them.",
    ],
    variables=[
        ("$\\varepsilon$", "Strain (dimensionless)", "-"),
        ("$\\Delta L$", "Change in length", "m"),
        ("$L_0$", "Original (unloaded) length", "m"),
    ],
    example="Strain-gauge instrumentation on a test wing spar. A gauge reading "
            "1200 microstrain means the surface has stretched 0.12%. Multiply "
            "by the material's Young's modulus to get the stress at that point "
            "- the standard way of turning a test into a load figure.",
    graphs=[
        Sweep(over="length0", y_label="Strain ε [-]",
              title="Strain against gauge length", lo_factor=0.3),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            "Above about 5% strain, engineering and true strain "
                            "part company and most metals are already yielding. "
                            "This ratio is still arithmetic, but it has stopped "
                            "describing elastic behaviour.")
              if abs(r) > 0.05 else None),
    ],
    related=["materials.young's_modulus", "materials.normal_stress",
             "struct.elastic_constants"],
    keywords=("epsilon", "microstrain", "gauge", "elongation", "stretch"),
)


YOUNGS_MODULUS = Calculator(
    slug="materials.young's_modulus",
    name="Young's modulus",
    latex=r"E = \frac{\sigma}{\varepsilon}",
    explanation=(
        "The stiffness of a material: how much stress it takes to produce a "
        "given strain. It is a property of the material, not the part - shape "
        "changes how stiff a component is, but not its Young's modulus."
    ),
    inputs=[
        Field("stress", "Stress σ", "MPa", 63.7),
        Field("strain_pct", "Strain ε", "%", 0.0912,
              help="0.0912% is 912 microstrain."),
    ],
    compute=lambda i: youngs_modulus(i.stress * 1e6, i.strain_pct / 100.0) / 1e9,
    result=Output("Young's modulus E", "GPa"),
    secondary=[
        Secondary("In megapascals", "MPa", lambda i, r: r * 1000.0),
        Secondary("In pascals", "Pa", lambda i, r: r * 1e9),
        Secondary("Strain in microstrain", "με", lambda i, r: i.strain_pct * 1e4),
    ],
    assumptions=[
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
    ],
    variables=[
        ("$E$", "Young's modulus (elastic modulus)", "Pa"),
        ("$\\sigma$", "Normal stress", "Pa"),
        ("$\\varepsilon$", "Strain", "-"),
    ],
    example="Identifying a material from a tensile test. A specimen at 63.7 "
            "MPa showing 912 microstrain gives E = 69.8 GPa - consistent with "
            "an aluminium alloy, and far too low for steel.",
    graphs=[
        Sweep(over="strain_pct", y_label="Young's modulus E [GPa]",
              title="Modulus inferred from the measured strain", lo_factor=0.4),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            "That modulus is outside the range of engineering "
                            "solids (roughly 0.01 GPa for soft rubbers to 1200 "
                            "GPa for diamond). Check whether the strain is in "
                            "percent rather than microstrain.")
              if not 0.001 <= r <= 1200.0 else None),
    ],
    references=[MATERIALS_TABLE],
    related=["materials.strain", "struct.elastic_constants",
             "struct.beam_bending"],
    keywords=("E", "modulus", "stiffness", "elastic", "hooke"),
)


FACTOR_OF_SAFETY = Calculator(
    slug="materials.factor_of_safety",
    name="Factor of safety",
    latex=r"FoS = \frac{\sigma_{strength}}{\sigma_{applied}}",
    explanation=(
        "How much margin there is between the stress in the part and the stress "
        "the material can take. <b>Which strength you divide by changes what the "
        "number means</b>: yield is where permanent deformation begins, ultimate "
        "is where it breaks. Choose the basis below - the answer is not "
        "meaningful without it."
    ),
    inputs=[
        Field("basis", "Strength basis", "", 0, kind="choice",
              options=["Yield strength", "Ultimate strength"],
              help="Yield: the part stops being reusable. Ultimate: the part "
                   "fails completely."),
        Field("strength", "Material strength", "MPa", 276.0, min=0.0,
              help="6061-T6 aluminium: yield 276 MPa, ultimate 310 MPa. Always "
                   "confirm against a datasheet."),
        Field("applied", "Applied stress", "MPa", 63.7, min=0.0),
    ],
    compute=lambda i: safety_factor(i.strength * 1e6, i.applied * 1e6),
    result=Output("Factor of safety", "-"),
    secondary=[
        Secondary("Margin of safety (FoS − 1)", "-", lambda i, r: r - 1.0),
        Secondary("Allowable stress at FoS = 1.5", "MPa",
                  lambda i, r: i.strength / 1.5),
        Secondary("Headroom left", "MPa", lambda i, r: i.strength - i.applied),
    ],
    note=lambda i, r: "Computed against %s." % i.basis.lower(),
    assumptions=[
        "A factor of safety is only meaningful when you say which strength it "
        "is based on - yield and ultimate are different numbers, and the basis "
        "is stated under the result.",
        "Static loading only. Parts under cyclic load fail by fatigue far below "
        "their static strength, and that needs an S-N curve, not this ratio.",
        "Uses the nominal material strength. Real batches vary; aerospace work "
        "uses statistically derived allowables (A-basis or B-basis), not typical "
        "values. Give the strength an uncertainty above and this page will show "
        "what that scatter does to the margin.",
        "Temperature, corrosion, stress concentrations and manufacturing defects "
        "all reduce real strength.",
        "Typical targets for orientation: aircraft structure 1.5 on ultimate, "
        "lifting equipment 4-6, pressure vessels 3-4. Your requirement comes from "
        "the applicable standard, not from this app.",
    ],
    variables=[
        ("$FoS$", "Factor of safety", "-"),
        ("$\\sigma_{strength}$", "Yield or ultimate strength, as chosen", "Pa"),
        ("$\\sigma_{applied}$", "Stress actually in the part", "Pa"),
    ],
    example="Airframe bracket check. A bracket carrying 63.7 MPa made from "
            "6061-T6 (yield 276 MPa) has FoS 4.3 on yield. Aerospace practice "
            "usually demands 1.5 on ULTIMATE at limit load, so quoting a "
            "safety factor without naming the basis and the load case says "
            "very little.",
    graphs=[
        Sweep(over="applied", y_label="Factor of safety [-]",
              title="Margin against the stress in the part",
              lo_factor=0.3, hi_factor=2.5),
    ],
    checks=[
        Check(lambda i, r: ("danger",
                            "Applied stress exceeds the %s. The part would %s."
                            % (i.basis.lower(),
                               "yield permanently" if i.basis.startswith("Yield")
                               else "fracture"))
              if r < 1.0 else None),
        Check(lambda i, r: ("warning",
                            "Below 1.5 is a thin margin for most airframe "
                            "structure, and leaves nothing for material "
                            "variation, fatigue or manufacturing tolerance.")
              if 1.0 <= r < 1.5 else None),
    ],
    references=[MATERIALS_TABLE],
    related=["materials.normal_stress", "struct.beam_bending",
             "struct.buckling", "materials.specific_strength"],
    keywords=("FoS", "margin", "allowable", "yield", "ultimate", "safety"),
)


DENSITY = Calculator(
    slug="materials.density",
    name="Density",
    latex=r"\rho = \frac{m}{V}",
    explanation=(
        "Mass per unit volume. It converts a shape into a mass, which is how a "
        "CAD model becomes a mass budget - and mass budget is the currency of "
        "every aircraft and spacecraft design."
    ),
    inputs=[
        Field("mass", "Mass m", "kg", 2.7, min=0.0),
        Field("volume", "Volume V", "m³", 1.0e-3, widget=_volume_widget),
    ],
    compute=lambda i: density(i.mass, i.volume),
    result=Output("Density ρ", "kg/m³"),
    secondary=[
        Secondary("In grams per cubic centimetre", "g/cm³",
                  lambda i, r: r / 1000.0),
        Secondary("Specific gravity (relative to water)", "-",
                  lambda i, r: r / 1000.0),
        Secondary("Weight of this sample", "N", lambda i, r: i.mass * G0),
        Secondary("Volume used", "cm³", lambda i, r: i.volume * 1e6),
    ],
    assumptions=[
        "Uniform, solid material with no voids. Foams, honeycomb cores and "
        "3D-printed infill have a bulk density well below the solid material's.",
        "Density varies slightly with temperature; for solids the effect is small "
        "and usually ignored.",
        "Reference values: aluminium 2700 kg/m³, steel 7850, titanium 4500, "
        "carbon/epoxy laminate about 1600, water 1000 at 4 C.",
    ],
    variables=[
        ("$\\rho$", "Density", "kg/m³"),
        ("$m$", "Mass", "kg"),
        ("$V$", "Volume", "m³"),
    ],
    example="Mass budgeting from CAD. A 1000 cm³ aluminium bracket weighs "
            "2.7 kg. Switching to a carbon composite of density 1600 kg/m³ at "
            "the same volume saves 1.1 kg - before considering that the "
            "composite part probably needs a different shape to be as stiff.",
    graphs=[
        Sweep(over="mass", y_label="Density ρ [kg/m³]",
              title="Density against the mass of the sample"),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            "That is denser than osmium (22 590 kg/m³), the "
                            "densest element. Check the volume unit.")
              if r > 22590.0 else None),
    ],
    references=[MATERIALS_TABLE],
    related=["materials.specific_strength", "mech.force",
             "drone.flight_time"],
    keywords=("rho", "mass", "volume", "specific gravity", "mass budget"),
)


SPECIFIC_STRENGTH = Calculator(
    slug="materials.specific_strength",
    name="Specific strength",
    latex=r"\text{Specific strength} = \frac{\sigma}{\rho}",
    explanation=(
        "Strength divided by density - the figure of merit for anything that has "
        "to fly. It is why aerospace uses aluminium and carbon fibre instead of "
        "steel: steel is stronger, but not stronger <b>per kilogram</b>."
    ),
    inputs=[
        Field("strength", "Strength σ", "MPa", 276.0, min=0.0),
        Field("rho", "Density ρ", "kg/m³", 2700.0, min=0.0),
    ],
    compute=lambda i: specific_strength(i.strength * 1e6, i.rho) / 1000.0,
    result=Output("Specific strength", "kN·m/kg"),
    secondary=[
        Secondary("In N·m/kg (= J/kg)", "N·m/kg", lambda i, r: r * 1000.0),
        Secondary("In MPa per (g/cm³)", "MPa/(g/cm³)",
                  lambda i, r: i.strength / (i.rho / 1000.0)),
        Secondary("Breaking length (self-supporting column)", "km",
                  lambda i, r: r * 1000.0 / G0 / 1000.0),
    ],
    assumptions=[
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
    ],
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
    graphs=[
        Sweep(over="rho", y_label="Specific strength [kN·m/kg]",
              title="Why density decides the material", lo_factor=0.35,
              hi_factor=3.0),
    ],
    references=[MATERIALS_TABLE],
    related=["materials.density", "materials.factor_of_safety",
             "aero.wing_loading"],
    keywords=("strength to weight", "figure of merit", "breaking length",
              "specific", "lightweight"),
)


CALCULATORS = [
    NORMAL_STRESS,
    STRAIN,
    YOUNGS_MODULUS,
    FACTOR_OF_SAFETY,
    DENSITY,
    SPECIFIC_STRENGTH,
]
