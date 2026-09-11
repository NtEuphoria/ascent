"""Structures: section properties, beam bending and elastic constants.

A NOTE ON THE LETTER I
======================
Adding this module puts three different quantities sharing two letters into one
app, and confusing them is the most common source of wrong answers in beam and
shaft work:

    I  mass moment of inertia   [kg*m^2]  - resistance to angular acceleration
                                            (Rotational mechanics)
    I  second moment of area    [m^4]     - resistance to BENDING (this module)
    J  polar second moment      [m^4]     - resistance to TWISTING (this module)

They are not interchangeable, they do not share units, and for circular
sections only, J = 2I. Every page here says which one it means.
"""
from __future__ import annotations

from collections import OrderedDict

import numpy as np

from utils import validation as v
from utils.spec import Calculator, Field, Output, Secondary, Sweep

# ---------------------------------------------------------------------------
# Section property library
# ---------------------------------------------------------------------------

SECTIONS = OrderedDict([
    ("Solid rectangle", {
        "formula": lambda b, h, t: b * h ** 3 / 12.0,
        "area": lambda b, h, t: b * h,
        "extreme": lambda b, h, t: h / 2.0,
        "latex": r"I = \frac{b\,h^{3}}{12}",
        "uses": "b = width, h = depth (the dimension PARALLEL to the load)",
    }),
    ("Solid circle", {
        "formula": lambda b, h, t: np.pi * b ** 4 / 64.0,
        "area": lambda b, h, t: np.pi * b ** 2 / 4.0,
        "extreme": lambda b, h, t: b / 2.0,
        "latex": r"I = \frac{\pi d^{4}}{64}",
        "uses": "b = diameter. h and t are ignored.",
    }),
    ("Hollow circle (tube)", {
        "formula": lambda b, h, t: np.pi * (b ** 4 - max(b - 2 * t, 0) ** 4)
        / 64.0,
        "area": lambda b, h, t: np.pi * (b ** 2 - max(b - 2 * t, 0) ** 2) / 4.0,
        "extreme": lambda b, h, t: b / 2.0,
        "latex": r"I = \frac{\pi (d_o^{4} - d_i^{4})}{64}",
        "uses": "b = outer diameter, t = wall thickness. h is ignored.",
    }),
    ("Hollow rectangle (box)", {
        "formula": lambda b, h, t: (b * h ** 3
                                    - max(b - 2 * t, 0)
                                    * max(h - 2 * t, 0) ** 3) / 12.0,
        "area": lambda b, h, t: b * h - max(b - 2 * t, 0) * max(h - 2 * t, 0),
        "extreme": lambda b, h, t: h / 2.0,
        "latex": r"I = \frac{B H^{3} - b h^{3}}{12}",
        "uses": "b = outer width, h = outer depth, t = wall thickness",
    }),
])

BEAM_CASES = OrderedDict([
    ("Cantilever, point load at the end", {
        "moment": lambda load, length: load * length,
        "deflection": lambda load, length, e, i: load * length ** 3
        / (3.0 * e * i),
        "load_unit": "N",
        "latex": r"M = P L, \qquad \delta = \frac{P L^{3}}{3EI}",
    }),
    ("Cantilever, uniform load", {
        "moment": lambda load, length: load * length ** 2 / 2.0,
        "deflection": lambda load, length, e, i: load * length ** 4
        / (8.0 * e * i),
        "load_unit": "N/m",
        "latex": r"M = \frac{wL^{2}}{2}, \qquad \delta = \frac{wL^{4}}{8EI}",
    }),
    ("Simply supported, centre point load", {
        "moment": lambda load, length: load * length / 4.0,
        "deflection": lambda load, length, e, i: load * length ** 3
        / (48.0 * e * i),
        "load_unit": "N",
        "latex": r"M = \frac{PL}{4}, \qquad \delta = \frac{PL^{3}}{48EI}",
    }),
    ("Simply supported, uniform load", {
        "moment": lambda load, length: load * length ** 2 / 8.0,
        "deflection": lambda load, length, e, i: 5.0 * load * length ** 4
        / (384.0 * e * i),
        "load_unit": "N/m",
        "latex": r"M = \frac{wL^{2}}{8}, \qquad \delta = \frac{5wL^{4}}{384EI}",
    }),
    ("Fixed both ends, centre point load", {
        "moment": lambda load, length: load * length / 8.0,
        "deflection": lambda load, length, e, i: load * length ** 3
        / (192.0 * e * i),
        "load_unit": "N",
        "latex": r"M = \frac{PL}{8}, \qquad \delta = \frac{PL^{3}}{192EI}",
    }),
    ("Fixed both ends, uniform load", {
        "moment": lambda load, length: load * length ** 2 / 12.0,
        "deflection": lambda load, length, e, i: load * length ** 4
        / (384.0 * e * i),
        "load_unit": "N/m",
        "latex": r"M = \frac{wL^{2}}{12}, \qquad \delta = \frac{wL^{4}}{384EI}",
    }),
])


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def second_moment_of_area(section: str, width: float, depth: float,
                          thickness: float) -> float:
    """I about the centroidal axis   [m^4] - resistance to BENDING."""
    if section not in SECTIONS:
        raise v.ValidationError(f"Unknown section: {section}")
    width = v.positive(width, "Width or diameter", "m")
    depth = v.positive(depth, "Depth", "m")
    thickness = v.non_negative(thickness, "Wall thickness", "m")
    if "Hollow" in section and thickness <= 0:
        raise v.ValidationError(
            "A hollow section needs a wall thickness greater than zero.")
    if "Hollow circle" in section and 2 * thickness >= width:
        raise v.ValidationError(
            "Wall thickness is at least half the outer diameter - the section "
            "would be solid or inside out.")
    return float(SECTIONS[section]["formula"](width, depth, thickness))


def section_area(section: str, width: float, depth: float,
                 thickness: float) -> float:
    """Cross-sectional area   [m^2]"""
    return float(SECTIONS[section]["area"](width, depth, thickness))


def section_modulus(second_moment: float, extreme_fibre: float) -> float:
    """Z = I / c   [m^3] - strength per unit bending moment."""
    second_moment = v.positive(second_moment, "Second moment of area", "m^4")
    extreme_fibre = v.positive(extreme_fibre, "Distance to extreme fibre", "m")
    return second_moment / extreme_fibre


def bending_moment(case: str, load: float, length: float) -> float:
    """Maximum bending moment for the chosen load case   [N*m]"""
    if case not in BEAM_CASES:
        raise v.ValidationError(f"Unknown load case: {case}")
    load = v.non_negative(load, "Load", "N or N/m")
    length = v.positive(length, "Span", "m")
    return float(BEAM_CASES[case]["moment"](load, length))


def bending_stress(moment: float, extreme_fibre: float,
                   second_moment: float) -> float:
    """sigma = M c / I   [Pa], maximum at the outermost fibre."""
    moment = v.finite(moment, "Bending moment", "N*m")
    extreme_fibre = v.positive(extreme_fibre, "Distance to extreme fibre", "m")
    second_moment = v.positive(second_moment, "Second moment of area", "m^4")
    return moment * extreme_fibre / second_moment


def beam_deflection(case: str, load: float, length: float, modulus: float,
                    second_moment: float) -> float:
    """Maximum deflection for the chosen load case   [m]"""
    if case not in BEAM_CASES:
        raise v.ValidationError(f"Unknown load case: {case}")
    load = v.non_negative(load, "Load", "N or N/m")
    length = v.positive(length, "Span", "m")
    modulus = v.positive(modulus, "Young's modulus", "Pa")
    second_moment = v.positive(second_moment, "Second moment of area", "m^4")
    return float(BEAM_CASES[case]["deflection"](load, length, modulus,
                                                second_moment))


def shear_modulus(youngs_modulus: float, poisson_ratio: float) -> float:
    """G = E / (2(1 + nu))   [Pa]"""
    youngs_modulus = v.positive(youngs_modulus, "Young's modulus", "Pa")
    poisson_ratio = v.in_range(poisson_ratio, "Poisson's ratio", -0.999, 0.4999)
    return youngs_modulus / (2.0 * (1.0 + poisson_ratio))


def bulk_modulus(youngs_modulus: float, poisson_ratio: float) -> float:
    """K = E / (3(1 - 2 nu))   [Pa] - diverges as nu approaches 0.5."""
    youngs_modulus = v.positive(youngs_modulus, "Young's modulus", "Pa")
    poisson_ratio = v.in_range(poisson_ratio, "Poisson's ratio", -0.999, 0.4999)
    return youngs_modulus / (3.0 * (1.0 - 2.0 * poisson_ratio))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

_SECTION = Calculator(
    slug="struct.second_moment",
    name="Second moment of area",
    latex=r"I = \frac{b\,h^{3}}{12}, \qquad Z = \frac{I}{c}",
    explanation=(
        "How much a cross-section resists <b>bending</b> - the I in EI and in "
        "Mc/I. It depends on shape far more than on how much material there "
        "is: depth is cubed, so a beam stood on edge is dramatically stiffer "
        "than the same beam laid flat."),
    inputs=[
        Field("section", "Section", "", 0, kind="choice",
              options=list(SECTIONS.keys())),
        Field("width", "Width b (or diameter)", "mm", 20.0, min=0.0),
        Field("depth", "Depth h", "mm", 40.0, min=0.0,
              help="The dimension parallel to the load. Ignored for circles."),
        Field("thickness", "Wall thickness t", "mm", 2.0, min=0.0,
              help="Hollow sections only."),
    ],
    compute=lambda i: second_moment_of_area(
        i.section, i.width / 1000.0, i.depth / 1000.0, i.thickness / 1000.0),
    result=Output("Second moment of area I", "m⁴", sig=4),
    secondary=[
        Secondary("In mm⁴ (the usual working unit)", "mm⁴",
                  lambda i, r: r * 1e12),
        Secondary("Section modulus Z = I/c", "mm³",
                  lambda i, r: section_modulus(
                      r, SECTIONS[i.section]["extreme"](
                          i.width / 1000.0, i.depth / 1000.0,
                          i.thickness / 1000.0)) * 1e9),
        Secondary("Cross-sectional area", "mm²",
                  lambda i, r: section_area(i.section, i.width, i.depth,
                                            i.thickness)),
        Secondary("Radius of gyration", "mm",
                  lambda i, r: float(np.sqrt(
                      r * 1e12 / section_area(i.section, i.width, i.depth,
                                              i.thickness)))),
    ],
    assumptions=[
        "This is the SECOND MOMENT OF AREA in m⁴ - resistance to bending. It "
        "is NOT the mass moment of inertia in kg·m², which resists angular "
        "acceleration and lives under Rotational mechanics. Same letter, "
        "different quantity, different units.",
        "About the centroidal axis. Shifting the axis needs the parallel-axis "
        "term, I = I_centre + A d².",
        "mm⁴ to m⁴ is a factor of 10⁻¹². Combined with MPa = N/mm², unit "
        "bookkeeping is most of the work in beam problems - both are shown "
        "above so the conversion is never guessed.",
        "Depth h is the dimension PARALLEL to the load. Swapping b and h "
        "changes I by (h/b)² - a 2:1 rectangle is four times stiffer one way "
        "than the other.",
        "Thin-wall formulas assume the wall is small relative to the overall "
        "size.",
    ],
    graph=Sweep(over="depth", y_label="Second moment of area I [m⁴]",
                lo_factor=0.2, hi_factor=2.0,
                title="I vs depth - cubic, which is why beams are deep rather "
                      "than wide"),
    variables=[
        ("$I$", "Second moment of area (bending)", "m⁴"),
        ("$Z$", "Section modulus, I/c", "m³"),
        ("$b, h$", "Width and depth", "m"),
        ("$c$", "Distance from the neutral axis to the outermost fibre", "m"),
    ],
    example=(
        "Orientation matters more than material. A 20 × 40 mm bar on edge has "
        "I = 1.07e5 mm⁴; laid flat it is 2.67e4 mm⁴ - four times less stiff "
        "from the same piece of aluminium. Turning the beam is free; buying "
        "four times the material is not."),
    keywords=("second moment", "area moment", "section", "bending", "i beam",
              "section modulus", "stiffness"),
)


def _beam_case(i):
    return i.case


_BEAM = Calculator(
    slug="struct.beam_bending",
    name="Beam bending",
    latex=r"\sigma = \frac{M c}{I}, \qquad \delta = k\,\frac{P L^{3}}{EI}",
    explanation=(
        "Stress and deflection for the standard load cases. Two different "
        "questions live here: <b>strength</b> comes from M/Z, <b>stiffness</b> "
        "from EI. A beam can be plenty strong and still unusably floppy - "
        "report both and let neither imply the other."),
    inputs=[
        Field("case", "Load case", "", 0, kind="choice",
              options=list(BEAM_CASES.keys())),
        Field("load", "Load (P in N, or w in N/m)", "", 500.0, min=0.0,
              help="Point load in newtons, or load per metre for the uniform "
                   "cases - the selected case decides which."),
        Field("length", "Span L", "m", 1.0, min=0.0),
        Field("modulus", "Young's modulus E", "GPa", 69.0, min=0.0,
              help="Aluminium 69, steel 200, titanium 114."),
        Field("second_moment", "Second moment of area I", "mm⁴", 1.0e5,
              min=0.0, help="From the Second moment of area page."),
        Field("extreme", "Distance to outer fibre c", "mm", 20.0, min=0.0),
    ],
    compute=lambda i: bending_stress(
        bending_moment(i.case, i.load, i.length),
        i.extreme / 1000.0, i.second_moment * 1e-12) / 1e6,
    result=Output("Maximum bending stress σ", "MPa"),
    secondary=[
        Secondary("Maximum bending moment", "N·m",
                  lambda i, r: bending_moment(i.case, i.load, i.length)),
        Secondary("Maximum deflection", "mm",
                  lambda i, r: beam_deflection(i.case, i.load, i.length,
                                               i.modulus * 1e9,
                                               i.second_moment * 1e-12) * 1000.0),
        Secondary("Deflection as a fraction of span", "L/x",
                  lambda i, r: i.length / max(beam_deflection(
                      i.case, i.load, i.length, i.modulus * 1e9,
                      i.second_moment * 1e-12), 1e-12)),
        Secondary("Safety factor against 276 MPa yield", "-",
                  lambda i, r: 276.0 / r if r > 0 else float("inf")),
    ],
    assumptions=[
        "EULER-BERNOULLI beam theory: plane sections stay plane and shear "
        "deformation is neglected. Valid for slender beams, span over depth of "
        "roughly 10 or more. Short deep beams deflect more than this predicts.",
        "Small deflections, linear elastic, stress below yield.",
        "Homogeneous isotropic material with a constant cross-section along "
        "the span.",
        "Deflection scales with L⁴ for uniform load and L³ for a point load - "
        "doubling the span is 8 to 16 times the sag. Span dominates everything "
        "else.",
        "The fixed-end cases assume genuinely rigid supports. Real bolted or "
        "bonded joints sit somewhere between pinned and fixed, so the true "
        "answer lies between the two cases - use them as bounds.",
        "The safety-factor figure uses 276 MPa (6061-T6 aluminium yield) purely "
        "as a reference point. Substitute your own material.",
    ],
    graph=Sweep(over="length", y_label="Maximum bending stress [MPa]",
                lo_factor=0.2, hi_factor=2.5,
                title="Stress vs span"),
    variables=[
        ("$\\sigma$", "Maximum bending stress", "Pa"),
        ("$M$", "Bending moment", "N·m"),
        ("$c$", "Distance from neutral axis to outer fibre", "m"),
        ("$I$", "Second moment of area", "m⁴"),
        ("$E$", "Young's modulus", "Pa"),
        ("$\\delta$", "Maximum deflection", "m"),
    ],
    example=(
        "A drone arm as a cantilever. A 500 N end load on a 1 m arm with "
        "I = 1e5 mm⁴ and c = 20 mm gives 100 MPa - safe in aluminium - but "
        "24 mm of deflection, which is L/41 and far too floppy to fly. "
        "Strength passed; stiffness failed."),
    keywords=("beam", "bending", "deflection", "cantilever", "stress", "span",
              "simply supported"),
)

_ELASTIC = Calculator(
    slug="struct.elastic_constants",
    name="Elastic constants (E, ν, G, K)",
    latex=(r"G = \frac{E}{2(1+\nu)}, \qquad K = \frac{E}{3(1-2\nu)}"),
    explanation=(
        "An isotropic material has only <b>two</b> independent elastic "
        "constants - give any two and the rest follow. Shear modulus G is what "
        "torsion needs; bulk modulus K describes resistance to uniform "
        "compression and runs away to infinity as ν approaches 0.5."),
    inputs=[
        Field("e", "Young's modulus E", "GPa", 69.0, min=0.0,
              help="Aluminium 69, steel 200, titanium 114."),
        Field("nu", "Poisson's ratio ν", "-", 0.33, min=-0.999, max=0.4999,
              help="Steel 0.29, aluminium 0.33, titanium 0.34, rubber ~0.4999."),
    ],
    compute=lambda i: shear_modulus(i.e * 1e9, i.nu) / 1e9,
    result=Output("Shear modulus G", "GPa"),
    secondary=[
        Secondary("Bulk modulus K", "GPa",
                  lambda i, r: bulk_modulus(i.e * 1e9, i.nu) / 1e9),
        Secondary("G as a fraction of E", "-", lambda i, r: r / i.e),
        Secondary("Lateral strain per unit axial strain", "-",
                  lambda i, r: -i.nu),
    ],
    note=lambda i, r: (
        "Poisson's ratio near 0.5 means a nearly incompressible material - "
        "rubber, say - and the bulk modulus runs away towards infinity."
        if i.nu > 0.47 else
        "Negative Poisson's ratio: an auxetic material, which gets fatter when "
        "stretched. Real but rare." if i.nu < 0 else None),
    assumptions=[
        "ISOTROPIC, homogeneous, linear elastic. These relations are exactly "
        "true for isotropic materials and simply invalid for composites, wood, "
        "or strongly textured rolled stock - a unidirectional laminate needs "
        "nine independent constants, not two.",
        "Thermodynamics bounds ν between -1 and 0.5. Engineering materials sit "
        "at 0.2 to 0.35; cork is near 0, and rubber approaches 0.5.",
        "At ν = 0.5 the material is incompressible and K is infinite. The input "
        "is capped just below to keep the arithmetic meaningful.",
        "Room temperature. Stiffness generally falls as temperature rises, and "
        "polymers change dramatically near their glass transition.",
    ],
    graph=Sweep(over="nu", y_label="Shear modulus G [GPa]", lo=0.0,
                hi_factor=1.45,
                title="Shear modulus vs Poisson's ratio at fixed E"),
    variables=[
        ("$E$", "Young's modulus", "Pa"),
        ("$\\nu$", "Poisson's ratio", "-"),
        ("$G$", "Shear modulus", "Pa"),
        ("$K$", "Bulk modulus", "Pa"),
    ],
    example=(
        "Getting G for a torsion calculation. Aluminium at E = 69 GPa and "
        "ν = 0.33 gives G = 25.9 GPa - about 38% of E, which is typical for "
        "metals. Torsional stiffness depends on G, not E, so using E there "
        "overestimates it by more than two and a half times."),
    keywords=("elastic", "poisson", "shear modulus", "bulk modulus", "isotropic"),
)

CALCULATORS = [_SECTION, _BEAM, _ELASTIC]
