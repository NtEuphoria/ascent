"""Aerodynamics calculators.

Structure used by every calculator module in this project:
  1. Pure functions at the top - no Streamlit, fully unit-tested, self-validating.
  2. render_* functions below - layout only, calling the pure functions.
  3. A CALCULATORS dict at the bottom mapping menu label -> render function.
"""
from __future__ import annotations

import numpy as np
import streamlit as st

from utils import ui
from utils import validation as v
from utils.constants import G0, MU_AIR_SL, RHO_SL
from utils.plotting import PRIMARY, mark_point, new_figure, show

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


def _velocity_sweep(velocity: float):
    """A 0 -> 1.6x sweep around the user's operating speed, for graphs."""
    top = max(velocity * 1.6, 10.0)
    return np.linspace(0.0, top, 200)


def render_lift() -> None:
    p = "aero_lift"
    ui.page_header(
        "Lift",
        r"L = \tfrac{1}{2}\,\rho\,V^{2}\,S\,C_L",
        "Lift is the aerodynamic force perpendicular to the oncoming flow. "
        "Velocity is <b>squared</b>, so lift is far more sensitive to speed than "
        "to anything else on this page: fly 2x faster and you get 4x the lift at "
        "the same lift coefficient; 3x faster gives 9x.",
        p,
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        rho = ui.number("Air density ρ", "kg/m³", f"{p}_rho", RHO_SL, min_value=0.0,
                        help="1.225 kg/m³ is ISA sea level. It falls with altitude.")
    with c2:
        vel = ui.number("Velocity V", "m/s", f"{p}_v", 50.0, min_value=0.0,
                        help="True airspeed relative to the air mass.")
    with c3:
        area = ui.number("Wing area S", "m²", f"{p}_s", 16.2, min_value=0.0)
    with c4:
        cl = ui.number("Lift coefficient C_L", "-", f"{p}_cl", 0.5,
                       help="Dimensionless. Depends on aerofoil, angle of attack "
                            "and flap setting. Negative values mean downforce.")

    value = ui.compute(lambda: lift(rho, vel, area, cl))
    if value is not None:
        q = dynamic_pressure(rho, vel)
        ui.result(
            "Lift force L", value, "N",
            secondary=[
                ("Dynamic pressure q", q, "Pa"),
                ("Mass this lift supports at 1 g", value / G0, "kg"),
                ("Lift per unit wing area", value / area, "N/m²"),
            ],
        )
    ui.assumptions([
        "Steady, incompressible flow - reliable below roughly Mach 0.3 "
        "(about 100 m/s at sea level). Above that, compressibility changes C_L.",
        "C_L is the value for this exact condition: aerofoil, angle of attack, "
        "flap setting and Reynolds number. It is not a fixed property of the wing.",
        "S is the reference area that C_L was defined against - normally the full "
        "projected planform area, including the part buried in the fuselage.",
        "No ground effect and no propeller slipstream over the wing.",
        "This is an exact definition, not an estimate: the equation defines C_L.",
    ])

    if ui.graph_toggle(p):
        sweep = _velocity_sweep(vel)
        fig, (ax,) = new_figure()
        ax.plot(sweep, 0.5 * rho * sweep ** 2 * area * cl, color=PRIMARY, linewidth=2)
        if vel <= sweep[-1]:
            mark_point(ax, vel, lift(rho, vel, area, cl), "current")
        ax.set_xlabel("Velocity V [m/s]")
        ax.set_ylabel("Lift L [N]")
        ax.set_title("Lift vs velocity (parabolic: L is proportional to V squared)",
                     fontsize=10, loc="left")
        show(fig)

    ui.reference(
        variables=[
            ("$L$", "Lift force", "N"),
            ("$\\rho$", "Air density", "kg/m³"),
            ("$V$", "True airspeed", "m/s"),
            ("$S$", "Reference wing area", "m²"),
            ("$C_L$", "Lift coefficient (dimensionless)", "-"),
        ],
        example="Wing sizing for a small UAV. At sea level, 18 m/s, S = 0.65 m² "
                "and C_L = 0.8, the wing makes about 103 N of lift - enough to hold "
                "a 10.5 kg aircraft in level flight. Halve the speed to 9 m/s and "
                "lift collapses to about 26 N, which is why slow flight needs flaps "
                "(higher C_L) or more wing area.",
    )


def render_drag() -> None:
    p = "aero_drag"
    ui.page_header(
        "Drag",
        r"D = \tfrac{1}{2}\,\rho\,V^{2}\,S\,C_D",
        "Drag is the force component along the flow direction. It has the same "
        "form as lift, so it also grows with the square of speed - and the power "
        "needed to overcome it, P = D × V, grows with the <b>cube</b> of speed.",
        p,
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        rho = ui.number("Air density ρ", "kg/m³", f"{p}_rho", RHO_SL, min_value=0.0)
    with c2:
        vel = ui.number("Velocity V", "m/s", f"{p}_v", 50.0, min_value=0.0)
    with c3:
        area = ui.number("Reference area S", "m²", f"{p}_s", 16.2, min_value=0.0,
                         help="Must be the same reference area used to define C_D.")
    with c4:
        cd = ui.number("Drag coefficient C_D", "-", f"{p}_cd", 0.032, min_value=0.0)

    value = ui.compute(lambda: drag(rho, vel, area, cd))
    if value is not None:
        ui.result(
            "Drag force D", value, "N",
            secondary=[
                ("Dynamic pressure q", dynamic_pressure(rho, vel), "Pa"),
                ("Power to overcome drag (P = D × V)", value * vel, "W"),
                ("Equivalent thrust needed", value, "N"),
            ],
        )
    ui.assumptions([
        "C_D is the total drag coefficient at this condition (parasite + induced), "
        "referenced to the same area S as the value you entered.",
        "C_D is not constant: it rises with lift (induced drag) and changes with "
        "Reynolds and Mach number.",
        "Steady, incompressible flow below roughly Mach 0.3.",
        "P = D × V is the propulsive power delivered to the air, before propeller "
        "and motor efficiency losses.",
    ])

    if ui.graph_toggle(p):
        sweep = _velocity_sweep(vel)
        fig, (ax,) = new_figure()
        ax.plot(sweep, 0.5 * rho * sweep ** 2 * area * cd, color=PRIMARY, linewidth=2)
        if vel <= sweep[-1]:
            mark_point(ax, vel, drag(rho, vel, area, cd), "current")
        ax.set_xlabel("Velocity V [m/s]")
        ax.set_ylabel("Drag D [N]")
        ax.set_title("Drag vs velocity", fontsize=10, loc="left")
        show(fig)

    ui.reference(
        variables=[
            ("$D$", "Drag force", "N"),
            ("$\\rho$", "Air density", "kg/m³"),
            ("$V$", "True airspeed", "m/s"),
            ("$S$", "Reference area", "m²"),
            ("$C_D$", "Drag coefficient (dimensionless)", "-"),
        ],
        example="Estimating cruise thrust. If a UAV needs 12 N of drag-balancing "
                "thrust at 25 m/s, the propeller must deliver 300 W of useful power "
                "to the air. At 50 m/s the same aircraft needs 4x the thrust and 8x "
                "the power - the cube law is why top speed is so expensive.",
    )


def render_dynamic_pressure() -> None:
    p = "aero_q"
    ui.page_header(
        "Dynamic pressure",
        r"q = \tfrac{1}{2}\,\rho\,V^{2}",
        "Dynamic pressure is the kinetic energy per unit volume of the moving air. "
        "It is the common factor in every aerodynamic force, and it is what an "
        "airspeed indicator (a pitot-static system) actually measures.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        rho = ui.number("Air density ρ", "kg/m³", f"{p}_rho", RHO_SL, min_value=0.0)
    with c2:
        vel = ui.number("Velocity V", "m/s", f"{p}_v", 50.0, min_value=0.0)

    value = ui.compute(lambda: dynamic_pressure(rho, vel))
    if value is not None:
        ui.result(
            "Dynamic pressure q", value, "Pa",
            secondary=[
                ("In kilopascals", value / 1000.0, "kPa"),
                ("As a fraction of sea-level static pressure", value / 101325.0, "-"),
                ("Force on a 1 m² flat plate with C_D = 1.2", value * 1.2, "N"),
            ],
        )
    ui.assumptions([
        "Incompressible flow. Above about Mach 0.3 the true stagnation pressure "
        "rise exceeds 0.5 ρ V² and a compressible correction is needed.",
        "ρ is the density where the vehicle actually is, not sea-level density.",
        "V is true airspeed. Indicated airspeed is derived from q assuming "
        "sea-level density, which is why IAS reads low at altitude.",
    ])

    if ui.graph_toggle(p):
        sweep = _velocity_sweep(vel)
        fig, (ax,) = new_figure()
        ax.plot(sweep, 0.5 * rho * sweep ** 2, color=PRIMARY, linewidth=2)
        if vel <= sweep[-1]:
            mark_point(ax, vel, dynamic_pressure(rho, vel), "current")
        ax.set_xlabel("Velocity V [m/s]")
        ax.set_ylabel("Dynamic pressure q [Pa]")
        ax.set_title("Dynamic pressure vs velocity", fontsize=10, loc="left")
        show(fig)

    ui.reference(
        variables=[
            ("$q$", "Dynamic pressure", "Pa"),
            ("$\\rho$", "Air density", "kg/m³"),
            ("$V$", "True airspeed", "m/s"),
        ],
        example="Structural load cases. A quadcopter arm flying into a 20 m/s gust "
                "sees q = 245 Pa; multiplied by the frontal area and a drag "
                "coefficient, that gives the side load the arm must survive.",
    )


def render_lift_to_drag() -> None:
    p = "aero_ld"
    ui.page_header(
        "Lift-to-drag ratio",
        r"\frac{L}{D} = \frac{C_L}{C_D}",
        "The single best measure of aerodynamic efficiency. Because lift and drag "
        "share the identical 0.5 ρ V² S factor, that factor cancels exactly and "
        "the force ratio equals the coefficient ratio.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        cl = ui.number("Lift coefficient C_L", "-", f"{p}_cl", 0.5)
    with c2:
        cd = ui.number("Drag coefficient C_D", "-", f"{p}_cd", 0.032, min_value=0.0)

    value = ui.compute(lambda: lift_to_drag(cl, cd))
    if value is not None:
        ui.result(
            "Lift-to-drag ratio L/D", value, "-",
            secondary=[
                ("Glide ratio (distance per unit height lost)", value, "m per m"),
                ("Glide angle below horizontal", np.degrees(np.arctan(1.0 / value))
                 if value != 0 else float("nan"), "°"),
                ("Drag as a fraction of weight in level flight", 1.0 / value
                 if value != 0 else float("nan"), "-"),
            ],
        )
    ui.assumptions([
        "Both coefficients are evaluated at the same flight condition - same angle "
        "of attack, same reference area, same Reynolds and Mach number.",
        "The glide-ratio reading assumes an unpowered, steady glide with a shallow "
        "angle, where lift is approximately equal to weight.",
        "Typical values for orientation: a competition sailplane 40-60, an airliner "
        "15-20, a small fixed-wing UAV 8-15, a multirotor in forward flight 2-5.",
    ])
    ui.reference(
        variables=[
            ("$C_L$", "Lift coefficient", "-"),
            ("$C_D$", "Drag coefficient", "-"),
            ("$L/D$", "Lift-to-drag ratio", "-"),
        ],
        example="Range planning. An aircraft gliding at L/D = 15 from 1000 m "
                "altitude covers about 15 km in still air. The same number sets the "
                "thrust needed in cruise: T = W / (L/D).",
    )


def render_wing_loading() -> None:
    p = "aero_wl"
    ui.page_header(
        "Wing loading",
        r"\frac{W}{S} = \frac{\text{weight}}{\text{wing area}}",
        "How much weight each square metre of wing must carry. It sets stall speed, "
        "turn performance and how roughly the aircraft rides through gusts. "
        "This uses <b>weight in newtons</b>, not mass in kilograms.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        weight = ui.weight_inputs(p, default_mass=1200.0, label="Aircraft")
    with c2:
        area = ui.number("Wing area S", "m²", f"{p}_s", 16.2, min_value=0.0)

    value = ui.compute(lambda: wing_loading(weight, area))
    if value is not None:
        ui.result(
            "Wing loading W/S", value, "N/m²",
            secondary=[
                ("Equivalent mass per area (m/S)", value / G0, "kg/m²"),
                ("In pound-force per square foot", value * 0.0208854, "lbf/ft²"),
                ("Stall speed at ρ = 1.225, C_Lmax = 1.4",
                 float(np.sqrt(2.0 * value / (RHO_SL * 1.4))), "m/s"),
            ],
        )
    ui.assumptions([
        "Wing loading is quoted at a stated weight - usually maximum take-off "
        "weight. The same aircraft has a lower wing loading when nearly empty.",
        "S is the same reference area used for the lift and drag coefficients.",
        "The stall-speed figure is an illustration using assumed sea-level density "
        "and C_Lmax = 1.4; it is an estimate, not a value for your aircraft.",
        "'Equivalent mass per area' is shown because many hobby sources quote "
        "g/dm² or kg/m²; that is a mass per area, not a force per area.",
    ])
    ui.reference(
        variables=[
            ("$W$", "Weight (force), W = m g", "N"),
            ("$S$", "Wing reference area", "m²"),
            ("$W/S$", "Wing loading", "N/m²"),
        ],
        example="Choosing a wing for a fixed-wing drone. Low wing loading "
                "(under about 100 N/m²) means slow, gentle flight and short "
                "take-offs but poor gust tolerance. High wing loading means a "
                "faster, smoother ride but a higher stall and landing speed.",
    )


def render_aspect_ratio() -> None:
    p = "aero_ar"
    ui.page_header(
        "Aspect ratio",
        r"AR = \frac{b^{2}}{S}",
        "How slender the wing is. High aspect ratio means long, thin wings, which "
        "cut induced drag (the drag penalty of making lift) and raise L/D - the "
        "reason sailplanes and high-altitude UAVs have such long wings.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        span = ui.number("Wingspan b", "m", f"{p}_b", 10.9, min_value=0.0)
    with c2:
        area = ui.number("Wing area S", "m²", f"{p}_s", 16.2, min_value=0.0)

    value = ui.compute(lambda: aspect_ratio(span, area))
    if value is not None:
        ui.result(
            "Aspect ratio AR", value, "-",
            secondary=[
                ("Mean geometric chord (S/b)", area / span, "m"),
                ("Oswald-corrected induced drag factor 1/(π e AR), e = 0.8",
                 1.0 / (np.pi * 0.8 * value), "-"),
            ],
        )
    ui.assumptions([
        "b²/S is the general definition and works for any planform. For a "
        "rectangular wing it simplifies to span divided by chord.",
        "b is the full tip-to-tip span, not the semi-span.",
        "'Mean geometric chord' S/b is not the same as the mean aerodynamic chord "
        "(MAC) used for stability work, except on an untapered wing.",
        "The induced-drag factor uses an assumed Oswald efficiency e = 0.8 and is "
        "an estimate for orientation only.",
    ])
    ui.reference(
        variables=[
            ("$AR$", "Aspect ratio", "-"),
            ("$b$", "Wingspan, tip to tip", "m"),
            ("$S$", "Wing area", "m²"),
        ],
        example="Comparing designs. A Cessna 172 has AR of about 7.3; a high-"
                "performance sailplane reaches 30 or more. Induced drag scales "
                "with 1/AR, so doubling aspect ratio at the same lift roughly "
                "halves the induced drag - paid for in wing bending loads.",
    )


def render_reynolds() -> None:
    p = "aero_re"
    ui.page_header(
        "Reynolds number",
        r"Re = \frac{\rho\,V\,L}{\mu} = \frac{V\,L}{\nu}",
        "The ratio of inertial to viscous forces. It tells you which flow regime "
        "you are in, and it is why a model aircraft does not behave like a scaled "
        "airliner: small and slow means low Re, thicker boundary layers and worse "
        "aerofoil performance.",
        p,
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        rho = ui.number("Air density ρ", "kg/m³", f"{p}_rho", RHO_SL, min_value=0.0)
    with c2:
        vel = ui.number("Velocity V", "m/s", f"{p}_v", 25.0, min_value=0.0)
    with c3:
        length = ui.number("Characteristic length L", "m", f"{p}_l", 0.25,
                           min_value=0.0,
                           help="Wing chord for an aerofoil, diameter for a pipe "
                                "or sphere, body length for a fuselage.")
    with c4:
        mu = ui.number("Dynamic viscosity μ", "Pa·s", f"{p}_mu", MU_AIR_SL,
                       min_value=0.0,
                       help="Air at 15 C: 1.789e-5 Pa·s. Water at 20 C: 1.00e-3.")

    value = ui.compute(lambda: reynolds_number(rho, vel, length, mu))
    if value is not None:
        ui.result(
            "Reynolds number Re", value, "-",
            secondary=[
                ("Kinematic viscosity ν = μ/ρ", mu / rho if rho > 0
                 else float("nan"), "m²/s"),
                ("Speed for Re = 500,000 at this length",
                 500000.0 * mu / (rho * length) if rho > 0 else float("nan"), "m/s"),
            ],
        )
        if value < 1e5:
            st.caption("Low Reynolds regime. Typical of small drones and model "
                       "aircraft: laminar separation bubbles are common and "
                       "aerofoil data measured at high Re does not apply.")
        elif value < 5e5:
            st.caption("Transitional range for a smooth flat plate. Real transition "
                       "depends strongly on surface roughness, pressure gradient "
                       "and free-stream turbulence.")
        else:
            st.caption("Turbulent boundary layer expected over most of the surface.")
    ui.assumptions([
        "Re is only meaningful alongside the length you chose - always state it "
        "(for example 'Re = 250,000 based on chord').",
        "The flat-plate transition value near 5 × 10⁵ is a rule of thumb, not a "
        "law. Roughness or turbulence can trip the flow far earlier.",
        "μ depends on temperature, not much on pressure. The default is air at "
        "15 C; at -50 C at altitude it is closer to 1.47e-5 Pa·s.",
    ])
    ui.reference(
        variables=[
            ("$Re$", "Reynolds number", "-"),
            ("$\\rho$", "Fluid density", "kg/m³"),
            ("$V$", "Flow velocity", "m/s"),
            ("$L$", "Characteristic length", "m"),
            ("$\\mu$", "Dynamic viscosity", "Pa·s"),
            ("$\\nu$", "Kinematic viscosity, μ/ρ", "m²/s"),
        ],
        example="Choosing an aerofoil for a drone. A 25 cm chord at 25 m/s gives "
                "Re of about 428,000, so you need aerofoil data measured near that "
                "Re - published data at Re = 3,000,000 from a full-size aircraft "
                "will overpromise maximum lift and underpredict drag.",
    )


CALCULATORS = {
    "Lift": render_lift,
    "Drag": render_drag,
    "Dynamic pressure": render_dynamic_pressure,
    "Lift-to-drag ratio": render_lift_to_drag,
    "Wing loading": render_wing_loading,
    "Aspect ratio": render_aspect_ratio,
    "Reynolds number": render_reynolds,
}
