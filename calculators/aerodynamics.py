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
from utils.constants import G0, MU_AIR_SL, RHO_SL
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

_DRAG = Calculator(
    slug="aero.drag",
    name="Drag",
    latex=r"D = \tfrac{1}{2}\,\rho\,V^{2}\,S\,C_D",
    explanation=(
        "Drag is the force component along the flow direction. It has the same "
        "form as lift, so it also grows with the square of speed - and the power "
        "needed to overcome it, P = D × V, grows with the <b>cube</b> of speed."
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
        Secondary("Equivalent thrust needed", "N", lambda i, r: r),
    ],
    assumptions=[
        "C_D is the total drag coefficient at this condition (parasite + induced), "
        "referenced to the same area S as the value you entered.",
        "C_D is not constant: it rises with lift (induced drag) and changes with "
        "Reynolds and Mach number.",
        "Steady, incompressible flow below roughly Mach 0.3.",
        "P = D × V is the propulsive power delivered to the air, before propeller "
        "and motor efficiency losses.",
    ],
    graph=Sweep(over="v", y_label="Drag D [N]", hi_factor=1.6, hi_min=10.0,
                title="Drag vs velocity"),
    variables=[
        ("$D$", "Drag force", "N"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$V$", "True airspeed", "m/s"),
        ("$S$", "Reference area", "m²"),
        ("$C_D$", "Drag coefficient (dimensionless)", "-"),
    ],
    example=(
        "Estimating cruise thrust. If a UAV needs 12 N of drag-balancing thrust at "
        "25 m/s, the propeller must deliver 300 W of useful power to the air. At "
        "50 m/s the same aircraft needs 4x the thrust and 8x the power - the cube "
        "law is why top speed is so expensive."
    ),
    keywords=("drag", "cd", "parasite", "resistance"),
)

_DYNAMIC_PRESSURE = Calculator(
    slug="aero.dynamic_pressure",
    name="Dynamic pressure",
    latex=r"q = \tfrac{1}{2}\,\rho\,V^{2}",
    explanation=(
        "Dynamic pressure is the kinetic energy per unit volume of the moving air. "
        "It is the common factor in every aerodynamic force, and it is what an "
        "airspeed indicator (a pitot-static system) actually measures."
    ),
    inputs=[
        Field("rho", "Air density ρ", "kg/m³", RHO_SL, min=0.0),
        Field("v", "Velocity V", "m/s", 50.0, min=0.0),
    ],
    compute=lambda i: dynamic_pressure(i.rho, i.v),
    result=Output("Dynamic pressure q", "Pa"),
    secondary=[
        Secondary("In kilopascals", "kPa", lambda i, r: r / 1000.0),
        Secondary("As a fraction of sea-level static pressure", "-",
                  lambda i, r: r / 101325.0),
        Secondary("Force on a 1 m² flat plate with C_D = 1.2", "N",
                  lambda i, r: r * 1.2),
    ],
    assumptions=[
        "Incompressible flow. Above about Mach 0.3 the true stagnation pressure "
        "rise exceeds 0.5 ρ V² and a compressible correction is needed.",
        "ρ is the density where the vehicle actually is, not sea-level density.",
        "V is true airspeed. Indicated airspeed is derived from q assuming "
        "sea-level density, which is why IAS reads low at altitude.",
    ],
    graph=Sweep(over="v", y_label="Dynamic pressure q [Pa]", hi_factor=1.6,
                hi_min=10.0, title="Dynamic pressure vs velocity"),
    variables=[
        ("$q$", "Dynamic pressure", "Pa"),
        ("$\\rho$", "Air density", "kg/m³"),
        ("$V$", "True airspeed", "m/s"),
    ],
    example=(
        "Structural load cases. A quadcopter arm flying into a 20 m/s gust sees "
        "q = 245 Pa; multiplied by the frontal area and a drag coefficient, that "
        "gives the side load the arm must survive."
    ),
    keywords=("q", "dynamic", "pressure", "pitot"),
)

_LIFT_TO_DRAG = Calculator(
    slug="aero.lift_to_drag",
    name="Lift-to-drag ratio",
    latex=r"\frac{L}{D} = \frac{C_L}{C_D}",
    explanation=(
        "The single best measure of aerodynamic efficiency. Because lift and drag "
        "share the identical 0.5 ρ V² S factor, that factor cancels exactly and "
        "the force ratio equals the coefficient ratio."
    ),
    inputs=[
        Field("cl", "Lift coefficient C_L", "-", 0.5),
        Field("cd", "Drag coefficient C_D", "-", 0.032, min=0.0),
    ],
    compute=lambda i: lift_to_drag(i.cl, i.cd),
    result=Output("Lift-to-drag ratio L/D", "-"),
    secondary=[
        Secondary("Glide ratio (distance per unit height lost)", "m per m",
                  lambda i, r: r),
        Secondary("Glide angle below horizontal", "°",
                  lambda i, r: float(np.degrees(np.arctan(1.0 / r)))),
        Secondary("Drag as a fraction of weight in level flight", "-",
                  lambda i, r: 1.0 / r),
    ],
    assumptions=[
        "Both coefficients are evaluated at the same flight condition - same angle "
        "of attack, same reference area, same Reynolds and Mach number.",
        "The glide-ratio reading assumes an unpowered, steady glide with a shallow "
        "angle, where lift is approximately equal to weight.",
        "Typical values for orientation: a competition sailplane 40-60, an airliner "
        "15-20, a small fixed-wing UAV 8-15, a multirotor in forward flight 2-5.",
    ],
    variables=[
        ("$C_L$", "Lift coefficient", "-"),
        ("$C_D$", "Drag coefficient", "-"),
        ("$L/D$", "Lift-to-drag ratio", "-"),
    ],
    example=(
        "Range planning. An aircraft gliding at L/D = 15 from 1000 m altitude "
        "covers about 15 km in still air. The same number sets the thrust needed "
        "in cruise: T = W / (L/D)."
    ),
    keywords=("ld", "efficiency", "glide", "ratio"),
)

_WING_LOADING = Calculator(
    slug="aero.wing_loading",
    name="Wing loading",
    latex=r"\frac{W}{S} = \frac{\text{weight}}{\text{wing area}}",
    explanation=(
        "How much weight each square metre of wing must carry. It sets stall speed, "
        "turn performance and how roughly the aircraft rides through gusts. "
        "This uses <b>weight in newtons</b>, not mass in kilograms."
    ),
    inputs=[
        Field("weight", "Aircraft", "", 1200.0, kind="weight"),
        Field("s", "Wing area S", "m²", 16.2, min=0.0),
    ],
    compute=lambda i: wing_loading(i.weight, i.s),
    result=Output("Wing loading W/S", "N/m²"),
    secondary=[
        Secondary("Equivalent mass per area (m/S)", "kg/m²", lambda i, r: r / G0),
        Secondary("In pound-force per square foot", "lbf/ft²",
                  lambda i, r: r * 0.0208854),
        Secondary("Stall speed at ρ = 1.225, C_Lmax = 1.4", "m/s",
                  lambda i, r: float(np.sqrt(2.0 * r / (RHO_SL * 1.4)))),
    ],
    assumptions=[
        "Wing loading is quoted at a stated weight - usually maximum take-off "
        "weight. The same aircraft has a lower wing loading when nearly empty.",
        "S is the same reference area used for the lift and drag coefficients.",
        "The stall-speed figure is an illustration using assumed sea-level density "
        "and C_Lmax = 1.4; it is an estimate, not a value for your aircraft.",
        "'Equivalent mass per area' is shown because many hobby sources quote "
        "g/dm² or kg/m²; that is a mass per area, not a force per area.",
    ],
    variables=[
        ("$W$", "Weight (force), W = m g", "N"),
        ("$S$", "Wing reference area", "m²"),
        ("$W/S$", "Wing loading", "N/m²"),
    ],
    example=(
        "Choosing a wing for a fixed-wing drone. Low wing loading (under about "
        "100 N/m²) means slow, gentle flight and short take-offs but poor gust "
        "tolerance. High wing loading means a faster, smoother ride but a higher "
        "stall and landing speed."
    ),
    keywords=("wing loading", "ws", "w/s"),
)

_ASPECT_RATIO = Calculator(
    slug="aero.aspect_ratio",
    name="Aspect ratio",
    latex=r"AR = \frac{b^{2}}{S}",
    explanation=(
        "How slender the wing is. High aspect ratio means long, thin wings, which "
        "cut induced drag (the drag penalty of making lift) and raise L/D - the "
        "reason sailplanes and high-altitude UAVs have such long wings."
    ),
    inputs=[
        Field("b", "Wingspan b", "m", 10.9, min=0.0),
        Field("s", "Wing area S", "m²", 16.2, min=0.0),
    ],
    compute=lambda i: aspect_ratio(i.b, i.s),
    result=Output("Aspect ratio AR", "-"),
    secondary=[
        Secondary("Mean geometric chord (S/b)", "m", lambda i, r: i.s / i.b),
        Secondary("Oswald-corrected induced drag factor 1/(π e AR), e = 0.8", "-",
                  lambda i, r: 1.0 / (np.pi * 0.8 * r)),
    ],
    assumptions=[
        "b²/S is the general definition and works for any planform. For a "
        "rectangular wing it simplifies to span divided by chord.",
        "b is the full tip-to-tip span, not the semi-span.",
        "'Mean geometric chord' S/b is not the same as the mean aerodynamic chord "
        "(MAC) used for stability work, except on an untapered wing.",
        "The induced-drag factor uses an assumed Oswald efficiency e = 0.8 and is "
        "an estimate for orientation only.",
    ],
    variables=[
        ("$AR$", "Aspect ratio", "-"),
        ("$b$", "Wingspan, tip to tip", "m"),
        ("$S$", "Wing area", "m²"),
    ],
    example=(
        "Comparing designs. A Cessna 172 has AR of about 7.3; a high-performance "
        "sailplane reaches 30 or more. Induced drag scales with 1/AR, so doubling "
        "aspect ratio at the same lift roughly halves the induced drag - paid for "
        "in wing bending loads."
    ),
    keywords=("aspect", "ar", "span", "slenderness"),
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
