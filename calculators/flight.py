"""Flight-performance calculators.

Only equations that are exact or have clearly stated assumptions are included.
Breguet range and endurance were held back from version 1 for exactly that
reason - the answer turns on assumptions that deserve stating rather than
defaulting - and now have their own page under Drones, "Electric range &
endurance", where the constant-weight form and its limits are spelled out.
"""
from __future__ import annotations

import numpy as np

from utils import validation as v
from utils.constants import (GAMMA_AIR, G0, P_SL, RHO_SL, R_AIR,
                             T_SL_K)
from utils.spec import (Calculator, Check, Field, Output, Reference, Secondary,
                        Sweep)

# ISA troposphere constants. Deliberately re-stated here rather than imported
# from calculators/reference.py: a calculator module should not depend on
# another calculator module, only on utils.
ISA_LAPSE_RATE = 0.0065                       # K/m, 0 to 11 km
ISA_TROPOPAUSE_M = 11000.0
ISA_T_TROPOPAUSE = T_SL_K - ISA_LAPSE_RATE * ISA_TROPOPAUSE_M      # 216.65 K
_ISA_PRESSURE_EXPONENT = G0 / (R_AIR * ISA_LAPSE_RATE)             # 5.2559
_ISA_DENSITY_EXPONENT = _ISA_PRESSURE_EXPONENT - 1.0               # 4.2559

MS_TO_KNOT = 1852.0 / 3600.0        # exact: one nautical mile is 1852 m
MS_TO_FPM = 60.0 / 0.3048           # exact: one foot is 0.3048 m
M_TO_FT = 1.0 / 0.3048              # exact

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def weight_from_mass(mass: float) -> float:
    """W = m * g0   [N]. The single place mass becomes weight."""
    mass = v.non_negative(mass, "Mass", "kg")
    return mass * G0


def thrust_to_weight(thrust: float, weight: float) -> float:
    """TWR = T / W   [-]  (dimensionless: force divided by force)"""
    thrust = v.non_negative(thrust, "Thrust", "N")
    weight = v.positive(weight, "Weight", "N")
    return thrust / weight


def power_to_mass(power: float, mass: float) -> float:
    """P/m   [W/kg]. Commonly called 'power-to-weight', but the unit is per kg."""
    power = v.non_negative(power, "Power", "W")
    mass = v.positive(mass, "Mass", "kg")
    return power / mass


def stall_speed(weight: float, rho: float, area: float, cl_max: float) -> float:
    """V_stall = sqrt( 2W / (ρ * S * C_Lmax) )   [m/s]

    From L = W in steady 1 g level flight at the maximum usable C_L.
    """
    weight = v.non_negative(weight, "Weight", "N")
    rho = v.positive(rho, "Air density", "kg/m³")
    area = v.positive(area, "Wing area", "m²")
    cl_max = v.positive(cl_max, "Maximum lift coefficient")
    return float(np.sqrt(2.0 * weight / (rho * area * cl_max)))


def glide_ratio(lift_to_drag: float) -> float:
    """Glide ratio equals L/D exactly - distance covered per unit height lost."""
    return v.positive(lift_to_drag, "Lift-to-drag ratio")


def glide_distance(height: float, lift_to_drag: float) -> float:
    """d = h * (L/D)   [m], exact in still air for a steady glide."""
    height = v.non_negative(height, "Height lost", "m")
    return height * glide_ratio(lift_to_drag)


def glide_angle_deg(lift_to_drag: float) -> float:
    """gamma = arctan(1 / (L/D))   [deg] below the horizon."""
    return float(np.degrees(np.arctan(1.0 / glide_ratio(lift_to_drag))))


def glide_speed(wing_loading_value: float, rho: float, cl: float,
                lift_to_drag: float) -> float:
    """V = sqrt( 2 (W/S) cos(gamma) / (rho C_L) )   [m/s]"""
    wing_loading_value = v.positive(wing_loading_value, "Wing loading", "N/m^2")
    rho = v.positive(rho, "Air density", "kg/m^3")
    cl = v.positive(cl, "Lift coefficient")
    gamma = np.radians(glide_angle_deg(lift_to_drag))
    return float(np.sqrt(2.0 * wing_loading_value * np.cos(gamma) / (rho * cl)))


def sink_rate(wing_loading_value: float, rho: float, cl: float,
              lift_to_drag: float) -> float:
    """w = V sin(gamma)   [m/s] - how fast height is being spent."""
    speed = glide_speed(wing_loading_value, rho, cl, lift_to_drag)
    return speed * float(np.sin(np.radians(glide_angle_deg(lift_to_drag))))


def rate_of_climb(thrust: float, drag: float, velocity: float, weight: float) -> float:
    """RC = V * (T - D) / W   [m/s]

    Exact for a steady (unaccelerated) climb with thrust along the flight path:
    T - D - W sin(γ) = 0, and RC = V sin(γ).
    """
    thrust = v.non_negative(thrust, "Thrust", "N")
    drag = v.non_negative(drag, "Drag", "N")
    velocity = v.non_negative(velocity, "Airspeed", "m/s")
    weight = v.positive(weight, "Weight", "N")
    return velocity * (thrust - drag) / weight


# --- Turn performance ------------------------------------------------------


def load_factor(bank_deg: float) -> float:
    """n = 1 / cos(phi)   [-]

    In a steady level turn the vertical component of lift must still carry the
    weight, so lift rises to W / cos(phi). The result is a pure number: 'g'.
    """
    bank_deg = v.in_range(bank_deg, "Bank angle", 0.0, 89.0, "deg")
    return 1.0 / float(np.cos(np.radians(bank_deg)))


def turn_radius(velocity: float, bank_deg: float) -> float:
    """r = V² / (g tan(phi))   [m]

    The horizontal component of lift, W tan(phi), is the centripetal force.
    Mass cancels: two aircraft at the same speed and bank turn on the same
    circle whatever they weigh.
    """
    velocity = v.non_negative(velocity, "True airspeed", "m/s")
    bank_deg = v.in_range(bank_deg, "Bank angle", 0.1, 89.0, "deg")
    return velocity ** 2 / (G0 * float(np.tan(np.radians(bank_deg))))


def turn_rate_deg_s(velocity: float, bank_deg: float) -> float:
    """omega = g tan(phi) / V   [deg/s]"""
    velocity = v.positive(velocity, "True airspeed", "m/s")
    bank_deg = v.in_range(bank_deg, "Bank angle", 0.0, 89.0, "deg")
    return float(np.degrees(G0 * np.tan(np.radians(bank_deg)) / velocity))


def stall_speed_in_turn(stall_speed_1g: float, bank_deg: float) -> float:
    """V_s(n) = V_s(1g) * sqrt(n)   [m/s]

    Stall speed scales with the square root of load factor, because stall is
    set by lift and lift goes as the square of speed.
    """
    stall_speed_1g = v.non_negative(stall_speed_1g, "1 g stall speed", "m/s")
    return stall_speed_1g * float(np.sqrt(load_factor(bank_deg)))


# --- Atmosphere and airspeed ----------------------------------------------


def isa_pressure(altitude_m: float) -> float:
    """Static pressure in the International Standard Atmosphere   [Pa].

    Pressure altitude is *defined* as the ISA altitude at which the ambient
    pressure occurs, so this is the exact inverse of an altimeter set to 1013.25
    hPa. Two layers are modelled: the troposphere to 11 km and the isothermal
    lower stratosphere to 20 km.
    """
    altitude_m = v.in_range(altitude_m, "Pressure altitude", -1000.0, 20000.0, "m")
    if altitude_m <= ISA_TROPOPAUSE_M:
        temperature = T_SL_K - ISA_LAPSE_RATE * altitude_m
        return P_SL * (temperature / T_SL_K) ** _ISA_PRESSURE_EXPONENT
    at_tropopause = P_SL * (ISA_T_TROPOPAUSE / T_SL_K) ** _ISA_PRESSURE_EXPONENT
    return at_tropopause * float(np.exp(
        -G0 * (altitude_m - ISA_TROPOPAUSE_M) / (R_AIR * ISA_T_TROPOPAUSE)))


def isa_temperature(altitude_m: float) -> float:
    """ISA air temperature at a geopotential altitude   [K]."""
    altitude_m = v.in_range(altitude_m, "Altitude", -1000.0, 20000.0, "m")
    if altitude_m <= ISA_TROPOPAUSE_M:
        return T_SL_K - ISA_LAPSE_RATE * altitude_m
    return ISA_T_TROPOPAUSE


def air_density(pressure_pa: float, temperature_k: float) -> float:
    """rho = p / (R T)   [kg/m³]  - the ideal gas law for dry air."""
    pressure_pa = v.non_negative(pressure_pa, "Static pressure", "Pa")
    temperature_k = v.positive(temperature_k, "Temperature", "K")
    return pressure_pa / (R_AIR * temperature_k)


def density_from_altitude_and_temperature(altitude_m: float,
                                          oat_c: float) -> float:
    """Air density from pressure altitude and the *actual* air temperature."""
    kelvin = v.finite(oat_c, "Outside air temperature", "deg C") + 273.15
    return air_density(isa_pressure(altitude_m), kelvin)


def density_ratio(rho: float) -> float:
    """sigma = rho / rho_sea-level   [-]. Almost every performance number
    scales with some power of this."""
    rho = v.positive(rho, "Air density", "kg/m³")
    return rho / RHO_SL


def tas_from_eas(eas: float, rho: float) -> float:
    """TAS = EAS / sqrt(sigma)   [m/s]

    Equivalent airspeed is the speed at sea level that would give the same
    dynamic pressure, so this follows directly from q = 0.5 rho V².
    """
    eas = v.non_negative(eas, "Equivalent airspeed", "m/s")
    return eas / float(np.sqrt(density_ratio(rho)))


def eas_from_tas(tas: float, rho: float) -> float:
    """EAS = TAS * sqrt(sigma)   [m/s] - the exact inverse of tas_from_eas."""
    tas = v.non_negative(tas, "True airspeed", "m/s")
    return tas * float(np.sqrt(density_ratio(rho)))


def isa_density(altitude_m: float) -> float:
    """Air density in the standard atmosphere at this altitude   [kg/m³]."""
    return air_density(isa_pressure(altitude_m), isa_temperature(altitude_m))


def density_altitude(rho: float) -> float:
    """The ISA altitude at which the air has this density   [m].

    Inverting sigma = (1 - L h / T0)^(g/(R L) - 1) for h. Valid in the
    troposphere, which covers every altitude a light aircraft or drone reaches;
    above the tropopause density no longer maps one-to-one onto this formula.
    """
    sigma = density_ratio(rho)
    return (T_SL_K / ISA_LAPSE_RATE) * (
        1.0 - sigma ** (1.0 / _ISA_DENSITY_EXPONENT))


def speed_of_sound(temperature_k: float) -> float:
    """a = sqrt(gamma R T)   [m/s]. Depends on temperature only."""
    temperature_k = v.positive(temperature_k, "Temperature", "K")
    return float(np.sqrt(GAMMA_AIR * R_AIR * temperature_k))


def mach_number(tas: float, temperature_k: float) -> float:
    """M = V / a   [-]"""
    tas = v.non_negative(tas, "True airspeed", "m/s")
    return tas / speed_of_sound(temperature_k)


def true_airspeed_at_altitude(eas: float, altitude_m: float,
                              oat_c: float) -> float:
    """TAS from EAS, pressure altitude and the actual outside air temperature."""
    return tas_from_eas(eas, density_from_altitude_and_temperature(
        altitude_m, oat_c))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _twr_authority(i, r):
    """The control-authority reading, which is what TWR is really for."""
    if r < 1.0:
        return ("danger",
                f"TWR {r:.2f} is below 1. A rotorcraft cannot hover here: it "
                f"would need {100.0 / r:.0f}% of the thrust it has. Check the "
                "thrust figure is static thrust for the whole vehicle, at this "
                "air density and at a battery voltage you will still have at "
                "the end of the flight.")
    if r < 1.5:
        return ("warning",
                f"TWR {r:.2f} leaves little in reserve. Hovering already needs "
                f"{100.0 / r:.0f}% of available thrust, so only "
                f"{100.0 * (1.0 - 1.0 / r):.0f}% is left for attitude control, "
                "gust rejection and climb - and it disappears as the battery "
                "sags. Multirotors are normally designed for 1.8-2.2. For a "
                "fixed-wing aircraft this range is entirely normal: the wing "
                "carries the weight, not the thrust.")
    return None


def _twr_regime(i, r):
    if r >= 6.0:
        return ("info",
                f"At TWR {r:.1f} hover sits near {100.0 / r:.0f}% throttle, so "
                "the whole hover region is squeezed into the bottom of the "
                "stick travel and the vehicle feels twitchy. This is why racing "
                "multirotors use throttle curves. Thrust is rarely the limit "
                "here - ESC current, propeller structure and pilot reaction "
                "time are.")
    if r > 1.0:
        return ("info",
                f"TWR {r:.2f} is above 1, so thrust alone can support the "
                "vehicle. A rotorcraft can hover and climb vertically; a "
                "fixed-wing aircraft can accelerate while pointed straight up, "
                "which is the defining trick of a modern fighter.")
    return None


_TWR = Calculator(
    slug="flight.twr",
    name="Thrust-to-weight ratio",
    latex=r"TWR = \frac{T}{W},\qquad W = m\,g",
    explanation=(
        "Thrust divided by weight - both forces, so the result is dimensionless. "
        "Below 1 the vehicle cannot accelerate vertically; above 1 it can climb "
        "straight up. Mixing mass (kg) with thrust (N) here is the classic error, "
        "so the input below converts for you and shows its working."
    ),
    inputs=[
        Field("thrust", "Total thrust T", "N", 1600.0, min=0.0,
              help="Total for every motor together, not per motor. Motor data "
                   "quoted in grams-force is a force: 1000 gf = 9.807 N."),
        Field("weight", "Vehicle", "", 120.0, kind="weight"),
    ],
    compute=lambda i: thrust_to_weight(i.thrust, i.weight),
    result=Output("Thrust-to-weight ratio", "-"),
    secondary=[
        Secondary("Excess thrust (T - W)", "N", lambda i, r: i.thrust - i.weight),
        Secondary("Peak vertical acceleration (TWR - 1) × g", "m/s²",
                  lambda i, r: (r - 1.0) * G0),
        Secondary("Vehicle mass", "kg", lambda i, r: i.weight / G0),
        Secondary("Throttle fraction needed to hover (1 / TWR)", "-",
                  lambda i, r: 1.0 / r),
        Secondary("Thrust expressed as a mass equivalent", "kgf",
                  lambda i, r: i.thrust / G0),
        Secondary("Thrust that would give TWR = 2", "N",
                  lambda i, r: 2.0 * i.weight),
    ],
    note=lambda i, r: ("TWR below 1: this vehicle cannot hover or climb vertically "
                       "on thrust alone. Fixed-wing aircraft are normally in this "
                       "range and use the wing to carry weight.") if r < 1.0 else None,
    checks=[Check(_twr_authority), Check(_twr_regime)],
    assumptions=[
        "Thrust is the total static thrust available at this air density and "
        "battery/throttle state. Electric motor thrust falls as the battery sags; "
        "propeller thrust falls with altitude and forward speed.",
        "Weight is computed with standard gravity g = 9.80665 m/s².",
        "The vertical-acceleration figure assumes thrust points straight up and "
        "ignores aerodynamic drag, so it is an upper bound.",
        "Static thrust is not flight thrust. A propeller loses thrust as the "
        "vehicle speeds up, because the air is already arriving fast; a "
        "multirotor in a fast climb has noticeably less thrust than the bench "
        "test suggests.",
        "Thrust falls roughly in proportion to air density, so a TWR measured at "
        "sea level is optimistic at altitude or on a hot day. Design the margin "
        "for the worst site you will fly from, not the bench.",
        "The hover-throttle figure is thrust fraction, not stick position. "
        "Thrust goes roughly as the square of propeller RPM, and RPM is not "
        "linear in throttle command, so 50% thrust is rarely 50% stick.",
        "On a multirotor, losing one motor removes far more than its share of "
        "thrust: the remaining motors must also produce a yaw and roll "
        "imbalance. A quad with TWR 2 cannot fly on three motors.",
        "Reference points: airliner at take-off 0.25-0.35, aerobatic aircraft "
        "around 1, a stable camera multirotor 1.8-2.2, a racing quad 8-14.",
    ],
    graphs=[
        Sweep(over="thrust", y_label="Thrust-to-weight ratio [-]",
              hi_factor=2.0, hi_min=100.0,
              title="TWR vs available thrust"),
        Sweep(over="weight", y_label="Thrust-to-weight ratio [-]",
              lo_factor=0.4, hi_factor=2.0, x_label="Weight W [N]",
              title="TWR vs weight (payload penalty)"),
    ],
    references=[
        Reference(
            title="Typical thrust-to-weight by class",
            columns=("Vehicle", "TWR"),
            rows=[
                ("Airliner at take-off weight", "0.25 - 0.35"),
                ("Business jet at take-off weight", "0.30 - 0.45"),
                ("Light piston trainer (static thrust)", "0.25 - 0.35"),
                ("Aerobatic aircraft (Extra 300 class)", "0.9 - 1.1"),
                ("Fighter, clean, full afterburner", "1.0 - 1.3"),
                ("Launch vehicle at lift-off", "1.2 - 1.5"),
                ("Cinematography / survey multirotor", "1.8 - 2.2"),
                ("Freestyle FPV multirotor", "4 - 8"),
                ("Racing multirotor", "8 - 14"),
            ],
            note="Fighter and launch-vehicle figures are at combat weight and "
                 "lift-off mass respectively - quoting TWR without the weight "
                 "it was taken at is meaningless. Propeller aircraft are "
                 "normally specified by power loading instead, because their "
                 "thrust changes so much with airspeed.",
        ),
        Reference(
            title="What TWR buys a multirotor",
            columns=("TWR", "Hover throttle", "What it feels like"),
            rows=[
                ("1.0", "100%", "Cannot hover - no margin at all"),
                ("1.5", "67%", "Floor for a stable platform; poor in gusts"),
                ("2.0", "50%", "The usual design target; symmetric authority"),
                ("3.0", "33%", "Brisk; lifts a heavy payload comfortably"),
                ("5.0", "20%", "Aerobatic; hover is low on the stick"),
                ("10.0", "10%", "Racing; needs a throttle curve to be flyable"),
            ],
            note="Hover throttle is exactly 1/TWR as a thrust fraction. It is "
                 "the single most useful reading of this number: it tells you "
                 "how much thrust is left for everything other than holding "
                 "the vehicle up.",
        ),
    ],
    related=["drone.twr", "drone.hover_thrust", "flight.power_to_weight",
             "flight.rate_of_climb", "prop.momentum_theory"],
    variables=[
        ("$T$", "Total thrust", "N"),
        ("$W$", "Weight (force)", "N"),
        ("$m$", "Mass", "kg"),
        ("$g$", "Standard gravity, 9.80665", "m/s²"),
    ],
    example=(
        "Multirotor design check. A 2.5 kg quadcopter weighs 24.52 N. Four "
        "motors each producing 12 N give 48 N total, a TWR of 1.96. Hover then "
        "sits at 51% of available thrust, leaving 49% for attitude control and "
        "climb, and the best vertical acceleration is (1.96 - 1) x g = "
        "9.39 m/s². That is why 2.0 is the standard target: authority is "
        "symmetric about the hover point."
    ),
    keywords=("twr", "thrust", "weight", "ratio", "hover", "throttle",
              "control authority", "t/w"),
)

_PWR = Calculator(
    slug="flight.power_to_weight",
    name="Power-to-weight ratio",
    latex=(r"\frac{P}{m}\;\left[\mathrm{W/kg}\right], \qquad \frac{P}{W}\;"
           r"\left[\mathrm{W/N} = \mathrm{m/s}\right]"),
    explanation=(
        "Usually quoted as watts per kilogram, which is strictly a power-to-<b>mass"
        "</b> ratio. Both forms are shown: divide by mass for the industry-standard "
        "W/kg, or by weight for W/N, which has units of metres per second and is an "
        "absolute ceiling on climb rate."
    ),
    inputs=[
        Field("power", "Power P", "W", 1500.0, min=0.0),
        Field("mass", "Mass m", "kg", 2.5, min=0.0),
    ],
    compute=lambda i: power_to_mass(i.power, i.mass),
    result=Output("Power-to-mass ratio P/m", "W/kg"),
    secondary=[
        Secondary("Weight W = m g", "N", lambda i, r: i.mass * G0),
        Secondary("Power per unit weight P/W", "W/N  (= m/s)",
                  lambda i, r: i.power / (i.mass * G0)),
        Secondary("Absolute climb-rate ceiling (no drag, 100% efficient)", "m/s",
                  lambda i, r: i.power / (i.mass * G0)),
        Secondary("Power loading (mass carried per kilowatt)", "kg/kW",
                  lambda i, r: 1000.0 / r),
        Secondary("Power in mechanical horsepower", "hp",
                  lambda i, r: i.power / 745.6998715822702),
        Secondary("Time to raise its own weight by 100 m (ideal)", "s",
                  lambda i, r: 100.0 * i.mass * G0 / i.power),
    ],
    note=lambda i, r: (
        f"P/W = {i.power / (i.mass * G0):.2f} m/s is a hard ceiling, not a "
        "prediction. Multiply by propulsive efficiency and subtract what drag "
        "already consumes in level flight and a realistic best climb rate is "
        "usually a third to a half of it."),
    checks=[
        Check(lambda i, r: ("info",
                            f"{r:,.0f} W/kg is burst territory. Specific power "
                            "this high is limited by heat, not by the motor's "
                            "torque: winding temperature, magnet temperature "
                            "and battery C-rating all set how many seconds you "
                            "can hold it. Size the cooling and the pack for the "
                            "duty cycle, not the peak.")
              if r >= 1000.0 else None),
        Check(lambda i, r: ("warning",
                            f"{r:,.0f} W/kg is below what a multirotor needs to "
                            "hover. Ideal hover power per unit mass is "
                            "g·sqrt(DL / 2ρ); at a typical disc loading of "
                            "100 N/m² that is about 63 W/kg of useful power, "
                            "which after a figure of merit near 0.7 and motor "
                            "and ESC losses becomes roughly 105 W/kg of "
                            "electrical power. A fixed-wing aircraft is "
                            "perfectly happy down here - it is the wing, not "
                            "the power, that holds it up.")
              if r < 100.0 else None),
    ],
    assumptions=[
        "P is the power at the stated point in the chain. Electrical input power to "
        "the ESC, shaft power at the motor, and useful propulsive power delivered "
        "to the air are three different numbers - say which one you mean.",
        "The climb-rate ceiling assumes every watt becomes potential energy: no "
        "drag, no propeller loss, no motor loss. Real climb rate is a fraction of "
        "it. This is an upper bound, not a prediction.",
        "W/kg is a power-to-mass ratio. The term 'power-to-weight' is conventional "
        "but not dimensionally accurate.",
        "Peak and continuous power are different numbers by a factor of two or "
        "more on an electric drive. A figure quoted from a burst test says "
        "nothing about what the vehicle can sustain once the motor is hot.",
        "Electrical power available falls as the pack discharges: a 6S lithium "
        "pack sags from about 25 V to 20 V, so the same throttle command near "
        "the end of a flight delivers roughly 20% less power.",
        "Mass here must be the flying mass including payload and battery. "
        "Quoting specific power against dry mass flatters the vehicle by "
        "exactly the fraction the battery weighs, which for a multirotor is "
        "often a third of the total.",
        "Specific power says nothing about endurance. Energy density, not power "
        "density, sets how long you fly, and the two trade against each other "
        "in every battery chemistry.",
    ],
    graphs=[
        Sweep(over="power", y_label="Power-to-mass ratio [W/kg]",
              hi_factor=2.0, hi_min=100.0,
              title="Specific power vs available power"),
        Sweep(over="mass", y_label="Power-to-mass ratio [W/kg]",
              lo_factor=0.4, hi_factor=2.0,
              title="Specific power vs mass (payload penalty)"),
    ],
    references=[
        Reference(
            title="Specific power of real machines",
            columns=("Machine", "P/m [W/kg]"),
            rows=[
                ("Human, sustained for an hour", "3 - 5"),
                ("Human, peak sprint", "15 - 20"),
                ("Family car (110 kW, 1400 kg)", "~79"),
                ("Light aircraft (Cessna 172, 180 hp)", "~116"),
                ("Camera multirotor", "150 - 250"),
                ("Sports car", "150 - 250"),
                ("Formula 1 car (735 kW, 798 kg)", "~921"),
                ("Racing multirotor, burst", "1000 - 2500"),
            ],
            note="Car and aircraft figures use engine shaft power against kerb "
                 "or take-off mass; multirotor figures are electrical power "
                 "into the ESCs against flying mass. Comparing across the two "
                 "conventions overstates the electric vehicle by the drivetrain "
                 "efficiency, so state which you are quoting.",
        ),
        Reference(
            title="Where the power goes",
            columns=("Stage", "Typical efficiency", "Left from 1000 W"),
            rows=[
                ("Battery terminals", "-", "1000 W"),
                ("ESC", "0.95 - 0.98", "~960 W"),
                ("Brushless motor", "0.80 - 0.90", "~820 W"),
                ("Propeller (hover figure of merit)", "0.65 - 0.80", "~590 W"),
                ("Useful power to the air", "-", "~590 W"),
            ],
            note="Figures are for a well-matched small electric drive near its "
                 "best operating point; efficiency collapses at very low "
                 "throttle and at high winding temperature. Propeller figure "
                 "of merit is a hover number - in fast forward flight the "
                 "propeller is a different machine with different losses.",
        ),
    ],
    related=["flight.twr", "flight.rate_of_climb", "drone.power",
             "prop.hover_endurance", "prop.momentum_theory"],
    variables=[
        ("$P$", "Power", "W"),
        ("$m$", "Mass", "kg"),
        ("$W$", "Weight, m g", "N"),
    ],
    example=(
        "Racing drone comparison. A 600 g quad pulling 1200 W has 2000 W/kg, "
        "roughly 25 times a family car and more than twice a Formula 1 car. "
        "That number, not thrust alone, is what makes the acceleration feel "
        "violent - and it is why the flight lasts three minutes."
    ),
    keywords=("power", "weight", "pwr", "wkg", "specific power",
              "power loading", "power to mass"),
)

def _stall_density_check(i, r):
    """The EAS point: the *indicated* stall speed does not move with altitude."""
    sigma = i.rho / RHO_SL
    if abs(sigma - 1.0) < 0.02:
        return None
    eas = stall_speed(i.weight, RHO_SL, i.s, i.cl_max)
    where = ""
    if 0.30 < sigma < 1.0:
        where = f" - about {density_altitude(i.rho):,.0f} m of density altitude"
    if sigma < 1.0:
        return ("info",
                f"Air density is {sigma * 100:.0f}% of sea level{where}. The "
                f"{r:.1f} m/s above is TRUE airspeed, and it grows as "
                "1/sqrt(sigma) with altitude. The airspeed indicator measures "
                "dynamic pressure, not speed, so it will still read "
                f"{eas:.1f} m/s at the stall - exactly what it reads at sea "
                "level. That is why stall speeds are published as indicated or "
                "equivalent airspeed: in EAS the stall speed is a constant.")
    return ("info",
            f"Air density is {sigma * 100:.0f}% of sea level - cold or "
            "below-sea-level air. True stall speed drops to "
            f"{r:.1f} m/s, but the airspeed indicator will still read "
            f"{eas:.1f} m/s at the stall. The indicated stall speed never "
            "moves with density; only the true airspeed does.")


_STALL = Calculator(
    slug="flight.stall_speed",
    name="Stall speed",
    latex=r"V_{stall} = \sqrt{\frac{2W}{\rho\,S\,C_{L,max}}}",
    explanation=(
        "The slowest speed at which the wing can still carry the weight in level "
        "flight. It comes straight from setting lift equal to weight and using the "
        "largest lift coefficient the wing can reach before it stalls. The answer "
        "is a <b>true</b> airspeed; in equivalent airspeed - what the instrument "
        "shows - the stall speed is the same number at every altitude."
    ),
    inputs=[
        Field("weight", "Aircraft", "", 12.0, kind="weight"),
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0),
        Field("s", "Wing area S", "m²", 0.65, min=0.0),
        Field("cl_max", "Maximum lift coefficient C_Lmax", "-", 1.3, min=0.0,
              help="Clean wing typically 1.2-1.5; with flaps 1.8-2.5. Use "
                   "wind-tunnel or flight-test data if you have it."),
    ],
    compute=lambda i: stall_speed(i.weight, i.rho, i.s, i.cl_max),
    result=Output("Stall speed V_stall", "m/s"),
    secondary=[
        Secondary("In km/h", "km/h", lambda i, r: r * 3.6),
        Secondary("Recommended approach speed (1.3 × V_stall)", "m/s",
                  lambda i, r: r * 1.3),
        Secondary("Stall speed in a 45° banked turn (× 1.19)", "m/s",
                  lambda i, r: r * 1.1892),
        Secondary("In knots", "kn", lambda i, r: r / MS_TO_KNOT),
        Secondary("Equivalent airspeed at the stall (what the ASI shows)", "m/s",
                  lambda i, r: stall_speed(i.weight, RHO_SL, i.s, i.cl_max)),
        Secondary("True stall speed at 3000 m ISA", "m/s",
                  lambda i, r: stall_speed(i.weight, isa_density(3000.0), i.s,
                                           i.cl_max)),
    ],
    checks=[
        Check(_stall_density_check),
        Check(lambda i, r: ("warning",
                            f"C_Lmax = {i.cl_max:.2f} is very high. A clean wing "
                            "tops out near 1.5, single slotted flaps reach about "
                            "2.4, and only slats plus double-slotted flaps get "
                            "past 2.8. Above 3.2 you are either modelling a "
                            "blown or powered-lift wing or the number is wrong - "
                            "and stall speed goes as 1/sqrt(C_Lmax), so an "
                            "optimistic C_Lmax produces an optimistically low "
                            "stall speed.")
              if i.cl_max > 2.6 else None),
        Check(lambda i, r: ("info",
                            f"C_Lmax = {i.cl_max:.2f} is low for a maximum. "
                            "Check you have not entered a cruise C_L by "
                            "mistake. Values this low do occur on small, slow "
                            "wings: below about Re = 200,000 a typical aerofoil "
                            "loses much of its maximum lift to laminar "
                            "separation.")
              if i.cl_max < 0.8 else None),
    ],
    assumptions=[
        "Steady, wings-level, 1 g flight. In a banked turn the load factor n "
        "raises stall speed by sqrt(n) - a 60° bank means n = 2 and a 41% higher "
        "stall speed.",
        "The result is a TRUE airspeed. Stall speed is constant in equivalent "
        "airspeed, so the value on the airspeed indicator does not change with "
        "altitude even though the true speed does - this is the single most "
        "useful fact on the page.",
        "C_Lmax is the single most uncertain input here and is Reynolds-dependent. "
        "A small slow aircraft will not reach the C_Lmax quoted for a full-size one.",
        "This is an estimate of aerodynamic stall only. Propeller slipstream, "
        "ground effect and centre-of-gravity position all shift real stall speed.",
        "The 1.3x approach-speed figure is a common convention, not a regulation.",
        "Stall is an angle-of-attack limit, not a speed limit. A wing can be "
        "stalled at any airspeed and any attitude; the speed here is simply the "
        "slowest speed at which 1 g level flight is still possible.",
        "Only W, S and C_Lmax appear, so stall speed depends on weight and area "
        "purely through the wing loading W/S. Two aircraft with the same wing "
        "loading and the same C_Lmax stall at the same speed whatever their size.",
        "A frozen, wet or bug-contaminated leading edge can cut C_Lmax by 20-30%, "
        "which raises stall speed by 10-20% with no warning from any instrument.",
    ],
    graph=Sweep(over="weight", y_label="Stall speed [m/s]", lo_factor=0.3,
                hi_factor=1.7, x_label="Weight W [N]",
                title="Stall speed vs weight (square-root relationship)"),
    graphs=[
        Sweep(over="cl_max", y_label="Stall speed [m/s]", lo=0.4,
              hi_factor=2.0, hi_min=3.0,
              title="Stall speed vs C_Lmax (what flaps buy)"),
        Sweep(over="rho", y_label="Stall speed, true airspeed [m/s]",
              lo=0.30, hi_factor=1.1, hi_min=1.35,
              title="True stall speed vs air density"),
        Sweep(over="s", y_label="Stall speed [m/s]", lo_factor=0.3,
              hi_factor=2.0, title="Stall speed vs wing area"),
    ],
    references=[
        Reference(
            title="Maximum lift coefficient by configuration",
            columns=("Wing configuration", "C_Lmax"),
            rows=[
                ("Small, slow wing below Re ≈ 200,000", "0.9 - 1.2"),
                ("Clean wing, conventional aerofoil", "1.2 - 1.5"),
                ("Clean wing, dedicated high-lift section", "1.5 - 1.8"),
                ("Plain or split flap", "1.7 - 2.0"),
                ("Single slotted flap", "2.0 - 2.4"),
                ("Double slotted flap", "2.4 - 2.8"),
                ("Slats plus double slotted flap", "2.8 - 3.2"),
            ],
            note="Whole-aircraft values at sensible Reynolds numbers. A wing "
                 "section tested in isolation reaches more than the wing on an "
                 "aircraft does, because the fuselage junction, the tail "
                 "download and the trim condition all cost lift.",
        ),
        Reference(
            title="Stall speed in a banked turn",
            columns=("Bank angle", "Load factor n", "Stall speed × sqrt(n)"),
            rows=[
                ("0°", "1.00", "1.00"),
                ("15°", "1.04", "1.02"),
                ("30°", "1.15", "1.07"),
                ("45°", "1.41", "1.19"),
                ("60°", "2.00", "1.41"),
                ("75°", "3.86", "1.97"),
                ("80°", "5.76", "2.40"),
            ],
            note="Exact arithmetic for a steady level turn: n = 1/cos(bank) and "
                 "stall speed scales with sqrt(n). This is why a steep turn at "
                 "low speed on the base-to-final turn is the classic fatal "
                 "accident - past 60° of bank the stall speed climbs faster "
                 "than most pilots expect.",
        ),
    ],
    related=["aero.lift", "aero.wing_loading", "flight.turn", "flight.airspeed",
             "flight.glide"],
    variables=[
        ("$V_{stall}$", "Stall speed (true airspeed)", "m/s"),
        ("$W$", "Weight", "N"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$S$", "Wing area", "m²"),
        ("$C_{L,max}$", "Maximum usable lift coefficient", "-"),
    ],
    example=(
        "Setting a safe launch speed for a fixed-wing UAV. A 12 kg aircraft "
        "(117.7 N) with 0.65 m² of wing and C_Lmax = 1.3 stalls at 15.08 m/s at "
        "sea level - 54.3 km/h, or 29.3 kn - so a 1.3x approach gives 19.6 m/s. "
        "Fly the same aircraft from a 3000 m strip and the true stall speed "
        "rises to 17.50 m/s, 16% faster, while the airspeed indicator still "
        "reads 15.08. Adding a 2 kg payload raises weight 20% and stall speed "
        "by sqrt(1.2) = 9.5%; landing loads rise with the square of that."
    ),
    keywords=("stall", "vstall", "minimum speed", "clmax", "vs1", "vso",
              "accelerated stall", "eas", "indicated airspeed"),
)


def _climb_angle_deg(i) -> float:
    """sin(γ) = (T - D)/W, clamped so an impossible ratio still plots."""
    ratio = max(min((i.thrust - i.drag_force) / i.weight, 1.0), -1.0)
    return float(np.degrees(np.arcsin(ratio)))


def _climb_note(i, value):
    if i.thrust < i.drag_force:
        return ("Thrust is less than drag, so this is a descent: the negative rate "
                "of climb is the sink rate.")
    return None


_CLIMB = Calculator(
    slug="flight.rate_of_climb",
    name="Rate of climb",
    latex=r"RC = \frac{V\,(T - D)}{W} = V \sin\gamma",
    explanation=(
        "Climb comes from <b>excess thrust</b>. Whatever thrust is left after "
        "balancing drag gets converted into gaining height. Multiply that excess "
        "by airspeed and divide by weight and you have the vertical speed."
    ),
    inputs=[
        Field("thrust", "Thrust T", "N", 40.0, min=0.0),
        Field("drag_force", "Drag D at this speed", "N", 14.0, min=0.0),
        Field("velocity", "Airspeed V", "m/s", 22.0, min=0.0),
        Field("weight", "Aircraft", "", 12.0, kind="weight"),
    ],
    compute=lambda i: rate_of_climb(i.thrust, i.drag_force, i.velocity, i.weight),
    result=Output("Rate of climb", "m/s"),
    secondary=[
        Secondary("Climb angle γ", "°", lambda i, r: _climb_angle_deg(i)),
        Secondary("Excess thrust (T - D)", "N",
                  lambda i, r: i.thrust - i.drag_force),
        Secondary("Excess power (T - D) × V", "W",
                  lambda i, r: (i.thrust - i.drag_force) * i.velocity),
        Secondary("Time to climb 100 m", "s",
                  lambda i, r: 100.0 / r if r > 0 else float("nan")),
        Secondary("In feet per minute", "ft/min", lambda i, r: r * MS_TO_FPM),
        Secondary("Ground distance used to climb 100 m", "m",
                  lambda i, r: (100.0 * i.velocity
                                * float(np.cos(np.radians(_climb_angle_deg(i))))
                                / r) if r > 0 else float("nan")),
    ],
    note=_climb_note,
    checks=[
        Check(lambda i, r: ("danger",
                            "Excess thrust exceeds weight: (T - D)/W = "
                            f"{(i.thrust - i.drag_force) / i.weight:.2f}. There "
                            "is no steady climb angle that satisfies "
                            "sin(γ) = (T - D)/W, so the aircraft cannot hold "
                            "this airspeed - it would accelerate. A vertical "
                            "climb is possible but it is an accelerating one, "
                            "and this equation no longer describes it.")
              if (i.thrust - i.drag_force) / i.weight >= 1.0 else None),
        Check(lambda i, r: ("warning",
                            f"A climb angle of {_climb_angle_deg(i):.0f}° is "
                            "steep enough that the level-flight approximations "
                            "break down. Lift only has to be W·cos(γ) = "
                            f"{float(np.cos(np.radians(_climb_angle_deg(i)))) * 100:.0f}%"
                            " of weight, so real induced drag is lower than in "
                            "level flight and the true climb rate is a little "
                            "better than this. Propeller efficiency usually "
                            "moves the other way.")
              if 0.35 <= (i.thrust - i.drag_force) / i.weight < 1.0 else None),
        Check(lambda i, r: ("info",
                            f"A climb rate of {r:.2f} m/s "
                            f"({r * MS_TO_FPM:.0f} ft/min) is essentially the "
                            "definition of a ceiling. Service ceiling is the "
                            "altitude where the best climb rate has fallen to "
                            "0.5 m/s (100 ft/min) for a piston aircraft or "
                            "1.5 m/s (300 ft/min) for a jet; the absolute "
                            "ceiling is where it reaches zero and only one "
                            "airspeed will still hold height.")
              if 0.0 < r <= 0.5 else None),
    ],
    assumptions=[
        "Steady (unaccelerated) climb: airspeed is constant, so all excess power "
        "goes into height, none into acceleration.",
        "Thrust acts along the flight path. For a propeller aircraft climbing at a "
        "shallow angle this is a good approximation.",
        "D is the drag at this airspeed <b>in the climb</b>. Lift in a climb equals "
        "W cos(γ), slightly less than in level flight, so induced drag is slightly "
        "lower than the level-flight value.",
        "The climb angle uses sin(γ) = (T - D)/W, which is exact for a steady "
        "climb and is capped at plus/minus 90 degrees here.",
        "Drag is held fixed as the sweeps vary airspeed. Real drag has a minimum "
        "at one speed and rises on both sides of it, so a real climb-rate curve "
        "is a hump with a best-rate speed in the middle, not the straight line "
        "the 'vs airspeed' graph draws. Re-enter D for each speed you test.",
        "Both thrust and drag fall with altitude - thrust roughly with density, "
        "drag less so - which is why excess thrust shrinks as you climb and why "
        "a ceiling exists at all. This page is one altitude at a time.",
        "Climb performance is quoted at a weight. The same excess thrust divided "
        "by a heavier aircraft gives proportionally less climb, so a full "
        "payload cuts climb rate directly.",
    ],
    graphs=[
        Sweep(over="thrust", y_label="Rate of climb [m/s]", lo_factor=0.3,
              hi_factor=1.8, title="Climb rate vs thrust"),
        Sweep(over="drag_force", y_label="Rate of climb [m/s]", lo=0.0,
              hi_factor=3.0, title="Climb rate vs drag"),
        Sweep(over="weight", y_label="Rate of climb [m/s]", lo_factor=0.4,
              hi_factor=2.0, x_label="Weight W [N]",
              title="Climb rate vs weight"),
        Sweep(over="velocity", y_label="Rate of climb [m/s]", lo=0.0,
              hi_factor=1.8, title="Climb rate vs airspeed, drag held fixed"),
    ],
    references=[
        Reference(
            title="Typical rates of climb",
            columns=("Aircraft", "m/s", "ft/min"),
            rows=[
                ("Light twin, one engine out", "0.5 - 1.5", "100 - 300"),
                ("Sailplane in a strong thermal", "3 - 5", "600 - 1000"),
                ("Light piston single at sea level", "3 - 4", "600 - 800"),
                ("Airliner, initial climb after take-off", "12 - 15", "2400 - 3000"),
                ("Aerobatic single (Extra 300 class)", "~16", "~3200"),
                ("Fighter, afterburner, low level", "150 - 250", "30k - 50k"),
            ],
            note="Sea-level figures at typical operating weight. Every one of "
                 "them falls steadily with altitude as thrust decays with air "
                 "density. The sailplane row is the odd one out: it has no "
                 "excess thrust at all and is climbing because the air around "
                 "it is going up faster than it sinks through it.",
        ),
        Reference(
            title="The two climb speeds",
            columns=("Speed", "Maximises", "Answers"),
            rows=[
                ("V_x, best angle", "Excess thrust T − D",
                 "Most height per metre of ground: obstacle clearance"),
                ("V_y, best rate", "Excess power V(T − D)",
                 "Most height per second: getting to cruise altitude"),
                ("V_bg, best glide", "L/D",
                 "Most ground per metre of height, engine off"),
            ],
            note="V_x is slower than V_y for a propeller aircraft. The two "
                 "converge as you climb and meet exactly at the absolute "
                 "ceiling, where a single airspeed is the only one that still "
                 "holds height.",
        ),
    ],
    related=["flight.twr", "flight.power_to_weight", "aero.drag",
             "flight.glide", "flight.airspeed"],
    variables=[
        ("$RC$", "Rate of climb (vertical speed)", "m/s"),
        ("$V$", "True airspeed along the flight path", "m/s"),
        ("$T$", "Thrust", "N"),
        ("$D$", "Drag", "N"),
        ("$W$", "Weight", "N"),
        ("$\\gamma$", "Climb angle relative to the horizon", "°"),
    ],
    example=(
        "Checking whether a UAV clears an obstacle after launch. A 12 kg aircraft "
        "weighs 117.7 N. With 40 N of thrust against 14 N of drag at 22 m/s, the "
        "climb rate is 4.86 m/s (957 ft/min) and the climb angle is 12.76° - so "
        "gaining 100 m takes 20.6 s and uses 441 m of ground. A 30 m mast 200 m "
        "down the runway is cleared with room to spare; a 50 m one at the same "
        "distance is not, because 200 m of ground buys only 45 m of height."
    ),
    keywords=("climb", "roc", "vertical speed", "excess thrust",
              "excess power", "service ceiling", "time to climb", "vx", "vy"),
)

_GLIDE = Calculator(
    slug="flight.glide",
    name="Glide performance",
    latex=(r"d = h\,\frac{L}{D}, \qquad \tan\gamma = \frac{1}{L/D}, "
           r"\qquad w = V\sin\gamma"),
    explanation=(
        "How far an unpowered aircraft travels for the height it gives up. The "
        "glide ratio <b>is</b> the lift-to-drag ratio - and it does not depend "
        "on weight. A heavier aircraft glides exactly as far, just faster and "
        "sinking quicker."),
    inputs=[
        Field("ld", "Lift-to-drag ratio L/D", "-", 15.0, min=0.0),
        Field("height", "Height lost h", "m", 1000.0, min=0.0),
        Field("wing_loading", "Wing loading W/S", "N/m²", 120.0, min=0.0,
              help="For the airspeed and sink rate. Has no effect on how far "
                   "you glide."),
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0),
        Field("cl", "Lift coefficient C_L", "-", 0.8, min=0.0),
    ],
    compute=lambda i: glide_distance(i.height, i.ld),
    result=Output("Glide distance", "m"),
    secondary=[
        Secondary("Glide ratio", "m per m", lambda i, r: glide_ratio(i.ld)),
        Secondary("Glide angle below horizontal", "°",
                  lambda i, r: glide_angle_deg(i.ld)),
        Secondary("Airspeed along the glide path", "m/s",
                  lambda i, r: glide_speed(i.wing_loading, i.rho, i.cl, i.ld)),
        Secondary("Sink rate", "m/s",
                  lambda i, r: sink_rate(i.wing_loading, i.rho, i.cl, i.ld)),
        Secondary("Time in the air", "s",
                  lambda i, r: i.height / sink_rate(i.wing_loading, i.rho,
                                                    i.cl, i.ld)),
        Secondary("Minimum-sink speed (0.760 × this speed)", "m/s",
                  lambda i, r: 0.759836 * glide_speed(i.wing_loading, i.rho,
                                                      i.cl, i.ld)),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            f"L/D = {i.ld:.0f} is beyond anything that has "
                            "flown. The best open-class sailplanes reach about "
                            "70, and nothing else comes close. Check whether "
                            "you have entered a glide ratio in feet-per-mile or "
                            "a percentage by mistake.")
              if i.ld > 70.0 else None),
        Check(lambda i, r: ("info",
                            f"At L/D = {i.ld:.1f} the glide angle is "
                            f"{glide_angle_deg(i.ld):.0f}°, which is steep "
                            "enough that the shallow-glide intuition stops "
                            "working: you are descending nearly as fast as you "
                            "are going forward. A helicopter in autorotation "
                            "lives near 4 and the Space Shuttle landed at about "
                            "4.5, so this is a real regime - just not a "
                            "forgiving one.")
              if i.ld < 4.0 else None),
        Check(lambda i, r: ("warning",
                            f"C_L = {i.cl:.2f} is at or beyond the stall for "
                            "most clean wings, so the airspeed and sink rate "
                            "below are not flyable. Best L/D normally occurs "
                            "near C_L = 0.6-1.0; if you want the slowest "
                            "descent, that is minimum sink, and it still sits "
                            "well below C_Lmax.")
              if i.cl > 1.4 else None),
    ],
    assumptions=[
        "Steady, unaccelerated glide in still air, with lift perpendicular and "
        "drag parallel to the FLIGHT PATH rather than to the horizon. Under "
        "that convention d = h × (L/D) is exact, not a small-angle "
        "approximation.",
        "Glide distance is independent of weight. Weight changes the speed and "
        "the sink rate, not the distance - which surprises nearly everyone.",
        "Best glide and minimum sink are DIFFERENT speeds. Best glide maximises "
        "L/D; minimum sink maximises C_L^1.5/C_D and is slower. Do not use one "
        "number for both.",
        "Still air. A headwind shortens ground distance and is answered by "
        "flying faster than best glide; a tailwind by flying slower.",
        "L/D here is the value at this airspeed, not the aircraft's maximum.",
        "Height lost is height above the ground you intend to land on, not "
        "altitude above sea level. Terrain elevation is the most common way "
        "this calculation is used wrongly.",
        "The airspeed and sink rate use the wing loading, density and C_L you "
        "entered, and they DO depend on weight - only the distance does not. "
        "A heavier aircraft flies the same glide path faster and steeper in "
        "time, arriving at the same place sooner.",
        "The 0.760 minimum-sink factor and the 0.877 sink-rate factor assume a "
        "parabolic drag polar, C_D = C_D0 + k C_L². Real polars depart from "
        "that near the stall and near the drag rise, so treat the factors as "
        "close guides rather than exact values for your aircraft.",
        "A windmilling propeller adds drag and can cut L/D by several points; "
        "a feathered or stopped one costs far less. The manufacturer's best "
        "glide figure assumes one specific propeller condition.",
    ],
    graph=Sweep(over="ld", y_label="Glide distance [m]", lo_factor=0.2,
                hi_factor=2.5,
                title="Glide distance vs L/D at a fixed height lost"),
    graphs=[
        Sweep(over="height", y_label="Glide distance [m]", lo=0.0,
              hi_factor=2.0, title="Glide distance vs height lost"),
    ],
    references=[
        Reference(
            title="Glide ratios of real aircraft",
            columns=("Aircraft", "Glide ratio (L/D)"),
            rows=[
                ("Modern open-class sailplane", "50 - 70"),
                ("15 m standard-class sailplane", "38 - 45"),
                ("Airliner, all engines out", "15 - 19"),
                ("Hang glider, modern flexwing", "12 - 17"),
                ("Fixed-wing UAV", "8 - 15"),
                ("Light aircraft (Cessna 172 class)", "~9"),
                ("Paraglider", "8 - 11"),
                ("Space Shuttle orbiter, subsonic approach", "~4.5"),
                ("Helicopter in autorotation", "~4"),
                ("Multirotor with no power", "≈ 0 - it descends, it does not glide"),
            ],
            note="Best-glide figures at the aircraft's best-glide speed and "
                 "weight, in still air. Anything that adds drag - gear down, "
                 "flaps out, a windmilling propeller, a damaged airframe - "
                 "takes points off directly.",
        ),
        Reference(
            title="Best glide vs minimum sink",
            columns=("Quantity", "Best glide", "Minimum sink"),
            rows=[
                ("Maximises", "L/D", "C_L^1.5 / C_D"),
                ("Airspeed", "V", "0.760 × V"),
                ("Sink rate", "w", "0.877 × w"),
                ("Lift coefficient", "C_L", "1.732 × C_L"),
                ("Use it for", "Reaching a distant field",
                 "Staying up longest, thermalling"),
            ],
            note="Exact ratios for a parabolic drag polar C_D = C_D0 + k C_L². "
                 "They are different speeds and confusing them is the classic "
                 "error: flying at minimum sink to reach a far-off runway "
                 "wastes about 12% of the distance you had.",
        ),
    ],
    related=["aero.lift_to_drag", "aero.drag", "aero.wing_loading",
             "flight.stall_speed", "flight.rate_of_climb"],
    variables=[
        ("$d$", "Ground distance covered", "m"),
        ("$h$", "Height lost", "m"),
        ("$L/D$", "Lift-to-drag ratio, equal to the glide ratio", "-"),
        ("$\\gamma$", "Glide angle below the horizon", "°"),
        ("$w$", "Sink rate", "m/s"),
    ],
    example=(
        "Engine failure planning. A UAV at L/D = 15 losing 1000 m covers 15 km "
        "in still air, descending at 3.81°. At a wing loading of 120 N/m² and "
        "C_L = 0.8 it flies that glide at 15.63 m/s, sinking 1.04 m/s, which "
        "buys 962 s - 16 minutes - to pick a field and set up. Doubling the "
        "payload changes neither the 15 km nor the 3.81°; it just makes the "
        "aircraft fly faster and arrive sooner. To stay up longest instead, "
        "slow to the minimum-sink speed of 11.88 m/s, where the sink rate "
        "falls to 0.91 m/s - but the glide then covers only about 13 km."),
    keywords=("glide", "gliding", "dead stick", "sink rate", "glide ratio",
              "engine failure", "best glide", "minimum sink", "autorotation"),
)

CALCULATORS = [_TWR, _PWR, _STALL, _CLIMB, _GLIDE]
