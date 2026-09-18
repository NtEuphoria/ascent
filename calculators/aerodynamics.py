"""Aerodynamics calculators.

Structure used by every calculator module in this project:
  1. Pure functions at the top - no Streamlit, fully unit-tested, self-validating.
  2. Calculator specs below - pure data describing each page.
  3. A CALCULATORS list at the bottom, which app.py turns into navigation.

The specs carry no layout code. utils/render.py decides how a calculator looks,
so a change to the visual system is one edit there rather than one per page.
"""
from __future__ import annotations

import numpy as np

from utils import validation as v
from utils.constants import (A_SL, G0, GAMMA_AIR, MU_AIR_SL, R_AIR, RHO_SL)
from utils.spec import (Calculator, Check, Field, Output, Reference,
                        Secondary, Sweep)

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def dynamic_pressure(rho: float, velocity: float) -> float:
    """q = 0.5 * ρ * V²   [Pa]"""
    rho = v.non_negative(rho, "Air density", "kg/m³")
    velocity = v.non_negative(velocity, "Velocity", "m/s")
    return 0.5 * rho * velocity ** 2


def lift(rho: float, velocity: float, area: float, cl: float) -> float:
    """L = 0.5 * ρ * V² * S * C_L   [N]

    C_L may be negative (inverted flight, downforce), so it is not restricted.
    """
    area = v.positive(area, "Wing area", "m²")
    cl = v.finite(cl, "Lift coefficient")
    return dynamic_pressure(rho, velocity) * area * cl


def drag(rho: float, velocity: float, area: float, cd: float) -> float:
    """D = 0.5 * ρ * V² * S * C_D   [N]"""
    area = v.positive(area, "Reference area", "m²")
    cd = v.non_negative(cd, "Drag coefficient")
    return dynamic_pressure(rho, velocity) * area * cd


def lift_to_drag(cl: float, cd: float) -> float:
    """L/D = C_L / C_D   [-]  (the 0.5*ρ*V²*S factor cancels exactly)"""
    cl = v.finite(cl, "Lift coefficient")
    cd = v.positive(cd, "Drag coefficient")
    return cl / cd


def wing_loading(weight: float, area: float) -> float:
    """W/S = weight / wing area   [N/m²]  (weight, not mass)"""
    weight = v.non_negative(weight, "Weight", "N")
    area = v.positive(area, "Wing area", "m²")
    return weight / area


def aspect_ratio(span: float, area: float) -> float:
    """AR = b² / S   [-]"""
    span = v.positive(span, "Wingspan", "m")
    area = v.positive(area, "Wing area", "m²")
    return span ** 2 / area


def reynolds_number(rho: float, velocity: float, length: float, mu: float) -> float:
    """Re = ρ * V * L / μ   [-]"""
    rho = v.non_negative(rho, "Air density", "kg/m³")
    velocity = v.non_negative(velocity, "Velocity", "m/s")
    length = v.positive(length, "Characteristic length", "m")
    mu = v.positive(mu, "Dynamic viscosity", "Pa·s")
    return rho * velocity * length / mu


def induced_drag_coefficient(cl: float, ar: float, e: float = 0.8) -> float:
    """C_Di = C_L² / (π e AR)   [-]

    The drag penalty of making lift with a finite span. Prandtl's lifting-line
    result: the wing leaves a pair of trailing vortices behind it, and the
    energy in that wake has to come from somewhere.
    """
    cl = v.finite(cl, "Lift coefficient")
    ar = v.positive(ar, "Aspect ratio")
    e = v.positive(e, "Span efficiency factor")
    return cl ** 2 / (np.pi * e * ar)


def drag_polar(cd0: float, cl: float, ar: float, e: float = 0.8) -> float:
    """C_D = C_D0 + C_L² / (π e AR)   [-]"""
    cd0 = v.non_negative(cd0, "Zero-lift drag coefficient")
    return cd0 + induced_drag_coefficient(cl, ar, e)


def cl_for_max_lift_to_drag(cd0: float, ar: float, e: float = 0.8) -> float:
    """C_L at the best L/D of a parabolic polar:  C_L* = sqrt(π e AR C_D0).

    Differentiating C_L/C_D gives C_D0 = C_L²/(π e AR): best L/D happens where
    induced drag exactly equals zero-lift drag, so the polar is half parasite
    and half induced there.
    """
    cd0 = v.non_negative(cd0, "Zero-lift drag coefficient")
    ar = v.positive(ar, "Aspect ratio")
    e = v.positive(e, "Span efficiency factor")
    return float(np.sqrt(np.pi * e * ar * cd0))


def max_lift_to_drag(cd0: float, ar: float, e: float = 0.8) -> float:
    """(L/D)max = 0.5 * sqrt(π e AR / C_D0)   [-]"""
    cd0 = v.positive(cd0, "Zero-lift drag coefficient")
    ar = v.positive(ar, "Aspect ratio")
    e = v.positive(e, "Span efficiency factor")
    return 0.5 * float(np.sqrt(np.pi * e * ar / cd0))


def speed_of_sound(temperature_k: float) -> float:
    """a = sqrt(γ R T)   [m/s]

    Depends on temperature alone, not on pressure or altitude directly: at
    11 km the air is thin *and* cold, and it is only the cold that slows sound.
    """
    temperature_k = v.positive(temperature_k, "Temperature", "K")
    return float(np.sqrt(GAMMA_AIR * R_AIR * temperature_k))


def mach_number(velocity: float, temperature_k: float) -> float:
    """M = V / a, with a = sqrt(γ R T)   [-]"""
    velocity = v.non_negative(velocity, "Velocity", "m/s")
    return velocity / speed_of_sound(temperature_k)


def skin_friction_laminar(re: float) -> float:
    """Blasius average skin-friction coefficient, C_f = 1.328 / sqrt(Re)  [-]

    Averaged over a smooth flat plate of length L wetted on one side, with the
    boundary layer laminar for the whole length.
    """
    re = v.positive(re, "Reynolds number")
    return 1.328 / float(np.sqrt(re))


def skin_friction_turbulent(re: float) -> float:
    """Prandtl's 1/7-power result, C_f = 0.074 / Re^0.2   [-]

    Average over a smooth flat plate turbulent from the leading edge. Fitted
    for roughly 5e5 < Re < 1e7; above that use the Schlichting correlation.
    """
    re = v.positive(re, "Reynolds number")
    return 0.074 / re ** 0.2


def boundary_layer_laminar(length: float, re: float) -> float:
    """Laminar boundary-layer thickness at x = L, δ = 5.0 L / sqrt(Re)   [m]"""
    length = v.positive(length, "Length", "m")
    re = v.positive(re, "Reynolds number")
    return 5.0 * length / float(np.sqrt(re))


def boundary_layer_turbulent(length: float, re: float) -> float:
    """Turbulent boundary-layer thickness at x = L, δ = 0.37 L / Re^0.2  [m]"""
    length = v.positive(length, "Length", "m")
    re = v.positive(re, "Reynolds number")
    return 0.37 * length / re ** 0.2


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

_LIFT = Calculator(
    slug="aero.lift",
    name="Lift",
    latex=r"L = \tfrac{1}{2}\,\rho\,V^{2}\,S\,C_L",
    explanation=(
        "Lift is the aerodynamic force perpendicular to the oncoming flow. "
        "Velocity is <b>squared</b>, so lift is far more sensitive to speed than "
        "to anything else on this page: fly 2x faster and you get 4x the lift at "
        "the same lift coefficient; 3x faster gives 9x."
    ),
    inputs=[
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0,
              help="1.225 kg/m³ is ISA sea level. It falls with altitude."),
        Field("v", "Velocity V", "m/s", 50.0, min=0.0,
              help="True airspeed relative to the air mass."),
        Field("s", "Wing area S", "m²", 16.2, min=0.0),
        Field("cl", "Lift coefficient C_L", "-", 0.5,
              help="Dimensionless. Depends on aerofoil, angle of attack and flap "
                   "setting. Negative values mean downforce."),
    ],
    compute=lambda i: lift(i.rho, i.v, i.s, i.cl),
    result=Output("Lift force L", "N"),
    secondary=[
        Secondary("Dynamic pressure q", "Pa",
                  lambda i, r: dynamic_pressure(i.rho, i.v)),
        Secondary("Mass this lift supports at 1 g", "kg", lambda i, r: r / G0),
        Secondary("Lift per unit wing area", "N/m²", lambda i, r: r / i.s),
    ],
    assumptions=[
        "Steady, incompressible flow - reliable below roughly Mach 0.3 "
        "(about 100 m/s at sea level). Above that, compressibility changes C_L.",
        "C_L is the value for this exact condition: aerofoil, angle of attack, "
        "flap setting and Reynolds number. It is not a fixed property of the wing.",
        "S is the reference area that C_L was defined against - normally the full "
        "projected planform area, including the part buried in the fuselage.",
        "No ground effect and no propeller slipstream over the wing.",
        "This is an exact definition, not an estimate: the equation defines C_L.",
    ],
    graphs=[
        Sweep(over="v", y_label="Lift L [N]", hi_factor=1.6, hi_min=10.0,
              title="Lift vs velocity"),
        Sweep(over="cl", y_label="Lift L [N]", lo=0.0, hi_factor=2.0,
              hi_min=1.5, title="Lift vs lift coefficient"),
        Sweep(over="s", y_label="Lift L [N]", hi_factor=2.0, hi_min=1.0,
              title="Lift vs wing area"),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            f"At {i.v:.0f} m/s you are near Mach "
                            f"{i.v / 340.3:.2f} at sea level. Above about Mach "
                            "0.3 air can no longer be treated as "
                            "incompressible, and C_L starts to change with "
                            "speed - this number becomes an underestimate.")
              if i.v > 102.0 else None),
        Check(lambda i, r: ("info",
                            "A negative C_L means the wing is pushing down "
                            "rather than up - inverted flight, or a race-car "
                            "wing.") if i.cl < 0 else None),
    ],
    references=[
        Reference(
            title="Typical lift coefficients",
            columns=("Condition", "C_L"),
            rows=[
                ("Transport aircraft in cruise", "0.4 - 0.6"),
                ("Light aircraft in cruise", "0.3 - 0.5"),
                ("Sailplane in cruise", "0.4 - 0.8"),
                ("Maximum, plain aerofoil, no flaps", "1.2 - 1.5"),
                ("Maximum, with slotted flaps", "2.0 - 2.8"),
                ("Maximum, with slats and flaps", "2.5 - 3.2"),
                ("Flat plate, thin-aerofoil theory", "2*pi*alpha (alpha in rad)"),
            ],
            note="Ranges for whole aircraft at sensible angles of attack. A "
                 "specific aerofoil section can exceed these; a wing with a "
                 "fuselage through it usually does not.",
        ),
    ],
    related=["aero.drag", "aero.lift_to_drag", "aero.wing_loading",
             "flight.stall_speed"],
    variables=[
        ("$L$", "Lift force", "N"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$V$", "True airspeed", "m/s"),
        ("$S$", "Reference wing area", "m²"),
        ("$C_L$", "Lift coefficient (dimensionless)", "-"),
    ],
    example=(
        "Wing sizing for a small UAV. At sea level, 18 m/s, S = 0.65 m² and "
        "C_L = 0.8, the wing makes about 103 N of lift - enough to hold a 10.5 kg "
        "aircraft in level flight. Halve the speed to 9 m/s and lift collapses to "
        "about 26 N, which is why slow flight needs flaps (higher C_L) or more "
        "wing area."
    ),
    keywords=("lift", "wing", "cl", "aerofoil", "airfoil"),
)

def _drag_power(i, xs):
    """P = D V = 0.5 ρ V³ S C_D, swept over velocity."""
    xs = np.asarray(xs, dtype=float)
    return 0.5 * i.rho * xs ** 3 * i.s * i.cd


_DRAG = Calculator(
    slug="aero.drag",
    name="Drag",
    latex=r"D = \tfrac{1}{2}\,\rho\,V^{2}\,S\,C_D",
    explanation=(
        "Drag is the force component along the flow direction. It has the same "
        "form as lift, so it also grows with the square of speed - and the power "
        "needed to overcome it, P = D × V, grows with the <b>cube</b> of speed. "
        "That cube is the central fact of vehicle design: it is why doubling top "
        "speed costs eight times the engine, and why an efficient cruise is always "
        "a slow one."
    ),
    inputs=[
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0),
        Field("v", "Velocity V", "m/s", 50.0, min=0.0),
        Field("s", "Reference area S", "m²", 16.2, min=0.0,
              help="Must be the same reference area used to define C_D."),
        Field("cd", "Drag coefficient C_D", "-", 0.032, min=0.0),
    ],
    compute=lambda i: drag(i.rho, i.v, i.s, i.cd),
    result=Output("Drag force D", "N"),
    secondary=[
        Secondary("Dynamic pressure q", "Pa",
                  lambda i, r: dynamic_pressure(i.rho, i.v)),
        Secondary("Power to overcome drag (P = D × V)", "W", lambda i, r: r * i.v),
        Secondary("The same power in horsepower", "hp",
                  lambda i, r: r * i.v / 745.6999),
        Secondary("Drag per unit reference area (D/S)", "N/m²",
                  lambda i, r: r / i.s),
        Secondary("Drag area C_D × S", "m²", lambda i, r: i.cd * i.s),
        Secondary("Equivalent thrust needed", "N", lambda i, r: r),
    ],
    assumptions=[
        "C_D is the total drag coefficient at this condition (parasite + induced), "
        "referenced to the same area S as the value you entered. Mixing a "
        "frontal-area C_D with a wing area is the single most common error here "
        "and can be wrong by a factor of ten.",
        "C_D is not constant: it rises with lift (induced drag) and changes with "
        "Reynolds and Mach number. A cruise value does not hold in a climb.",
        "Steady, incompressible flow below roughly Mach 0.3. Above about Mach 0.7 "
        "wave drag appears and C_D can double before the aircraft reaches Mach 1; "
        "this equation has no way to know that.",
        "P = D × V is the propulsive power delivered to the air, before propeller "
        "and motor efficiency losses. Divide by propeller efficiency (0.6-0.85) "
        "and drivetrain efficiency to get shaft or electrical power.",
        "The flow is attached. Once a wing stalls or a bluff body sheds a large "
        "wake, C_D jumps and no longer varies smoothly with angle of attack.",
        "No ground effect, no interference drag from nearby bodies, and the "
        "vehicle is in undisturbed air rather than another vehicle's wake.",
    ],
    graphs=[
        Sweep(over="v", y_label="Drag D [N]", hi_factor=1.6, hi_min=10.0,
              title="Drag vs velocity"),
        Sweep(over="v", y_label="Power required P [W]", hi_factor=1.6,
              hi_min=10.0, title="Power required vs velocity",
              fn=_drag_power),
        Sweep(over="cd", y_label="Drag D [N]", lo=0.0, hi_factor=2.0,
              hi_min=0.1, title="Drag vs drag coefficient"),
        Sweep(over="s", y_label="Drag D [N]", hi_factor=2.0, hi_min=1.0,
              title="Drag vs reference area"),
    ],
    checks=[
        Check(lambda i, r: ("danger",
                            f"Mach {i.v / A_SL:.2f} at sea level: this is the "
                            "transonic range. Shock waves form on the upper "
                            "surface, wave drag appears and C_D can rise by a "
                            "factor of two or more between Mach 0.7 and Mach 1. "
                            "A fixed C_D cannot represent that.")
              if i.v > 0.7 * A_SL else
              ("warning",
               f"At {i.v:.0f} m/s you are near Mach {i.v / A_SL:.2f} at sea "
               "level. Above about Mach 0.3 air stops behaving as "
               "incompressible and C_D begins to climb with speed, so this "
               "number is an underestimate.")
              if i.v > 0.3 * A_SL else None),
        Check(lambda i, r: ("info",
                            f"C_D = {i.cd:g} is higher than a flat plate held "
                            "square to the flow (about 1.2). That is possible "
                            "for a parachute or a cupped shape, but check that "
                            "C_D and S are referenced to the same area.")
              if i.cd > 1.3 else None),
        Check(lambda i, r: ("info",
                            f"C_D = {i.cd:g} is lower than a clean sailplane "
                            "(about 0.010 on wing area). Worth confirming the "
                            "reference area before trusting it.")
              if 0.0 < i.cd < 0.008 else None),
    ],
    references=[
        Reference(
            title="Drag coefficients of bodies",
            columns=("Shape", "C_D", "Reference area"),
            rows=[
                ("Streamlined strut or teardrop", "0.04 - 0.09", "frontal"),
                ("Smooth sphere, Re 10⁴ - 2×10⁵", "0.47", "frontal"),
                ("Smooth sphere, above the drag crisis", "0.1 - 0.2", "frontal"),
                ("Long circular cylinder, cross-flow", "1.0 - 1.2", "frontal"),
                ("Flat plate square to the flow", "1.17 - 1.28", "frontal"),
                ("Modern car", "0.25 - 0.35", "frontal"),
                ("Cyclist, upright", "0.9 - 1.1", "frontal ≈ 0.4-0.5 m²"),
                ("Parachute canopy", "1.3 - 1.5", "canopy"),
            ],
            note="Frontal area means the silhouette seen from straight ahead. "
                 "The sphere entry shows why the reference matters: the same "
                 "ball changes C_D by a factor of three across the drag crisis "
                 "near Re = 3×10⁵, which is exactly what dimples on a golf ball "
                 "exploit.",
        ),
        Reference(
            title="Zero-lift drag coefficients of aircraft",
            columns=("Aircraft", "C_D0 (wing area)"),
            rows=[
                ("Sailplane, clean", "0.008 - 0.015"),
                ("Jet transport, cruise", "0.015 - 0.020"),
                ("Light aircraft, retractable gear", "0.020 - 0.025"),
                ("Light aircraft, fixed gear", "0.025 - 0.035"),
                ("Small fixed-wing UAV", "0.030 - 0.050"),
                ("Agricultural aircraft with spray gear", "0.055 - 0.065"),
            ],
            note="These are zero-lift (parasite) values referenced to wing "
                 "area, so they exclude induced drag. In real cruise the total "
                 "C_D is higher - add C_L²/(π e AR) from the drag polar page.",
        ),
    ],
    related=["aero.dynamic_pressure", "aero.lift_to_drag", "flight.glide"],
    variables=[
        ("$D$", "Drag force", "N"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$V$", "True airspeed", "m/s"),
        ("$S$", "Reference area", "m²"),
        ("$C_D$", "Drag coefficient (dimensionless)", "-"),
    ],
    example=(
        "Sizing a UAV propulsion system. A 0.65 m² wing with C_D = 0.045 at "
        "25 m/s and sea-level density makes 11.2 N of drag, so the propeller must "
        "put 280 W into the air just to hold speed. Double the speed to 50 m/s "
        "and drag becomes 44.8 N and the power 2,239 W - four times the thrust "
        "and eight times the power for twice the speed."
    ),
    keywords=("drag", "cd", "parasite", "resistance", "power required",
              "cube law", "form drag", "thrust required"),
)

_DYNAMIC_PRESSURE = Calculator(
    slug="aero.dynamic_pressure",
    name="Dynamic pressure",
    latex=r"q = \tfrac{1}{2}\,\rho\,V^{2}",
    explanation=(
        "Dynamic pressure is the kinetic energy per unit volume of the moving air. "
        "It is the common factor in every aerodynamic force, and it is what an "
        "airspeed indicator (a pitot-static system) actually measures. An aircraft "
        "does not really care about speed or altitude separately - it cares about "
        "<b>q</b>, which is why the same indicated airspeed gives the same handling "
        "at sea level and at 10 km."
    ),
    inputs=[
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0,
              help="1.225 kg/m³ at ISA sea level; about 0.736 at 5 km and "
                   "0.414 at 10 km."),
        Field("v", "Velocity V", "m/s", 50.0, min=0.0,
              help="True airspeed - the speed relative to the air mass."),
    ],
    compute=lambda i: dynamic_pressure(i.rho, i.v),
    result=Output("Dynamic pressure q", "Pa"),
    secondary=[
        Secondary("In kilopascals", "kPa", lambda i, r: r / 1000.0),
        Secondary("As a fraction of sea-level static pressure", "-",
                  lambda i, r: r / 101325.0),
        Secondary("In pound-force per square foot", "lbf/ft²",
                  lambda i, r: r * 0.0208854),
        Secondary("Equivalent airspeed (what a sea-level ASI would read)", "m/s",
                  lambda i, r: float(np.sqrt(2.0 * r / RHO_SL))),
        Secondary("Force on a 1 m² flat plate with C_D = 1.2", "N",
                  lambda i, r: r * 1.2),
        Secondary("Mach number at ISA sea level", "-", lambda i, r: i.v / A_SL),
    ],
    assumptions=[
        "Incompressible flow. Above about Mach 0.3 the true impact pressure "
        "measured by a pitot tube exceeds 0.5 ρ V² by roughly M²/4 - about 2% at "
        "Mach 0.3, 6% at Mach 0.5 and 17% at Mach 0.8.",
        "ρ is the density where the vehicle actually is, not sea-level density. "
        "Using 1.225 at altitude overstates every aerodynamic force.",
        "V is true airspeed. Indicated airspeed is derived from q assuming "
        "sea-level density, which is why IAS reads low at altitude - and why "
        "stall happens at the same IAS all the way up.",
        "The air is undisturbed. Inside a propeller slipstream or another "
        "vehicle's wake the local q is different from the free-stream value.",
        "Dynamic pressure is not a pressure you would measure with a static "
        "port. It is the difference between total and static pressure, which is "
        "why a pitot-static system needs both.",
        "The equivalent-airspeed figure assumes the ISA sea-level density of "
        "1.225 kg/m³ and ignores instrument and position error.",
    ],
    graphs=[
        Sweep(over="v", y_label="Dynamic pressure q [Pa]", hi_factor=1.6,
              hi_min=10.0, title="Dynamic pressure vs velocity"),
        Sweep(over="rho", y_label="Dynamic pressure q [Pa]", lo=0.0,
              hi_factor=1.2, hi_min=1.3,
              title="Dynamic pressure vs air density"),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            f"Mach {i.v / A_SL:.2f} at sea-level temperature. "
                            "A pitot tube here reads an impact pressure about "
                            f"{100.0 * ((i.v / A_SL) ** 2 / 4 + (i.v / A_SL) ** 4 / 40):.0f}% "
                            "above 0.5 ρ V². Use the compressible form of the "
                            "pitot equation rather than this one.")
              if i.v > 0.3 * A_SL else None),
        Check(lambda i, r: ("info",
                            f"At ρ = {i.rho:g} kg/m³ a sea-level-calibrated "
                            "airspeed indicator would read about "
                            f"{i.v * float(np.sqrt(i.rho / RHO_SL)):.1f} m/s "
                            f"while you are truly doing {i.v:.1f} m/s. Equivalent "
                            "airspeed is what the structure and the wing feel; "
                            "true airspeed is what the map cares about.")
              if i.rho > 0 and abs(i.rho - RHO_SL) / RHO_SL > 0.02 else None),
    ],
    references=[
        Reference(
            title="Dynamic pressure at ISA sea level",
            columns=("Speed [m/s]", "Speed [km/h]", "q [Pa]"),
            rows=[
                ("5 (light breeze)", "18", "15.3"),
                ("10", "36", "61.3"),
                ("20 (fresh gale)", "72", "245"),
                ("25", "90", "383"),
                ("33 (hurricane force)", "119", "667"),
                ("50", "180", "1,531"),
                ("100", "360", "6,125"),
                ("150", "540", "13,781"),
            ],
            note="Computed at ρ = 1.225 kg/m³. At altitude the same true "
                 "airspeed gives less q: at 10 km (ρ = 0.414) every value here "
                 "falls to about a third.",
        ),
    ],
    related=["aero.lift", "aero.drag", "aero.reynolds",
             "constants___reference.standard_atmosphere_(isa)"],
    variables=[
        ("$q$", "Dynamic pressure", "Pa"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$V$", "True airspeed", "m/s"),
    ],
    example=(
        "Structural load cases. A quadcopter arm flying into a 20 m/s gust sees "
        "q = 245 Pa; multiplied by the frontal area and a drag coefficient, that "
        "gives the side load the arm must survive. The same arm at 50 m/s sees "
        "1,531 Pa - six times the load for two-and-a-half times the speed."
    ),
    keywords=("q", "dynamic", "pressure", "pitot", "eas", "ias",
              "equivalent airspeed", "impact pressure", "airspeed indicator"),
)

_LIFT_TO_DRAG = Calculator(
    slug="aero.lift_to_drag",
    name="Lift-to-drag ratio",
    latex=r"\frac{L}{D} = \frac{C_L}{C_D}",
    explanation=(
        "The single best measure of aerodynamic efficiency. Because lift and drag "
        "share the identical 0.5 ρ V² S factor, that factor cancels exactly and "
        "the force ratio equals the coefficient ratio. L/D is three numbers at "
        "once: the still-air glide ratio, the reciprocal of the thrust fraction "
        "needed in cruise, and the term that sets range in the Breguet equation."
    ),
    inputs=[
        Field("cl", "Lift coefficient C_L", "-", 0.5,
              help="At the same flight condition as C_D. Negative means "
                   "downforce, and L/D comes out negative with it."),
        Field("cd", "Drag coefficient C_D", "-", 0.032, min=0.0,
              help="Total drag coefficient, parasite plus induced, on the same "
                   "reference area as C_L."),
    ],
    compute=lambda i: lift_to_drag(i.cl, i.cd),
    result=Output("Lift-to-drag ratio L/D", "-"),
    secondary=[
        Secondary("Glide ratio (distance per unit height lost)", "m per m",
                  lambda i, r: r),
        Secondary("Glide angle below horizontal", "°",
                  lambda i, r: float(np.degrees(np.arctan(1.0 / r)))),
        Secondary("Still-air glide distance from 1,000 m", "m",
                  lambda i, r: 1000.0 * r),
        Secondary("Drag as a fraction of weight in level flight", "-",
                  lambda i, r: 1.0 / r),
        Secondary("Thrust needed per tonne of weight in cruise", "N",
                  lambda i, r: 1000.0 * G0 / r),
    ],
    assumptions=[
        "Both coefficients are evaluated at the same flight condition - same angle "
        "of attack, same reference area, same Reynolds and Mach number. Taking "
        "C_L from one source and C_D from another is the usual way this goes "
        "wrong.",
        "The glide-ratio reading assumes an unpowered, steady glide with a shallow "
        "angle, where lift is approximately equal to weight. Below about L/D = 5 "
        "the small-angle approximation starts to matter and the true glide ratio "
        "is slightly worse than L/D.",
        "Glide ratio through the air, not over the ground. A headwind or sink "
        "reduces the distance actually covered, sometimes drastically.",
        "L/D is independent of weight, but the speed at which you achieve it is "
        "not: a heavier aircraft reaches the same best L/D at a higher airspeed "
        "and therefore a higher sink rate.",
        "This page takes C_L and C_D as given. Where they come from a parabolic "
        "polar, best L/D occurs at one specific C_L - see the drag polar page.",
        "Nothing here knows about compressibility. Above the drag-divergence "
        "Mach number C_D climbs steeply and L/D falls away with it.",
    ],
    graphs=[
        Sweep(over="cl", y_label="L/D [-]", lo=0.0, hi_factor=3.0, hi_min=1.5,
              title="L/D vs lift coefficient"),
        Sweep(over="cd", y_label="L/D [-]", lo_factor=0.3, hi_factor=3.0,
              hi_min=0.05, title="L/D vs drag coefficient"),
    ],
    checks=[
        Check(lambda i, r: ("warning",
                            f"L/D = {r:.0f} is beyond every aircraft ever "
                            "flown - the best open-class sailplanes reach about "
                            "70. Check that C_L and C_D use the same reference "
                            "area and the same flight condition.")
              if r > 70 else None),
        Check(lambda i, r: ("info",
                            "A negative L/D means C_L is negative: the surface "
                            "is making downforce. For a race-car wing the useful "
                            "figure is the magnitude, downforce per unit drag.")
              if r < 0 else None),
        Check(lambda i, r: ("info",
                            f"L/D = {r:.1f} is bluff-body territory rather than "
                            "wing territory - a multirotor in forward flight, a "
                            "lifting body, or a wing well past the stall. Nearly "
                            "a quarter of the weight has to be carried by thrust "
                            "in level flight.")
              if 0 < r < 4 else None),
    ],
    references=[
        Reference(
            title="Typical maximum lift-to-drag ratios",
            columns=("Aircraft", "Best L/D"),
            rows=[
                ("Open-class sailplane (25-30 m span)", "50 - 70"),
                ("15 m class sailplane", "40 - 45"),
                ("Modern airliner in cruise", "17 - 20"),
                ("Earlier jet transport", "15 - 17"),
                ("Wandering albatross", "about 20"),
                ("Hang glider", "10 - 16"),
                ("Light single, fixed gear", "8 - 12"),
                ("Small fixed-wing UAV", "8 - 15"),
                ("Helicopter, whole aircraft", "4 - 5"),
                ("Space Shuttle orbiter, subsonic", "about 4.5"),
                ("Multirotor in forward flight", "2 - 5"),
            ],
            note="Best L/D, reached at one particular airspeed and angle of "
                 "attack. Cruise is usually flown a little faster than that, at "
                 "90-95% of the best value, because arriving matters too.",
        ),
        Reference(
            title="Glide angle for a given L/D",
            columns=("L/D", "Glide angle", "Distance from 1,000 m"),
            rows=[
                ("2", "26.6°", "2.0 km"),
                ("4", "14.0°", "4.0 km"),
                ("5", "11.3°", "5.0 km"),
                ("10", "5.7°", "10 km"),
                ("15", "3.8°", "15 km"),
                ("20", "2.9°", "20 km"),
                ("30", "1.9°", "30 km"),
                ("50", "1.1°", "50 km"),
            ],
            note="Angle is arctan(1/(L/D)) below the horizon, in still air. "
                 "Distance assumes the glide starts and ends in the same air "
                 "mass, with no wind and no lift or sink.",
        ),
    ],
    related=["flight.glide", "aero.aspect_ratio", "aero.drag",
             "flight.stall_speed"],
    variables=[
        ("$C_L$", "Lift coefficient", "-"),
        ("$C_D$", "Drag coefficient", "-"),
        ("$L/D$", "Lift-to-drag ratio", "-"),
    ],
    example=(
        "Range planning. With C_L = 0.5 and C_D = 0.032 the ratio is 15.6, so "
        "from 1,000 m the aircraft glides about 15.6 km in still air, descending "
        "at 3.7° below the horizon. The same number sets cruise thrust: "
        "T = W/(L/D), which is 628 N per tonne of aircraft - roughly 6% of its "
        "own weight."
    ),
    keywords=("ld", "l/d", "efficiency", "glide", "ratio", "glide angle",
              "finesse", "aerodynamic efficiency", "range"),
)

def _stall_speed_vs_area(i, xs):
    """V_stall = sqrt(2 (W/S) / (ρ C_Lmax)) at ρ = 1.225, C_Lmax = 1.4."""
    xs = np.asarray(xs, dtype=float)
    safe = np.where(xs > 0.0, xs, np.nan)
    return np.sqrt(2.0 * i.weight / safe / (RHO_SL * 1.4))


def _wing_loading_class(i, r):
    """Name the class of aircraft this wing loading belongs to."""
    if r < 15:
        return ("warning",
                f"{r:,.0f} N/m² is below a human-powered aircraft "
                "(about 10-20 N/m²). Check the units on the wing area - an "
                "answer this low usually means square centimetres were entered "
                "as square metres.")
    if r < 60:
        return ("info",
                f"{r:,.0f} N/m² ({r / G0:.1f} kg/m²) is paraglider, hang-glider "
                "and park-flyer territory. Very slow flight and short take-offs, "
                "but the aircraft is thrown around badly by gusts and cannot "
                "penetrate wind.")
    if r < 300:
        return ("info",
                f"{r:,.0f} N/m² ({r / G0:.1f} kg/m²) is small-UAV, microlight "
                "and ultralight territory - slow, docile, and still noticeably "
                "gust-sensitive.")
    if r < 1200:
        return ("info",
                f"{r:,.0f} N/m² ({r / G0:.1f} kg/m²) is the light-aircraft and "
                "sailplane band. A Cessna 172 at maximum weight is about "
                "670 N/m².")
    if r < 4000:
        return ("info",
                f"{r:,.0f} N/m² ({r / G0:.1f} kg/m²) is business-jet territory: "
                "a smooth ride and a fast cruise, paid for with high-lift devices "
                "to keep the approach speed manageable.")
    return ("info",
            f"{r:,.0f} N/m² ({r / G0:.1f} kg/m²) is jet-transport and fighter "
            "territory. Aircraft in this band need slats and large flaps simply "
            "to land, and their approach speeds are set by C_Lmax, not by the "
            "clean wing.")


_WING_LOADING = Calculator(
    slug="aero.wing_loading",
    name="Wing loading",
    latex=r"\frac{W}{S} = \frac{\text{weight}}{\text{wing area}}",
    explanation=(
        "How much weight each square metre of wing must carry. It sets stall speed, "
        "turn performance and how roughly the aircraft rides through gusts. "
        "This uses <b>weight in newtons</b>, not mass in kilograms. Stall speed "
        "goes as the square root of wing loading, so quadrupling W/S only doubles "
        "the speed at which the aircraft falls out of the sky - which is why heavy "
        "aircraft are viable at all."
    ),
    inputs=[
        Field("weight", "Aircraft", "", 1200.0, kind="weight"),
        Field("s", "Wing area S", "m²", 16.2, min=0.0,
              help="Full reference planform area, including the part buried in "
                   "the fuselage - the same S used for C_L and C_D."),
    ],
    compute=lambda i: wing_loading(i.weight, i.s),
    result=Output("Wing loading W/S", "N/m²"),
    secondary=[
        Secondary("Equivalent mass per area (m/S)", "kg/m²", lambda i, r: r / G0),
        Secondary("In pound-force per square foot", "lbf/ft²",
                  lambda i, r: r * 0.0208854),
        Secondary("In grams-force per square decimetre", "g/dm²",
                  lambda i, r: r / G0 * 10.0),
        Secondary("Stall speed at ρ = 1.225, C_Lmax = 1.4", "m/s",
                  lambda i, r: float(np.sqrt(2.0 * r / (RHO_SL * 1.4)))),
        Secondary("The same stall speed in km/h", "km/h",
                  lambda i, r: float(np.sqrt(2.0 * r / (RHO_SL * 1.4))) * 3.6),
        Secondary("Speed to fly at C_L = 0.4, ρ = 1.225", "m/s",
                  lambda i, r: float(np.sqrt(2.0 * r / (RHO_SL * 0.4)))),
    ],
    assumptions=[
        "Wing loading is quoted at a stated weight - usually maximum take-off "
        "weight. The same aircraft has a lower wing loading when nearly empty, "
        "which is why landing speeds are lower than take-off speeds.",
        "S is the same reference area used for the lift and drag coefficients. "
        "Using exposed panel area instead of full planform area inflates W/S by "
        "10-20% on a typical airliner.",
        "The stall-speed figure is an illustration using assumed sea-level density "
        "and C_Lmax = 1.4; it is an estimate, not a value for your aircraft. Flaps "
        "raise C_Lmax and lower the speed; ice or a dirty wing does the opposite.",
        "Both speed figures are for straight, level, unaccelerated flight. In a "
        "60° banked turn the wing carries 2 g and the stall speed rises by 41%.",
        "'Equivalent mass per area' is shown because many hobby sources quote "
        "g/dm² or kg/m²; that is a mass per area, not a force per area. The two "
        "differ by exactly g = 9.80665 and are constantly confused.",
        "Gust response goes the other way from stall speed: a high wing loading "
        "rides gusts smoothly, which is a comfort and fatigue benefit, not an "
        "aerodynamic one.",
    ],
    graphs=[
        Sweep(over="s", y_label="Wing loading W/S [N/m²]", lo_factor=0.3,
              hi_factor=2.0, hi_min=2.0, title="Wing loading vs wing area"),
        Sweep(over="weight", y_label="Wing loading W/S [N/m²]", lo=0.0,
              hi_factor=1.6, hi_min=100.0, title="Wing loading vs weight",
              x_label="Aircraft weight W [N]"),
        Sweep(over="s", y_label="Stall speed [m/s]", lo_factor=0.3,
              hi_factor=2.0, hi_min=2.0,
              title="Stall speed vs wing area", fn=_stall_speed_vs_area),
    ],
    checks=[
        Check(_wing_loading_class),
        Check(lambda i, r: ("warning",
                            f"{r:,.0f} N/m² is higher than any production "
                            "aircraft at maximum take-off weight - a 747-400 is "
                            "about 7,200 N/m². Check that the wing area is the "
                            "full reference area and that the weight is in "
                            "newtons rather than kilograms.")
              if r > 8500 else None),
    ],
    references=[
        Reference(
            title="Wing loading across aircraft classes",
            columns=("Aircraft or class", "W/S [N/m²]", "m/S [kg/m²]"),
            rows=[
                ("Human-powered aircraft", "10 - 20", "1 - 2"),
                ("RC model / park flyer", "20 - 60", "2 - 6"),
                ("Paraglider", "35 - 45", "3.5 - 4.5"),
                ("Hang glider", "40 - 80", "4 - 8"),
                ("Small fixed-wing survey UAV", "50 - 120", "5 - 12"),
                ("Microlight / ultralight", "150 - 250", "15 - 25"),
                ("15 m class sailplane, dry", "350 - 500", "35 - 50"),
                ("Cessna 172 at MTOW", "630 - 700", "64 - 72"),
                ("Cirrus SR22 at MTOW", "about 1,200", "about 121"),
                ("Business jet at MTOW", "2,200 - 3,900", "225 - 400"),
                ("Airbus A320 / Boeing 737 at MTOW", "6,200 - 6,300", "634 - 640"),
                ("F-16 at MTOW", "about 6,800", "about 690"),
                ("Boeing 747-400 at MTOW", "about 7,200", "about 733"),
            ],
            note="Quoted at maximum take-off weight unless stated. The same "
                 "aircraft on approach, with fuel burned off, is typically "
                 "20-30% lower. Sailplanes carrying water ballast move up their "
                 "range deliberately, to cruise faster between thermals.",
        ),
        Reference(
            title="Stall speed for a given wing loading",
            columns=("W/S [N/m²]", "Stall speed [m/s]", "Stall speed [km/h]"),
            rows=[
                ("40", "6.8", "25"),
                ("80", "9.7", "35"),
                ("200", "15.3", "55"),
                ("500", "24.1", "87"),
                ("1,000", "34.1", "123"),
                ("2,500", "54.0", "194"),
                ("5,000", "76.4", "275"),
                ("7,200", "91.6", "330"),
            ],
            note="Computed at ISA sea level with C_Lmax = 1.4, which is a clean "
                 "wing with no flaps. A transport with slats and double-slotted "
                 "flaps reaches C_Lmax near 3.0, which cuts these speeds by "
                 "about a third - that is what all that machinery on the trailing "
                 "edge buys.",
        ),
    ],
    related=["flight.stall_speed", "aero.lift", "aero.aspect_ratio",
             "flight.glide"],
    variables=[
        ("$W$", "Weight (force), W = m g", "N"),
        ("$S$", "Wing reference area", "m²"),
        ("$W/S$", "Wing loading", "N/m²"),
    ],
    example=(
        "Choosing a wing for a fixed-wing drone. A 1,200 kg light aircraft on "
        "16.2 m² of wing loads it at 726 N/m², or 74.1 kg/m², and stalls near "
        "29 m/s (105 km/h) with a clean wing. Low wing loading (under about "
        "100 N/m²) means slow, gentle flight and short take-offs but poor gust "
        "tolerance. High wing loading means a faster, smoother ride but a higher "
        "stall and landing speed."
    ),
    keywords=("wing loading", "ws", "w/s", "kg/m2", "g/dm2", "span loading",
              "gust response", "stall"),
)

def _induced_factor_vs_span(i, xs):
    """1/(π e AR) with AR = b²/S, swept over span at fixed area, e = 0.8."""
    xs = np.asarray(xs, dtype=float)
    safe = np.where(xs > 0.0, xs, np.nan)
    return i.s / (np.pi * 0.8 * safe ** 2)


def _aspect_ratio_class(i, r):
    """Name the design family this slenderness belongs to."""
    if r < 1.0:
        return ("warning",
                f"AR = {r:.2f} means the wing is wider fore-and-aft than it is "
                "from tip to tip. Check that b is the full tip-to-tip span and "
                "that S is in square metres.")
    if r < 5.0:
        return ("info",
                f"AR = {r:.2f} is low - delta wings, fighters and lifting bodies. "
                "Induced drag is heavy, but the wing is light, stiff, rolls fast "
                "and stays attached to very high angles of attack.")
    if r < 9.0:
        return ("info",
                f"AR = {r:.2f} is the general-aviation and early-jet band. A "
                "Cessna 172 is about 7.4 and a Boeing 747-400 about 7.7.")
    if r < 15.0:
        return ("info",
                f"AR = {r:.2f} is high: modern airliners (A320 about 9.5, 787 "
                "about 9.6) and long-endurance UAVs. Here the wing structure, "
                "not the aerodynamics, is usually what stops you going further.")
    if r <= 40.0:
        return ("info",
                f"AR = {r:.2f} is sailplane and HALE territory (15 m class "
                "sailplanes are about 25, Global Hawk about 32). Bending loads, "
                "flutter and gust response set the limit, not drag.")
    return ("warning",
            f"AR = {r:.0f} exceeds any piloted aircraft. Even a 30 m open-class "
            "sailplane only reaches the high thirties. Worth re-checking b and S.")


_ASPECT_RATIO = Calculator(
    slug="aero.aspect_ratio",
    name="Aspect ratio",
    latex=r"AR = \frac{b^{2}}{S}",
    explanation=(
        "How slender the wing is. High aspect ratio means long, thin wings, which "
        "cut induced drag (the drag penalty of making lift) and raise L/D - the "
        "reason sailplanes and high-altitude UAVs have such long wings. The "
        "mechanism is the tip vortex: a long wing pushes a large mass of air down "
        "gently, a short one pushes a small mass down hard, and the wasted "
        "kinetic energy in the wake goes as the square of that downwash."
    ),
    inputs=[
        Field("b", "Wingspan b", "m", 10.9, min=0.0,
              help="Full tip-to-tip span, not the semi-span."),
        Field("s", "Wing area S", "m²", 16.2, min=0.0,
              help="Reference planform area, including the part inside the "
                   "fuselage."),
    ],
    compute=lambda i: aspect_ratio(i.b, i.s),
    result=Output("Aspect ratio AR", "-"),
    secondary=[
        Secondary("Mean geometric chord (S/b)", "m", lambda i, r: i.s / i.b),
        Secondary("Oswald-corrected induced drag factor 1/(π e AR), e = 0.8", "-",
                  lambda i, r: 1.0 / (np.pi * 0.8 * r)),
        Secondary("Ideal elliptical factor 1/(π AR), e = 1", "-",
                  lambda i, r: 1.0 / (np.pi * r)),
        Secondary("Induced drag coefficient at C_L = 0.5, e = 0.8", "-",
                  lambda i, r: induced_drag_coefficient(0.5, r, 0.8)),
        Secondary("Finite-wing lift-curve slope (a₀ = 2π, e = 0.8)", "per °",
                  lambda i, r: float(np.radians(
                      2.0 * np.pi / (1.0 + 2.0 / (0.8 * r))))),
    ],
    assumptions=[
        "b²/S is the general definition and works for any planform. For a "
        "rectangular wing it simplifies to span divided by chord.",
        "b is the full tip-to-tip span, not the semi-span. Halving this by "
        "mistake divides the aspect ratio by four.",
        "'Mean geometric chord' S/b is not the same as the mean aerodynamic chord "
        "(MAC) used for stability work, except on an untapered wing. Using S/b to "
        "place a centre of gravity on a tapered wing will put it in the wrong "
        "place.",
        "The induced-drag factor uses an assumed Oswald efficiency e = 0.8 and is "
        "an estimate for orientation only. A clean sailplane reaches 0.90-0.95; a "
        "delta may be nearer 0.6.",
        "Lifting-line theory sits behind all of this, and it assumes a "
        "straight, unswept, moderate-to-high aspect ratio wing. Below about "
        "AR = 4, and on strongly swept wings, its predictions drift.",
        "The lift-curve slope shown assumes a two-dimensional section slope of "
        "2π per radian. Real aerofoils come in 5-10% below that, and "
        "compressibility raises it again by the Prandtl-Glauert factor.",
        "Aspect ratio says nothing about structure, and structure is what "
        "actually limits it: root bending moment grows with span at a given "
        "lift, so the wing gets heavier as fast as the drag falls.",
    ],
    graphs=[
        Sweep(over="b", y_label="Aspect ratio AR [-]", lo=0.0, hi_factor=2.0,
              hi_min=2.0, title="Aspect ratio vs wingspan"),
        Sweep(over="s", y_label="Aspect ratio AR [-]", lo_factor=0.3,
              hi_factor=2.0, hi_min=2.0, title="Aspect ratio vs wing area"),
        Sweep(over="b", y_label="Induced drag factor 1/(π e AR) [-]", lo_factor=0.4,
              hi_factor=2.0, hi_min=2.0,
              title="Induced drag factor vs wingspan",
              fn=_induced_factor_vs_span),
    ],
    checks=[
        Check(_aspect_ratio_class),
        Check(lambda i, r: ("info",
                            f"A span of {i.b:g} m on {i.s:g} m² gives a mean "
                            f"chord of {i.s / i.b:.2f} m. At typical flight "
                            "speeds that chord sets the Reynolds number, which "
                            "is what decides whether published aerofoil data "
                            "applies.")
              if i.b > 0 and i.s / i.b < 0.3 else None),
    ],
    references=[
        Reference(
            title="Aspect ratio of real aircraft",
            columns=("Aircraft", "Span [m]", "Wing area [m²]", "AR"),
            rows=[
                ("Concorde", "25.6", "358.2", "1.8"),
                ("Space Shuttle orbiter", "23.8", "249.9", "2.3"),
                ("Lockheed F-104", "6.68", "18.2", "2.4"),
                ("General Dynamics F-16", "9.45", "27.9", "3.2"),
                ("Cessna 172", "10.97", "16.2", "7.4"),
                ("Boeing 747-400", "64.4", "541.2", "7.7"),
                ("Airbus A320", "34.1", "122.6", "9.5"),
                ("Boeing 787-8", "60.1", "377.0", "9.6"),
                ("Lockheed U-2", "31.4", "92.9", "10.6"),
                ("Wandering albatross", "3.1", "0.62", "15"),
                ("15 m class sailplane", "15.0", "9.0", "25"),
                ("Northrop Grumman Global Hawk", "39.9", "50.2", "32"),
            ],
            note="Published span and reference area; different sources define "
                 "wing area slightly differently (with or without the fuselage "
                 "carry-through), so treat the last digit as indicative.",
        ),
        Reference(
            title="What aspect ratio buys, at e = 0.8",
            columns=("AR", "1/(π e AR)", "C_Di at C_L = 0.8"),
            rows=[
                ("2", "0.199", "0.127"),
                ("4", "0.099", "0.064"),
                ("6", "0.066", "0.042"),
                ("8", "0.050", "0.032"),
                ("10", "0.040", "0.025"),
                ("15", "0.027", "0.017"),
                ("20", "0.020", "0.013"),
                ("25", "0.016", "0.010"),
                ("30", "0.013", "0.008"),
            ],
            note="Note the diminishing return: going from AR 2 to AR 6 removes "
                 "0.085 of induced drag coefficient, while going from AR 20 to "
                 "AR 30 removes only 0.005. Past the teens you are buying very "
                 "little drag for a great deal of structure.",
        ),
    ],
    related=["aero.lift_to_drag", "aero.wing_loading", "aero.drag",
             "flight.glide"],
    variables=[
        ("$AR$", "Aspect ratio", "-"),
        ("$b$", "Wingspan, tip to tip", "m"),
        ("$S$", "Wing area", "m²"),
        ("$e$", "Oswald span efficiency factor", "-"),
    ],
    example=(
        "Comparing designs. A Cessna 172 has AR of about 7.3, giving an induced "
        "drag factor 1/(π·0.8·7.33) = 0.0543. A 15 m class sailplane with 9.0 m² "
        "of wing reaches AR = 25 and a factor of 0.0159 - less than a third the "
        "induced drag at the same lift coefficient. That is most of the reason "
        "one glides at 45:1 and the other at 9:1, and it is paid for entirely in "
        "wing bending loads."
    ),
    keywords=("aspect", "ar", "span", "slenderness", "induced drag", "chord",
              "wingspan", "oswald", "span efficiency"),
)


def _reynolds_note(i, value):
    if value < 1e5:
        return ("Low Reynolds regime. Typical of small drones and model aircraft: "
                "laminar separation bubbles are common and aerofoil data measured "
                "at high Re does not apply.")
    if value < 5e5:
        return ("Transitional range for a smooth flat plate. Real transition "
                "depends strongly on surface roughness, pressure gradient and "
                "free-stream turbulence.")
    return "Turbulent boundary layer expected over most of the surface."


_REYNOLDS = Calculator(
    slug="aero.reynolds",
    name="Reynolds number",
    latex=r"Re = \frac{\rho\,V\,L}{\mu} = \frac{V\,L}{\nu}",
    explanation=(
        "The ratio of inertial to viscous forces. It tells you which flow regime "
        "you are in, and it is why a model aircraft does not behave like a scaled "
        "airliner: small and slow means low Re, thicker boundary layers and worse "
        "aerofoil performance."
    ),
    inputs=[
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0),
        Field("v", "Velocity V", "m/s", 25.0, min=0.0),
        Field("length", "Characteristic length L", "m", 0.25, min=0.0,
              help="Wing chord for an aerofoil, diameter for a pipe or sphere, "
                   "body length for a fuselage."),
        Field("mu", "Dynamic viscosity μ", "Pa·s", MU_AIR_SL, min=0.0,
              help="Air at 15 °C: 1.789e-5 Pa·s. Water at 20 °C: 1.00e-3."),
    ],
    compute=lambda i: reynolds_number(i.rho, i.v, i.length, i.mu),
    result=Output("Reynolds number Re", "-"),
    secondary=[
        Secondary("Kinematic viscosity ν = μ/ρ", "m²/s", lambda i, r: i.mu / i.rho),
        Secondary("Speed for Re = 500,000 at this length", "m/s",
                  lambda i, r: 500000.0 * i.mu / (i.rho * i.length)),
    ],
    note=_reynolds_note,
    assumptions=[
        "Re is only meaningful alongside the length you chose - always state it "
        "(for example 'Re = 250,000 based on chord').",
        "The flat-plate transition value near 5 × 10⁵ is a rule of thumb, not a "
        "law. Roughness or turbulence can trip the flow far earlier.",
        "μ depends on temperature, not much on pressure. The default is air at "
        "15 °C; at -50 °C at altitude it is closer to 1.47e-5 Pa·s.",
    ],
    variables=[
        ("$Re$", "Reynolds number", "-"),
        ("$\\rho$", "Fluid density", "kg/m³"),
        ("$V$", "Flow velocity", "m/s"),
        ("$L$", "Characteristic length", "m"),
        ("$\\mu$", "Dynamic viscosity", "Pa·s"),
        ("$\\nu$", "Kinematic viscosity, μ/ρ", "m²/s"),
    ],
    example=(
        "Choosing an aerofoil for a drone. A 25 cm chord at 25 m/s gives Re of "
        "about 428,000, so you need aerofoil data measured near that Re - "
        "published data at Re = 3,000,000 from a full-size aircraft will "
        "overpromise maximum lift and underpredict drag."
    ),
    keywords=("reynolds", "re", "viscous", "laminar", "turbulent"),
)

CALCULATORS = [
    _LIFT,
    _DRAG,
    _DYNAMIC_PRESSURE,
    _LIFT_TO_DRAG,
    _WING_LOADING,
    _ASPECT_RATIO,
    _REYNOLDS,
]
