"""Control-systems calculators: tracking error and a PID simulator.

The plant is a first-order lag (τ * dy/dt = K*u - y), the simplest model that
still behaves like a real system: it has inertia, it cannot respond instantly,
and it needs integral action to remove steady-state error. It is a teaching
model, not a model of your hardware.
"""
from __future__ import annotations

import numpy as np
import streamlit as st

from utils import ui
from utils import validation as v
from utils.plotting import ACCENT, MUTED, PRIMARY, new_figure, show
from utils.spec import Calculator, Field, Output, Secondary, Sweep

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def control_error(setpoint: float, measured: float) -> float:
    """e = setpoint - measured_value"""
    setpoint = v.finite(setpoint, "Setpoint")
    measured = v.finite(measured, "Measured value")
    return setpoint - measured


def simulate_pid(kp: float, ki: float, kd: float, setpoint: float,
                 initial_value: float, plant_gain: float, time_constant: float,
                 duration: float, u_min: float, u_max: float,
                 derivative_on_measurement: bool = True, dt: float = None):
    """Simulate a PID controller driving a first-order plant.

    Controller:  u = Kp*e + Ki*integral(e) + Kd*de/dt      (e = setpoint - y)
    Plant:       τ * dy/dt = K*u - y

    Integration is forward Euler with a small fixed step. Integral wind-up is
    handled by conditional integration: while the output is saturated, the
    integral term stops accumulating.

    Returns (t, y, u) as numpy arrays.
    """
    for name, gain in (("Kp", kp), ("Ki", ki), ("Kd", kd)):
        v.finite(gain, name)
    setpoint = v.finite(setpoint, "Setpoint")
    initial_value = v.finite(initial_value, "Initial value")
    plant_gain = v.non_zero(plant_gain, "Plant gain K")
    time_constant = v.positive(time_constant, "Plant time constant", "s")
    duration = v.positive(duration, "Simulation duration", "s")
    u_min = v.finite(u_min, "Minimum output")
    u_max = v.finite(u_max, "Maximum output")
    if u_max <= u_min:
        raise v.ValidationError("Maximum controller output must be greater than "
                                "the minimum.")

    if dt is None:
        dt = min(0.01, time_constant / 50.0, duration / 200.0)
    steps = int(round(duration / dt)) + 1
    if steps > 20001:                      # keep the UI responsive
        steps = 20001
        dt = duration / (steps - 1)

    t = np.linspace(0.0, duration, steps)
    y = np.zeros(steps)
    u = np.zeros(steps)

    y[0] = initial_value
    integral = 0.0
    previous_error = setpoint - initial_value
    previous_y = initial_value

    for k in range(steps):
        error = setpoint - y[k]
        if derivative_on_measurement:
            # Differentiating the measurement avoids the large spike ("derivative
            # kick") that a step change in setpoint produces with de/dt.
            derivative_term = -kd * (y[k] - previous_y) / dt
        else:
            derivative_term = kd * (error - previous_error) / dt

        candidate = kp * error + ki * (integral + error * dt) + derivative_term
        if u_min <= candidate <= u_max:
            integral += error * dt          # only integrate while unsaturated
            u[k] = candidate
        else:
            u[k] = min(max(candidate, u_min), u_max)

        previous_error = error
        previous_y = y[k]
        if k < steps - 1:
            dydt = (plant_gain * u[k] - y[k]) / time_constant
            y[k + 1] = y[k] + dydt * dt

    return t, y, u


def response_metrics(t, y, setpoint: float, initial_value: float) -> dict:
    """Standard step-response measures. Returns NaN where undefined."""
    span = setpoint - initial_value
    blank = {"overshoot_pct": float("nan"), "rise_time": float("nan"),
             "settling_time": float("nan"), "steady_state_error": setpoint - y[-1],
             "peak": float(np.max(y) if span >= 0 else np.min(y))}
    if span == 0:
        return blank

    progress = (np.asarray(y) - initial_value) / span      # 0 at start, 1 on target
    peak_progress = float(np.max(progress))
    blank["overshoot_pct"] = max(peak_progress - 1.0, 0.0) * 100.0

    above_10 = np.flatnonzero(progress >= 0.1)
    above_90 = np.flatnonzero(progress >= 0.9)
    if above_10.size and above_90.size:
        blank["rise_time"] = float(t[above_90[0]] - t[above_10[0]])

    outside = np.flatnonzero(np.abs(progress - 1.0) > 0.02)   # +/- 2% band
    if outside.size == 0:
        blank["settling_time"] = 0.0
    elif outside[-1] + 1 < len(t):
        blank["settling_time"] = float(t[outside[-1] + 1])
    return blank


def damped_frequency(natural_frequency: float, damping: float) -> float:
    """omega_d = omega_n sqrt(1 - zeta^2)   [rad/s] - the frequency you SEE."""
    natural_frequency = v.positive(natural_frequency, "Natural frequency",
                                   "rad/s")
    damping = v.in_range(damping, "Damping ratio", 0.0, 0.999)
    return natural_frequency * float(np.sqrt(1.0 - damping ** 2))


def overshoot_percent(damping: float) -> float:
    """Mp = exp(-pi zeta / sqrt(1 - zeta^2)) * 100   [%]

    Only defined for an underdamped system. At zeta >= 1 there is no overshoot.
    """
    damping = v.in_range(damping, "Damping ratio", 0.0, 10.0)
    if damping >= 1.0:
        return 0.0
    return float(np.exp(-np.pi * damping / np.sqrt(1.0 - damping ** 2)) * 100.0)


def peak_time(natural_frequency: float, damping: float) -> float:
    """tp = pi / omega_d   [s]"""
    return float(np.pi / damped_frequency(natural_frequency, damping))


def settling_time(natural_frequency: float, damping: float) -> float:
    """ts ~= 4 / (zeta omega_n)   [s] to within 2% - an envelope estimate."""
    natural_frequency = v.positive(natural_frequency, "Natural frequency",
                                   "rad/s")
    damping = v.positive(damping, "Damping ratio")
    return 4.0 / (damping * natural_frequency)


def rise_time(natural_frequency: float, damping: float) -> float:
    """tr = (pi - arccos(zeta)) / omega_d   [s], 0 to 100% for underdamped."""
    damping = v.in_range(damping, "Damping ratio", 0.0, 0.999)
    return float((np.pi - np.arccos(damping))
                 / damped_frequency(natural_frequency, damping))


def ziegler_nichols(ultimate_gain: float, ultimate_period: float,
                    controller: str = "PID"):
    """Classic ultimate-gain tuning rules. Returns (Kp, Ki, Kd).

    Targets quarter-amplitude decay, which is aggressive by modern standards -
    roughly 25% overshoot and a gain margin near 2.
    """
    ultimate_gain = v.positive(ultimate_gain, "Ultimate gain Ku")
    ultimate_period = v.positive(ultimate_period, "Ultimate period Tu", "s")
    if controller == "P":
        return 0.5 * ultimate_gain, 0.0, 0.0
    if controller == "PI":
        kp = 0.45 * ultimate_gain
        ti = ultimate_period / 1.2
        return kp, kp / ti, 0.0
    kp = 0.6 * ultimate_gain
    ti = ultimate_period / 2.0
    td = ultimate_period / 8.0
    return kp, kp / ti, kp * td


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def render_error() -> None:
    p = "ctrl_err"
    ui.page_header(
        "Control error",
        r"e(t) = r(t) - y(t)",
        "The starting point of every feedback loop: the difference between where "
        "you want to be and where you are. Everything a controller does is a "
        "response to this one number.",
        p,
    )
    c1, c2 = st.columns(2)
    with c1:
        setpoint = ui.number("Setpoint r (target)", "units", f"{p}_sp", 100.0)
    with c2:
        measured = ui.number("Measured value y", "units", f"{p}_pv", 92.0)

    value = ui.compute(lambda: control_error(setpoint, measured))
    if value is not None:
        ui.result(
            "Error e", value, "units",
            secondary=[
                ("Absolute error", abs(value), "units"),
                ("As a percentage of the setpoint",
                 abs(value) / abs(setpoint) * 100.0 if setpoint != 0
                 else float("nan"), "%"),
                ("Proportional action at Kp = 2", 2.0 * value, "output units"),
            ],
        )
        st.caption("Positive error: the measurement is below the setpoint, so the "
                   "controller must push harder." if value > 0 else
                   "Negative error: the measurement has overshot the setpoint."
                   if value < 0 else "On target.")
    ui.assumptions([
        "Sign convention: error = setpoint minus measurement. The opposite "
        "convention exists and flips the sign of every gain - be consistent.",
        "The measurement is assumed accurate. Sensor bias, noise and lag all "
        "corrupt the error a real controller sees.",
        "Setpoint and measurement must be in the same units.",
    ])
    ui.reference(
        variables=[
            ("$e(t)$", "Control error", "process units"),
            ("$r(t)$", "Setpoint (reference)", "process units"),
            ("$y(t)$", "Measured process value", "process units"),
        ],
        example="Drone altitude hold. Commanded 100 m, barometer reads 92 m, "
                "so the error is +8 m and the controller increases thrust. The "
                "same error drives the integral and derivative terms too.",
    )


def render_pid() -> None:
    p = "ctrl_pid"
    ui.page_header(
        "PID controller simulator",
        r"u(t) = K_p\,e(t) + K_i\!\int_0^t\! e(\tau)\,d\tau + K_d\,\frac{de(t)}{dt}",
        "Three terms, three jobs. <b>Proportional</b> reacts to the error right "
        "now. <b>Integral</b> accumulates past error and removes the steady offset "
        "that P alone leaves behind. <b>Derivative</b> reacts to how fast the error "
        "is changing and damps overshoot. Move the gains and watch the response.",
        p,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Controller gains**")
        kp = ui.number("Proportional gain Kp", "-", f"{p}_kp", 2.0)
        ki = ui.number("Integral gain Ki", "1/s", f"{p}_ki", 1.0)
        kd = ui.number("Derivative gain Kd", "s", f"{p}_kd", 0.1)
    with c2:
        st.markdown("**Target and start point**")
        setpoint = ui.number("Setpoint", "units", f"{p}_sp", 1.0)
        initial = ui.number("Initial value", "units", f"{p}_y0", 0.0)
        duration = ui.number("Simulation duration", "s", f"{p}_dur", 10.0,
                             min_value=0.0)
    with c3:
        st.markdown("**Plant and limits**")
        plant_gain = ui.number("Plant gain K", "-", f"{p}_k", 1.0,
                               help="Steady-state output per unit of controller "
                                    "output.")
        tau = ui.number("Plant time constant τ", "s", f"{p}_tau", 1.0,
                        min_value=0.0,
                        help="Time to reach 63% of a step change with no control.")
        limits = ui.number("Output limit (±)", "-", f"{p}_lim", 10.0,
                           min_value=0.0,
                           help="Actuator saturation. Integral wind-up is "
                                "prevented while saturated.")

    derivative_on_measurement = st.checkbox(
        "Derivative on measurement (recommended)", value=True, key=f"{p}_dom",
        help="Differentiating the measurement instead of the error avoids the "
             "large 'derivative kick' when the setpoint changes suddenly.")

    simulation = ui.compute(lambda: simulate_pid(
        kp, ki, kd, setpoint, initial, plant_gain, tau, duration,
        -limits, limits, derivative_on_measurement))

    if simulation is not None:
        t, y, u = simulation
        metrics = response_metrics(t, y, setpoint, initial)
        ui.result(
            "Final value after simulation", float(y[-1]), "units",
            secondary=[
                ("Steady-state error", metrics["steady_state_error"], "units"),
                ("Overshoot", metrics["overshoot_pct"], "%"),
                ("Rise time (10-90%)", metrics["rise_time"], "s"),
                ("Settling time (±2%)", metrics["settling_time"], "s"),
            ],
        )
        if not np.isfinite(metrics["settling_time"]):
            st.caption("The response had not settled within ±2% of the setpoint "
                       "by the end of the simulation window.")

        fig, (ax_y, ax_u) = new_figure(rows=2, height=2.5)
        ax_y.axhline(setpoint, color=MUTED, linestyle="--", linewidth=1.2,
                     label="Setpoint")
        ax_y.plot(t, y, color=PRIMARY, linewidth=2, label="Response y(t)")
        ax_y.set_ylabel("Process value")
        ax_y.legend(loc="lower right", fontsize=9, frameon=False)
        ax_y.set_title("Closed-loop step response", fontsize=10, loc="left")
        ax_u.plot(t, u, color=ACCENT, linewidth=1.6, label="Control output u(t)")
        # Only draw the saturation limits when the controller gets near them,
        # otherwise they stretch the axis and flatten the trace.
        if float(np.max(np.abs(u))) > 0.6 * limits:
            ax_u.axhline(limits, color=MUTED, linestyle=":", linewidth=1)
            ax_u.axhline(-limits, color=MUTED, linestyle=":", linewidth=1)
            ax_u.annotate("output limit", xy=(t[-1], limits), xytext=(-64, 4),
                          textcoords="offset points", fontsize=9, color=MUTED)
        ax_u.set_ylabel("Controller output")
        ax_u.set_xlabel("Time [s]")
        ax_u.legend(loc="upper right", fontsize=9, frameon=False)
        show(fig)

        st.warning(
            "**Educational simulation.** This is an idealised first-order plant "
            "with perfect, noise-free measurement and no time delay. Real systems "
            "have sensor noise, actuator dynamics, transport delay and nonlinear "
            "behaviour. Gains tuned here are a starting point for intuition only - "
            "they are not a substitute for tuning and validating a controller on "
            "the real hardware, with safety measures in place."
        )

    ui.assumptions([
        "Plant model: τ * dy/dt = K*u - y, a first-order lag. Your system is "
        "almost certainly not exactly this.",
        "Forward Euler integration at a fixed time step; the step is chosen small "
        "relative to the plant time constant.",
        "Ideal, instantaneous, noise-free measurement and no transport delay.",
        "Controller output is clamped to the limit you set, and the integral term "
        "stops accumulating while clamped (conditional integration anti-wind-up).",
        "Continuous-time behaviour is approximated. A real digital controller runs "
        "at a fixed sample rate, which adds its own lag.",
    ])
    ui.reference(
        variables=[
            ("$u(t)$", "Controller output (to the actuator)", "output units"),
            ("$e(t)$", "Error, setpoint minus measurement", "process units"),
            ("$K_p$", "Proportional gain", "-"),
            ("$K_i$", "Integral gain", "1/s"),
            ("$K_d$", "Derivative gain", "s"),
            ("$K$", "Plant steady-state gain", "-"),
            ("$\\tau$", "Plant time constant", "s"),
        ],
        example="Drone altitude hold, motor speed control, robot joint position, "
                "temperature control - all the same three terms. Try it: set Ki to "
                "0 and watch the response settle short of the setpoint (that gap "
                "is steady-state error). Bring Ki back and it closes. Push Kp high "
                "with Kd at 0 and the response oscillates.",
    )


_SECOND_ORDER = Calculator(
    slug="ctrl.second_order",
    name="Second-order step response",
    latex=(r"M_p = e^{-\pi\zeta/\sqrt{1-\zeta^{2}}}, \qquad "
           r"\omega_d = \omega_n\sqrt{1-\zeta^{2}}, \qquad "
           r"t_s \approx \frac{4}{\zeta\omega_n}"),
    explanation=(
        "The shape of a response, from two numbers. Damping ratio ζ sets how "
        "much it overshoots and rings; natural frequency ωn sets how fast it "
        "all happens. The PID simulator's plant is first-order and so cannot "
        "overshoot on its own - this is where the oscillation comes from."),
    inputs=[
        Field("zeta", "Damping ratio ζ", "-", 0.5, min=0.0, max=0.999,
              help="Under 1 is underdamped and rings. 0.707 is the usual "
                   "target, giving about 4.3% overshoot."),
        Field("wn", "Natural frequency ωn", "rad/s", 10.0, min=0.0,
              help="In rad/s, not Hz. Divide by 2π for hertz."),
    ],
    compute=lambda i: overshoot_percent(i.zeta),
    result=Output("Overshoot", "%"),
    secondary=[
        Secondary("Damped frequency ωd (what you actually see)", "rad/s",
                  lambda i, r: damped_frequency(i.wn, i.zeta)),
        Secondary("Peak time", "s", lambda i, r: peak_time(i.wn, i.zeta)),
        Secondary("Rise time (0-100%)", "s",
                  lambda i, r: rise_time(i.wn, i.zeta)),
        Secondary("Settling time (±2%)", "s",
                  lambda i, r: settling_time(i.wn, i.zeta)),
        Secondary("Ringing frequency", "Hz",
                  lambda i, r: damped_frequency(i.wn, i.zeta) / (2.0 * np.pi)),
    ],
    note=lambda i, r: (
        "ζ = 0.707 - the usual design target, about 4.3% overshoot with a fast "
        "settle." if 0.69 < i.zeta < 0.72 else
        "Very lightly damped: this will ring for a long time." if i.zeta < 0.2
        else None),
    assumptions=[
        "CANONICAL second order: two poles, no zeros, unity DC gain. A zero in "
        "the numerator increases overshoot, sometimes a lot, and these formulas "
        "then UNDER-estimate it. Real closed loops are rarely canonical.",
        "The overshoot formula needs 0 < ζ < 1. At ζ ≥ 1 there is no overshoot "
        "and no damped frequency to speak of.",
        "Settling time 4/(ζωn) is an envelope approximation, good to perhaps "
        "10-20%. The exact value jumps as the last excursion crosses the band.",
        "ωn is NOT the frequency you observe. The ringing you see is ωd, and "
        "both are in rad/s rather than hertz - the 2π catches people constantly.",
    ],
    graph=Sweep(over="zeta", y_label="Overshoot [%]", lo=0.02, hi_factor=2.0,
                title="Overshoot vs damping ratio - 0.707 gives about 4.3%"),
    variables=[
        ("$\\zeta$", "Damping ratio", "-"),
        ("$\\omega_n$", "Natural frequency", "rad/s"),
        ("$\\omega_d$", "Damped (observed) frequency", "rad/s"),
        ("$M_p$", "Peak overshoot", "%"),
        ("$t_s$", "Settling time to ±2%", "s"),
    ],
    example=(
        "Specifying a servo loop. Asking for under 5% overshoot means ζ of at "
        "least about 0.69; asking to settle within 0.5 s then fixes ωn at "
        "roughly 12 rad/s. Those two numbers are the whole specification, and "
        "everything else follows from them."),
    keywords=("second order", "damping", "overshoot", "settling", "zeta",
              "natural frequency", "step response", "ringing"),
)


def _zn_gains(i):
    return ziegler_nichols(i.ku, i.tu, i.controller)


_ZIEGLER = Calculator(
    slug="ctrl.ziegler_nichols",
    name="Ziegler–Nichols tuning",
    latex=(r"K_p = 0.6\,K_u, \qquad T_i = \frac{T_u}{2}, "
           r"\qquad T_d = \frac{T_u}{8}"),
    explanation=(
        "Starting gains from two measurements: the proportional gain at which "
        "the loop just oscillates steadily (Ku) and the period of that "
        "oscillation (Tu). Feed the results into the PID simulator to see what "
        "they do - and expect to detune them."),
    inputs=[
        Field("controller", "Controller type", "", 0, kind="choice",
              options=["PID", "PI", "P"]),
        Field("ku", "Ultimate gain Ku", "-", 8.0, min=0.0,
              help="Proportional gain at which the loop oscillates steadily."),
        Field("tu", "Ultimate period Tu", "s", 1.5, min=0.0,
              help="Period of that sustained oscillation."),
    ],
    compute=lambda i: _zn_gains(i)[0],
    result=Output("Proportional gain Kp", "-"),
    secondary=[
        Secondary("Integral gain Ki", "1/s", lambda i, r: _zn_gains(i)[1]),
        Secondary("Derivative gain Kd", "s", lambda i, r: _zn_gains(i)[2]),
        Secondary("Integral time Ti", "s",
                  lambda i, r: (_zn_gains(i)[0] / _zn_gains(i)[1]
                                if _zn_gains(i)[1] else float("nan"))),
        Secondary("Derivative time Td", "s",
                  lambda i, r: (_zn_gains(i)[2] / _zn_gains(i)[0]
                                if _zn_gains(i)[0] else float("nan"))),
        Secondary("Halved Kp (a common detune)", "-",
                  lambda i, r: r / 2.0),
    ],
    assumptions=[
        "Ziegler-Nichols targets QUARTER-AMPLITUDE DECAY: roughly 25% overshoot "
        "and a gain margin near 2. That is aggressive by modern standards and "
        "often unacceptable on real hardware. Halving Kp is standard practice.",
        "Finding Ku experimentally means deliberately driving a system into "
        "sustained oscillation. On anything with stored energy, a moving mass, "
        "or a person nearby, that is dangerous. Do it in simulation first.",
        "Assumes a self-regulating process with a single dominant lag. "
        "Integrating plants - most position loops - need different rules.",
        "Performs poorly on lag-dominant processes and on plants with strong "
        "oscillatory modes.",
        "Modern alternatives worth knowing: Cohen-Coon, AMIGO, and lambda/IMC "
        "tuning, which trade aggression for robustness.",
    ],
    variables=[
        ("$K_u$", "Ultimate gain - where the loop just oscillates", "-"),
        ("$T_u$", "Period of that oscillation", "s"),
        ("$K_p, K_i, K_d$", "Resulting PID gains", "-, 1/s, s"),
        ("$T_i, T_d$", "Integral and derivative times", "s"),
    ],
    example=(
        "Tuning a temperature loop. If it oscillates steadily at Kp = 8 with a "
        "1.5 s period, Ziegler-Nichols suggests Kp 4.8, Ki 6.4, Kd 0.9. Put "
        "those into the PID simulator, then halve Kp and compare - the detuned "
        "version is usually the one you would actually ship."),
    keywords=("ziegler", "nichols", "tuning", "pid", "gains", "ku", "tu"),
)

_PID = Calculator(
    slug="ctrl.pid", name="PID simulator", latex="", explanation="",
    render=render_pid,
    keywords=("pid", "controller", "simulate", "tuning", "step response"),
)

_ERROR = Calculator(
    slug="ctrl.error", name="Control error", latex="", explanation="",
    render=render_error,
    keywords=("error", "setpoint", "measured", "feedback"),
)

CALCULATORS = [_ERROR, _PID, _SECOND_ORDER, _ZIEGLER]
