"""Drone powertrain studio: size a multirotor from airframe to pack.

Chains four things that are separate pages elsewhere, in the order the design
actually happens:

    the aircraft  ->  the propulsion  ->  the battery  ->  a verdict

Everything is computed by the existing verified functions - momentum theory and
hover power from calculators/propulsion.py, pack voltage, sag and endurance
from calculators/drones.py - so this page cannot drift away from what those
pages say.

The one thing this studio does that a naive flight-time estimate does not: it
feeds the sagged pack voltage back into the current. A battery is a voltage
source with a resistor in series with it, the ESC answers a voltage drop by
drawing more current, and the extra current comes out of the same coulombs that
were supposed to be your flight time.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple

import streamlit as st

from calculators import drones, propulsion
from studios import shell
from utils import ui
from utils.constants import A_SL, G0, GRAM_FORCE_N, RHO_SL
from utils.formatting import format_number
from utils.spec import Calculator

PREFIX = "studio_drone"

INCH_M = 0.0254
"""Metres in an inch, exact by definition. Propellers are sold in inches
everywhere in the world, including where everything else is metric."""

TWR_TARGET = 2.0
"""Thrust-to-weight a multirotor is designed to. At 2.0 hover sits at half
throttle, which leaves as much thrust above the hover point as below it - the
symmetry the attitude controller needs to answer a gust in either direction."""

TWR_FLOOR = 1.5
"""Below this the aircraft is not controllable in any useful sense: hovering
already needs two thirds of the available thrust, so a turn, a gust or its own
descending wake has almost nothing left to answer with."""

CELL_FLOOR_V = 3.3
"""Volts per cell under load that the pack must stay above. This is the usual
ESC low-voltage cutoff; below 3.0 V (drones.LIPO_CUTOFF_V) the cell is being
damaged rather than merely emptied."""

DISK_LOADING_BAND = (25.0, 500.0)
"""N/m² the hover is sane in, matching the band the momentum-theory page warns
outside. Under 25 the rotors are enormous, heavy and easily upset by wind; over
500 induced power dominates the whole aircraft and the downwash starts moving
the ground around."""

TIP_MACH_LIMIT = 0.70
"""Rotational tip Mach above which compressibility and noise take over. The
propeller page warns at the same number; most propellers are designed to stay
under about 0.75 and full-scale helicopters hold 0.6-0.65 in hover."""


def current_for_power(power_w: float, voltage: float) -> float:
    """I = P / V   [A] - drones.electrical_power read backwards.

    The only piece of arithmetic in this studio that is not a call into a
    calculator page, and it is the inverse of one that is: feeding this current
    and this voltage back into drones.electrical_power returns the power it
    started from. That round trip is what the test for it checks.
    """
    if voltage <= 0:
        raise ValueError("Pack voltage must be greater than zero.")
    if power_w < 0:
        raise ValueError("Power cannot be negative.")
    return power_w / voltage


# ---------------------------------------------------------------------------
# The aircraft
# ---------------------------------------------------------------------------
class Aircraft(NamedTuple):
    weight: float               # N, all-up
    radius: float               # m, one rotor
    area: float                 # m^2, one rotor disk
    thrust_per_rotor: float     # N each rotor must make to hover
    disk_loading: float         # N/m^2, per rotor
    induced_velocity: float     # m/s of downwash in hover
    ideal_power: float          # W, all rotors, momentum-theory floor


def aircraft(mass_kg: float, n_rotors: int, diameter_in: float,
             rho: float = RHO_SL) -> Aircraft:
    """What the airframe asks of the air before any hardware is chosen.

    Every rotor carries an equal share of the weight, which is what a level
    hover means. The ideal power that comes out of this is a floor no rotor
    beats - it is the power needed just to throw enough air downward, with a
    perfect, lossless, infinitely thin disk doing the throwing.
    """
    mass_kg = float(mass_kg)
    if mass_kg <= 0:
        raise ValueError("All-up mass must be greater than zero.")
    diameter_m = float(diameter_in) * INCH_M
    if diameter_m <= 0:
        raise ValueError("Rotor diameter must be greater than zero.")

    weight = mass_kg * G0
    radius = diameter_m / 2.0
    area = propulsion.disk_area(radius)
    per_rotor = drones.hover_thrust_per_motor(weight, n_rotors)
    return Aircraft(
        weight=weight,
        radius=radius,
        area=area,
        thrust_per_rotor=per_rotor,
        disk_loading=propulsion.disk_loading(per_rotor, area),
        induced_velocity=propulsion.induced_velocity_hover(per_rotor, area,
                                                           rho),
        # Each rotor pays its own ideal power; the aircraft pays all of them.
        ideal_power=n_rotors * propulsion.ideal_hover_power(per_rotor, area,
                                                            rho),
    )


# ---------------------------------------------------------------------------
# The propulsion
# ---------------------------------------------------------------------------
class Powertrain(NamedTuple):
    shaft_power: float          # W, all rotors, after the figure of merit
    electrical_power: float     # W, all rotors, after motor and ESC losses
    power_loading: float        # g/W, the drone community's yardstick
    system_merit: float         # ideal power / electrical power
    tip_speed: float            # m/s, rotational component only
    tip_mach: float             # tip speed / speed of sound at sea level
    max_thrust: float           # N, every motor at full throttle
    thrust_to_weight: float     # -


def powertrain(craft: Aircraft, n_rotors: int, figure_of_merit: float,
               efficiency: float, hover_rpm: float, max_thrust_gf: float,
               rho: float = RHO_SL) -> Powertrain:
    """What the rotors, motors and ESCs turn that demand into.

    Two efficiencies in series and they are not the same kind of thing. The
    figure of merit is aerodynamic: how close this rotor gets to the ideal disk
    of the step before. The drivetrain efficiency is electrical: how much of the
    power that leaves the battery reaches the shaft at all.

    Shaft power is the electrical calculation run with a perfect drivetrain, so
    the two can never disagree about the rotor.
    """
    shaft = propulsion.hover_electrical_power(
        craft.weight, n_rotors, craft.radius, figure_of_merit, 1.0, rho)
    electrical = propulsion.hover_electrical_power(
        craft.weight, n_rotors, craft.radius, figure_of_merit, efficiency, rho)

    speed = propulsion.tip_speed(float(hover_rpm) / 60.0, craft.radius * 2.0)
    thrust_max = drones.total_thrust(
        n_rotors, drones.grams_force_to_newton(max_thrust_gf))
    return Powertrain(
        shaft_power=shaft,
        electrical_power=electrical,
        # power_loading returns N/W; a gram-force per watt is the same number
        # divided by the newtons in a gram-force.
        power_loading=propulsion.power_loading(craft.weight, electrical)
        / GRAM_FORCE_N,
        # The whole aircraft measured against the ideal disk: FM and drivetrain
        # efficiency multiplied together, computed rather than assumed.
        system_merit=propulsion.figure_of_merit(craft.ideal_power, electrical),
        tip_speed=speed,
        tip_mach=speed / A_SL,
        max_thrust=thrust_max,
        thrust_to_weight=thrust_max / craft.weight,
    )


# ---------------------------------------------------------------------------
# The battery
# ---------------------------------------------------------------------------
class Battery(NamedTuple):
    pack_voltage: float         # V at rest
    energy_wh: float            # Wh nameplate
    resistance: float           # ohm, whole pack
    hover_current: float        # A, at the sagged voltage
    c_rate: float               # multiples of capacity per hour
    sag: float                  # V lost inside the pack
    loaded_voltage: float       # V at the terminals while hovering
    loaded_cell_voltage: float  # V per cell while hovering
    internal_heat: float        # W dissipated in the cells
    endurance: float            # minutes, counting the sagged current
    endurance_ideal: float      # minutes, ignoring sag - the optimistic one


def battery(drive: Powertrain, cells: int, volts_per_cell: float,
            capacity_ah: float, milliohm_per_cell: float,
            usable_fraction: float) -> Battery:
    """The pack, and what hovering does to it.

    The current is found twice. The first pass divides the hover power by the
    resting pack voltage; that current sags the pack, and the ESC answers the
    lower voltage by drawing more current for the same power, so the second
    pass divides by the sagged voltage. One pass is enough - at any sag a pack
    should be asked to survive, a third pass moves the answer by well under a
    percent.

    Endurance is then counted in coulombs, not watt-hours, because it is the
    charge leaving the pack that empties it, and the extra current the sag
    causes is charge spent heating the cells rather than turning the rotors.
    """
    open_circuit = int(cells) * float(volts_per_cell)
    energy = drones.battery_energy_wh(open_circuit, capacity_ah)
    resistance = drones.pack_internal_resistance(cells, milliohm_per_cell)

    first_pass = current_for_power(drive.electrical_power, open_circuit)
    sagged = drones.loaded_pack_voltage(cells, volts_per_cell,
                                        milliohm_per_cell, first_pass)
    current = current_for_power(drive.electrical_power, sagged)

    sag = drones.voltage_sag(current, resistance)
    loaded = drones.loaded_pack_voltage(cells, volts_per_cell,
                                        milliohm_per_cell, current)
    return Battery(
        pack_voltage=open_circuit,
        energy_wh=energy,
        resistance=resistance,
        hover_current=current,
        # A C rate is current as a multiple of capacity: 5 A out of a 5 Ah pack
        # is 1 C, and empties it in an hour.
        c_rate=current / float(capacity_ah),
        sag=sag,
        loaded_voltage=loaded,
        loaded_cell_voltage=loaded / int(cells),
        # The sag and the current are across and through the same resistance,
        # so their product is the heat staying inside the pack.
        internal_heat=drones.electrical_power(sag, current),
        endurance=drones.flight_time_minutes(capacity_ah, usable_fraction,
                                             current),
        endurance_ideal=propulsion.hover_endurance_minutes(
            energy, usable_fraction, drive.electrical_power),
    )


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------
def verdicts(craft: Aircraft, drive: Powertrain, pack: Battery,
             target_minutes: float, c_rating: float) -> List[Dict[str, object]]:
    """Every check this studio makes, with the margin that decided it."""
    low, high = DISK_LOADING_BAND
    disk_margin = min(craft.disk_loading / low, high / craft.disk_loading)
    return [
        shell.check(
            "Thrust-to-weight", drive.thrust_to_weight >= TWR_TARGET,
            drive.thrust_to_weight / TWR_TARGET,
            f"{format_number(drive.thrust_to_weight, 3)}:1 at full throttle, "
            f"hovering at {format_number(100.0 / drive.thrust_to_weight, 3)}% "
            f"of it; {TWR_TARGET} is the target and {TWR_FLOOR} the floor"),
        shell.check(
            "Hover endurance", pack.endurance >= target_minutes,
            pack.endurance / target_minutes if target_minutes > 0
            else float("inf"),
            f"{format_number(pack.endurance, 3)} min against a "
            f"{format_number(target_minutes, 3)} min target"),
        shell.check(
            "Discharge rate", pack.c_rate <= c_rating,
            c_rating / pack.c_rate if pack.c_rate > 0 else float("inf"),
            f"hovering draws {format_number(pack.hover_current, 3)} A, "
            f"{format_number(pack.c_rate, 3)}C against a "
            f"{format_number(c_rating, 3)}C pack"),
        shell.check(
            "Pack voltage under load",
            pack.loaded_cell_voltage >= CELL_FLOOR_V,
            pack.loaded_cell_voltage / CELL_FLOOR_V,
            f"{format_number(pack.loaded_cell_voltage, 3)} V per cell while "
            f"hovering, floor is {CELL_FLOOR_V} V"),
        shell.check(
            "Disk loading", low <= craft.disk_loading <= high, disk_margin,
            f"{format_number(craft.disk_loading, 3)} N/m² throwing air down at "
            f"{format_number(craft.induced_velocity, 3)} m/s, band is "
            f"{format_number(low, 3)}-{format_number(high, 3)} N/m²"),
        shell.check(
            "Tip speed", drive.tip_mach <= TIP_MACH_LIMIT,
            TIP_MACH_LIMIT / drive.tip_mach if drive.tip_mach > 0
            else float("inf"),
            f"Mach {format_number(drive.tip_mach, 2)} "
            f"({format_number(drive.tip_speed, 3)} m/s), limit is Mach "
            f"{TIP_MACH_LIMIT}"),
    ]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def render(prefs=None, catalogue=None) -> None:
    prefs = prefs or {}
    ui.page_header(
        "Drone powertrain",
        r"P_{elec} = \frac{N}{FM\,\eta}\,\frac{(W/N)^{3/2}}{\sqrt{2\rho A}},"
        r"\qquad V_{load} = V_{oc} - I R_{int}",
        "Take a multirotor from an all-up mass to a flight time: what the air "
        "charges to hold the aircraft up, what the rotors and motors add to "
        "that bill, and what it does to the pack. Every number comes from the "
        "same functions the individual calculator pages use.",
        PREFIX)

    # -- 1 ------------------------------------------------------------------
    shell.step(1, "The aircraft",
               "Mass and disk area decide the hover before any hardware does.")
    a, b, c, d = st.columns(4)
    with a:
        mass = st.number_input("All-up mass [kg]", value=1.5, min_value=0.01,
                               step=0.1, key=f"{PREFIX}_mass",
                               help="Everything that leaves the ground: "
                                    "airframe, battery, payload, the lot.")
    with b:
        rotors = int(st.number_input("Rotors", value=4, min_value=1,
                                     max_value=32, step=1,
                                     key=f"{PREFIX}_rotors",
                                     help="Count discs, not blades. Coaxial "
                                          "pairs do not have twice the disk "
                                          "area - the lower rotor works in the "
                                          "upper one's wake."))
    with c:
        diameter = st.number_input("Rotor diameter [in]", value=10.0,
                                   min_value=0.5, step=0.5,
                                   key=f"{PREFIX}_dia",
                                   help="The number on the propeller. "
                                        "10 in = 0.254 m.")
    with d:
        rho = st.number_input("Air density [kg/m³]", value=RHO_SL,
                              min_value=0.05, step=0.025, key=f"{PREFIX}_rho",
                              help="1.225 at sea level on a standard day. "
                                   "Hot and high is thinner, and induced power "
                                   "goes as 1/√ρ.")

    try:
        craft = aircraft(mass, rotors, diameter, rho)
    except Exception as exc:
        ui.error(exc)
        return

    shell.figures([("Disk area, one rotor", craft.area, "m²"),
                   ("Hover thrust per rotor", craft.thrust_per_rotor, "N"),
                   ("Disk loading", craft.disk_loading, "N/m²"),
                   ("Downwash", craft.induced_velocity, "m/s"),
                   ("Ideal hover power", craft.ideal_power, "W")])
    st.caption("That power is a floor, not an estimate. It is what a perfect "
               "rotor would need just to throw enough air downward, and no "
               "blade, motor or firmware beats it.")

    # -- 2 ------------------------------------------------------------------
    shell.step(2, "The propulsion",
               "What the rotors, motors and ESCs add to that floor.")
    e, f, g, h = st.columns(4)
    with e:
        merit = st.slider("Figure of merit", 0.30, 0.80, 0.55, 0.01,
                          key=f"{PREFIX}_fm",
                          help="How close the rotor gets to the ideal disk. "
                               "A multirotor propeller is 0.40-0.65; only a "
                               "full-scale helicopter rotor reaches 0.75.")
    with f:
        efficiency = st.slider("Motor + ESC efficiency", 0.40, 0.98, 0.80,
                               0.01, key=f"{PREFIX}_eta",
                               help="Electrical in, shaft out. 0.75-0.85 is "
                                    "typical near the hover point; it falls "
                                    "away at both very low and very high "
                                    "throttle.")
    with g:
        hover_rpm = st.number_input("Hover rotor speed [rpm]", value=4800.0,
                                    min_value=1.0, step=100.0,
                                    key=f"{PREFIX}_rpm",
                                    help="From a propeller thrust test at the "
                                         "hover thrust above, or Kv × loaded "
                                         "pack voltage × hover throttle.")
    with h:
        max_gf = st.number_input("Max thrust per motor [gf]", value=1100.0,
                                 min_value=0.0, step=50.0,
                                 key=f"{PREFIX}_maxgf",
                                 help="The top row of the motor's thrust "
                                      "table, on this propeller and this cell "
                                      "count. A gram-force is a force: "
                                      "1 gf = 0.00981 N.")

    try:
        drive = powertrain(craft, rotors, merit, efficiency, hover_rpm, max_gf,
                           rho)
    except Exception as exc:
        ui.error(exc)
        return

    shell.figures([("Shaft power", drive.shaft_power, "W"),
                   ("Electrical power", drive.electrical_power, "W"),
                   ("Power loading", drive.power_loading, "g/W"),
                   ("System figure of merit", drive.system_merit, "-"),
                   ("Tip speed", drive.tip_speed, "m/s"),
                   ("Thrust-to-weight", drive.thrust_to_weight, ":1")])
    st.caption(f"Two losses in series and only one of them is electrical. The "
               f"system figure of merit is the ideal power divided by what the "
               f"battery is actually asked for, so it is FM × efficiency - "
               f"{format_number(drive.system_merit, 3)} here, against 1.0 for "
               f"a perfect aircraft that cannot be built.")

    # -- 3 ------------------------------------------------------------------
    shell.step(3, "The battery",
               "The pack has to supply that power, and it fights back.")
    i, j, k = st.columns(3)
    with i:
        cells = int(st.number_input("Cells in series (S)", value=4,
                                    min_value=1, max_value=24, step=1,
                                    key=f"{PREFIX}_cells"))
        v_cell = st.number_input("Resting volts per cell [V]", value=3.70,
                                 min_value=2.5, max_value=4.25, step=0.05,
                                 key=f"{PREFIX}_vcell",
                                 help="4.20 full, 3.70 nominal, 3.50 getting "
                                      "low. Sizing at nominal describes the "
                                      "middle of the flight rather than the "
                                      "best minute of it.")
    with j:
        capacity = st.number_input("Capacity [Ah]", value=5.0, min_value=0.01,
                                   step=0.5, key=f"{PREFIX}_cap",
                                   help="5000 mAh is 5.0 Ah.")
        c_rating = st.number_input("Rated discharge [C]", value=30.0,
                                   min_value=0.1, step=5.0,
                                   key=f"{PREFIX}_crate",
                                   help="Continuous, not burst. A printed "
                                        "100C is a burst figure; a genuine "
                                        "high-discharge LiPo sustains 20-40C.")
    with k:
        r_cell = st.number_input("Internal resistance per cell [mΩ]",
                                 value=4.0, min_value=0.0, step=0.5,
                                 key=f"{PREFIX}_rcell",
                                 help="Your charger measures this. 2-6 mΩ is a "
                                      "healthy LiPo; a Li-ion 18650 is 30-60. "
                                      "It rises with age and steeply in the "
                                      "cold.")
        usable = st.slider("Usable fraction of capacity", 0.30, 1.00, 0.80,
                           0.05, key=f"{PREFIX}_usable",
                           help="Land on a reserve. Above 0.85 cycle life "
                                "falls steeply and the last volts collapse "
                                "fastest.")

    try:
        pack = battery(drive, cells, v_cell, capacity, r_cell, usable)
    except Exception as exc:
        ui.error(exc)
        return

    shell.figures([("Pack voltage at rest", pack.pack_voltage, "V"),
                   ("Pack energy", pack.energy_wh, "Wh"),
                   ("Hover current", pack.hover_current, "A"),
                   ("Discharge rate", pack.c_rate, "C"),
                   ("Voltage sag", pack.sag, "V"),
                   ("Loaded pack voltage", pack.loaded_voltage, "V")])
    shell.figures([("Volts per cell under load", pack.loaded_cell_voltage,
                    "V"),
                   ("Heat inside the pack", pack.internal_heat, "W"),
                   ("Hover endurance", pack.endurance, "min"),
                   ("Endurance ignoring sag", pack.endurance_ideal, "min")])
    st.caption(
        f"The two endurance figures differ by "
        f"{format_number(pack.endurance_ideal - pack.endurance, 2)} min "
        f"because the ESC answers a sagging pack by pulling more current for "
        f"the same power. That extra current still comes out of the pack's "
        f"coulombs - it just heats the cells "
        f"({format_number(pack.internal_heat, 3)} W here) instead of turning "
        f"the rotors.")

    # -- 4 ------------------------------------------------------------------
    shell.step(4, "The verdict",
               "Whether what you described will actually fly, and for how long.")
    target = st.number_input("Target hover endurance [min]", value=12.0,
                             min_value=0.1, step=1.0, key=f"{PREFIX}_target",
                             help="The requirement this aircraft exists to "
                                  "meet. Hover is the worst case; forward "
                                  "flight on a multirotor is usually a little "
                                  "cheaper, manoeuvring a lot more expensive.")
    shell.verdict_board(verdicts(craft, drive, pack, target, c_rating))

    shell.send_to_project(PREFIX, [
        ("All-up mass", mass, "kg"),
        ("Rotor diameter", craft.radius * 2.0, "m"),
        ("Hover electrical power", drive.electrical_power, "W"),
        ("Hover current", pack.hover_current, "A"),
        ("Pack energy", pack.energy_wh, "Wh"),
        ("Hover endurance", pack.endurance, "min"),
    ], note="from the drone powertrain studio")

    ui.assumptions([
        "Momentum theory, which knows nothing about blades. It assumes a "
        "uniformly loaded disk in still air with no swirl, no tip losses and "
        "no blade of its own. The figure of merit is where all of that is "
        "hidden, so an FM taken from the wrong propeller moves every power "
        "and endurance number on this page in proportion.",
        "Hover only, in still air, out of ground effect. Climbing costs "
        "roughly the extra thrust times the climb rate on top of this; "
        "manoeuvring costs far more than that; and within about one rotor "
        "radius of the ground the same thrust costs noticeably less power, "
        "which is why a drone that will not climb still lifts off.",
        "Every rotor carries an identical share of the weight. A payload hung "
        "off-centre, or a coaxial pair where the lower rotor works in the "
        "upper one's wake, breaks that - the loaded rotors need more power "
        "than this page charges, and hit their thrust limit first.",
        "Rotor speed is something you tell this page, not something it solves "
        "for. There is no propeller model here: nothing checks that the "
        "diameter, pitch and rpm you entered actually make the hover thrust "
        "the first step demands. If the rpm is wrong, only the tip-speed "
        "check is wrong with it - the power numbers do not depend on it.",
        "Motor and ESC efficiency is one number covering copper losses, iron "
        "losses, switching losses and the propeller adapter. A real motor's "
        "efficiency peaks well below its maximum current and falls away on "
        "both sides, so a single figure flatters an aircraft hovering far off "
        "that peak - a very low or very high hover throttle most of all.",
        "Max thrust per motor is taken straight from you and assumed "
        "available. It is a bench figure measured on a fresh, cold, fully "
        "charged pack; by mid-flight the pack is at nominal voltage and warm, "
        "and the same motor makes measurably less. Thrust-to-weight in the "
        "air is lower than thrust-to-weight in the table.",
        "The pack is modelled as a perfect voltage source behind one constant "
        "resistance. Real internal resistance rises as the pack empties, rises "
        "with age, and can double in the cold - so a design that clears the "
        "voltage-under-load check on paper can still brown out on a winter "
        "flight or in its last minute.",
        "Voltage sag is computed at the hover current only. A punch-out or a "
        "hard correction draws several times that, and the sag goes up with "
        "it - which is when a pack that hovers happily hits the ESC cutoff. "
        "Check the loaded voltage again at the current your max thrust implies.",
        "Endurance counts charge out of the pack, so it already includes the "
        "extra current the sag causes. It does not include the capacity a pack "
        "simply fails to deliver at high discharge rates, the energy lost "
        "warming the cells at the start of a flight, or the reserve you should "
        "be landing on - the usable fraction is yours to set honestly.",
        "The current is found in one refinement pass rather than solved "
        "exactly: hover power divided by the resting voltage, then divided "
        "again by the voltage that current sags the pack to. At any sag a pack "
        "should be asked to survive this is worth well under a percent; at a "
        "sag where it would matter, the pack has already failed the "
        "voltage-under-load check.",
        f"Tip Mach uses the sea-level speed of sound ({A_SL} m/s) and the "
        "rotational tip speed alone. Cold air is slower, which pushes the real "
        "Mach number up, and any forward speed adds to the tip's own speed "
        "vectorially - so a rotor near the limit here is over it in flight.",
        "Nothing here checks structure, thermals or control. The arms, the "
        "motor mounts and the ESC's ability to carry this current for a whole "
        "flight are all outside this page.",
    ])


CALCULATORS = [
    Calculator(slug="studio.drone_powertrain", name="Drone powertrain",
               latex="", explanation="", render=render,
               keywords=("studio", "drone", "multirotor", "quadcopter",
                         "powertrain", "hover", "battery", "lipo", "endurance",
                         "flight time", "motor", "esc", "propeller", "thrust "
                         "to weight", "sag", "workflow")),
]
