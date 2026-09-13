"""The structure studio.

A studio reimplements no physics - it chains the same hand-checked functions
the calculator pages use - so what these tests defend is the chaining: that
each quantity handed from one step to the next means what the next step thinks
it means, and that the verdicts move in the right direction.

The one exception is the member's mass, which is the definition of density
rearranged rather than a call into a calculator module, so it gets a test with
an independently derived expected value.
"""
from __future__ import annotations

import math

import pytest

from conftest import goto

from calculators import materials, structures
from studios import structure
from studios.structure import (MATERIALS, Material, loading, member, stability,
                               verdicts)

ALUMINIUM = MATERIALS["Aluminium 6061-T6"]
STEEL = MATERIALS["Steel, mild (A36)"]

TUBE = ("Hollow circle (tube)", 25.0, 25.0, 2.0)
"""The page's default member: a 25 mm aluminium tube with a 2 mm wall."""

CASE = "Simply supported, centre point load"


def default_member(material: Material = ALUMINIUM, length: float = 1.5):
    return member(*TUBE, length, material)


# --------------------------------------------------------------------------
# 1. The member
# --------------------------------------------------------------------------
def test_the_section_properties_come_from_the_section_library():
    """Including the mm to m conversion, which is the easiest thing on the
    page to get wrong by a factor of a thousand to the fourth power."""
    memb = default_member()
    assert memb.second_moment == pytest.approx(
        structures.second_moment_of_area("Hollow circle (tube)", 0.025, 0.025,
                                         0.002))
    assert memb.area == pytest.approx(
        structures.section_area("Hollow circle (tube)", 0.025, 0.025, 0.002))
    assert memb.extreme == pytest.approx(0.0125)


def test_section_modulus_is_the_second_moment_over_the_extreme_fibre():
    memb = default_member()
    assert memb.section_modulus == pytest.approx(
        memb.second_moment / memb.extreme)


def test_radius_of_gyration_is_the_root_of_i_over_a():
    memb = default_member()
    assert memb.gyration == pytest.approx(
        math.sqrt(memb.second_moment / memb.area))


def test_mass_is_density_times_area_times_length():
    """Hand-checked against a value derived without this module: a 100 x 50 mm
    solid steel bar 2 m long is 0.005 m^2 by 2 m = 0.01 m^3, and at
    7850 kg/m^3 that is 78.5 kg."""
    memb = member("Solid rectangle", 100.0, 50.0, 0.0, 2.0, STEEL)
    assert memb.area == pytest.approx(0.005)
    assert memb.mass == pytest.approx(78.5)


def test_moment_capacity_is_yield_times_the_section_modulus():
    """The moment that first yields the outer fibre - the inverse of the
    bending stress formula, so the two cannot disagree."""
    memb = default_member()
    assert memb.moment_capacity == pytest.approx(
        ALUMINIUM.yield_strength * memb.section_modulus)
    at_capacity = structures.bending_stress(memb.moment_capacity, memb.extreme,
                                            memb.second_moment)
    assert at_capacity == pytest.approx(ALUMINIUM.yield_strength)


def test_standing_a_rectangle_on_edge_multiplies_i_by_four():
    """Depth is cubed. Doubling it at constant area is worth more than any
    change of material available."""
    flat = member("Solid rectangle", 40.0, 20.0, 0.0, 1.0, ALUMINIUM)
    edge = member("Solid rectangle", 20.0, 40.0, 0.0, 1.0, ALUMINIUM)
    assert edge.second_moment / flat.second_moment == pytest.approx(4.0)
    assert edge.mass == pytest.approx(flat.mass)


def test_a_zero_length_member_is_refused_rather_than_massless():
    with pytest.raises(ValueError):
        member(*TUBE, 0.0, ALUMINIUM)
    with pytest.raises(ValueError):
        member(*TUBE, -1.0, ALUMINIUM)


# --------------------------------------------------------------------------
# 2. The loading
# --------------------------------------------------------------------------
def test_bending_stress_is_the_case_moment_through_the_section():
    memb = default_member()
    result = loading(memb, CASE, 45.0, 1.5, 800.0, ALUMINIUM)
    expected_moment = structures.bending_moment(CASE, 45.0, 1.5)
    assert result.moment == pytest.approx(expected_moment)
    assert result.bending_stress == pytest.approx(
        structures.bending_stress(expected_moment, memb.extreme,
                                  memb.second_moment))


def test_axial_stress_is_the_load_spread_over_the_area():
    """Hand-checked: 1000 N on a 10 x 10 mm bar is 1e-4 m^2, so 10 MPa."""
    memb = member("Solid rectangle", 10.0, 10.0, 0.0, 1.0, ALUMINIUM)
    result = loading(memb, CASE, 0.0, 1.0, 1000.0, ALUMINIUM)
    assert memb.area == pytest.approx(1e-4)
    assert result.axial_stress == pytest.approx(10e6)


def test_the_combined_stress_is_the_two_superposed():
    """On the compression face they point the same way, so the worst fibre
    carries the sum. This is the number the verdict judges."""
    memb = default_member()
    result = loading(memb, CASE, 45.0, 1.5, 800.0, ALUMINIUM)
    assert result.combined_stress == pytest.approx(
        result.bending_stress + result.axial_stress)
    assert result.combined_stress > result.bending_stress


def test_removing_the_axial_load_leaves_pure_bending():
    memb = default_member()
    beam_only = loading(memb, CASE, 45.0, 1.5, 0.0, ALUMINIUM)
    assert beam_only.axial_stress == pytest.approx(0.0)
    assert beam_only.combined_stress == pytest.approx(beam_only.bending_stress)


def test_removing_the_transverse_load_leaves_a_pure_strut():
    memb = default_member()
    strut = loading(memb, CASE, 0.0, 1.5, 800.0, ALUMINIUM)
    assert strut.moment == pytest.approx(0.0)
    assert strut.deflection == pytest.approx(0.0)
    assert strut.combined_stress == pytest.approx(strut.axial_stress)


def test_a_stiffer_material_changes_deflection_but_not_stress():
    """Stress is load and geometry; only deflection cares about E. The
    expensive misunderstanding this page exists partly to prevent."""
    memb_al = default_member(ALUMINIUM)
    memb_st = member(*TUBE, 1.5, STEEL)
    al = loading(memb_al, CASE, 45.0, 1.5, 800.0, ALUMINIUM)
    st = loading(memb_st, CASE, 45.0, 1.5, 800.0, STEEL)
    assert st.combined_stress == pytest.approx(al.combined_stress)
    assert st.deflection < al.deflection
    assert al.deflection / st.deflection == pytest.approx(200.0 / 69.0)


def test_the_case_library_decides_the_moment():
    """A cantilever with the load at the tip carries four times the moment a
    simply supported member of the same span does - the reason the load case
    is a choice and not a constant."""
    memb = default_member()
    tip = loading(memb, "Cantilever, point load at the end", 45.0, 1.5, 0.0,
                  ALUMINIUM)
    centre = loading(memb, CASE, 45.0, 1.5, 0.0, ALUMINIUM)
    assert tip.moment / centre.moment == pytest.approx(4.0)
    assert tip.bending_stress / centre.bending_stress == pytest.approx(4.0)


def test_every_case_in_the_library_can_be_loaded():
    """A new entry in BEAM_CASES must not be able to break this page
    silently."""
    memb = default_member()
    for case in structures.BEAM_CASES:
        result = loading(memb, case, 45.0, 1.5, 800.0, ALUMINIUM)
        assert result.moment > 0
        assert result.deflection > 0


# --------------------------------------------------------------------------
# 3. Stability
# --------------------------------------------------------------------------
def test_the_critical_load_is_the_euler_load_for_that_end_condition():
    memb = default_member()
    stab = stability(memb, 1.5, "Fixed - pinned (K = 0.7)", 800.0, ALUMINIUM)
    assert stab.critical_load == pytest.approx(
        structures.euler_buckling_load(ALUMINIUM.modulus, memb.second_moment,
                                       1.5, 0.7))
    assert stab.slenderness == pytest.approx(
        structures.slenderness_ratio(1.5, memb.gyration, 0.7))


def test_holding_both_ends_quadruples_the_critical_load():
    """K halves from 1.0 to 0.5 and it appears squared, so the same member
    carries four times as much simply by being clamped."""
    memb = default_member()
    pinned = stability(memb, 1.5, "Pinned - pinned (K = 1.0)", 800.0,
                       ALUMINIUM)
    fixed = stability(memb, 1.5, "Fixed - fixed (K = 0.5)", 800.0, ALUMINIUM)
    assert fixed.critical_load / pinned.critical_load == pytest.approx(4.0)
    assert fixed.slenderness / pinned.slenderness == pytest.approx(0.5)


def test_a_flagpole_is_the_worst_case_in_the_library():
    memb = default_member()
    loads = {name: stability(memb, 1.5, name, 800.0, ALUMINIUM).critical_load
             for name in structures.END_CONDITIONS}
    assert min(loads, key=loads.get) == "Fixed - free, flagpole (K = 2.0)"


def test_a_stronger_alloy_does_not_help_a_column_at_all():
    """P_cr contains E and I and no strength whatsoever. The most surprising
    thing about columns, and the reason this studio separates the stress check
    from the buckling check."""
    memb = default_member()
    weak = Material(ALUMINIUM.modulus, 100e6, ALUMINIUM.density)
    strong = Material(ALUMINIUM.modulus, 900e6, ALUMINIUM.density)
    assert (stability(memb, 1.5, "Pinned - pinned (K = 1.0)", 800.0,
                      weak).critical_load
            == pytest.approx(stability(memb, 1.5, "Pinned - pinned (K = 1.0)",
                                       800.0, strong).critical_load))


def test_a_stronger_alloy_does_move_the_transition_slenderness():
    """It changes nothing about where the column buckles, only about where
    Euler stops being the right description of it - and it moves the wrong
    way: a stronger alloy needs a MORE slender column before Euler applies."""
    memb = default_member()
    weak = Material(ALUMINIUM.modulus, 100e6, ALUMINIUM.density)
    strong = Material(ALUMINIUM.modulus, 900e6, ALUMINIUM.density)
    ends = "Pinned - pinned (K = 1.0)"
    assert (stability(memb, 1.5, ends, 800.0, strong).transition
            < stability(memb, 1.5, ends, 800.0, weak).transition)


def test_at_the_transition_the_euler_stress_is_half_the_yield_strength():
    """What the transition slenderness actually means, and the claim the page
    makes in its caption. Derived by hand rather than taken from the module:
    sigma_cr = pi^2 E / lambda^2, and at lambda = sqrt(2 pi^2 E / sigma_y)
    that collapses to sigma_y / 2."""
    for material in MATERIALS.values():
        transition = structures.transition_slenderness(material.modulus,
                                                       material.yield_strength)
        euler_stress = math.pi ** 2 * material.modulus / transition ** 2
        assert euler_stress == pytest.approx(material.yield_strength / 2.0)


def test_a_slender_member_is_an_euler_column_and_a_stubby_one_is_not():
    memb = default_member()
    ends = "Pinned - pinned (K = 1.0)"
    assert stability(memb, 1.5, ends, 800.0, ALUMINIUM).euler_applies
    assert not stability(memb, 0.3, ends, 800.0, ALUMINIUM).euler_applies


def test_below_the_transition_euler_over_predicts_the_failure_load():
    """Not by a little. A 50 mm steel bar 200 mm long is nowhere near a
    column, and the Euler formula still hands back a critical stress an order
    of magnitude above anything the steel could reach."""
    memb = member("Solid circle", 50.0, 0.0, 0.0, 0.2, STEEL)
    stab = stability(memb, 0.2, "Pinned - pinned (K = 1.0)", 10e3, STEEL)
    assert not stab.euler_applies
    assert stab.critical_stress > 10.0 * STEEL.yield_strength


def test_the_buckling_margin_is_one_exactly_at_the_critical_load():
    """The number a reader has to be able to trust: below one it goes."""
    memb = default_member()
    ends = "Pinned - pinned (K = 1.0)"
    critical = stability(memb, 1.5, ends, 1.0, ALUMINIUM).critical_load
    assert stability(memb, 1.5, ends, critical,
                     ALUMINIUM).buckling_margin == pytest.approx(1.0)


def test_a_member_with_no_axial_load_never_buckles():
    memb = default_member()
    stab = stability(memb, 1.5, "Pinned - pinned (K = 1.0)", 0.0, ALUMINIUM)
    assert stab.buckling_margin == float("inf")


# --------------------------------------------------------------------------
# 4. The verdict
# --------------------------------------------------------------------------
def check_named(result, label):
    return next(item for item in result if item["label"] == label)


def default_verdicts(length=1.5, material=ALUMINIUM, load=45.0, axial=800.0,
                     ends="Pinned - pinned (K = 1.0)", case=CASE,
                     factor=structure.DEFAULT_FACTOR_OF_SAFETY,
                     fraction=structure.DEFAULT_SPAN_FRACTION,
                     section=TUBE):
    memb = member(*section, length, material)
    return verdicts(memb, loading(memb, case, load, length, axial, material),
                    stability(memb, length, ends, axial, material),
                    length, material, factor, fraction)


def test_the_pages_default_design_passes_every_check():
    assert all(item["ok"] for item in default_verdicts())


def test_there_are_four_checks_and_the_last_is_about_the_model():
    result = default_verdicts()
    assert [item["label"] for item in result] == [
        "Combined stress", "Deflection", "Buckling", "Euler validity"]


def test_margin_and_verdict_never_disagree():
    """Margin reads the same on all four checks - one is exactly at the limit
    and below one fails. A check whose margin said otherwise would quietly
    mislead every reader of the board."""
    cases = [
        {}, {"load": 500.0}, {"axial": 4000.0}, {"length": 0.3},
        {"length": 4.0}, {"material": STEEL}, {"axial": 0.0},
        {"section": ("Solid circle", 6.0, 0.0, 0.0)},
        {"ends": "Fixed - free, flagpole (K = 2.0)"},
        {"case": "Cantilever, uniform load", "load": 200.0},
    ]
    for kwargs in cases:
        for item in default_verdicts(**kwargs):
            assert item["ok"] == (item["margin"] >= 1.0), (kwargs, item)


def test_a_stubby_column_fails_only_on_euler_validity():
    """The check that earns this page. Every load check passes with enormous
    margin - the stress is tiny, it barely moves, and the Euler load is more
    than two hundred times the applied one - and the design is still being
    sized against a formula that does not describe it."""
    result = default_verdicts(length=0.5, material=STEEL, load=500.0,
                              axial=10e3,
                              section=("Solid circle", 50.0, 0.0, 0.0))
    failed = [item["label"] for item in result if not item["ok"]]
    assert failed == ["Euler validity"]
    assert check_named(result, "Buckling")["margin"] > 200.0


def test_the_failing_euler_check_says_it_is_an_over_estimate():
    """It has to report as a model-applicability problem, not as a passing
    number, because the number it would pass with is wrong in the
    unconservative direction."""
    result = default_verdicts(length=0.5, material=STEEL, load=500.0,
                              axial=10e3,
                              section=("Solid circle", 50.0, 0.0, 0.0))
    detail = check_named(result, "Euler validity")["detail"]
    assert "OVER-estimate" in detail
    assert "below the transition" in detail


def test_lengthening_the_same_column_makes_euler_apply_again():
    """Slenderness is the only thing the validity check looks at, so the fix
    is geometry rather than material."""
    section = ("Solid circle", 50.0, 0.0, 0.0)
    stubby = check_named(default_verdicts(length=0.5, material=STEEL,
                                          load=0.0, axial=10e3,
                                          section=section), "Euler validity")
    slender = check_named(default_verdicts(length=2.0, material=STEEL,
                                           load=0.0, axial=10e3,
                                           section=section), "Euler validity")
    assert not stubby["ok"] and slender["ok"]


def test_the_stress_margin_is_one_exactly_at_the_allowable():
    """Yield divided by the factor of safety, not bare yield."""
    length, factor = 1.5, 2.0
    memb = default_member()
    base = loading(memb, CASE, 45.0, length, 800.0, ALUMINIUM)
    at_limit = Material(ALUMINIUM.modulus, base.combined_stress * factor,
                        ALUMINIUM.density)
    result = verdicts(memb, loading(memb, CASE, 45.0, length, 800.0, at_limit),
                      stability(memb, length, "Pinned - pinned (K = 1.0)",
                                800.0, at_limit),
                      length, at_limit, factor,
                      structure.DEFAULT_SPAN_FRACTION)
    assert check_named(result, "Combined stress")["margin"] == \
        pytest.approx(1.0)


def test_a_member_sitting_exactly_at_yield_fails_the_stress_check():
    """Exactly at yield is a failure once any factor of safety is asked for,
    which is the whole point of asking for one."""
    length = 1.5
    memb = default_member()
    base = loading(memb, CASE, 45.0, length, 800.0, ALUMINIUM)
    at_yield = Material(ALUMINIUM.modulus, base.combined_stress,
                        ALUMINIUM.density)
    result = verdicts(memb, loading(memb, CASE, 45.0, length, 800.0, at_yield),
                      stability(memb, length, "Pinned - pinned (K = 1.0)",
                                800.0, at_yield),
                      length, at_yield, 2.0, structure.DEFAULT_SPAN_FRACTION)
    check = check_named(result, "Combined stress")
    assert not check["ok"]
    assert check["margin"] == pytest.approx(0.5)


def test_the_axial_load_alone_can_fail_the_stress_check():
    """Bending is not the only way to overstress a member, and a studio that
    only checked the bending stress would say this one was fine."""
    bending_only = default_verdicts(load=45.0, axial=0.0)
    squeezed = default_verdicts(load=45.0, axial=30e3)
    assert bending_only[0]["ok"]
    assert not squeezed[0]["ok"]


def test_the_deflection_limit_is_the_span_fraction_the_user_sets():
    memb = default_member()
    result = loading(memb, CASE, 45.0, 1.5, 800.0, ALUMINIUM)
    exact = 1.5 / result.deflection
    assert check_named(default_verdicts(fraction=exact),
                       "Deflection")["margin"] == pytest.approx(1.0)
    assert not check_named(default_verdicts(fraction=exact * 2.0),
                           "Deflection")["ok"]


def test_stiffness_governs_this_design_not_strength():
    """The lesson a slender aerospace member teaches: it is nowhere near
    yielding and still too floppy to use. Sizing on stress alone would have
    called it finished."""
    result = default_verdicts()
    assert check_named(result, "Combined stress")["margin"] > \
        check_named(result, "Deflection")["margin"]


def test_a_long_floppy_member_fails_stiffness_and_buckling_together():
    result = default_verdicts(length=4.0)
    failed = [item["label"] for item in result if not item["ok"]]
    assert "Deflection" in failed and "Buckling" in failed


# --------------------------------------------------------------------------
# What the mass buys
# --------------------------------------------------------------------------
def test_steel_is_stronger_than_aluminium_and_worse_per_kilogram():
    """Why aerospace structures are not made of the stronger metal."""
    assert STEEL.yield_strength < MATERIALS["4130 steel, normalised"].\
        yield_strength
    steel_per_kg = materials.specific_strength(STEEL.yield_strength,
                                               STEEL.density)
    alu_per_kg = materials.specific_strength(ALUMINIUM.yield_strength,
                                             ALUMINIUM.density)
    assert alu_per_kg > 3.0 * steel_per_kg


def test_the_metals_all_have_about_the_same_specific_stiffness():
    """Roughly 25 MN·m/kg for steel, aluminium and titanium alike - so a
    stiffness-driven part gets no lighter by swapping metal, only by changing
    shape or leaving metals behind. The claim the page's caption makes."""
    for name in ("Aluminium 6061-T6", "Steel, mild (A36)",
                 "Titanium 6Al-4V", "4130 steel, normalised"):
        material = MATERIALS[name]
        assert material.modulus / material.density == \
            pytest.approx(25.5e6, rel=0.05)
    carbon = MATERIALS["Carbon fibre (quasi-isotropic)"]
    assert carbon.modulus / carbon.density > 40e6


def test_capacity_per_kilogram_rewards_moving_material_outwards():
    """A tube and a solid bar of the same mass are not the same member: the
    tube puts its material where the stress is."""
    solid = member("Solid circle", 12.0, 0.0, 0.0, 1.0, ALUMINIUM)
    tube = member("Hollow circle (tube)", 25.0, 0.0, 2.0, 1.0, ALUMINIUM)
    assert tube.mass == pytest.approx(solid.mass, rel=0.3)
    assert (tube.moment_capacity / tube.mass
            > 2.0 * solid.moment_capacity / solid.mass)


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------
def test_the_studio_exports_one_calculator_the_app_can_register():
    assert len(structure.CALCULATORS) == 1
    spec = structure.CALCULATORS[0]
    assert spec.slug == "studio.structure"
    assert spec.name == "Structure"
    assert spec.render is structure.render
    assert "studio" in spec.keywords and "buckling" in spec.keywords


def test_every_widget_key_is_under_this_studios_prefix():
    """Two studios sharing a widget key would silently drive each other's
    inputs, which is not a failure any physics test would catch."""
    source = open(structure.__file__, encoding="utf-8").read()
    assert structure.PREFIX == "studio_structure"
    assert 'key=f"{PREFIX}' in source
    assert "key=\"" not in source


def _rendered():
    """The Structure studio as the app actually draws it.

    Through the real app rather than AppTest.from_function, which serialises
    only the function body into a temp script and so loses the module's own
    imports - the page then fails on `ui` being undefined, which says nothing
    about the studio.
    """
    at = goto("Studios")
    at.sidebar.radio[0].set_value("Structure").run()
    return at


def test_the_page_renders_without_error():
    assert not _rendered().exception


def test_the_rendered_page_names_the_three_quantities_called_i_or_j():
    """The disambiguation has to be on the page, not only in a docstring."""
    text = " ".join(element.value for element in _rendered().markdown)
    assert "second moment of AREA" in text or "SECOND MOMENT OF AREA" in text
    assert "kg·m²" in text
    assert "polar second moment J" in text


def test_the_assumptions_say_aluminium_has_no_endurance_limit():
    text = " ".join(element.value for element in _rendered().markdown)
    assert "NO ENDURANCE LIMIT" in text
    assert "holes" in text and "weld" in text
