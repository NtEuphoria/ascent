"""Turns a Calculator spec into a page.

This is the one place that decides how a calculator looks, so visual changes -
motion, theming, hover states, layout - happen here once instead of in 47
hand-written render functions.

Two implementation details matter and are easy to get wrong:

1. **The error slot is reserved, never conditionally inserted.** Streamlit keys
   elements without an id by their array index, so inserting an error message
   above the result would shift every sibling below it and remount them -
   replaying entrance animations and reloading any embedded frame. `st.empty()`
   holds the slot whether or not there is anything to say.

2. **Containers carry a `key`**, which Streamlit turns into a `.st-key-<key>`
   class name. That is the supported, stable hook for CSS - far safer than
   targeting internal `data-testid` attributes.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import streamlit as st

from . import ui
from .plotting import PRIMARY, mark_point, new_figure, show
from .spec import Calculator, Field, Inputs
from .validation import ValidationError

MAX_COLUMNS = 4


def _layout_rows(fields: List[Field]) -> List[List[Field]]:
    """Group inputs into rows of at most MAX_COLUMNS, keeping rows even."""
    if len(fields) <= MAX_COLUMNS:
        return [fields]
    rows, row_size = [], 3 if len(fields) % 3 == 0 else MAX_COLUMNS
    for start in range(0, len(fields), row_size):
        rows.append(fields[start:start + row_size])
    return rows


def _widget(field: Field, prefix: str) -> Any:
    """Draw one input and return its value."""
    key = f"{prefix}_{field.key}"
    if field.widget is not None:
        return field.widget(key, field)
    if field.kind == "weight":
        # Always returns newtons, and shows W = m x g on screen when the user
        # gives a mass. The one path by which weight enters any calculator.
        return ui.weight_inputs(key, default_mass=field.default,
                                label=field.label)
    if field.kind == "int":
        return ui.integer(f"{field.label} [{field.unit}]" if field.unit
                          else field.label, key, int(field.default),
                          min_value=int(field.min if field.min is not None else 1),
                          max_value=None if field.max is None else int(field.max),
                          help=field.help)
    if field.kind == "choice":
        return st.selectbox(field.label, list(field.options or []), key=key,
                            help=field.help)
    if field.kind == "slider":
        return st.slider(f"{field.label} [{field.unit}]" if field.unit
                         else field.label,
                         min_value=float(field.min if field.min is not None else 0),
                         max_value=float(field.max if field.max is not None else 100),
                         value=float(field.default),
                         step=float(field.step) if field.step else None,
                         key=key, help=field.help)
    return ui.number(field.label, field.unit, key, field.default,
                     min_value=field.min, max_value=field.max, step=field.step,
                     help=field.help)


def collect_inputs(calc: Calculator) -> Inputs:
    """Draw every input field and gather the values."""
    values: Dict[str, Any] = {}
    for row in _layout_rows(calc.inputs):
        columns = st.columns(len(row))
        for column, field in zip(columns, row):
            with column:
                values[field.key] = _widget(field, calc.prefix)
    return Inputs(values)


def _sweep_series(calc: Calculator, values: Inputs):
    """Recompute the result across a range of one input.

    Points that fail validation (a zero area, a negative speed) become NaN so
    the curve simply breaks there instead of the page erroring.
    """
    sweep = calc.graph
    current = float(values[sweep.over])
    high = max(current * sweep.hi_factor, sweep.hi_min or 0.0)
    if high <= 0:
        high = max(sweep.hi_min or 1.0, 1.0)
    if sweep.lo is not None:
        low = sweep.lo
    elif sweep.lo_factor is not None:
        low = max(current * sweep.lo_factor, 0.0)
    else:
        low = 0.0
    xs = np.linspace(low, high, 200)

    if sweep.fn is not None:
        return xs, np.asarray(sweep.fn(values, xs), dtype=float)

    base = values.as_dict()
    ys = np.empty_like(xs)
    for index, x in enumerate(xs):
        trial = dict(base)
        trial[sweep.over] = float(x)
        try:
            ys[index] = calc.compute(Inputs(trial))
        except (ValidationError, ZeroDivisionError, ValueError):
            ys[index] = np.nan
    return xs, ys


def _draw_graph(calc: Calculator, values: Inputs, result: float) -> None:
    sweep = calc.graph
    field = next((f for f in calc.inputs if f.key == sweep.over), None)
    xs, ys = _sweep_series(calc, values)

    fig, (ax,) = new_figure()
    ax.plot(xs, ys, color=PRIMARY, linewidth=2)
    current = float(values[sweep.over])
    if np.isfinite(result) and xs[0] <= current <= xs[-1]:
        mark_point(ax, current, result, "current")
    ax.set_xlabel(sweep.x_label or
                  (f"{field.label} [{field.unit}]" if field else sweep.over))
    ax.set_ylabel(sweep.y_label)
    if sweep.log_y:
        ax.set_yscale("log")
    ax.set_title(sweep.title, fontsize=10, loc="left")
    show(fig)


def render(calc: Calculator) -> None:
    """Draw a complete calculator page."""
    if calc.render is not None:          # imperative escape hatch
        calc.render()
        return

    ui.page_header(calc.name, calc.latex, calc.explanation, calc.prefix)
    values = collect_inputs(calc)

    # Reserved slots: these elements always exist, so nothing below them ever
    # shifts index and remounts. See the module docstring.
    error_slot = st.empty()
    result_slot = st.container(key=f"result_{calc.prefix}")
    note_slot = st.empty()

    result = None
    try:
        result = calc.compute(values)
    except ValidationError as exc:
        error_slot.error(str(exc))
    except ZeroDivisionError:
        error_slot.error("Division by zero - check the inputs above.")

    if result is not None:
        secondary = []
        for item in calc.secondary:
            try:
                secondary.append((item.label, item.fn(values, result), item.unit))
            except (ValidationError, ZeroDivisionError, ValueError):
                continue          # a supporting value is never worth an error
        with result_slot:
            ui.result(calc.result.label, result, calc.result.unit,
                      secondary=secondary, sig=calc.result.sig)
        if calc.note is not None:
            caption = calc.note(values, result)
            if caption:
                note_slot.caption(caption)

    ui.assumptions(calc.assumptions)

    if calc.graph is not None and ui.graph_toggle(calc.prefix):
        if result is not None:
            _draw_graph(calc, values, result)

    ui.reference(calc.variables, calc.example)
