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

from . import theme
from .formatting import format_number, set_thousands_separator
from .validation import ValidationError

DISCLAIMER = (
    "For education and preliminary engineering calculations. "
    "Critical designs must be independently verified."
)

def inject_css(prefs=None) -> None:
    """Called once per rerun from app.py. Styling lives in utils/theme.py."""
    prefs = prefs or {}
    set_thousands_separator(prefs.get("thousands_separator", True))
    theme.inject(prefs.get("appearance", "Follow system"),
                 prefs.get("motion", "Full"),
                 prefs.get("accent", "Blue"),
                 prefs.get("density", "Comfortable"))


def app_header(title: str, acronym: str, subtitle: str) -> None:
    """Name, what the name stands for, then what the app does."""
    st.markdown(f'<div class="a-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="a-spine">{acronym}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="a-sub">{subtitle}</div>', unsafe_allow_html=True)
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


def page_header(title: str, latex: str, explanation: str, prefix: str,
                favourite: bool = False) -> bool:
    """Draw the page header. Returns True if the favourite star was clicked."""
    left, star, right = st.columns([6, 0.8, 1.2], vertical_alignment="center")
    with left:
        st.markdown(f'<div class="a-calc-title">{title}</div>',
                    unsafe_allow_html=True)
    with star:
        starred = st.button(
            "★" if favourite else "☆", key=f"fav::{prefix}",
            help="Remove from favourites" if favourite
            else "Add to favourites - pins it to the top of the sidebar",
            use_container_width=True)
    with right:
        reset_button(prefix)
    st.latex(latex)
    st.markdown(f'<div class="a-note">{explanation}</div>', unsafe_allow_html=True)
    # No "Inputs" heading: a row of labelled fields needs no announcing, and
    # one less label per page is one less thing between the user and the work.
    st.write("")
    return starred


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
    parts = ['<div class="a-result">',
             f'<div class="a-result-label">{label}</div>',
             f'<div class="a-result-value">{format_number(value, sig)}'
             f'<span class="a-result-unit">{unit}</span></div>']
    if secondary:
        items = "".join(
            f'<div><div class="a-sec-k">{name}</div>'
            f'<div class="a-sec-v">{format_number(val, sig)}'
            f'<span class="a-sec-u"> {sunit}</span></div></div>'
            for name, val, sunit in secondary
        )
        parts.append(f'<div class="a-sec">{items}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def error(exc: Exception) -> None:
    st.error(f"{exc}")


def assumptions(items) -> None:
    """Stated directly under the result - never hidden behind a click."""
    st.markdown('<div class="a-label">Assumptions</div>', unsafe_allow_html=True)
    bullets = "".join(f"<li>{item}</li>" for item in items)
    st.markdown(f'<ul class="a-tight">{bullets}</ul>', unsafe_allow_html=True)


def graph_toggle(prefix: str, label: str = "Show graph") -> bool:
    return st.checkbox(label, key=f"{prefix}_graph")


def reference(variables, example: str, show_example: bool = True) -> None:
    """Variable definitions and a real-world use, at the bottom of every page."""
    st.divider()
    if not show_example:
        st.markdown('<div class="a-label">Variables</div>',
                    unsafe_allow_html=True)
        rows = ["| Symbol | Meaning | Unit |", "| --- | --- | --- |"]
        rows += [f"| {sym} | {meaning} | {unit} |"
                 for sym, meaning, unit in variables]
        st.markdown("\n".join(rows))
        return
    left, right = st.columns([1.15, 1])
    with left:
        st.markdown('<div class="a-label">Variables</div>', unsafe_allow_html=True)
        rows = ["| Symbol | Meaning | Unit |", "| --- | --- | --- |"]
        rows += [f"| {sym} | {meaning} | {unit} |" for sym, meaning, unit in variables]
        st.markdown("\n".join(rows))
    with right:
        st.markdown('<div class="a-label">Where this is used</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="a-note">{example}</div>', unsafe_allow_html=True)


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
