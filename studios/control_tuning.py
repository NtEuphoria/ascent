"""Control tuning studio: turn a response specification into gains, and check
whether the loop you are about to write can actually deliver it.

Four steps, in the order the decision is really made:

    what you want  ->  the response that implies  ->  tuning  ->  a verdict

A specification is written in the language of the response ("no more than 10%
overshoot, settled inside 1.6 s"). A controller is written in the language of
gains. This page walks that gap in one direction and back again: the overshoot
limit fixes the damping ratio, the settling target then fixes the natural
frequency, those two predict the whole shape of the step, and a PID simulation
of the same step says whether the gains you have chosen land anywhere near it.

Everything is computed by the existing verified functions in
`calculators/controls.py` - the second-order relations, the Ziegler-Nichols
rules, the PID simulator and its response metrics - so this page cannot drift
away from what those pages say.

The check that earns this page its keep is the sample rate. A continuous design
is derived on paper and then run on a computer at a fixed rate, and the hold
between samples is a delay the design never knew about. `sampling_phase_lag`
puts a number on the phase that costs, which is the usual reason a loop that
simulated beautifully oscillates on the bench.
"""
from __future__ import annotations

import math
from typing import Dict, List, NamedTuple

import streamlit as st

from calculators import controls
from studios import shell
from utils import ui
from utils.formatting import format_number
from utils.plotting import ACCENT, MUTED, PRIMARY, new_figure, show
from utils.spec import Calculator

PREFIX = "studio_control"

SAMPLES_PER_BANDWIDTH = 10.0
"""Sample rate, as a multiple of the closed-loop bandwidth, below which a
digital controller stops behaving like the continuous design it came from.
Ten is the floor; twenty is the figure most people design to."""

COMFORTABLE_SAMPLES = 20.0
"""The upper end of the usual 10-20x rule, quoted so the margin has a target
rather than only a cliff."""

ZN_OVERSHOOT = 25.0
"""Overshoot Ziegler-Nichols aims at. The rules target quarter-amplitude decay,
which lands near 25% - so an overshoot budget tighter than this is asking ZN
for something it was never designed to give."""

OFFSET_FRACTION = 0.02
"""Residual error, as a fraction of the setpoint, used when asking what
proportional gain alone would cost. The same 2% as the settling band, so the
two numbers are answering the same question."""

SETPOINT = 1.0
INITIAL = 0.0
"""The simulated step is 0 to 1. Overshoot and settling time are both measured
against the size of the step, so the units cancel and any step of the same
shape gives the same numbers."""

DURATION_FACTOR = 3.0
"""Simulation window, as a multiple of the settling target. Long enough to show
a response that meets the target settling down, short enough that one that
misses it is visibly still moving when the window ends."""


# ---------------------------------------------------------------------------
# 1. What you want
# ---------------------------------------------------------------------------
class Target(NamedTuple):
    damping: float              # zeta the overshoot limit implies
    natural_frequency: float    # rad/s the settling target then implies
    bandwidth_hz: float         # omega_n / 2pi, the loop's bandwidth in Hz
    max_overshoot: float        # %, as specified
    settling_target: float      # s, as specified
    sample_rate: float          # Hz
    sample_ratio: float         # sample rate / bandwidth
    phase_lag: float            # degrees given away to sampling and delay


def target(max_overshoot_pct: float, settling_target_s: float,
           sample_rate_hz: float, extra_delay_ms: float = 0.0) -> Target:
    """The specification, read as a damping ratio and a natural frequency.

    Overshoot depends on zeta alone, so the overshoot limit fixes zeta with no
    reference to speed at all - that is `damping_for_overshoot`, which is
    `overshoot_percent` run backwards.

    Settling time is the only place speed enters: ts ~= 4 / (zeta * omega_n),
    so with zeta already decided the settling target fixes omega_n. That one
    line of algebra is `settling_time` run backwards, and the round trip is
    asserted by the tests rather than assumed.

    Bandwidth is taken as omega_n / 2pi. For a canonical second-order loop at
    zeta = 0.707 that is exactly the -3 dB bandwidth, and it is the convention
    the second-order page already uses when it talks about sample rates.
    """
    settling_target_s = float(settling_target_s)
    if settling_target_s <= 0:
        raise ValueError("Target settling time must be greater than zero.")

    damping = controls.damping_for_overshoot(max_overshoot_pct)
    natural_frequency = 4.0 / (damping * settling_target_s)
    bandwidth_hz = natural_frequency / (2.0 * math.pi)

    sample_rate_hz = float(sample_rate_hz)
    phase_lag = controls.sampling_phase_lag(bandwidth_hz, sample_rate_hz,
                                            extra_delay_ms)
    return Target(damping, natural_frequency, bandwidth_hz,
                  float(max_overshoot_pct), settling_target_s, sample_rate_hz,
                  sample_rate_hz / bandwidth_hz, phase_lag)


# ---------------------------------------------------------------------------
# 2. The response that implies
# ---------------------------------------------------------------------------
class Shape(NamedTuple):
    overshoot: float            # %
    peak_time: float            # s
    rise_time: float            # s, 0-100%
    damped_frequency: float     # rad/s - the frequency you see
    ringing_hz: float           # Hz
    cycles: float               # visible cycles before it settles
    settling_time: float        # s, back out of the natural frequency


def shape(spec: Target) -> Shape:
    """Every standard measure of the step the specification describes.

    Nothing here is new physics: the same five functions the second-order page
    calls, handed the zeta and omega_n that step 1 derived.
    """
    damped = controls.damped_frequency(spec.natural_frequency, spec.damping)
    return Shape(
        controls.overshoot_percent(spec.damping),
        controls.peak_time(spec.natural_frequency, spec.damping),
        controls.rise_time(spec.natural_frequency, spec.damping),
        damped,
        damped / (2.0 * math.pi),
        controls.ringing_cycles(spec.damping),
        controls.settling_time(spec.natural_frequency, spec.damping),
    )


# ---------------------------------------------------------------------------
# 3. Tuning
# ---------------------------------------------------------------------------
class Loop(NamedTuple):
    kp: float
    ki: float
    kd: float
    overshoot: float            # %, measured off the simulation
    rise_time: float            # s, 10-90% - NOT the same measure as Shape
    settling_time: float        # s, +/-2%
    final_error: float          # setpoint minus the last simulated value
    offset: float               # what Kp alone would leave uncorrected
    kp_for_offset: float        # Kp that would hold that offset to 2%
    t: object                   # time array, for the plot
    y: object                   # response array


def loop(kp: float, ki: float, kd: float, plant_gain: float,
         time_constant: float, duration: float, output_limit: float) -> Loop:
    """Run the PID simulator on a first-order plant and read the response.

    The measured numbers come from `response_metrics`, the same function the
    PID page prints, so the simulated column here and that page agree by
    construction.

    Two extra numbers say what the integral term is doing for its living:
    `proportional_offset` is the steady error this Kp would be stuck with if Ki
    were zero, and `gain_for_offset` is the Kp it would take to hold that error
    to 2% of the setpoint without any integral action at all.
    """
    t, y, _ = controls.simulate_pid(kp, ki, kd, SETPOINT, INITIAL, plant_gain,
                                    time_constant, duration, -output_limit,
                                    output_limit)
    metrics = controls.response_metrics(t, y, SETPOINT, INITIAL)
    return Loop(
        kp, ki, kd,
        metrics["overshoot_pct"], metrics["rise_time"],
        metrics["settling_time"],
        controls.control_error(SETPOINT, float(y[-1])),
        controls.proportional_offset(SETPOINT, kp, plant_gain),
        controls.gain_for_offset(OFFSET_FRACTION, abs(plant_gain)),
        t, y,
    )


# ---------------------------------------------------------------------------
# 4. The verdict
# ---------------------------------------------------------------------------
def _margin(limit: float, actual: float) -> float:
    """How many times over the limit something is. NaN where the simulation
    never produced the quantity at all, which reads as "—" rather than as a
    number that was measured."""
    if actual != actual:                      # NaN
        return float("nan")
    if actual <= 0:
        return float("inf")
    return limit / actual


def verdicts(spec: Target, result: Loop,
             ziegler: bool) -> List[Dict[str, object]]:
    """Every check this studio makes, with the margin that decided it.

    Overshoot and settling are judged on the SIMULATED response, not on the
    second-order prediction - the prediction was derived from the requirement
    and would pass itself by construction.
    """
    checks = [
        shell.check(
            "Overshoot",
            result.overshoot <= spec.max_overshoot,
            _margin(spec.max_overshoot, result.overshoot),
            f"the loop peaks {format_number(result.overshoot, 3)}% over, "
            f"against a {format_number(spec.max_overshoot, 3)}% limit"),
        shell.check(
            "Settling time",
            result.settling_time <= spec.settling_target,
            _margin(spec.settling_target, result.settling_time),
            f"settles in {format_number(result.settling_time, 3)} s, "
            f"against {format_number(spec.settling_target, 3)} s asked for"
            if result.settling_time == result.settling_time else
            "never settled inside ±2% before the window ended"),
        shell.check(
            "Sample rate",
            spec.sample_ratio >= SAMPLES_PER_BANDWIDTH,
            spec.sample_ratio / SAMPLES_PER_BANDWIDTH,
            f"{format_number(spec.sample_rate, 4)} Hz is "
            f"{format_number(spec.sample_ratio, 3)}× the "
            f"{format_number(spec.bandwidth_hz, 3)} Hz bandwidth and gives "
            f"away {format_number(spec.phase_lag, 3)}° of phase; wanted at "
            f"least {int(SAMPLES_PER_BANDWIDTH)}×, ideally "
            f"{int(COMFORTABLE_SAMPLES)}×"),
    ]
    if ziegler:
        checks.append(shell.check(
            "Ziegler–Nichols overshoot",
            spec.max_overshoot >= ZN_OVERSHOOT,
            spec.max_overshoot / ZN_OVERSHOOT,
            f"the rules aim at about {int(ZN_OVERSHOOT)}% overshoot and your "
            f"limit is {format_number(spec.max_overshoot, 3)}%, so expect to "
            f"detune rather than to ship these gains"))
    return checks


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def render(prefs=None, catalogue=None) -> None:
    prefs = prefs or {}
    ui.page_header(
        "Control tuning",
        r"\zeta = \frac{-\ln M_p}{\sqrt{\pi^{2} + \ln^{2} M_p}}, \qquad "
        r"\omega_n = \frac{4}{\zeta\, t_s}, \qquad "
        r"f_s \ge 10\,\frac{\omega_n}{2\pi}",
        "Start from what the response has to do - how far it may overshoot and "
        "how quickly it must settle - and work back to the damping, the speed "
        "and the gains that would deliver it. Then check the one thing a "
        "tuning table never mentions: whether the computer running the loop is "
        "sampling fast enough for any of it to still be true.",
        PREFIX)

    # -- 1 ------------------------------------------------------------------
    shell.step(1, "What you want",
               "The specification, and the rate the loop will run at.")
    a, b, c, d = st.columns(4)
    with a:
        max_overshoot = st.number_input(
            "Maximum overshoot [%]", value=10.0, min_value=0.1,
            max_value=99.0, step=1.0, key=f"{PREFIX}_os",
            help="How far past the target a step command may swing. This one "
                 "number fixes the damping ratio, with no reference to speed.")
    with b:
        settling_target = st.number_input(
            "Target settling time [s]", value=1.6, min_value=0.001, step=0.1,
            key=f"{PREFIX}_ts",
            help="Time to get inside ±2% of the target and stay there.")
    with c:
        sample_rate = st.number_input(
            "Loop sample rate [Hz]", value=50.0, min_value=0.1, step=10.0,
            key=f"{PREFIX}_fs",
            help="How often the controller actually runs on the hardware.")
    with d:
        extra_delay = st.number_input(
            "Extra loop delay [ms]", value=0.0, min_value=0.0, step=0.5,
            key=f"{PREFIX}_delay",
            help="Anything between the measurement and the actuator that the "
                 "sample period does not already cover: filter group delay, a "
                 "bus round trip, a smart actuator's own loop.")

    try:
        spec = target(max_overshoot, settling_target, sample_rate, extra_delay)
    except ValueError as exc:
        st.error(str(exc))
        return

    shell.figures([("Damping ratio ζ", spec.damping, "-"),
                   ("Natural frequency ωn", spec.natural_frequency, "rad/s"),
                   ("Closed-loop bandwidth", spec.bandwidth_hz, "Hz"),
                   ("Sample rate", spec.sample_ratio, "× bandwidth")])
    st.caption("Overshoot depends on damping alone, so the overshoot limit "
               "fixes ζ before speed is discussed at all. Settling time is "
               "where speed enters: with ζ decided, ts ≈ 4/(ζωn) is the only "
               "ωn that meets it.")

    # -- 2 ------------------------------------------------------------------
    shell.step(2, "The response that implies",
               "What a step command would look like if the loop behaved.")
    try:
        predicted = shape(spec)
    except ValueError as exc:
        st.error(str(exc))
        return

    shell.figures([("Overshoot", predicted.overshoot, "%"),
                   ("Peak at", predicted.peak_time, "s"),
                   ("Rise time (0-100%)", predicted.rise_time, "s"),
                   ("Ringing frequency", predicted.ringing_hz, "Hz"),
                   ("Cycles of ringing", predicted.cycles, "-")])
    st.caption(
        f"The ringing you would see is {format_number(predicted.ringing_hz, 3)}"
        f" Hz, not the {format_number(spec.bandwidth_hz, 3)} Hz bandwidth - "
        "damping slows the oscillation as well as shrinking it. "
        f"{format_number(predicted.cycles, 2)} cycles fit inside the settling "
        "time: under about half a cycle reads as a single overshoot, above "
        "three or four reads as a system that rings.")

    # -- 3 ------------------------------------------------------------------
    shell.step(3, "Tuning",
               "Gains, and a simulation of the same step to check them "
               "against.")
    source = st.radio("Where the gains come from",
                      ["Ziegler–Nichols", "Straight from you"],
                      horizontal=True, key=f"{PREFIX}_source")
    ziegler = source == "Ziegler–Nichols"

    if ziegler:
        st.warning(
            "**Ziegler–Nichols starts with a deliberate instability.** Ku is "
            "the proportional gain at which the loop oscillates steadily, and "
            "finding it means driving the plant into sustained oscillation on "
            "purpose. Do not do that on hardware that can hurt someone, "
            "damage itself, or lose something expensive - anything with a "
            "moving mass, stored energy, a heater, a person nearby. Get Ku "
            "from a model, from a relay test, or from a scaled-down rig. The "
            "classic rules are also aggressive: they target quarter-amplitude "
            "decay, roughly 25% overshoot, and halving Kp afterwards is normal "
            "practice rather than an admission of failure. What comes out "
            "below is a starting point to be tested and detuned, not an "
            "answer.")
        e, f, g = st.columns(3)
        with e:
            controller = st.selectbox("Controller", ["PID", "PI", "P"],
                                      key=f"{PREFIX}_ctrl")
        with f:
            ultimate_gain = st.number_input(
                "Ultimate gain Ku [-]", value=4.0, min_value=0.001, step=0.5,
                key=f"{PREFIX}_ku",
                help="Proportional gain at which the loop oscillates steadily "
                     "- neither growing nor dying away.")
        with g:
            ultimate_period = st.number_input(
                "Ultimate period Tu [s]", value=0.6, min_value=0.001,
                step=0.05, key=f"{PREFIX}_tu",
                help="Period of that sustained oscillation.")
        try:
            kp, ki, kd = controls.ziegler_nichols(ultimate_gain,
                                                  ultimate_period, controller)
        except ValueError as exc:
            st.error(str(exc))
            return
    else:
        e, f, g = st.columns(3)
        with e:
            kp = st.number_input("Proportional gain Kp [-]", value=2.4,
                                 step=0.1, key=f"{PREFIX}_kp")
        with f:
            ki = st.number_input("Integral gain Ki [1/s]", value=8.0, step=0.5,
                                 key=f"{PREFIX}_ki")
        with g:
            kd = st.number_input("Derivative gain Kd [s]", value=0.18,
                                 step=0.01, key=f"{PREFIX}_kd")

    h, i, j = st.columns(3)
    with h:
        plant_gain = st.number_input(
            "Plant gain K [-]", value=1.0, step=0.1, key=f"{PREFIX}_k",
            help="Steady output per unit of controller output, with the loop "
                 "open.")
    with i:
        time_constant = st.number_input(
            "Plant time constant τ [s]", value=0.5, min_value=0.001, step=0.1,
            key=f"{PREFIX}_tau",
            help="Time the open-loop plant takes to reach 63% of a step.")
    with j:
        output_limit = st.number_input(
            "Output limit (±) [-]", value=10.0, min_value=0.01, step=1.0,
            key=f"{PREFIX}_lim",
            help="Actuator saturation. The simulator stops accumulating "
                 "integral while it is clamped.")

    duration = DURATION_FACTOR * spec.settling_target
    try:
        result = loop(kp, ki, kd, plant_gain, time_constant, duration,
                      output_limit)
    except ValueError as exc:
        st.error(str(exc))
        return

    shell.figures([("Proportional Kp", result.kp, "-"),
                   ("Integral Ki", result.ki, "1/s"),
                   ("Derivative Kd", result.kd, "s")])
    shell.figures([("Overshoot, simulated", result.overshoot, "%"),
                   ("Rise time (10-90%)", result.rise_time, "s"),
                   ("Settling time, simulated", result.settling_time, "s"),
                   ("Error left at the end", result.final_error, "units")])

    fig, (ax,) = new_figure(height=2.8)
    ax.axhline(SETPOINT, color=MUTED, linestyle="--", linewidth=1.2,
               label="Setpoint")
    ax.axhline(SETPOINT * (1.0 + spec.max_overshoot / 100.0), color=ACCENT,
               linestyle=":", linewidth=1.2, label="Overshoot limit")
    ax.axvline(spec.settling_target, color=MUTED, linestyle=":", linewidth=1.2,
               label="Settling target")
    ax.plot(result.t, result.y, color=PRIMARY, linewidth=2,
            label="Simulated response")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Process value")
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    show(fig)

    st.caption(
        f"Predicted against simulated: {format_number(predicted.overshoot, 3)}"
        f"% overshoot and {format_number(spec.settling_target, 3)} s settling "
        f"from the second-order relations, "
        f"{format_number(result.overshoot, 3)}% and "
        f"{format_number(result.settling_time, 3)} s out of the simulator. "
        "They will not agree exactly and are not meant to - the prediction "
        "describes a canonical two-pole loop, the simulation is a PID "
        "controller on a one-pole plant. The two rise times are different "
        "measures as well: the prediction is 0-100%, the simulation 10-90%.")

    st.caption(
        f"What the integral term is worth here: at Kp = "
        f"{format_number(result.kp, 3)} with Ki set to zero, the loop would "
        f"sit {format_number(result.offset, 3)} units short of a "
        f"{format_number(SETPOINT, 2)}-unit setpoint and stay there. Holding "
        f"that offset to {int(OFFSET_FRACTION * 100)}% with proportional "
        f"action alone would need Kp = "
        f"{format_number(result.kp_for_offset, 4)} - which is how chasing "
        "accuracy with gain runs into the stability limit long before it "
        "reaches the specification.")

    # -- 4 ------------------------------------------------------------------
    shell.step(4, "The verdict",
               "Whether the loop you just described meets what you asked for.")
    shell.verdict_board(verdicts(spec, result, ziegler))

    shell.send_to_project(PREFIX, [
        ("Damping ratio", spec.damping, "-"),
        ("Natural frequency", spec.natural_frequency, "rad/s"),
        ("Loop sample rate", spec.sample_rate, "Hz"),
        ("Proportional gain Kp", result.kp, "-"),
    ], note="from the control tuning studio")

    ui.assumptions([
        "The second-order metrics describe a CANONICAL second-order system: "
        "two poles, no zeros, unity DC gain. A real mechanism is not one. It "
        "has extra poles, structural modes, backlash and compliance, and a "
        "closed loop almost always has a zero somewhere - which increases "
        "overshoot, sometimes a lot, so these numbers then under-estimate it.",
        "No actuator saturation and no rate limit are modelled in the "
        "prediction, and this is the single biggest reason real loops behave "
        "worse than predicted. A loop that hits its limit on the way up spends "
        "the climb with no authority in reserve, arrives with too much speed "
        "and overshoots further than any linear formula says. The simulator "
        "does clamp its output, but a clamp is not a rate limit, a slew "
        "limit, or a motor that runs out of torque at speed.",
        "There is no disturbance and no sensor noise anywhere on this page. "
        "Both change the answer: disturbance rejection can want quite "
        "different gains from setpoint tracking, and noise is what stops you "
        "using the derivative gain the step response would like.",
        "Settling time is 4/(ζωn), an envelope approximation good to perhaps "
        "10-20%. The exact value jumps as the last excursion crosses the ±2% "
        "band, so a measured settling time moves in steps where this formula "
        "is smooth.",
        "Bandwidth is taken as ωn/2π. That is exact for a canonical loop at "
        "ζ = 0.707 and approximate either side of it, so the sample-rate "
        "ratio is a guide rather than a measurement. If you have a measured "
        "closed-loop frequency response, believe that instead.",
        "The sample-rate check counts the zero-order hold as half a sample "
        "period of pure delay, plus whatever extra delay you entered. It says "
        "nothing about aliasing - a signal with energy above half the sample "
        "rate needs an analogue anti-alias filter, and that filter adds phase "
        "lag of its own that belongs in the extra-delay box.",
        "The simulation is NOT sampled. It integrates a continuous plant with "
        "a small fixed Euler step chosen from the plant time constant, so the "
        "sample rate you entered above does not affect the trace at all. That "
        "is deliberate - it is why the sample-rate check has to be a separate "
        "verdict - but it also means a large Kd relative to that internal "
        "step makes the trace ring at the step frequency, which is a "
        "numerical artefact rather than a prediction.",
        "The simulated plant is a first-order lag, τ·dy/dt = K·u − y. It has "
        "one pole, so it cannot overshoot on its own and every oscillation in "
        "the trace comes from the controller. Ziegler-Nichols also assumes a "
        "self-regulating process with one dominant lag; an integrating plant, "
        "which is most position loops, needs different rules entirely.",
        "Ku and Tu are measurements of YOUR plant, while the simulation runs "
        "the first-order lag above. Gains that came from one plant are being "
        "tested against another, so treat the simulated column as a sanity "
        "check on the gains, not as a prediction of your hardware.",
        "Everything here is a starting point for a controller that will be "
        "tuned on the real machine, with limits, a way to stop it, and "
        "nobody within reach of the moving parts.",
    ])


CALCULATORS = [
    Calculator(slug="studio.control_tuning", name="Control tuning", latex="",
               explanation="", render=render,
               keywords=("studio", "control", "tuning", "pid", "damping",
                         "overshoot", "settling", "sample rate", "bandwidth",
                         "ziegler", "nichols", "gains", "loop", "workflow")),
]
