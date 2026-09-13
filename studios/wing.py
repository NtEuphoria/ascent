"""Wing study: size a wing, then find out where its own model expires.

Chains four steps in the order a wing actually gets designed:

    the aircraft  ->  the aerofoil and drag  ->  the flight envelope  ->  a verdict

Everything is computed by the existing verified functions - geometry, the drag
polar and best L/D from calculators/aerodynamics.py, the atmosphere, stall,
climb, turn and glide from calculators/flight.py - so this page cannot drift
away from what those pages say.

Two of the verdicts are unusual, and they are the point of the page. The Mach
and Reynolds checks do not ask whether the wing is good; they ask whether the
parabolic drag polar used everywhere above is still a description of reality.
A wing can pass every performance check and still be a fantasy because it was
sized with aerofoil data that does not apply to it.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple

import streamlit as st

from calculators import aerodynamics as aero
from calculators import flight
from studios import shell
from utils import ui
from utils.constants import MU_AIR_SL
from utils.formatting import format_number
from utils.spec import Calculator

PREFIX = "studio_wing"

APPROACH_MARGIN = 1.3
"""Cruise speed wanted as a multiple of stall speed. 1.3 V_s is the standard
approach-speed margin in civil practice; below it the aircraft is flying on the
back of the drag curve, where slowing down needs more power, not less."""

MACH_LIMIT = 0.3
"""Above roughly this Mach number air can no longer be treated as
incompressible, and the whole drag polar on this page stops being right."""

REYNOLDS_FLOOR = 2.0e5
"""Below roughly this chord Reynolds number a published aerofoil polar almost
certainly does not apply. Laminar separation bubbles appear, C_D0 can double
and C_Lmax collapses - the single most common error in small-UAV wing design."""


# ---------------------------------------------------------------------------
# The aircraft
# ---------------------------------------------------------------------------
class Aircraft(NamedTuple):
    weight: float           # N
    aspect_ratio: float     # -
    wing_loading: float     # N/m^2
    density: float          # kg/m^3 at the cruise altitude
    temperature: float      # K at the cruise altitude
    mean_chord: float       # m, the mean geometric chord S/b


def aircraft(mass_kg: float, span_m: float, area_m2: float,
             altitude_m: float, isa_deviation_c: float = 0.0) -> Aircraft:
    """The four numbers a wing is drawn from, turned into the four it is sized by.

    Density comes from ISA pressure at this altitude and the *actual* air
    temperature, so a hot day thins the air without moving the altimeter. With
    no temperature deviation this reduces exactly to the standard atmosphere.

    Mean chord here is the mean geometric chord S/b, which is what sets the
    Reynolds number for a rectangular wing. A tapered wing's mean aerodynamic
    chord is larger.
    """
    weight = flight.weight_from_mass(mass_kg)
    ratio = aero.aspect_ratio(span_m, area_m2)      # validates span and area
    loading = aero.wing_loading(weight, area_m2)
    temperature = flight.isa_temperature(altitude_m) + float(isa_deviation_c)
    density = flight.air_density(flight.isa_pressure(altitude_m), temperature)
    return Aircraft(weight, ratio, loading, density, temperature,
                    float(area_m2) / float(span_m))


# ---------------------------------------------------------------------------
# The aerofoil and drag
# ---------------------------------------------------------------------------
class Polar(NamedTuple):
    cd0: float              # zero-lift drag coefficient, carried forward
    oswald: float           # span efficiency factor, carried forward
    cl_max: float           # maximum usable C_L, carried forward
    induced_factor: float   # k in C_D = C_D0 + k C_L^2
    cl_best: float          # C_L at the best L/D
    cd_best: float          # C_D there
    ld_max: float           # the best L/D itself


def polar(craft: Aircraft, cd0: float, oswald: float, cl_max: float) -> Polar:
    """The drag bookkeeping, and the one point on it that matters most.

    The induced-drag factor k = 1/(pi e AR) is read off the existing function
    rather than rewritten: C_Di at C_L = 1 *is* k, by definition.

    At the best L/D a parabolic polar is exactly half parasite and half
    induced, so C_D there comes out at twice C_D0. That is not a coincidence to
    be coded in - it falls out of chaining the two functions, and the tests
    check that it still does.
    """
    factor = aero.induced_drag_coefficient(1.0, craft.aspect_ratio, oswald)
    cl_best = aero.cl_for_max_lift_to_drag(cd0, craft.aspect_ratio, oswald)
    cd_best = aero.drag_polar(cd0, cl_best, craft.aspect_ratio, oswald)
    ld_max = aero.max_lift_to_drag(cd0, craft.aspect_ratio, oswald)
    return Polar(float(cd0), float(oswald), float(cl_max), factor, cl_best,
                 cd_best, ld_max)


# ---------------------------------------------------------------------------
# The flight envelope
# ---------------------------------------------------------------------------
class Envelope(NamedTuple):
    speed: float            # m/s true airspeed in cruise
    cl: float               # C_L needed to hold level flight there
    cd: float               # C_D that follows from the polar
    drag: float             # N
    power: float            # W delivered to the air
    lift_to_drag: float     # at the cruise point, not the best point
    stall: float            # m/s, wings level
    stall_banked: float     # m/s in the turn
    load_factor: float      # g in the turn
    climb_rate: float       # m/s at the cruise speed with the thrust given
    glide_ratio: float      # = (L/D)max
    glide_angle: float      # deg below the horizon
    glide_speed: float      # m/s at the best-glide point
    sink_rate: float        # m/s at the best-glide point
    reynolds: float         # on the mean chord
    mach: float             # at the cruise temperature, not sea level


def envelope(craft: Aircraft, wing: Polar, area_m2: float, speed: float,
             thrust: float, bank_deg: float) -> Envelope:
    """What the wing does across the speed range, from stall to cruise.

    Cruise C_L is not a guess: in steady level flight lift equals weight, so
    C_L = (W/S) / q and nothing else is free. Every drag number follows from
    that one lift coefficient through the polar.

    Glide figures are quoted at the best-L/D point rather than at the cruise
    point, because that is the condition an engine failure is flown at.
    """
    speed = float(speed)
    if speed <= 0:
        raise ValueError("Cruise speed must be greater than zero.")

    q = aero.dynamic_pressure(craft.density, speed)
    cl = craft.wing_loading / q
    cd = aero.drag_polar(wing.cd0, cl, craft.aspect_ratio, wing.oswald)
    drag_force = aero.drag(craft.density, speed, area_m2, cd)

    stall = flight.stall_speed(craft.weight, craft.density, area_m2,
                               wing.cl_max)
    return Envelope(
        speed, cl, cd, drag_force,
        drag_force * speed,                       # P = D V, into the air
        aero.lift_to_drag(cl, cd),
        stall,
        flight.stall_speed_in_turn(stall, bank_deg),
        flight.load_factor(bank_deg),
        flight.rate_of_climb(thrust, drag_force, speed, craft.weight),
        flight.glide_ratio(wing.ld_max),
        flight.glide_angle_deg(wing.ld_max),
        flight.glide_speed(craft.wing_loading, craft.density, wing.cl_best,
                           wing.ld_max),
        flight.sink_rate(craft.wing_loading, craft.density, wing.cl_best,
                         wing.ld_max),
        aero.reynolds_number(craft.density, speed, craft.mean_chord,
                             MU_AIR_SL),
        aero.mach_number(speed, craft.temperature))


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------
def verdicts(flying: Envelope, stall_target: float,
             ld_target: float) -> List[Dict[str, object]]:
    """Every check this studio makes, with the margin that decided it.

    The last two are different in kind from the first three. They do not judge
    the wing; they judge whether the model that produced every other number on
    the page still applies to it.
    """
    approach = APPROACH_MARGIN * flying.stall
    return [
        shell.check(
            "Stall speed", flying.stall <= stall_target,
            stall_target / flying.stall,
            f"stalls at {format_number(flying.stall, 3)} m/s against a "
            f"{format_number(stall_target, 3)} m/s target"),
        shell.check(
            "Approach margin", flying.speed >= approach,
            flying.speed / approach,
            f"cruises at {format_number(flying.speed, 3)} m/s, wanted "
            f"{APPROACH_MARGIN}x stall = {format_number(approach, 3)} m/s"),
        shell.check(
            "Cruise L/D", flying.lift_to_drag >= ld_target,
            flying.lift_to_drag / ld_target,
            f"{format_number(flying.lift_to_drag, 3)} at the cruise point "
            f"against a target of {format_number(ld_target, 3)}"),
        shell.check(
            "Incompressible flow", flying.mach <= MACH_LIMIT,
            MACH_LIMIT / flying.mach,
            f"Mach {format_number(flying.mach, 3)} against a limit of "
            f"{MACH_LIMIT} - above it this drag polar is the wrong model"),
        shell.check(
            "Aerofoil data applies", flying.reynolds >= REYNOLDS_FLOOR,
            flying.reynolds / REYNOLDS_FLOOR,
            f"Re {format_number(flying.reynolds, 3)} on the mean chord "
            f"against a floor of {format_number(REYNOLDS_FLOOR, 3)}"),
    ]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def render(prefs=None, catalogue=None) -> None:
    prefs = prefs or {}
    ui.page_header(
        "Wing study",
        r"C_L = \frac{W/S}{\tfrac{1}{2}\rho V^{2}}, \qquad "
        r"C_D = C_{D_0} + \frac{C_L^{2}}{\pi e A\!R}, \qquad "
        r"\left(\frac{L}{D}\right)_{\max} = "
        r"\frac{1}{2}\sqrt{\frac{\pi e A\!R}{C_{D_0}}}",
        "Take a wing from four dimensions to a flight envelope: what it weighs "
        "per square metre, what its drag polar looks like, how slowly it can "
        "fly and how far it glides - and then whether the model that produced "
        "all of that still applies at the speed and scale you chose. Every "
        "number comes from the same functions the individual calculator pages "
        "use.",
        PREFIX)

    # -- 1 ------------------------------------------------------------------
    shell.step(1, "The aircraft", "Mass, planform and where it flies.")
    a, b, c, d, e = st.columns(5)
    with a:
        mass = st.number_input("All-up mass [kg]", value=10.5, min_value=0.01,
                               step=0.5, key=f"{PREFIX}_mass",
                               help="Everything that leaves the ground, at the "
                                    "heaviest condition you intend to fly.")
    with b:
        span = st.number_input("Wingspan b [m]", value=2.2, min_value=0.01,
                               step=0.1, key=f"{PREFIX}_span")
    with c:
        area = st.number_input("Wing area S [m²]", value=0.65, min_value=0.001,
                               step=0.05, key=f"{PREFIX}_area",
                               help="Projected planform area, including the "
                                    "part buried in the fuselage - the same "
                                    "reference area the coefficients below "
                                    "are defined against.")
    with d:
        altitude = st.number_input("Cruise altitude [m]", value=500.0,
                                   min_value=-1000.0, max_value=20000.0,
                                   step=100.0, key=f"{PREFIX}_alt")
    with e:
        deviation = st.number_input("Temperature vs ISA [°C]", value=0.0,
                                    min_value=-40.0, max_value=40.0, step=1.0,
                                    key=f"{PREFIX}_isadev",
                                    help="A hot day thins the air without "
                                         "moving the altimeter. Zero is the "
                                         "standard atmosphere.")

    try:
        craft = aircraft(mass, span, area, altitude, deviation)
    except Exception as exc:
        st.error(f"{exc}")
        return

    shell.figures([("Weight", craft.weight, "N"),
                   ("Aspect ratio", craft.aspect_ratio, "-"),
                   ("Wing loading", craft.wing_loading, "N/m²"),
                   ("Air density", craft.density, "kg/m³"),
                   ("Mean chord S/b", craft.mean_chord, "m")])
    st.caption("Wing loading is the number that decides how fast this aircraft "
               "has to fly. Aspect ratio is the one that decides how much it "
               "costs to make lift: induced drag falls as span grows.")

    # -- 2 ------------------------------------------------------------------
    shell.step(2, "The aerofoil and drag",
               "Three coefficients, and the best point on the polar they make.")
    f, g, h = st.columns(3)
    with f:
        cd0 = st.number_input("Zero-lift drag C_D0", value=0.030,
                              min_value=0.0001, step=0.002, format="%.4f",
                              key=f"{PREFIX}_cd0",
                              help="The whole aircraft's parasite drag on the "
                                   "wing reference area - not the aerofoil "
                                   "section alone. 0.02-0.03 is a clean small "
                                   "aircraft, 0.04+ a draggy one.")
    with g:
        oswald = st.slider("Oswald efficiency e", 0.50, 1.00, 0.80, 0.01,
                           key=f"{PREFIX}_e",
                           help="1.0 is a perfect elliptic loading and nothing "
                                "real reaches it. 0.7-0.85 for a whole "
                                "aircraft, higher for a clean sailplane.")
    with h:
        cl_max = st.number_input("Maximum usable C_Lmax", value=1.30,
                                 min_value=0.05, step=0.05,
                                 key=f"{PREFIX}_clmax",
                                 help="Of the whole configuration, not of the "
                                      "aerofoil section. Take 10-20% off a "
                                      "2-D section figure.")

    try:
        wing = polar(craft, cd0, oswald, cl_max)
    except Exception as exc:
        st.error(f"{exc}")
        return

    shell.figures([("Induced factor k = 1/(πeAR)", wing.induced_factor, "-"),
                   ("C_L at best L/D", wing.cl_best, "-"),
                   ("C_D there", wing.cd_best, "-"),
                   ("Best L/D", wing.ld_max, "-")])
    st.caption("At the best L/D the polar is exactly half parasite and half "
               "induced, so C_D there is twice C_D0. That is where the wing is "
               "working hardest for its drag - and it is not where most "
               "aircraft cruise, because cruising there is slow.")

    # -- 3 ------------------------------------------------------------------
    shell.step(3, "The flight envelope",
               "One speed sets the cruise; the wing sets both ends of it.")
    i, j, k = st.columns(3)
    with i:
        speed = st.number_input("Cruise speed V [m/s]", value=22.0,
                                min_value=0.1, step=1.0, key=f"{PREFIX}_v",
                                help="True airspeed, not indicated.")
    with j:
        thrust = st.number_input("Thrust available [N]", value=25.0,
                                 min_value=0.0, step=1.0, key=f"{PREFIX}_t",
                                 help="At this speed. A propeller's thrust "
                                      "falls as the aircraft speeds up, so a "
                                      "static figure is optimistic here.")
    with k:
        bank = st.number_input("Bank angle in a turn [deg]", value=45.0,
                               min_value=0.0, max_value=89.0, step=5.0,
                               key=f"{PREFIX}_bank")

    try:
        flying = envelope(craft, wing, area, speed, thrust, bank)
    except Exception as exc:
        st.error(f"{exc}")
        return

    shell.figures([("Cruise C_L", flying.cl, "-"),
                   ("Cruise C_D", flying.cd, "-"),
                   ("Drag", flying.drag, "N"),
                   ("Power required", flying.power, "W"),
                   ("Cruise L/D", flying.lift_to_drag, "-")])
    shell.figures([("Stall speed", flying.stall, "m/s"),
                   (f"Stall at {format_number(bank, 3)}° bank",
                    flying.stall_banked, "m/s"),
                   ("Load factor in that turn", flying.load_factor, "g"),
                   ("Rate of climb at cruise speed", flying.climb_rate, "m/s")])
    shell.figures([("Best glide ratio", flying.glide_ratio, ":1"),
                   ("Glide angle", flying.glide_angle, "deg"),
                   ("Best-glide speed", flying.glide_speed, "m/s"),
                   ("Sink rate there", flying.sink_rate, "m/s"),
                   ("Reynolds on mean chord", flying.reynolds, "-"),
                   ("Mach", flying.mach, "-")])
    st.caption("Power required is D × V delivered to the air. Divide by "
               "propeller efficiency and then by drivetrain efficiency to get "
               "shaft or electrical power - typically 0.6-0.85 and 0.85-0.95, "
               "so the battery sees roughly half again as much.")

    # -- 4 ------------------------------------------------------------------
    shell.step(4, "The verdict",
               "Whether it flies - and whether these numbers still mean anything.")
    m, n = st.columns(2)
    with m:
        stall_target = st.number_input("Stall speed must be at or below [m/s]",
                                       value=15.0, min_value=0.1, step=0.5,
                                       key=f"{PREFIX}_vstarget",
                                       help="Set by how you land it: hand, "
                                            "belly, net or runway.")
    with n:
        ld_target = st.number_input("Cruise L/D must be at or above",
                                    value=11.0, min_value=0.1, step=0.5,
                                    key=f"{PREFIX}_ldtarget",
                                    help="Sets endurance and range directly: "
                                         "both scale with L/D.")

    shell.verdict_board(verdicts(flying, stall_target, ld_target))
    st.caption("The last two checks are not about the wing. They ask whether "
               "the parabolic polar and the published aerofoil data behind "
               "every number above still describe the air this wing flies in. "
               "A wing that fails either of them has not been sized - it has "
               "been sized with the wrong book.")

    shell.send_to_project(PREFIX, [
        ("All-up mass", mass, "kg"),
        ("Wingspan", span, "m"),
        ("Wing area", area, "m²"),
        ("Wing loading", craft.wing_loading, "N/m²"),
        ("Cruise speed", speed, "m/s"),
        ("Stall speed", flying.stall, "m/s"),
    ], note="from the wing study")

    ui.assumptions([
        "The drag polar is a <b>parabolic approximation</b>: C_D = C_D0 + "
        "C_L²/(πeAR). It is a curve fit, not a law. It breaks down near C_Lmax, "
        "where separation makes drag rise far faster than the square of C_L, "
        "and it misses the laminar bucket of a low-drag aerofoil at the other "
        "end - so both ends of the speed range are optimistic.",
        "C_D0 is taken as constant with speed and with lift. In reality it "
        "falls slowly as Reynolds number rises and climbs again with lift "
        "through interference and separation, so a single cruise value does "
        "not hold across the envelope.",
        "Oswald efficiency e lumps non-elliptic spanwise loading and every "
        "lift-dependent parasite effect into one number. Best L/D scales with "
        "the square root of it, so guessing e wrong by 15% moves the answer "
        "by about 7% - and e is almost always a guess.",
        "<b>C_Lmax is a property of the whole configuration, not of the "
        "aerofoil.</b> Fuselage interference, hinge gaps, surface finish, "
        "propeller wash, wing twist and Reynolds number all move it. A number "
        "taken from a 2-D section polar is typically 10-20% optimistic once "
        "the section becomes a wing on an aircraft.",
        "Cruise is steady, level, wings-level and 1 g, so lift equals weight "
        "exactly and C_L is forced. In a climb, a turn or a gust it is not, "
        "and both C_L and drag move with it.",
        "<b>Glide ratio is independent of weight</b> - it equals L/D, and "
        "ballast does not change the angle a wing glides at. <b>Best-glide "
        "speed is not:</b> it scales with the square root of wing loading, so "
        "a heavier aircraft flies the same angle faster and therefore sinks "
        "faster. That is why gliders carry water ballast for a fast day and "
        "dump it for a weak one.",
        "Sink rate is quoted at the best-L/D point, which is not minimum sink. "
        "Minimum sink happens at a higher C_L and a lower speed, and is the "
        "speed to fly to stay up rather than to go far.",
        "Reynolds number uses the mean geometric chord S/b, not the mean "
        "aerodynamic chord. For a tapered wing the MAC is larger, so the real "
        "figure is higher than shown at the root and lower at the tip - and "
        "the tip is where a stall starts.",
        f"Viscosity is the ISA sea-level value ({MU_AIR_SL:.3e} Pa·s). Air is "
        "colder and less viscous at altitude, so the true Reynolds number "
        "there is a few percent higher than shown. The Reynolds check "
        "therefore errs on the safe side.",
        f"The incompressible assumption holds to about Mach {MACH_LIMIT}. "
        "Above it density varies through the flow field, C_L and C_D both "
        "start changing with speed alone, and by Mach 0.7 wave drag appears "
        "that nothing on this page can see.",
        "Power required is D × V delivered to the air. It is not shaft power "
        "and it is certainly not battery power: divide by propeller and "
        "drivetrain efficiency for those.",
        "Rate of climb assumes thrust acts along the flight path and that the "
        "figure entered is available at this speed. Propeller thrust falls as "
        "speed rises, so a static thrust number overstates climb badly.",
        "Atmosphere is ISA plus a uniform temperature offset. Humidity, "
        "pressure systems and local terrain effects are ignored, and above "
        "20 km the model does not apply at all.",
        "No ground effect, no wing twist or washout, no compressibility "
        "correction, and no aeroelastic deflection. A high-aspect-ratio wing "
        "bends, and a bent wing is not the wing that was analysed.",
    ])


CALCULATORS = [
    Calculator(slug="studio.wing", name="Wing study", latex="",
               explanation="", render=render,
               keywords=("studio", "wing", "aerofoil", "airfoil", "aspect "
                         "ratio", "drag polar", "glide", "stall", "reynolds",
                         "mach", "uav", "sailplane", "workflow")),
]
