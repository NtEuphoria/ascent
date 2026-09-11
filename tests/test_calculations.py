"""Known-value tests for the pure calculation functions.

Every expected value here was worked out by hand from the equation, so a
regression in the physics fails the test rather than quietly changing an answer.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calculators import (aerodynamics as aero, controls, drones, electrical,
                         flight, materials, mechanical, reference, rotational)
from utils import conversions as cv
from utils.constants import G0
from utils.validation import ValidationError

REL = 1e-4


# --------------------------------------------------------------------------
# Aerodynamics
# --------------------------------------------------------------------------
def test_dynamic_pressure():
    # q = 0.5 * 1.225 * 50^2 = 1531.25 Pa
    assert aero.dynamic_pressure(1.225, 50.0) == pytest.approx(1531.25, rel=REL)


def test_lift_known_value():
    # L = 1531.25 * 16.2 * 0.5 = 12403.125 N
    assert aero.lift(1.225, 50.0, 16.2, 0.5) == pytest.approx(12403.125, rel=REL)


def test_lift_scales_with_velocity_squared():
    single = aero.lift(1.225, 25.0, 10.0, 0.5)
    double = aero.lift(1.225, 50.0, 10.0, 0.5)
    assert double == pytest.approx(4.0 * single, rel=REL)


def test_negative_cl_gives_downforce():
    assert aero.lift(1.225, 50.0, 16.2, -0.5) < 0


def test_drag_known_value():
    assert aero.drag(1.225, 50.0, 16.2, 0.032) == pytest.approx(793.8, rel=1e-3)


def test_lift_to_drag():
    assert aero.lift_to_drag(0.5, 0.032) == pytest.approx(15.625, rel=REL)


def test_wing_loading_uses_weight_not_mass():
    weight = 1200.0 * G0                      # 1200 kg -> 11767.98 N
    assert aero.wing_loading(weight, 16.2) == pytest.approx(726.4185, rel=1e-3)


def test_aspect_ratio_cessna_like():
    assert aero.aspect_ratio(10.9, 16.2) == pytest.approx(7.3339, rel=1e-3)


def test_aspect_ratio_rectangular_wing_equals_span_over_chord():
    span, chord = 8.0, 1.0
    assert aero.aspect_ratio(span, span * chord) == pytest.approx(span / chord)


def test_reynolds_number():
    value = aero.reynolds_number(1.225, 25.0, 0.25, 1.789e-5)
    assert value == pytest.approx(427963.0, rel=1e-3)


def test_area_must_be_positive():
    with pytest.raises(ValidationError):
        aero.lift(1.225, 50.0, 0.0, 0.5)


def test_negative_velocity_rejected():
    with pytest.raises(ValidationError):
        aero.lift(1.225, -10.0, 16.2, 0.5)


def test_zero_drag_coefficient_rejected_in_ld():
    with pytest.raises(ValidationError):
        aero.lift_to_drag(0.5, 0.0)


# --------------------------------------------------------------------------
# Flight performance
# --------------------------------------------------------------------------
def test_weight_from_mass():
    assert flight.weight_from_mass(120.0) == pytest.approx(1176.798, rel=REL)


def test_thrust_to_weight_is_dimensionless():
    assert flight.thrust_to_weight(1600.0, 1176.798) == pytest.approx(1.35953,
                                                                     rel=1e-4)


def test_twr_of_one_means_thrust_equals_weight():
    weight = flight.weight_from_mass(2.0)
    assert flight.thrust_to_weight(weight, weight) == pytest.approx(1.0)


def test_power_to_mass():
    assert flight.power_to_mass(1500.0, 2.5) == pytest.approx(600.0, rel=REL)


def test_stall_speed_known_value():
    weight = flight.weight_from_mass(12.0)
    value = flight.stall_speed(weight, 1.225, 0.65, 1.3)
    assert value == pytest.approx(15.079, rel=1e-3)


def test_stall_speed_scales_with_sqrt_weight():
    base = flight.stall_speed(100.0, 1.225, 1.0, 1.2)
    heavy = flight.stall_speed(400.0, 1.225, 1.0, 1.2)
    assert heavy == pytest.approx(2.0 * base, rel=REL)


def test_rate_of_climb_known_value():
    weight = flight.weight_from_mass(12.0)
    assert flight.rate_of_climb(40.0, 14.0, 22.0, weight) == pytest.approx(4.8607,
                                                                          rel=1e-3)


def test_thrust_below_drag_gives_descent():
    assert flight.rate_of_climb(10.0, 20.0, 20.0, 100.0) < 0


def test_zero_weight_rejected():
    with pytest.raises(ValidationError):
        flight.thrust_to_weight(100.0, 0.0)


# --------------------------------------------------------------------------
# Drones
# --------------------------------------------------------------------------
def test_gram_force_conversion():
    assert drones.grams_force_to_newton(1000.0) == pytest.approx(G0, rel=1e-9)


def test_total_thrust_four_motors():
    per_motor = drones.grams_force_to_newton(1200.0)
    assert drones.total_thrust(4, per_motor) == pytest.approx(47.0719, rel=1e-4)


def test_hover_thrust_per_motor():
    weight = 2.0 * G0
    assert drones.hover_thrust_per_motor(weight, 4) == pytest.approx(4.9033,
                                                                    rel=1e-4)


def test_flight_time_known_value():
    # 5 Ah at 80% usable, 25 A average -> 9.6 minutes
    assert drones.flight_time_minutes(5.0, 0.8, 25.0) == pytest.approx(9.6, rel=REL)


def test_flight_time_rejects_zero_current():
    with pytest.raises(ValidationError):
        drones.flight_time_minutes(5.0, 0.8, 0.0)


def test_flight_time_rejects_impossible_usable_fraction():
    with pytest.raises(ValidationError):
        drones.flight_time_minutes(5.0, 1.5, 25.0)


def test_fractional_motor_count_rejected():
    with pytest.raises(ValidationError):
        drones.total_thrust(0, 10.0)


def test_battery_energy():
    assert drones.battery_energy_wh(22.2, 5.0) == pytest.approx(111.0, rel=REL)


# --------------------------------------------------------------------------
# Mechanical
# --------------------------------------------------------------------------
def test_force():
    assert mechanical.force(2.0, 9.80665) == pytest.approx(19.6133, rel=1e-4)


def test_torque_perpendicular():
    assert mechanical.torque(0.25, 40.0, 90.0) == pytest.approx(10.0, rel=REL)


def test_torque_parallel_force_does_nothing():
    assert mechanical.torque(0.25, 40.0, 0.0) == pytest.approx(0.0, abs=1e-12)


def test_work_along_motion():
    assert mechanical.work(50.0, 3.0, 0.0) == pytest.approx(150.0, rel=REL)


def test_perpendicular_force_does_no_work():
    assert mechanical.work(50.0, 3.0, 90.0) == pytest.approx(0.0, abs=1e-12)


def test_power_from_work():
    assert mechanical.power(1000.0, 5.0) == pytest.approx(200.0, rel=REL)


def test_kinetic_energy():
    assert mechanical.kinetic_energy(2.0, 15.0) == pytest.approx(225.0, rel=REL)


def test_potential_energy():
    assert mechanical.potential_energy(2.0, 100.0) == pytest.approx(1961.33,
                                                                   rel=1e-4)


def test_momentum():
    assert mechanical.momentum(2.0, 15.0) == pytest.approx(30.0, rel=REL)


def test_gear_ratio_and_output_speed():
    ratio = mechanical.gear_ratio(60, 12)
    assert ratio == pytest.approx(5.0, rel=REL)
    assert mechanical.output_rpm(3000.0, ratio) == pytest.approx(600.0, rel=REL)


def test_gear_ratio_rejects_zero_teeth():
    with pytest.raises(ValidationError):
        mechanical.gear_ratio(60, 0)


def test_power_rejects_zero_time():
    with pytest.raises(ValidationError):
        mechanical.power(100.0, 0.0)


# --------------------------------------------------------------------------
# Rotational
# --------------------------------------------------------------------------
def test_rpm_to_rad_s():
    assert rotational.rpm_to_rad_s(8000.0) == pytest.approx(837.758, rel=1e-5)


def test_rpm_round_trip():
    assert rotational.rad_s_to_rpm(rotational.rpm_to_rad_s(1234.0)) == \
        pytest.approx(1234.0, rel=1e-9)


def test_rotational_power():
    omega = rotational.rpm_to_rad_s(8000.0)
    assert rotational.rotational_power(0.35, omega) == pytest.approx(293.22,
                                                                    rel=1e-3)


def test_centripetal_force():
    assert rotational.centripetal_force(0.01, 106.0, 0.127) == pytest.approx(
        884.72, rel=1e-3)


def test_moment_of_inertia_shapes():
    mass, radius = 0.05, 0.05
    disk = rotational.moment_of_inertia("Solid disk, about its central axis",
                                        mass, radius)
    hoop = rotational.moment_of_inertia(
        "Thin hoop or ring, about its central axis", mass, radius)
    sphere = rotational.moment_of_inertia("Solid sphere, about a diameter",
                                          mass, radius)
    assert disk == pytest.approx(6.25e-5, rel=REL)
    assert hoop == pytest.approx(2.0 * disk, rel=REL)      # hoop = 2 x disk
    assert sphere == pytest.approx(0.4 * mass * radius ** 2, rel=REL)


def test_rod_about_end_is_four_times_rod_about_centre():
    centre = rotational.moment_of_inertia("Thin rod, about its centre", 1.0, 1.0)
    end = rotational.moment_of_inertia("Thin rod, about one end", 1.0, 1.0)
    assert end == pytest.approx(4.0 * centre, rel=REL)


def test_rotational_kinetic_energy():
    omega = rotational.rpm_to_rad_s(8000.0)
    assert rotational.rotational_kinetic_energy(6.25e-5, omega) == pytest.approx(
        21.93, rel=1e-3)


def test_unknown_shape_rejected():
    with pytest.raises(ValidationError):
        rotational.moment_of_inertia("Banana", 1.0, 1.0)


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------
def test_normal_stress_10mm_bar():
    area = 78.54e-6                              # 10 mm diameter round bar
    assert materials.normal_stress(5000.0, area) / 1e6 == pytest.approx(63.66,
                                                                       rel=1e-3)


def test_strain():
    assert materials.strain(0.0012, 1.0) == pytest.approx(0.0012, rel=REL)


def test_youngs_modulus_identifies_aluminium():
    value = materials.youngs_modulus(63.7e6, 0.000912)
    assert value / 1e9 == pytest.approx(69.85, rel=1e-3)


def test_safety_factor():
    assert materials.safety_factor(276e6, 63.7e6) == pytest.approx(4.333, rel=1e-3)


def test_density():
    assert materials.density(2.7, 0.001) == pytest.approx(2700.0, rel=REL)


def test_specific_strength():
    assert materials.specific_strength(276e6, 2700.0) == pytest.approx(102222.0,
                                                                      rel=1e-4)


def test_zero_strain_rejected():
    with pytest.raises(ValidationError):
        materials.youngs_modulus(100e6, 0.0)


def test_zero_area_rejected():
    with pytest.raises(ValidationError):
        materials.normal_stress(1000.0, 0.0)


# --------------------------------------------------------------------------
# Electrical
# --------------------------------------------------------------------------
def test_ohms_law_all_three_forms_agree():
    voltage = electrical.ohms_law_voltage(0.5, 220.0)
    assert voltage == pytest.approx(110.0, rel=REL)
    assert electrical.ohms_law_current(voltage, 220.0) == pytest.approx(0.5,
                                                                       rel=REL)
    assert electrical.ohms_law_resistance(voltage, 0.5) == pytest.approx(220.0,
                                                                        rel=REL)


def test_power_forms_agree_for_ohmic_load():
    voltage, resistance = 12.0, 10.0
    current = electrical.ohms_law_current(voltage, resistance)
    assert electrical.power_vi(voltage, current) == pytest.approx(14.4, rel=REL)
    assert electrical.power_i2r(current, resistance) == pytest.approx(14.4, rel=REL)
    assert electrical.power_v2r(voltage, resistance) == pytest.approx(14.4, rel=REL)


def test_wiring_loss():
    assert electrical.power_i2r(60.0, 0.005) == pytest.approx(18.0, rel=REL)


def test_series_resistance():
    assert electrical.series_resistance([100.0, 200.0, 300.0]) == pytest.approx(
        600.0, rel=REL)


def test_parallel_resistance():
    assert electrical.parallel_resistance([100.0, 200.0, 300.0]) == pytest.approx(
        54.5455, rel=1e-4)


def test_equal_resistors_in_parallel_halve():
    assert electrical.parallel_resistance([100.0, 100.0]) == pytest.approx(50.0,
                                                                          rel=REL)


def test_parallel_total_below_smallest():
    values = [10.0, 47.0, 100.0]
    assert electrical.parallel_resistance(values) < min(values)


def test_parallel_rejects_zero_resistor():
    with pytest.raises(ValidationError):
        electrical.parallel_resistance([100.0, 0.0])


def test_zero_current_rejected_for_resistance():
    with pytest.raises(ValidationError):
        electrical.ohms_law_resistance(12.0, 0.0)


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------
def test_control_error():
    assert controls.control_error(100.0, 92.0) == pytest.approx(8.0, rel=REL)


def test_pid_with_integral_removes_steady_state_error():
    t, y, u = controls.simulate_pid(kp=2.0, ki=1.0, kd=0.1, setpoint=1.0,
                                    initial_value=0.0, plant_gain=1.0,
                                    time_constant=1.0, duration=30.0,
                                    u_min=-10.0, u_max=10.0)
    assert y[-1] == pytest.approx(1.0, abs=0.02)


def test_proportional_only_leaves_steady_state_error():
    t, y, u = controls.simulate_pid(kp=2.0, ki=0.0, kd=0.0, setpoint=1.0,
                                    initial_value=0.0, plant_gain=1.0,
                                    time_constant=1.0, duration=30.0,
                                    u_min=-10.0, u_max=10.0)
    # Closed-loop steady state for a first-order plant: y = Kp*K/(1 + Kp*K)
    assert y[-1] == pytest.approx(2.0 / 3.0, abs=0.01)


def test_pid_respects_output_limits():
    t, y, u = controls.simulate_pid(kp=50.0, ki=20.0, kd=0.0, setpoint=1.0,
                                    initial_value=0.0, plant_gain=1.0,
                                    time_constant=1.0, duration=10.0,
                                    u_min=-2.0, u_max=2.0)
    assert u.max() <= 2.0 + 1e-9
    assert u.min() >= -2.0 - 1e-9


def test_pid_starts_at_initial_value():
    t, y, u = controls.simulate_pid(kp=1.0, ki=0.0, kd=0.0, setpoint=5.0,
                                    initial_value=2.0, plant_gain=1.0,
                                    time_constant=1.0, duration=5.0,
                                    u_min=-10.0, u_max=10.0)
    assert y[0] == pytest.approx(2.0)


def test_pid_rejects_zero_time_constant():
    with pytest.raises(ValidationError):
        controls.simulate_pid(1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 5.0, -1.0, 1.0)


def test_pid_rejects_inverted_output_limits():
    with pytest.raises(ValidationError):
        controls.simulate_pid(1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 5.0, 5.0, -5.0)


def test_response_metrics_on_perfect_step():
    import numpy as np
    t = np.linspace(0, 10, 101)
    y = np.ones_like(t)
    y[0] = 0.0
    metrics = controls.response_metrics(t, y, 1.0, 0.0)
    assert metrics["steady_state_error"] == pytest.approx(0.0)
    assert metrics["overshoot_pct"] == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Conversions
# --------------------------------------------------------------------------
def test_exact_length_conversions():
    assert cv.convert(1.0, "Inch (in)", "Millimetre (mm)", cv.LENGTH) == \
        pytest.approx(25.4, rel=1e-12)
    assert cv.convert(1.0, "Mile (mi)", "Metre (m)", cv.LENGTH) == \
        pytest.approx(1609.344, rel=1e-12)
    assert cv.convert(1.0, "Metre (m)", "Foot (ft)", cv.LENGTH) == \
        pytest.approx(3.280839895, rel=1e-9)


def test_velocity_conversions():
    assert cv.convert(100.0, "Kilometre per hour (km/h)",
                      "Metre per second (m/s)", cv.VELOCITY) == \
        pytest.approx(27.77778, rel=1e-6)
    assert cv.convert(1.0, "Knot (kn)", "Metre per second (m/s)",
                      cv.VELOCITY) == pytest.approx(0.5144444, rel=1e-6)


def test_mass_and_force_are_separate_quantities():
    assert cv.convert(1.0, "Pound-mass (lb)", "Kilogram (kg)", cv.MASS) == \
        pytest.approx(0.45359237, rel=1e-12)
    assert cv.convert(1.0, "Pound-force (lbf)", "Newton (N)", cv.FORCE) == \
        pytest.approx(4.4482216152605, rel=1e-12)


def test_pressure_conversions():
    assert cv.convert(1.0, "Pound per square inch (psi)", "Pascal (Pa)",
                      cv.PRESSURE) == pytest.approx(6894.757293, rel=1e-9)
    assert cv.convert(1.0, "Bar (bar)", "Kilopascal (kPa)", cv.PRESSURE) == \
        pytest.approx(100.0, rel=1e-12)


def test_energy_and_power_conversions():
    assert cv.convert(1.0, "Kilowatt-hour (kWh)", "Joule (J)", cv.ENERGY) == \
        pytest.approx(3.6e6, rel=1e-12)
    assert cv.convert(1.0, "Horsepower, mechanical (hp)", "Watt (W)",
                      cv.POWER) == pytest.approx(745.6998716, rel=1e-9)
    assert cv.convert(1.0, "Horsepower, metric (PS)", "Watt (W)", cv.POWER) == \
        pytest.approx(735.49875, rel=1e-9)


def test_round_trip_conversion_is_lossless():
    original = 123.456
    metres = cv.convert(original, "Foot (ft)", "Metre (m)", cv.LENGTH)
    assert cv.convert(metres, "Metre (m)", "Foot (ft)", cv.LENGTH) == \
        pytest.approx(original, rel=1e-12)


def test_temperature_conversions():
    assert cv.convert_temperature(0.0, "Celsius (°C)", "Kelvin (K)") == \
        pytest.approx(273.15, rel=1e-12)
    assert cv.convert_temperature(100.0, "Celsius (°C)",
                                  "Fahrenheit (°F)") == pytest.approx(212.0,
                                                                        rel=1e-12)
    assert cv.convert_temperature(-40.0, "Celsius (°C)",
                                  "Fahrenheit (°F)") == pytest.approx(-40.0,
                                                                        abs=1e-9)


def test_below_absolute_zero_rejected():
    with pytest.raises(ValidationError):
        cv.convert_temperature(-300.0, "Celsius (°C)", "Kelvin (K)")
    with pytest.raises(ValidationError):
        cv.convert_temperature(-1.0, "Kelvin (K)", "Celsius (°C)")


# --------------------------------------------------------------------------
# Standard atmosphere
# --------------------------------------------------------------------------
def test_isa_sea_level_matches_published_constants():
    props = reference.isa_properties(0.0)
    assert props["temperature_k"] == pytest.approx(288.15, rel=1e-9)
    assert props["pressure_pa"] == pytest.approx(101325.0, rel=1e-9)
    assert props["density_kgm3"] == pytest.approx(1.225, rel=1e-3)
    assert props["speed_of_sound_ms"] == pytest.approx(340.29, rel=1e-3)


def test_isa_tropopause():
    props = reference.isa_properties(11000.0)
    assert props["temperature_k"] == pytest.approx(216.65, rel=1e-6)
    assert props["pressure_pa"] == pytest.approx(22632.0, rel=1e-3)


def test_isa_density_falls_with_altitude():
    assert reference.isa_properties(2000.0)["density_kgm3"] == pytest.approx(
        1.0066, rel=1e-3)
    assert reference.isa_properties(5000.0)["density_kgm3"] < \
        reference.isa_properties(2000.0)["density_kgm3"]


def test_isa_rejects_altitude_out_of_model_range():
    with pytest.raises(ValidationError):
        reference.isa_properties(25000.0)
    with pytest.raises(ValidationError):
        reference.isa_properties(-100.0)


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def test_number_formatting_is_readable():
    from utils.formatting import format_number
    assert format_number(12403.125) == "12,403"
    assert format_number(0.0012) == "0.0012"
    assert format_number(1.789e-5) == "1.789e-05"
    assert format_number(0.0) == "0"
    assert format_number(float("nan")) == "-"


def test_formatting_keeps_significant_digits():
    from utils.formatting import format_number
    assert format_number(9.80665) == "9.807"
    assert format_number(math.pi, sig=6) == "3.14159"


# --------------------------------------------------------------------------
# Propulsion - momentum theory, hover power, rocket equation
# --------------------------------------------------------------------------
def test_disk_area_is_the_swept_circle():
    from calculators import propulsion
    # A 10-inch propeller: R = 0.127 m -> pi r^2
    assert propulsion.disk_area(0.127) == pytest.approx(math.pi * 0.127 ** 2)


def test_induced_velocity_hover():
    from calculators import propulsion
    # v_h = sqrt(T / (2 rho A)), T = 4.9 N on a 10-inch rotor at sea level
    area = propulsion.disk_area(0.127)
    assert propulsion.induced_velocity_hover(4.9, area) == pytest.approx(
        6.2825, rel=1e-3)


def test_ideal_hover_power_known_value():
    from calculators import propulsion
    area = propulsion.disk_area(0.127)
    assert propulsion.ideal_hover_power(4.9, area) == pytest.approx(30.78,
                                                                   rel=1e-3)


def test_hover_power_scales_as_thrust_to_the_three_halves():
    """The central non-linearity: 2x thrust costs 2^1.5 = 2.83x power."""
    from calculators import propulsion
    area = propulsion.disk_area(0.127)
    single = propulsion.ideal_hover_power(10.0, area)
    double = propulsion.ideal_hover_power(20.0, area)
    assert double / single == pytest.approx(2 ** 1.5, rel=1e-6)


def test_doubling_rotor_radius_halves_ideal_power():
    """P is proportional to 1/R at fixed thrust - the case for big slow props."""
    from calculators import propulsion
    small = propulsion.ideal_hover_power(4.9, propulsion.disk_area(0.0635))
    large = propulsion.ideal_hover_power(4.9, propulsion.disk_area(0.127))
    assert small / large == pytest.approx(2.0, rel=1e-6)


def test_thinner_air_costs_more_hover_power():
    from calculators import propulsion
    area = propulsion.disk_area(0.127)
    sea_level = propulsion.ideal_hover_power(4.9, area, 1.225)
    altitude = propulsion.ideal_hover_power(4.9, area, 1.0)
    assert altitude > sea_level


def test_figure_of_merit():
    from calculators import propulsion
    assert propulsion.figure_of_merit(30.0, 55.0) == pytest.approx(0.5455,
                                                                  rel=1e-3)


def test_hover_electrical_power_and_endurance():
    from calculators import propulsion
    weight = 2.0 * G0
    power = propulsion.hover_electrical_power(weight, 4, 0.127, 0.55, 0.80)
    assert power == pytest.approx(280.2, rel=1e-3)
    assert propulsion.hover_endurance_minutes(111.0, 0.8, power) == \
        pytest.approx(19.0, rel=1e-2)


def test_twenty_percent_more_mass_costs_thirty_one_percent_more_power():
    from calculators import propulsion
    light = propulsion.hover_electrical_power(2.0 * G0, 4, 0.127, 0.55, 0.80)
    heavy = propulsion.hover_electrical_power(2.4 * G0, 4, 0.127, 0.55, 0.80)
    assert heavy / light == pytest.approx(1.2 ** 1.5, rel=1e-6)


def test_rocket_equation_known_values():
    from calculators import propulsion
    assert propulsion.delta_v(300.0, 1000.0, 300.0) == pytest.approx(3542,
                                                                    rel=1e-3)
    assert propulsion.delta_v(300.0, 1000.0, 200.0) == pytest.approx(4735,
                                                                    rel=1e-3)


def test_rocket_equation_depends_only_on_mass_ratio():
    from calculators import propulsion
    assert propulsion.delta_v(300.0, 1000.0, 250.0) == pytest.approx(
        propulsion.delta_v(300.0, 400.0, 100.0), rel=1e-9)


def test_rocket_rejects_gaining_mass():
    from calculators import propulsion
    with pytest.raises(ValidationError):
        propulsion.delta_v(300.0, 100.0, 200.0)


def test_propulsion_rejects_impossible_inputs():
    from calculators import propulsion
    with pytest.raises(ValidationError):
        propulsion.disk_area(0.0)
    with pytest.raises(ValidationError):
        propulsion.figure_of_merit(30.0, 0.0)
    with pytest.raises(ValidationError):
        # figure of merit above 1 would beat the ideal rotor
        propulsion.hover_electrical_power(20.0, 4, 0.127, 1.5, 0.8)
