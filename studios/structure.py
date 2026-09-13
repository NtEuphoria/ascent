"""Structure studio: a member under bending and axial compression.

The general case the other pages only touch one corner of, in the order the
sizing actually happens:

    the member  ->  the loading  ->  stability  ->  a verdict

A beam that is also a strut is the normal case in a real frame, and the two
failure modes it invites are not the same kind of thing. Bending and axial
compression add up into one stress you compare against yield. Buckling is not
a stress problem at all - a column goes unstable at a load that has nothing to
do with how strong the material is, and the formula that predicts it stops
being true below a slenderness this page works out and states.

Every number comes from the hand-checked functions in calculators/structures.py
and calculators/materials.py, so this page cannot drift away from what those
calculator pages say.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple

import streamlit as st

from calculators import materials, structures
from studios import shell
from utils import ui
from utils.constants import G0
from utils.formatting import format_number
from utils.spec import Calculator

PREFIX = "studio_structure"


class Material(NamedTuple):
    modulus: float          # E [Pa]
    yield_strength: float   # sigma_y [Pa]
    density: float          # rho [kg/m^3]


MATERIALS = {
    # E and yield match the lift-and-arm studio exactly, so the two pages
    # cannot quietly disagree about what "6061-T6" means.
    "Aluminium 6061-T6": Material(69e9, 276e6, 2700.0),
    "Aluminium 7075-T6": Material(72e9, 503e6, 2810.0),
    "Steel, mild (A36)": Material(200e9, 250e6, 7850.0),
    "4130 steel, normalised": Material(205e9, 435e6, 7850.0),
    "Titanium 6Al-4V": Material(114e9, 880e6, 4430.0),
    "Carbon fibre (quasi-isotropic)": Material(70e9, 600e6, 1600.0),
}

DEFAULT_SPAN_FRACTION = 250.0
"""Deflection limit as L/n. L/250 is the usual structural default for a member
carrying its full service load; L/360 is common under live load where a
plastered ceiling is hanging off it, and a machine tool wants far better. It is
a convention, not a law of nature - pick the one your job actually needs."""

DEFAULT_FACTOR_OF_SAFETY = 2.0
"""Applied to yield, not to ultimate. Yield is where the member stops coming
back to where it started, which for a structure is usually the failure that
matters, long before anything breaks."""


# ---------------------------------------------------------------------------
# 1. The member
# ---------------------------------------------------------------------------
class Member(NamedTuple):
    second_moment: float    # I [m^4], second moment of AREA about the bending
                            # axis - not a mass moment of inertia
    extreme: float          # c [m], neutral axis to the outermost fibre
    section_modulus: float  # Z = I / c [m^3]
    area: float             # A [m^2]
    gyration: float         # r = sqrt(I / A) [m]
    mass: float             # [kg]
    moment_capacity: float  # [N*m] moment that first yields the outer fibre


def member(section: str, width_mm: float, depth_mm: float, wall_mm: float,
           length_m: float, material: Material) -> Member:
    """Everything about the cross-section that the later steps need.

    Five numbers, all from the section library, and every one of them a
    different question about the same shape: I is how hard it is to bend, Z is
    how much moment it carries before the outer fibre yields, A is how much
    axial load it carries, r is how far the area effectively sits from the
    axis, and the mass is what you pay to have it.
    """
    length_m = float(length_m)
    if length_m <= 0:
        raise ValueError("Member length must be greater than zero.")

    width, depth, wall = width_mm / 1000.0, depth_mm / 1000.0, wall_mm / 1000.0
    second_moment = structures.second_moment_of_area(section, width, depth,
                                                     wall)
    extreme = structures.extreme_fibre(section, width, depth, wall)
    area = structures.section_area(section, width, depth, wall)
    modulus_z = structures.section_modulus(second_moment, extreme)
    gyration = structures.radius_of_gyration(second_moment, area)
    # Mass is the definition of density rearranged, m = rho * A * L. The only
    # arithmetic on this page that is not a call into a calculator module, and
    # the one thing here that is not a structural model.
    mass = material.density * area * length_m
    return Member(second_moment, extreme, modulus_z, area, gyration, mass,
                  material.yield_strength * modulus_z)


# ---------------------------------------------------------------------------
# 2. The loading
# ---------------------------------------------------------------------------
class Loading(NamedTuple):
    moment: float           # M [N*m] maximum for the chosen case
    bending_stress: float   # [Pa] at the extreme fibre
    axial_stress: float     # [Pa] magnitude, P / A
    combined_stress: float  # [Pa] the two superposed on the worst fibre
    deflection: float       # [m] maximum for the chosen case


def loading(memb: Member, case: str, load: float, length_m: float,
            axial_load: float, material: Material) -> Loading:
    """Bending from the load case, axial from the strut load, added.

    Superposition: on the compression face the bending stress and the axial
    compressive stress point the same way, so the worst fibre carries the sum.
    That is the fibre this studio checks. It is only legal because both are
    linear elastic responses of the same section - and it stops being true once
    anything yields.
    """
    moment = structures.bending_moment(case, load, length_m)
    bending = structures.bending_stress(moment, memb.extreme,
                                        memb.second_moment)
    # normal_stress signs compression negative; the magnitude is what adds to
    # the bending stress on the compression face.
    axial = abs(materials.normal_stress(abs(float(axial_load)), memb.area))
    deflection = structures.beam_deflection(case, load, length_m,
                                            material.modulus,
                                            memb.second_moment)
    return Loading(moment, bending, axial, abs(bending) + axial, deflection)


# ---------------------------------------------------------------------------
# 3. Stability
# ---------------------------------------------------------------------------
class Stability(NamedTuple):
    critical_load: float    # P_cr [N] from Euler
    critical_stress: float  # P_cr / A [Pa]
    slenderness: float      # KL / r [-]
    transition: float       # slenderness where Euler stops being usable [-]
    euler_applies: bool     # slenderness at or above the transition
    buckling_margin: float  # P_cr / P, 1.0 = exactly at the critical load


def stability(memb: Member, length_m: float, end_condition: str,
              axial_load: float, material: Material) -> Stability:
    """Whether the member goes unstable before anything about it yields.

    Nothing in the Euler load is a strength: P_cr = pi^2 E I / (KL)^2 contains
    stiffness and geometry only. Swapping mild steel for a heat-treated alloy
    of the same shape buys nothing at all here, which is the single most
    surprising thing about columns.
    """
    k_factor = structures.END_CONDITIONS[end_condition]
    critical = structures.euler_buckling_load(
        material.modulus, memb.second_moment, length_m, k_factor)
    slender = structures.slenderness_ratio(length_m, memb.gyration, k_factor)
    transition = structures.transition_slenderness(material.modulus,
                                                   material.yield_strength)
    axial = abs(float(axial_load))
    return Stability(
        critical, critical / memb.area, slender, transition,
        slender >= transition,
        critical / axial if axial > 0 else float("inf"))


# ---------------------------------------------------------------------------
# 4. The verdict
# ---------------------------------------------------------------------------
def verdicts(memb: Member, load_result: Loading, stab: Stability,
             length_m: float, material: Material,
             factor_of_safety: float = DEFAULT_FACTOR_OF_SAFETY,
             span_fraction: float = DEFAULT_SPAN_FRACTION
             ) -> List[Dict[str, object]]:
    """Every check this studio makes, with the margin that decided it.

    Margin reads the same on all four: 1.0 is exactly at the limit and below
    1.0 fails. Three of them are load checks. The fourth is not - it asks
    whether the buckling model used above is the right one at all, and it is
    the one worth reading first.
    """
    combined = load_result.combined_stress
    strength_margin = (
        materials.safety_factor(material.yield_strength, combined)
        / factor_of_safety if combined > 0 else float("inf"))

    limit = length_m / span_fraction
    stiffness_margin = (limit / load_result.deflection
                        if load_result.deflection > 0 else float("inf"))

    euler_margin = stab.slenderness / stab.transition
    if stab.euler_applies:
        euler_detail = (
            f"λ = {format_number(stab.slenderness, 3)} is at or above the "
            f"transition λ = {format_number(stab.transition, 3)}, so the Euler "
            f"curve is the right one here")
    else:
        euler_detail = (
            f"λ = {format_number(stab.slenderness, 3)} is below the transition "
            f"λ = {format_number(stab.transition, 3)}: Euler asks for "
            f"{format_number(stab.critical_stress / 1e6, 3)} MPa against a "
            f"{format_number(material.yield_strength / 1e6, 3)} MPa yield, so "
            f"P_cr above is an OVER-estimate of the real failure load")

    return [
        shell.check(
            "Combined stress", strength_margin >= 1.0, strength_margin,
            f"{format_number(combined / 1e6, 3)} MPa against "
            f"{format_number(material.yield_strength / 1e6, 3)} MPa yield, "
            f"wanted a factor of {format_number(factor_of_safety, 2)}"),
        shell.check(
            "Deflection", stiffness_margin >= 1.0, stiffness_margin,
            f"{format_number(load_result.deflection * 1000.0, 3)} mm against "
            f"an L/{format_number(span_fraction, 0)} limit of "
            f"{format_number(length_m / span_fraction * 1000.0, 3)} mm"),
        shell.check(
            "Buckling", stab.buckling_margin >= 1.0, stab.buckling_margin,
            f"P_cr = {format_number(stab.critical_load / 1000.0, 3)} kN "
            f"against the applied axial load, with no safety factor applied"),
        shell.check(
            "Euler validity", stab.euler_applies, euler_margin, euler_detail),
    ]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def render(prefs=None, catalogue=None) -> None:
    prefs = prefs or {}
    ui.page_header(
        "Structure",
        r"\sigma = \frac{M c}{I} + \frac{P}{A}, \qquad "
        r"P_{cr} = \frac{\pi^{2} E I}{(KL)^{2}}, \qquad "
        r"\lambda = \frac{KL}{r} \;\gtrless\; \sqrt{\frac{2\pi^{2}E}"
        r"{\sigma_y}}",
        "A member under bending and axial compression at the same time - the "
        "normal case in a real frame. Pick the section, pick the load case, "
        "add a strut load, and see whether it yields, sags, buckles, or "
        "whether the buckling formula even applies to something that stubby.",
        PREFIX)

    # -- 1 ------------------------------------------------------------------
    shell.step(1, "The member", "The cross-section, its span, and what it is "
                                "made of.")
    a, b, c, d = st.columns(4)
    with a:
        section = st.selectbox("Section", list(structures.SECTIONS), index=2,
                               key=f"{PREFIX}_section")
    with b:
        width = st.number_input("Width or diameter [mm]", value=25.0,
                                min_value=0.1, step=1.0, key=f"{PREFIX}_w")
    with c:
        depth = st.number_input("Depth [mm]", value=25.0, min_value=0.0,
                                step=1.0, key=f"{PREFIX}_d",
                                help="The dimension PARALLEL to the bending "
                                     "load. Ignored for circular sections.")
    with d:
        wall = st.number_input("Wall [mm]", value=2.0, min_value=0.0, step=0.5,
                               key=f"{PREFIX}_t")

    e, f = st.columns(2)
    with e:
        length = st.number_input("Length [m]", value=1.5, min_value=0.01,
                                 step=0.1, key=f"{PREFIX}_L",
                                 help="The same L is the bending span and the "
                                      "column length. A member that is braced "
                                      "part way along buckles over the braced "
                                      "length, not the whole one.")
    with f:
        material_name = st.selectbox("Material", list(MATERIALS),
                                     key=f"{PREFIX}_mat")
    material = MATERIALS[material_name]
    st.caption(structures.SECTIONS[section]["uses"])

    try:
        memb = member(section, width, depth, wall, length, material)
    except Exception as exc:
        st.error(f"{exc}")
        return

    shell.figures([
        ("Second moment of area I", memb.second_moment * 1e12, "mm⁴"),
        ("Section modulus Z", memb.section_modulus * 1e9, "mm³"),
        ("Area A", memb.area * 1e6, "mm²"),
        ("Radius of gyration r", memb.gyration * 1000.0, "mm"),
        ("Mass", memb.mass, "kg"),
    ])
    st.caption(
        f"I here is the second moment of AREA [m⁴], the resistance to bending "
        f"- not a mass moment of inertia [kg·m²] and not the polar J [m⁴]. "
        f"The member's own weight, {format_number(memb.mass * G0, 3)} N, is "
        f"NOT added to the load below; compare it against what you enter and "
        f"decide whether it matters.")

    # -- 2 ------------------------------------------------------------------
    shell.step(2, "The loading", "A bending case from the library, plus an "
                                 "axial squeeze.")
    case = st.selectbox("Bending case", list(structures.BEAM_CASES), index=2,
                        key=f"{PREFIX}_case")
    load_unit = structures.BEAM_CASES[case]["load_unit"]
    st.latex(structures.BEAM_CASES[case]["latex"])

    g, h, i = st.columns(3)
    with g:
        load = st.number_input(f"Transverse load [{load_unit}]", value=45.0,
                               min_value=0.0, step=5.0, key=f"{PREFIX}_load",
                               help="A point load in N, or a distributed load "
                                    "in N/m - the case decides which.")
    with h:
        axial = st.number_input("Axial compression [N]", value=800.0,
                                min_value=0.0, step=50.0, key=f"{PREFIX}_axial",
                                help="Squeezing the member along its length. "
                                     "Set it to zero for a pure beam.")
    with i:
        end_condition = st.selectbox("Column end condition",
                                     list(structures.END_CONDITIONS),
                                     key=f"{PREFIX}_ends",
                                     help="How the ends are held AGAINST "
                                          "BUCKLING. Chosen separately from "
                                          "the bending case, so keep the two "
                                          "physically consistent.")

    try:
        load_result = loading(memb, case, load, length, axial, material)
    except Exception as exc:
        st.error(f"{exc}")
        return

    shell.figures([
        ("Bending moment M", load_result.moment, "N·m"),
        ("Bending stress", load_result.bending_stress / 1e6, "MPa"),
        ("Axial stress", load_result.axial_stress / 1e6, "MPa"),
        ("Combined stress", load_result.combined_stress / 1e6, "MPa"),
        ("Deflection", load_result.deflection * 1000.0, "mm"),
    ])
    st.caption(
        "The two stresses are added on the compression face, where they point "
        "the same way. Deflection is from the transverse load alone - the "
        "extra bending an axial load causes by acting on an already-bent "
        "member (the P-δ effect) is not modelled, and it is unconservative "
        "exactly where the buckling margin is thin.")

    # -- 3 ------------------------------------------------------------------
    shell.step(3, "Stability", "Whether it goes unstable before it yields.")
    stab = stability(memb, length, end_condition, axial, material)
    shell.figures([
        ("Euler critical load P_cr", stab.critical_load / 1000.0, "kN"),
        ("Critical stress", stab.critical_stress / 1e6, "MPa"),
        ("Slenderness λ = KL/r", stab.slenderness, "-"),
        ("Transition λ", stab.transition, "-"),
    ])
    st.caption(
        f"At the transition slenderness the Euler critical stress is exactly "
        f"half the yield strength - that is what defines it. Below it the "
        f"column starts yielding on the way to buckling and the Euler "
        f"prediction runs away from reality; this member is at λ = "
        f"{format_number(stab.slenderness, 3)} against a transition of "
        f"{format_number(stab.transition, 3)}. Note that P_cr contains E and I "
        f"and no strength at all: a stronger alloy of the same shape buys "
        f"nothing here.")

    # -- 4 ------------------------------------------------------------------
    shell.step(4, "The verdict", "Whether what you described will actually "
                                 "stand up.")
    j, k = st.columns(2)
    with j:
        factor = st.number_input("Factor of safety on yield",
                                 value=DEFAULT_FACTOR_OF_SAFETY, min_value=1.0,
                                 step=0.1, key=f"{PREFIX}_fos")
    with k:
        span_fraction = st.number_input(
            "Deflection limit, L / n", value=DEFAULT_SPAN_FRACTION,
            min_value=1.0, step=10.0, key=f"{PREFIX}_span",
            help="L/250 is a common structural default. L/360 where something "
                 "brittle is attached, far stiffer for a machine.")

    shell.verdict_board(verdicts(memb, load_result, stab, length, material,
                                 factor, span_fraction))

    st.markdown('<div class="a-label">What the mass buys</div>',
                unsafe_allow_html=True)
    shell.figures([
        ("Specific strength σ_y/ρ",
         materials.specific_strength(material.yield_strength,
                                     material.density) / 1000.0, "kN·m/kg"),
        # Same arithmetic as specific_strength with E in place of yield: the
        # stiffness a kilogram of this material buys.
        ("Specific stiffness E/ρ", material.modulus / material.density / 1e6,
         "MN·m/kg"),
        ("Moment capacity", memb.moment_capacity, "N·m"),
        ("Capacity per kg", memb.moment_capacity / memb.mass, "N·m/kg"),
    ])
    st.caption(
        "Steel is stronger than aluminium and nearly three times as dense, so "
        "per kilogram carried it is the weaker choice - which is why aerospace "
        "structures are aluminium and carbon fibre even though a steel one "
        "would be smaller. Specific stiffness barely moves between steel, "
        "aluminium and titanium: they all sit near 25 MN·m/kg, so a "
        "stiffness-driven part gets no lighter by changing metal, only by "
        "changing shape - or by leaving metals altogether for a composite.")

    shell.send_to_project(PREFIX, [
        ("Member length", length, "m"),
        ("Second moment of area", memb.second_moment, "m⁴"),
        ("Member mass", memb.mass, "kg"),
        ("Combined stress", load_result.combined_stress, "Pa"),
        ("Euler critical load", stab.critical_load, "N"),
    ], note="from the structure studio")

    ui.assumptions([
        "I on this page is the SECOND MOMENT OF AREA [m⁴], the resistance to "
        "bending. It is not the mass moment of inertia [kg·m²] that the "
        "rotational pages use, and it is not the polar second moment J [m⁴] "
        "that resists twisting. The three share two letters and nothing else; "
        "mixing the first two is wrong by orders of magnitude, not by "
        "percent.",
        "Static stress only. Nothing here checks fatigue. Steel has a genuine "
        "endurance limit - below roughly half its ultimate strength it will "
        "cycle indefinitely - but ALUMINIUM HAS NO ENDURANCE LIMIT AT ALL. An "
        "aluminium member cycled long enough fails at any stress amplitude, so "
        "a passing static check here says nothing about a part that is loaded "
        "and unloaded millions of times.",
        "The member is prismatic, homogeneous and unbroken over its whole "
        "length. Real members are weakest at holes, welds, bolted joints and "
        "section changes: a hole concentrates stress by a factor of about "
        "three, a weld leaves a heat-affected zone that can lose a third of "
        "its parent strength (and in 6061 aluminium, far more than that), and "
        "none of it appears anywhere in these numbers. If it fails, it fails "
        "at a detail this page does not model.",
        "Bending and axial stress are superposed as a simple sum on the worst "
        "fibre, which is valid only while everything stays linear elastic. "
        "Compressive yield is taken equal to tensile yield - reasonable for "
        "the metals listed, wrong for composites and for anything brittle.",
        "The P-δ effect is ignored: the axial load acting on the member's own "
        "deflection adds bending that is not in the combined stress. That "
        "error grows as the axial load approaches P_cr, so a thin buckling "
        "margin makes the stress check optimistic as well.",
        "Buckling is checked about the SAME axis the bending uses. A real "
        "column buckles about its weakest axis, which for any section deeper "
        "than it is wide is the other one. Enter the weak-axis I if that is "
        "the axis that is free to go.",
        "Euler assumes a perfectly straight column, perfectly homogeneous, "
        "loaded exactly through the centroid. Real members arrive bent and are "
        "loaded slightly off-centre, so measured capacity sits below P_cr even "
        "where Euler applies. Design codes handle this with a column curve; "
        "this page does not.",
        "Local buckling is not modelled. A thin-walled tube or a slender web "
        "can crimp, dimple or fold well below the Euler load of the member as "
        "a whole - and the thinner the wall, the more likely local failure "
        "arrives first.",
        "Lateral-torsional buckling is not modelled either. A deep, narrow "
        "beam in bending can trip sideways and twist long before the "
        "compression flange yields, unless it is restrained along its length.",
        "The bending case and the column end condition are chosen "
        "independently, because a member's supports against bending and "
        "against buckling need not be the same. Nothing stops you picking a "
        "pair that could not physically coexist - that is on you.",
        "Deflection comes from bending only. Shear deflection is ignored, "
        "which is fine for a slender member and increasingly wrong for a "
        "short deep one, where it can add a noticeable fraction.",
        "The member's own weight is reported but NOT added to the load. For a "
        "long steel span carrying a light load it can be most of what the "
        "member is actually carrying.",
        f"The stiffness limit is whatever you set. L/{int(DEFAULT_SPAN_FRACTION)}"
        " is a common structural default rather than a standard, and the right "
        "number is the one your application needs.",
        "The carbon fibre entry is a quasi-isotropic in-plane average. A real "
        "laminate is only as good as its layup, and through the thickness - "
        "interlaminar - it is dramatically weaker than these figures suggest.",
    ])


CALCULATORS = [
    Calculator(slug="studio.structure", name="Structure", latex="",
               explanation="", render=render,
               keywords=("studio", "structure", "beam", "column", "strut",
                         "buckling", "euler", "slenderness", "bending",
                         "deflection", "section", "member", "workflow")),
]
