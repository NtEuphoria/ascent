"""Structures: section properties, beam bending, buckling, torsion and
elastic constants.

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

Mixing the first two is the expensive one: they differ by a factor with the
dimensions of mass per unit length, so the wrong one is not wrong by a few
percent, it is wrong by many orders of magnitude and in the wrong units.
"""
from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np

from utils import validation as v
from utils.spec import (Calculator, Check, Field, Output, Reference, Secondary,
                        Sweep)

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
        "needs": ("width", "depth"),
    }),
    ("Solid circle", {
        "formula": lambda b, h, t: np.pi * b ** 4 / 64.0,
        "area": lambda b, h, t: np.pi * b ** 2 / 4.0,
        "extreme": lambda b, h, t: b / 2.0,
        "latex": r"I = \frac{\pi d^{4}}{64}",
        "uses": "b = diameter. h and t are ignored.",
        "needs": ("width",),
    }),
    ("Hollow circle (tube)", {
        "formula": lambda b, h, t: np.pi * (b ** 4 - max(b - 2 * t, 0) ** 4)
        / 64.0,
        "area": lambda b, h, t: np.pi * (b ** 2 - max(b - 2 * t, 0) ** 2) / 4.0,
        "extreme": lambda b, h, t: b / 2.0,
        "latex": r"I = \frac{\pi (d_o^{4} - d_i^{4})}{64}",
        "uses": "b = outer diameter, t = wall thickness. h is ignored.",
        "needs": ("width", "thickness"),
    }),
    ("Hollow rectangle (box)", {
        "formula": lambda b, h, t: (b * h ** 3
                                    - max(b - 2 * t, 0)
                                    * max(h - 2 * t, 0) ** 3) / 12.0,
        "area": lambda b, h, t: b * h - max(b - 2 * t, 0) * max(h - 2 * t, 0),
        "extreme": lambda b, h, t: h / 2.0,
        "latex": r"I = \frac{B H^{3} - b h^{3}}{12}",
        "uses": "b = outer width, h = outer depth, t = wall thickness",
        "needs": ("width", "depth", "thickness"),
    }),
    # One thickness is used for both the flanges and the web. A real rolled
    # I-beam has a thicker flange than web; taking them equal is the honest
    # simplification for a page with one thickness box, and it under-estimates
    # I slightly for a typical rolled profile.
    ("I-beam (symmetric)", {
        "formula": lambda b, h, t: (b * h ** 3
                                    - max(b - t, 0)
                                    * max(h - 2 * t, 0) ** 3) / 12.0,
        "area": lambda b, h, t: b * h - max(b - t, 0) * max(h - 2 * t, 0),
        "extreme": lambda b, h, t: h / 2.0,
        "latex": r"I = \frac{B H^{3} - (B - t_w) h^{3}}{12}",
        "uses": "b = flange width, h = overall depth, t = flange AND web "
                "thickness (taken equal)",
        "needs": ("width", "depth", "thickness"),
    }),
])

# Effective-length factor K for Euler buckling: the multiplier on the real
# length that turns any column into the equivalent pinned-pinned one.
END_CONDITIONS = OrderedDict([
    ("Pinned - pinned (K = 1.0)", 1.0),
    ("Fixed - fixed (K = 0.5)", 0.5),
    ("Fixed - pinned (K = 0.7)", 0.7),
    ("Fixed - free, flagpole (K = 2.0)", 2.0),
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
    needs = SECTIONS[section].get("needs", ("width", "depth", "thickness"))
    # A circle has no depth and a solid bar has no wall. Demanding a positive
    # value for a dimension the formula never reads would make the page reject
    # a perfectly well-specified section.
    width = v.positive(width, "Width or diameter", "m")
    depth = (v.positive(depth, "Depth", "m") if "depth" in needs
             else float(depth or 0.0))
    thickness = v.non_negative(thickness, "Wall thickness", "m")
    if "Hollow" in section and thickness <= 0:
        raise v.ValidationError(
            "A hollow section needs a wall thickness greater than zero.")
    if "Hollow circle" in section and 2 * thickness >= width:
        raise v.ValidationError(
            "Wall thickness is at least half the outer diameter - the section "
            "would be solid or inside out.")
    if "I-beam" in section:
        if thickness <= 0:
            raise v.ValidationError(
                "An I-beam needs a flange/web thickness greater than zero.")
        if 2 * thickness >= depth or thickness >= width:
            raise v.ValidationError(
                "The flanges meet or the web is wider than the flange - that "
                "is a solid bar, not an I-beam.")
    return float(SECTIONS[section]["formula"](width, depth, thickness))


def extreme_fibre(section: str, width: float, depth: float,
                  thickness: float) -> float:
    """c, the distance from the neutral axis to the outermost fibre   [m]

    Named separately because it is the term people most often take from the
    wrong dimension: for a rectangle it is half the DEPTH, not half the width.
    """
    if section not in SECTIONS:
        raise v.ValidationError(f"Unknown section: {section}")
    return float(SECTIONS[section]["extreme"](width, depth, thickness))


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


def lame_first_parameter(youngs_modulus: float, poisson_ratio: float) -> float:
    """lambda = E nu / ((1 + nu)(1 - 2 nu))   [Pa]

    The other half of the (lambda, G) pair that finite-element codes actually
    store. Identically K - 2G/3.
    """
    youngs_modulus = v.positive(youngs_modulus, "Young's modulus", "Pa")
    poisson_ratio = v.in_range(poisson_ratio, "Poisson's ratio", -0.999, 0.4999)
    return (youngs_modulus * poisson_ratio
            / ((1.0 + poisson_ratio) * (1.0 - 2.0 * poisson_ratio)))


def constrained_modulus(youngs_modulus: float, poisson_ratio: float) -> float:
    """M = E(1 - nu) / ((1 + nu)(1 - 2 nu))   [Pa]

    Stiffness when sideways expansion is prevented - a thin bonded layer, soil
    in a confined column, the medium a longitudinal wave travels through.
    Identically K + 4G/3, and always stiffer than E.
    """
    youngs_modulus = v.positive(youngs_modulus, "Young's modulus", "Pa")
    poisson_ratio = v.in_range(poisson_ratio, "Poisson's ratio", -0.999, 0.4999)
    return (youngs_modulus * (1.0 - poisson_ratio)
            / ((1.0 + poisson_ratio) * (1.0 - 2.0 * poisson_ratio)))


# ---------------------------------------------------------------------------
# Torsion. J here is the POLAR SECOND MOMENT OF AREA [m^4], not the mass
# moment of inertia [kg*m^2] and not the torsion constant of a non-circular
# section - see the module docstring.
# ---------------------------------------------------------------------------


def polar_second_moment(outer_diameter: float,
                        inner_diameter: float = 0.0) -> float:
    """J = pi (d_o^4 - d_i^4) / 32   [m^4] - resistance to TWISTING.

    Circular sections only. For any circle J = 2I exactly, because the
    perpendicular-axis theorem gives J = I_x + I_y and the two are equal.
    """
    outer_diameter = v.positive(outer_diameter, "Outer diameter", "m")
    inner_diameter = v.non_negative(inner_diameter, "Inner diameter", "m")
    if inner_diameter >= outer_diameter:
        raise v.ValidationError(
            "The bore is at least as large as the shaft - there is no "
            "material left to carry the torque.")
    return math.pi * (outer_diameter ** 4 - inner_diameter ** 4) / 32.0


def torsional_shear_stress(torque: float, radius: float,
                           polar_moment: float) -> float:
    """tau = T r / J   [Pa], maximum at the outer surface.

    Shear stress varies linearly from zero on the axis to this value at the
    skin, which is why a hollow shaft loses so little strength.
    """
    torque = v.non_negative(torque, "Torque", "N*m")
    radius = v.positive(radius, "Radius", "m")
    polar_moment = v.positive(polar_moment, "Polar second moment", "m^4")
    return torque * radius / polar_moment


def angle_of_twist(torque: float, length: float, shear_mod: float,
                   polar_moment: float) -> float:
    """theta = T L / (G J)   [rad] over the whole length."""
    torque = v.non_negative(torque, "Torque", "N*m")
    length = v.positive(length, "Length", "m")
    shear_mod = v.positive(shear_mod, "Shear modulus", "Pa")
    polar_moment = v.positive(polar_moment, "Polar second moment", "m^4")
    return torque * length / (shear_mod * polar_moment)


# ---------------------------------------------------------------------------
# Column buckling
# ---------------------------------------------------------------------------


def euler_buckling_load(youngs_modulus: float, second_moment: float,
                        length: float, k_factor: float = 1.0) -> float:
    """P_cr = pi^2 E I / (K L)^2   [N]

    The load at which a perfectly straight elastic column stops being stable.
    Strength does not appear anywhere in it: a column buckles because it is
    slender, and a stronger alloy of the same metal does not help at all.
    """
    youngs_modulus = v.positive(youngs_modulus, "Young's modulus", "Pa")
    second_moment = v.positive(second_moment, "Second moment of area", "m^4")
    length = v.positive(length, "Column length", "m")
    k_factor = v.positive(k_factor, "End-condition factor K", "-")
    return (math.pi ** 2 * youngs_modulus * second_moment
            / (k_factor * length) ** 2)


def radius_of_gyration(second_moment: float, area: float) -> float:
    """r = sqrt(I / A)   [m] - how far from the axis the area effectively sits."""
    second_moment = v.positive(second_moment, "Second moment of area", "m^4")
    area = v.positive(area, "Cross-sectional area", "m^2")
    return math.sqrt(second_moment / area)


def slenderness_ratio(length: float, gyration: float,
                      k_factor: float = 1.0) -> float:
    """K L / r   [-] - the single number that decides how a column fails."""
    length = v.positive(length, "Column length", "m")
    gyration = v.positive(gyration, "Radius of gyration", "m")
    k_factor = v.positive(k_factor, "End-condition factor K", "-")
    return k_factor * length / gyration


def transition_slenderness(youngs_modulus: float, yield_strength: float) -> float:
    """sqrt(2 pi^2 E / sigma_y)   [-] - where Euler stops being usable.

    Below this slenderness the Euler curve predicts a critical stress above
    half the yield strength, the column yields on the way to buckling, and the
    prediction becomes an over-estimate. It is the tangency point of the Euler
    hyperbola and the J.B. Johnson parabola.
    """
    youngs_modulus = v.positive(youngs_modulus, "Young's modulus", "Pa")
    yield_strength = v.positive(yield_strength, "Yield strength", "Pa")
    return math.sqrt(2.0 * math.pi ** 2 * youngs_modulus / yield_strength)




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

_MATERIALS = Reference(
    title="Material properties",
    columns=("Material", "E [GPa]", "Yield [MPa]", "Density [kg/m³]"),
    rows=[
        ("Aluminium 6061-T6", "69", "276", "2700"),
        ("Aluminium 7075-T6", "72", "503", "2810"),
        ("Mild steel (A36)", "200", "250", "7850"),
        ("4130 steel, normalised", "205", "435", "7850"),
        ("Stainless 304, annealed", "193", "215", "8000"),
        ("Titanium 6Al-4V", "114", "880", "4430"),
        ("Carbon fibre, quasi-isotropic", "~70", "~600", "1600"),
        ("PLA (printed)", "3.5", "50", "1250"),
        ("ABS (printed)", "2.2", "40", "1040"),
    ],
    note="Typical published values for wrought material. A printed part is "
         "weaker across its layers than along them, often by half, and a "
         "composite laminate depends entirely on its layup - treat both rows "
         "as order-of-magnitude only.",
)

_TORSION = Calculator(
    slug="struct.torsion",
    name="Torsion of a shaft",
    latex=r"\tau = \frac{T r}{J}, \qquad \theta = \frac{T L}{G J}",
    explanation=(
        "A shaft carrying torque twists, and the shear stress is highest at "
        "the outer surface. Both depend on the <b>polar</b> second moment J, "
        "not the bending I - and on the <b>shear</b> modulus G, not E. Using E "
        "here overestimates stiffness by roughly two and a half times for a "
        "metal, which is one of the most common errors in shaft design."),
    inputs=[
        Field("torque", "Torque T", "N·m", 80.0, min=0.0),
        Field("outer", "Outer diameter", "mm", 25.0, min=0.0),
        Field("wall", "Wall thickness", "mm", 3.0, min=0.0,
              help="Set this to half the outer diameter or more for a solid "
                   "shaft."),
        Field("length", "Shaft length L", "m", 1.2, min=0.0),
        Field("shear_mod", "Shear modulus G", "GPa", 76.9, min=0.0,
              help="Steel about 77, aluminium about 26, titanium about 44. "
                   "Compute it from E and ν on the elastic-constants page."),
    ],
    compute=lambda i: torsional_shear_stress(
        i.torque, i.outer / 2000.0,
        polar_second_moment(i.outer / 1000.0,
                            max(i.outer - 2 * i.wall, 0.0) / 1000.0)),
    result=Output("Peak shear stress τ", "Pa"),
    secondary=[
        Secondary("In MPa", "MPa", lambda i, r: r / 1e6),
        Secondary("Polar second moment J", "mm⁴",
                  lambda i, r: polar_second_moment(
                      i.outer / 1000.0,
                      max(i.outer - 2 * i.wall, 0.0) / 1000.0) * 1e12),
        Secondary("Angle of twist", "degrees",
                  lambda i, r: np.degrees(angle_of_twist(
                      i.torque, i.length, i.shear_mod * 1e9,
                      polar_second_moment(
                          i.outer / 1000.0,
                          max(i.outer - 2 * i.wall, 0.0) / 1000.0)))),
        Secondary("Twist per metre", "degrees/m",
                  lambda i, r: np.degrees(angle_of_twist(
                      i.torque, 1.0, i.shear_mod * 1e9,
                      polar_second_moment(
                          i.outer / 1000.0,
                          max(i.outer - 2 * i.wall, 0.0) / 1000.0)))),
        Secondary("Torsional stiffness GJ/L", "N·m/rad",
                  lambda i, r: i.shear_mod * 1e9 * polar_second_moment(
                      i.outer / 1000.0,
                      max(i.outer - 2 * i.wall, 0.0) / 1000.0) / i.length),
    ],
    checks=[
        Check(lambda i, r: ("danger",
                            f"Peak shear stress is {r / 1e6:.0f} MPa. Steel "
                            "shears at roughly 0.58 of its tensile yield, so "
                            "mild steel gives up near 145 MPa - this shaft is "
                            "past it.") if r > 145e6 else None),
        Check(lambda i, r: ("info",
                            "Twist is over 1 degree per metre. That is the "
                            "usual rule-of-thumb limit for a power "
                            "transmission shaft; for a precision positioning "
                            "shaft it is already far too much.")
              if np.degrees(angle_of_twist(
                  i.torque, 1.0, i.shear_mod * 1e9,
                  polar_second_moment(
                      i.outer / 1000.0,
                      max(i.outer - 2 * i.wall, 0.0) / 1000.0))) > 1.0
              else None),
    ],
    references=[
        Reference(
            title="Shear modulus",
            columns=("Material", "G [GPa]", "G/E"),
            rows=[("Steel", "77", "0.38"), ("Aluminium", "26", "0.38"),
                  ("Titanium", "44", "0.38"), ("Brass", "37", "0.37"),
                  ("Carbon fibre, quasi-isotropic", "~5", "~0.07")],
            note="For isotropic metals G is close to 0.38 E because Poisson's "
                 "ratio sits near 0.3. A composite is nothing like isotropic "
                 "and its shear modulus is far lower than that ratio implies.",
        ),
    ],
    assumptions=[
        "J here is the POLAR second moment of area in m⁴ - resistance to "
        "twisting. It is not the bending I, and it is not the mass moment of "
        "inertia in kg·m². For a circular section J = 2I, but only for a "
        "circular section.",
        "Circular sections only. These formulas are wrong for a square or "
        "open channel section, where warping dominates and a square shaft is "
        "far more flexible in torsion than its size suggests.",
        "Linear elastic material, below the shear yield point.",
        "Uniform torque along the shaft, with no stress raisers. A keyway, "
        "step or cross-hole concentrates stress by a factor of 2 to 3 and is "
        "where shafts actually break.",
        "Small angles of twist, and no buckling of a thin wall.",
    ],
    graphs=[
        Sweep(over="outer", y_label="Peak shear stress τ [Pa]",
              lo_factor=0.5, hi_factor=1.8,
              title="Stress vs outer diameter"),
        Sweep(over="torque", y_label="Peak shear stress τ [Pa]", lo=0.0,
              hi_factor=2.0, title="Stress vs torque"),
        Sweep(over="wall", y_label="Peak shear stress τ [Pa]",
              lo_factor=0.3, hi_factor=2.0,
              title="Stress vs wall thickness"),
    ],
    variables=[
        ("$\\tau$", "Shear stress at the outer surface", "Pa"),
        ("$T$", "Applied torque", "N·m"),
        ("$r$", "Outer radius", "m"),
        ("$J$", "Polar second moment of area", "m⁴"),
        ("$G$", "Shear modulus", "Pa"),
        ("$L$", "Shaft length", "m"),
        ("$\\theta$", "Angle of twist", "rad"),
    ],
    example=(
        "A steel drive shaft, 25 mm outer diameter with a 3 mm wall, 1.2 m "
        "long, carrying 80 N·m. J = 2.56e4 mm⁴, peak shear stress 39.1 MPa - "
        "comfortable for steel - but it twists 2.80 degrees over its length. "
        "Strong enough and far too soft, which is exactly why both numbers "
        "are shown."),
    related=["struct.second_moment", "struct.elastic_constants",
             "struct.beam_bending", "struct.buckling"],
    keywords=("torsion", "twist", "shaft", "polar", "shear stress", "torque"),
)

_BUCKLING = Calculator(
    slug="struct.buckling",
    name="Column buckling",
    latex=r"P_{cr} = \frac{\pi^{2} E I}{(K L)^{2}}",
    explanation=(
        "A slender column fails by buckling sideways long before the material "
        "is anywhere near its yield stress, and the load it goes at depends "
        "on stiffness rather than strength. Making it out of a stronger alloy "
        "changes nothing; making it fatter or shorter changes everything."),
    inputs=[
        Field("modulus", "Young's modulus E", "GPa", 69.0, min=0.0,
              help="Aluminium 69, steel 200, titanium 114."),
        Field("outer", "Tube outer diameter", "mm", 25.0, min=0.0),
        Field("wall", "Wall thickness", "mm", 2.0, min=0.0),
        Field("length", "Column length L", "m", 1.5, min=0.0),
        Field("k_factor", "End condition", "", 0, kind="choice",
              options=list(END_CONDITIONS.keys())),
        Field("yield_strength", "Yield strength", "MPa", 276.0, min=0.0,
              help="Used to say whether Euler still applies at this "
                   "slenderness."),
    ],
    compute=lambda i: euler_buckling_load(
        i.modulus * 1e9,
        second_moment_of_area("Hollow circle (tube)", i.outer / 1000.0, 0.0,
                              i.wall / 1000.0),
        END_CONDITIONS[i.k_factor], i.length),
    result=Output("Critical buckling load P_cr", "N"),
    secondary=[
        Secondary("Mass this supports at 1 g", "kg", lambda i, r: r / 9.80665),
        Secondary("Critical stress P/A", "MPa",
                  lambda i, r: r / section_area(
                      "Hollow circle (tube)", i.outer / 1000.0, 0.0,
                      i.wall / 1000.0) / 1e6),
        Secondary("Slenderness ratio KL/r", "-",
                  lambda i, r: slenderness_ratio(
                      i.length,
                      radius_of_gyration(
                          second_moment_of_area(
                              "Hollow circle (tube)", i.outer / 1000.0, 0.0,
                              i.wall / 1000.0),
                          section_area("Hollow circle (tube)",
                                       i.outer / 1000.0, 0.0,
                                       i.wall / 1000.0)),
                      END_CONDITIONS[i.k_factor])),
        Secondary("Euler is valid above KL/r of", "-",
                  lambda i, r: transition_slenderness(i.modulus * 1e9,
                                                     i.yield_strength * 1e6)),
        Secondary("Effective length KL", "m",
                  lambda i, r: END_CONDITIONS[i.k_factor] * i.length),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            "This column is too stocky for the Euler formula. "
                            "Below the transition slenderness the column "
                            "yields on its way to buckling, and Euler "
                            "over-predicts the failure load - sometimes by a "
                            "lot. Use a Johnson parabola or simply check the "
                            "squash load P = A·σ_yield instead.")
              if slenderness_ratio(
                  i.length,
                  radius_of_gyration(
                      second_moment_of_area("Hollow circle (tube)",
                                            i.outer / 1000.0, 0.0,
                                            i.wall / 1000.0),
                      section_area("Hollow circle (tube)", i.outer / 1000.0,
                                   0.0, i.wall / 1000.0)),
                  END_CONDITIONS[i.k_factor])
              < transition_slenderness(i.modulus * 1e9,
                                       i.yield_strength * 1e6) else None),
        Check(lambda i, r: ("info",
                            "A fixed-free column has K = 2, so it buckles at "
                            "a quarter of the pinned-pinned load. End "
                            "conditions are squared - they matter as much as "
                            "the section does.")
              if END_CONDITIONS[i.k_factor] >= 2.0 else None),
    ],
    references=[
        Reference(
            title="Effective-length factor K",
            columns=("End conditions", "K", "P_cr relative to pinned"),
            rows=[("Fixed - fixed", "0.5", "4.0x"),
                  ("Fixed - pinned", "0.7", "2.0x"),
                  ("Pinned - pinned", "1.0", "1.0x"),
                  ("Fixed - free (flagpole)", "2.0", "0.25x")],
            note="Theoretical values. Real joints are never perfectly fixed, "
                 "so design codes use more conservative numbers - 0.65 and "
                 "0.80 in place of 0.5 and 0.7, and 2.10 for a flagpole.",
        ),
        _MATERIALS,
    ],
    assumptions=[
        "Perfectly straight column, perfectly centred load, no initial bow. "
        "Real columns have all three imperfections and fail below P_cr - this "
        "is an upper bound, not a design value.",
        "Euler applies only to SLENDER columns. Below the transition "
        "slenderness shown above, the material yields first and this formula "
        "over-predicts the failure load.",
        "Pin-ended buckling in the weakest direction. A section with "
        "different I about two axes buckles about the smaller one; this page "
        "uses a tube, which is the same in every direction.",
        "Elastic material throughout. Buckling that begins after yielding "
        "needs the tangent modulus, not E.",
        "No lateral bracing anywhere along the length. One brace at "
        "mid-height quarters the effective length and so quadruples the load.",
        "I here is the SECOND MOMENT OF AREA in m⁴, not the mass moment of "
        "inertia in kg·m².",
    ],
    graphs=[
        Sweep(over="length", y_label="Critical load P_cr [N]",
              lo_factor=0.4, hi_factor=2.0, log_y=True,
              title="Buckling load vs length"),
        Sweep(over="outer", y_label="Critical load P_cr [N]",
              lo_factor=0.6, hi_factor=1.8,
              title="Buckling load vs diameter"),
        Sweep(over="wall", y_label="Critical load P_cr [N]",
              lo_factor=0.3, hi_factor=2.0,
              title="Buckling load vs wall thickness"),
    ],
    variables=[
        ("$P_{cr}$", "Critical buckling load", "N"),
        ("$E$", "Young's modulus", "Pa"),
        ("$I$", "Second moment of area (smallest axis)", "m⁴"),
        ("$K$", "Effective-length factor", "-"),
        ("$L$", "Column length", "m"),
        ("$r$", "Radius of gyration, sqrt(I/A)", "m"),
    ],
    example=(
        "A 6061-T6 tube leg, 25 mm outer diameter with a 2 mm wall, 1.5 m "
        "long and pinned at both ends. P_cr = 2910 N - about 297 kg. Its "
        "slenderness ratio is 184, well above the transition value of 70, so "
        "Euler genuinely applies. The critical stress is only 20.2 MPa "
        "against a yield of 276 MPa: the material is nowhere near its limit "
        "and never gets the chance."),
    related=["struct.second_moment", "struct.beam_bending", "struct.torsion"],
    keywords=("buckling", "euler", "column", "strut", "slenderness",
              "critical load", "compression"),
)

CALCULATORS = [_SECTION, _BEAM, _TORSION, _BUCKLING, _ELASTIC]
