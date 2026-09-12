"""Structures physics, checked against values worked by hand.

The section and beam libraries are lookup tables of formulas, which is exactly
the shape of code where a single transposed coefficient hides forever - the
page still renders and the number is still plausible. Every entry is checked
against its textbook closed form here.
"""
from __future__ import annotations

import math

import pytest

from calculators import structures as s


# --------------------------------------------------------------------------
# Section properties
# --------------------------------------------------------------------------
def test_rectangle_is_b_h_cubed_over_twelve():
    assert s.second_moment_of_area("Solid rectangle", 0.05, 0.10, 0.0) == \
        pytest.approx(0.05 * 0.10 ** 3 / 12.0)


def test_depth_is_cubed_so_orientation_dominates():
    """A 2:1 section on edge is four times stiffer than laid flat. This is the
    single most useful fact on the page."""
    on_edge = s.second_moment_of_area("Solid rectangle", 0.02, 0.04, 0.0)
    laid_flat = s.second_moment_of_area("Solid rectangle", 0.04, 0.02, 0.0)
    assert on_edge / laid_flat == pytest.approx(4.0)


def test_circle_is_pi_d_fourth_over_sixtyfour():
    assert s.second_moment_of_area("Solid circle", 0.05, 0.0, 0.0) == \
        pytest.approx(math.pi * 0.05 ** 4 / 64.0)


def test_a_circle_does_not_demand_a_depth_it_never_uses():
    """The formula ignores depth, so requiring a positive one rejected a
    perfectly well-specified round bar."""
    assert s.second_moment_of_area("Solid circle", 0.05, 0.0, 0.0) > 0


def test_tube_is_the_difference_of_two_circles():
    assert s.second_moment_of_area("Hollow circle (tube)", 0.05, 0.0, 0.003) \
        == pytest.approx(math.pi * (0.05 ** 4 - 0.044 ** 4) / 64.0)


def test_a_tube_buys_more_stiffness_per_unit_of_material_than_a_bar():
    """Why every aircraft tube is hollow: material near the neutral axis
    barely contributes to I, so removing it costs less stiffness than it
    saves weight. A 50 mm tube with a 5 mm wall keeps 59% of the solid bar's
    stiffness using 36% of the material - 1.6 times the stiffness per unit
    area."""
    solid = s.second_moment_of_area("Solid circle", 0.05, 0.0, 0.0)
    tube = s.second_moment_of_area("Hollow circle (tube)", 0.05, 0.0, 0.005)
    area_solid = s.section_area("Solid circle", 0.05, 0.0, 0.0)
    area_tube = s.section_area("Hollow circle (tube)", 0.05, 0.0, 0.005)
    assert (tube / area_tube) / (solid / area_solid) == pytest.approx(1.64,
                                                                     abs=0.02)


def test_a_wall_thicker_than_the_radius_is_refused():
    with pytest.raises(Exception):
        s.second_moment_of_area("Hollow circle (tube)", 0.05, 0.0, 0.03)


def test_section_modulus_is_i_over_c():
    assert s.section_modulus(4.0e-6, 0.05) == pytest.approx(8.0e-5)


# --------------------------------------------------------------------------
# Beam cases, against their standard closed forms
# --------------------------------------------------------------------------
@pytest.mark.parametrize("case,expected", [
    ("Cantilever, point load at the end", 1000.0 * 2.0),
    ("Cantilever, uniform load", 1000.0 * 2.0 ** 2 / 2.0),
    ("Simply supported, centre point load", 1000.0 * 2.0 / 4.0),
    ("Simply supported, uniform load", 1000.0 * 2.0 ** 2 / 8.0),
    ("Fixed both ends, centre point load", 1000.0 * 2.0 / 8.0),
    ("Fixed both ends, uniform load", 1000.0 * 2.0 ** 2 / 12.0),
])
def test_every_beam_case_gives_its_textbook_moment(case, expected):
    assert s.bending_moment(case, 1000.0, 2.0) == pytest.approx(expected)


@pytest.mark.parametrize("case,coefficient,power", [
    ("Cantilever, point load at the end", 1.0 / 3.0, 3),
    ("Cantilever, uniform load", 1.0 / 8.0, 4),
    ("Simply supported, centre point load", 1.0 / 48.0, 3),
    ("Simply supported, uniform load", 5.0 / 384.0, 4),
    ("Fixed both ends, centre point load", 1.0 / 192.0, 3),
    ("Fixed both ends, uniform load", 1.0 / 384.0, 4),
])
def test_every_beam_case_gives_its_textbook_deflection(case, coefficient, power):
    load, length, e, i = 1000.0, 2.0, 69e9, 4.0e-6
    assert s.beam_deflection(case, load, length, e, i) == \
        pytest.approx(coefficient * load * length ** power / (e * i))


def test_fixing_both_ends_stiffens_a_beam_fourfold():
    args = (1000.0, 2.0, 69e9, 4.0e-6)
    simple = s.beam_deflection("Simply supported, centre point load", *args)
    fixed = s.beam_deflection("Fixed both ends, centre point load", *args)
    assert simple / fixed == pytest.approx(4.0)


def test_bending_stress_is_m_c_over_i():
    assert s.bending_stress(500.0, 0.02, 4.0e-6) == pytest.approx(2.5e6)


# --------------------------------------------------------------------------
# Elastic constants
# --------------------------------------------------------------------------
def test_shear_modulus_of_aluminium():
    assert s.shear_modulus(69e9, 0.33) == pytest.approx(69e9 / (2 * 1.33))


def test_bulk_modulus_of_aluminium():
    assert s.bulk_modulus(69e9, 0.33) == pytest.approx(69e9 / (3 * 0.34))


def test_an_incompressible_material_has_infinite_bulk_modulus():
    """Poisson's ratio of 0.5 is the physical limit; K blows up there, and the
    page must refuse rather than divide by zero."""
    with pytest.raises(Exception):
        s.bulk_modulus(69e9, 0.5)


def test_metals_land_near_the_three_eighths_rule():
    for modulus, ratio in ((200e9, 0.30), (69e9, 0.33), (114e9, 0.34)):
        assert 0.36 < s.shear_modulus(modulus, ratio) / modulus < 0.39


# --------------------------------------------------------------------------
# Torsion
# --------------------------------------------------------------------------
def test_polar_second_moment_is_twice_the_bending_one_for_a_circle():
    bending = s.second_moment_of_area("Solid circle", 0.05, 0.0, 0.0)
    assert s.polar_second_moment(0.05, 0.0) == pytest.approx(2.0 * bending)


def test_torsional_shear_stress_is_t_r_over_j():
    assert s.torsional_shear_stress(100.0, 0.025, 5.0e-7) == pytest.approx(5.0e6)


def test_angle_of_twist_is_t_l_over_g_j():
    assert s.angle_of_twist(100.0, 1.0, 26e9, 5.0e-7) == \
        pytest.approx(100.0 / (26e9 * 5.0e-7))


def test_the_worked_torsion_example_is_the_number_on_the_page():
    """25 mm OD, 3 mm wall, 1.2 m, 80 N*m, steel."""
    j = s.polar_second_moment(0.025, 0.019)
    stress = s.torsional_shear_stress(80.0, 0.0125, j)
    twist = math.degrees(s.angle_of_twist(80.0, 1.2, 76.9e9, j))
    assert stress / 1e6 == pytest.approx(39.1, abs=0.1)
    assert twist == pytest.approx(2.80, abs=0.01)


# --------------------------------------------------------------------------
# Buckling
# --------------------------------------------------------------------------
def test_euler_load_matches_the_closed_form():
    assert s.euler_buckling_load(200e9, 1e-8, 1.0, 1.0) == \
        pytest.approx(math.pi ** 2 * 200e9 * 1e-8)


def test_doubling_the_length_quarters_the_buckling_load():
    short = s.euler_buckling_load(69e9, 1e-8, 1.0, 1.0)
    long = s.euler_buckling_load(69e9, 1e-8, 1.0, 2.0)
    assert short / long == pytest.approx(4.0)


def test_end_conditions_are_squared_so_a_flagpole_is_four_times_worse():
    pinned = s.euler_buckling_load(69e9, 1e-8, 1.0, 1.0)
    flagpole = s.euler_buckling_load(69e9, 1e-8, 2.0, 1.0)
    assert pinned / flagpole == pytest.approx(4.0)


def test_radius_of_gyration_is_root_i_over_a():
    assert s.radius_of_gyration(4.0e-6, 1.0e-3) == pytest.approx(0.06324555, rel=1e-6)


def test_transition_slenderness_for_6061():
    assert s.transition_slenderness(69e9, 276e6) == pytest.approx(70.25, abs=0.01)


def test_the_worked_buckling_example_is_the_number_on_the_page():
    """6061 tube, 25 mm OD x 2 mm wall, 1.5 m, pinned-pinned."""
    i = s.second_moment_of_area("Hollow circle (tube)", 0.025, 0.0, 0.002)
    area = s.section_area("Hollow circle (tube)", 0.025, 0.0, 0.002)
    load = s.euler_buckling_load(69e9, i, 1.0, 1.5)
    slenderness = s.slenderness_ratio(1.5, s.radius_of_gyration(i, area), 1.0)
    assert load == pytest.approx(2910.0, abs=10.0)
    assert slenderness == pytest.approx(184.0, abs=1.0)
    assert load / area / 1e6 == pytest.approx(20.2, abs=0.1)


def test_the_example_column_is_slender_enough_for_euler_to_apply():
    """If it were not, the page's own Check would be firing on its own
    worked example."""
    i = s.second_moment_of_area("Hollow circle (tube)", 0.025, 0.0, 0.002)
    area = s.section_area("Hollow circle (tube)", 0.025, 0.0, 0.002)
    slenderness = s.slenderness_ratio(1.5, s.radius_of_gyration(i, area), 1.0)
    assert slenderness > s.transition_slenderness(69e9, 276e6)
