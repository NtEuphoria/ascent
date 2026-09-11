"""Shared UI building blocks.

Every calculator page is assembled from these helpers, so all pages look and
behave identically and a new equation only has to supply content, not layout.

Page recipe (see calculators/aerodynamics.py for a worked example):

    ui.page_header(title, latex, explanation, prefix)   # 1, 2, 3 + Reset
    ...ui.number(...) inputs...                         # 4 (labelled with units)
    ui.result(label, value, unit, secondary=[...])      # 5, 6
    ui.assumptions([...])                               # 8
    if ui.graph_toggle(prefix): ...                     # optional graph
    ui.reference(variables=[...], example="...")        # 3, 9
"""
from __future__ import annotations

import math

import streamlit as st

from .formatting import format_number
from .validation import ValidationError

DISCLAIMER = (
    "For education and preliminary engineering calculations. "
    "Critical designs must be independently verified."
)

_CSS = """
<style>
.block-container {max-width: 1150px; padding-top: 2.4rem; padding-bottom: 5rem;}
h1, h2, h3 {letter-spacing: -0.01em;}
.app-title {font-size: 1.9rem; font-weight: 700; letter-spacing: 0.08em;
  margin: 0 0 0.1rem 0; color: #1f4e79;}
.app-spine {font-size: 0.7rem; font-weight: 600; letter-spacing: 0.1em;
  text-transform: uppercase; opacity: 0.55; margin: 0 0 0.45rem 0;}
.app-sub {font-size: 0.92rem; opacity: 0.7; margin: 0 0 0.2rem 0; line-height: 1.45;}
.calc-title {font-size: 1.25rem; font-weight: 620; margin: 0;}
.result-card {border: 1px solid rgba(31,78,121,0.22); border-left: 4px solid #1f4e79;
  border-radius: 8px; padding: 0.85rem 1.15rem 0.95rem 1.15rem;
  background: rgba(31,78,121,0.045); margin: 0.2rem 0 0.4rem 0;}
.result-label {font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.09em;
  opacity: 0.62; font-weight: 600;}
.result-value {font-size: 2.35rem; font-weight: 620; line-height: 1.2;
  font-variant-numeric: tabular-nums; margin-top: 0.1rem;}
.result-unit {font-size: 1.05rem; font-weight: 500; opacity: 0.65; margin-left: 0.4rem;}
.sec-row {display: flex; flex-wrap: wrap; gap: 1.6rem; margin-top: 0.75rem;
  padding-top: 0.7rem; border-top: 1px solid rgba(31,78,121,0.15);}
.sec-k {font-size: 0.74rem; opacity: 0.62; letter-spacing: 0.02em;}
.sec-v {font-size: 1.02rem; font-weight: 580; font-variant-numeric: tabular-nums;}
.sec-u {font-size: 0.85rem; font-weight: 400; opacity: 0.65;}
.small-head {font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.09em;
  opacity: 0.58; font-weight: 600; margin: 1.15rem 0 0.35rem 0;}
ul.tight {margin: 0.1rem 0 0 0; padding-left: 1.1rem; font-size: 0.88rem;
  opacity: 0.85; line-height: 1.6;}
.note {font-size: 0.88rem; opacity: 0.85; line-height: 1.6;}
div[data-testid="stMetricValue"] {font-variant-numeric: tabular-nums;}
</style>
"""


def inject_css() -> None:
    """Called once per rerun from app.py."""
    st.markdown(_CSS, unsafe_allow_html=True)


def app_header(title: str, acronym: str, subtitle: str) -> None:
    """Name, what the name stands for, then what the app does."""
    st.markdown(f'<div class="app-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="app-spine">{acronym}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="app-sub">{subtitle}</div>', unsafe_allow_html=True)
    st.divider()


# --------------------------------------------------------------------------
# Page scaffolding
# --------------------------------------------------------------------------
def reset_button(prefix: str) -> None:
    """Clear every widget value belonging to this calculator.

    Deleting the session-state keys makes Streamlit fall back to each widget's
    declared default on the next run, so defaults live in exactly one place.
    """
    if st.button("Reset", key=f"reset::{prefix}", help="Restore default values",
                 use_container_width=True):
        for key in [k for k in st.session_state.keys() if k.startswith(f"{prefix}_")]:
            del st.session_state[key]
        st.rerun()


def page_header(title: str, latex: str, explanation: str, prefix: str) -> None:
    left, right = st.columns([6, 1], vertical_alignment="center")
    with left:
        st.markdown(f'<div class="calc-title">{title}</div>', unsafe_allow_html=True)
    with right:
        reset_button(prefix)
    st.latex(latex)
    st.markdown(f'<div class="note">{explanation}</div>', unsafe_allow_html=True)
    st.markdown('<div class="small-head">Inputs</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
def _auto_step(value: float) -> float:
    magnitude = abs(float(value))
    if magnitude == 0:
        return 1.0
    return float(10 ** (math.floor(math.log10(magnitude)) - 1))


def number(label: str, unit: str, key: str, value: float, min_value=None,
           max_value=None, step=None, help=None, fmt: str = "%.6g") -> float:
    """A float input with its unit shown in the label."""
    return st.number_input(
        f"{label} [{unit}]" if unit else label,
        value=float(value),
        min_value=None if min_value is None else float(min_value),
        max_value=None if max_value is None else float(max_value),
        step=float(step) if step is not None else _auto_step(value),
        format=fmt,
        key=key,
        help=help,
    )


def integer(label: str, key: str, value: int, min_value: int = 1,
            max_value=None, help=None) -> int:
    """A whole-number input (motor counts, gear teeth, resistor counts)."""
    return int(st.number_input(
        label,
        value=int(value),
        min_value=int(min_value),
        max_value=None if max_value is None else int(max_value),
        step=1,
        format="%d",
        key=key,
        help=help,
    ))


def choice(label: str, options, key: str, index: int = 0, horizontal: bool = True,
           help=None):
    return st.radio(label, options, index=index, key=key, horizontal=horizontal,
                    help=help)


def weight_inputs(prefix: str, default_mass: float = 12.0,
                  label: str = "Aircraft") -> float:
    """Mass-or-weight input that never mixes the two.

    Returns weight in newtons. If the user gives a mass, weight is computed as
    W = m * g0 and the conversion is shown, so the distinction stays visible.
    """
    from .constants import G0

    mode = st.radio(
        f"{label} input",
        ["Mass (kg)", "Weight (N)"],
        key=f"{prefix}_wmode",
        horizontal=True,
        help="Mass is an amount of matter (kg). Weight is the gravitational "
             "force on that mass (N). W = m × g, with g = 9.80665 m/s².",
    )
    if mode == "Mass (kg)":
        mass = number(f"{label} mass m", "kg", f"{prefix}_mass", default_mass,
                      min_value=0.0)
        weight = mass * G0
        st.caption(f"Weight W = m × g = {format_number(mass)} × 9.80665 = "
                   f"{format_number(weight)} N")
        return weight
    return number(f"{label} weight W", "N", f"{prefix}_weight",
                  default_mass * G0, min_value=0.0)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def result(label: str, value: float, unit: str, secondary=None, sig: int = 4) -> None:
    """The single large headline number, with optional supporting values."""
    parts = ['<div class="result-card">',
             f'<div class="result-label">{label}</div>',
             f'<div class="result-value">{format_number(value, sig)}'
             f'<span class="result-unit">{unit}</span></div>']
    if secondary:
        items = "".join(
            f'<div><div class="sec-k">{name}</div>'
            f'<div class="sec-v">{format_number(val, sig)}'
            f'<span class="sec-u"> {sunit}</span></div></div>'
            for name, val, sunit in secondary
        )
        parts.append(f'<div class="sec-row">{items}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def error(exc: Exception) -> None:
    st.error(f"{exc}")


def assumptions(items) -> None:
    """Stated directly under the result - never hidden behind a click."""
    st.markdown('<div class="small-head">Assumptions</div>', unsafe_allow_html=True)
    bullets = "".join(f"<li>{item}</li>" for item in items)
    st.markdown(f'<ul class="tight">{bullets}</ul>', unsafe_allow_html=True)


def graph_toggle(prefix: str, label: str = "Show graph") -> bool:
    return st.checkbox(label, key=f"{prefix}_graph")


def reference(variables, example: str) -> None:
    """Variable definitions and a real-world use, at the bottom of every page."""
    st.divider()
    left, right = st.columns([1.15, 1])
    with left:
        st.markdown('<div class="small-head">Variables</div>', unsafe_allow_html=True)
        rows = ["| Symbol | Meaning | Unit |", "| --- | --- | --- |"]
        rows += [f"| {sym} | {meaning} | {unit} |" for sym, meaning, unit in variables]
        st.markdown("\n".join(rows))
    with right:
        st.markdown('<div class="small-head">Where this is used</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="note">{example}</div>', unsafe_allow_html=True)


def compute(fn):
    """Run a calculation, showing a clear message instead of a bad number.

    Returns None when the inputs are invalid, so the caller can skip the
    result block while still rendering the educational content.
    """
    try:
        return fn()
    except ValidationError as exc:
        error(exc)
    except ZeroDivisionError:
        error(ValidationError("Division by zero - check the inputs above."))
    return None
