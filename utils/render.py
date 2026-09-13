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

import inspect
from typing import Any, Dict, List

import numpy as np
import streamlit as st

from . import analysis, charts, navigate, project as project_store
from . import settings, ui
from .formatting import format_number
from .spec import Calculator, Field, Inputs, Sweep
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


def _widget(field: Field, prefix: str, bound=None) -> Any:
    """Draw one input and return its value.

    A field bound to a project parameter is shown as a read-only figure rather
    than a disabled box with a value in it. Letting it be edited locally would
    reintroduce exactly the divergence the project exists to prevent - four
    pages quietly carrying four different masses.
    """
    key = f"{prefix}_{field.key}"
    if bound is not None:
        unit = f" {field.unit}" if field.unit else ""
        st.markdown(
            f'<div class="a-bound">'
            f'<div class="a-bound-k">{field.label}{unit}</div>'
            f'<div class="a-bound-v">{format_number(bound.value, 6)}'
            f'<span>{bound.source.lower()}</span></div>'
            f'<div class="a-bound-src">from project · {bound.label}</div>'
            f'</div>', unsafe_allow_html=True)
        return bound.value
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


def collect_inputs(calc: Calculator, project=None) -> Inputs:
    """Draw every input field and gather the values."""
    project = project if project is not None else {"parameters": {},
                                                   "bindings": {}}
    values: Dict[str, Any] = {}
    for row in _layout_rows(calc.inputs):
        columns = st.columns(len(row))
        for column, field in zip(columns, row):
            with column:
                bound = project_store.bound_value(project, calc.slug, field.key)
                values[field.key] = _widget(field, calc.prefix, bound)
    return Inputs(values)


def _sweep_series(calc: Calculator, values: Inputs, sweep: Sweep):
    """Recompute the result across a range of one input.

    Points that fail validation (a zero area, a negative speed) become NaN so
    the curve simply breaks there instead of the page erroring.
    """
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


def _draw_graph(calc: Calculator, values: Inputs, result: float, sweep: Sweep,
                index: int = 0, appearance: str = "Follow system") -> None:
    field = next((f for f in calc.inputs if f.key == sweep.over), None)
    xs, ys = _sweep_series(calc, values, sweep)
    current = float(values[sweep.over])
    in_range = bool(np.isfinite(result) and xs[0] <= current <= xs[-1])
    charts.sweep_chart(
        xs, ys,
        x_label=sweep.x_label or (f"{field.label} [{field.unit}]"
                                  if field else sweep.over),
        y_label=sweep.y_label,
        title=sweep.title,
        point_x=current if in_range else None,
        point_y=result if in_range else None,
        log_y=sweep.log_y,
        appearance=appearance,
    )
    _download_series(calc, sweep, field, xs, ys, index)


def _download_series(calc: Calculator, sweep: Sweep, field, xs, ys,
                     index: int) -> None:
    """Offer the plotted points as CSV.

    A curve you can only look at is a picture; a curve you can export is data.
    Built as text rather than through pandas so the column headers carry the
    units exactly as the axis does.
    """
    x_name = sweep.x_label or (f"{field.label} [{field.unit}]" if field
                               else sweep.over)
    rows = [f"{x_name},{sweep.y_label}"]
    rows += [f"{x:.10g},{'' if not np.isfinite(y) else format(y, '.10g')}"
             for x, y in zip(xs, ys)]
    st.download_button(
        "Download these points (CSV)",
        data="\n".join(rows).encode("utf-8"),
        file_name=f"{calc.slug.replace('.', '-')}-{sweep.over}.csv",
        mime="text/csv",
        key=f"dl_{calc.prefix}_{index}_{sweep.over}",
    )


def _copy_block(calc: Calculator, values: Inputs, result: float,
                secondary, significant: int) -> None:
    """A plain-text summary of the calculation, ready to paste.

    Streamlit has no clipboard API, but `st.code` renders with a copy button -
    so the honest way to offer "copy this result" is to show exactly the text
    that will be copied.
    """
    lines = [f"{calc.name}"]
    for field in calc.inputs:
        raw = values.as_dict().get(field.key)
        if isinstance(raw, (int, float)):
            unit = f" {field.unit}" if field.unit else ""
            lines.append(f"  {field.label} = {format_number(raw, 6)}{unit}")
        elif raw is not None:
            lines.append(f"  {field.label} = {raw}")
    lines.append(f"{calc.result.label} = "
                 f"{format_number(result, significant)} {calc.result.unit}")
    for label, value, unit in secondary:
        lines.append(f"  {label} = {format_number(value, significant)} {unit}")
    lines.append("")
    lines.append("Computed with ASCENT - verify critical designs independently.")

    with st.popover("Copy this calculation", use_container_width=False):
        st.code("\n".join(lines), language=None)




# ---------------------------------------------------------------------------
# The analysis area: everything derived from the result rather than shown with
# it. Kept below the assumptions, which stay visible on every page.
# ---------------------------------------------------------------------------
_LEVELS = {"info": st.info, "warning": st.warning, "danger": st.error}


def _uncertainty_panel(calc: Calculator, values: Inputs, result: float,
                       spread) -> None:
    """Where the uncertainty on this answer comes from.

    The contributions are the useful half. A band on its own says the answer
    is soft; the breakdown says which single measurement is making it soft,
    which is the difference between knowing you have a problem and knowing
    what to do about it.
    """
    low, high = spread.band(result)
    relative = spread.relative(result)
    unit = calc.result.unit
    st.markdown(
        f'<div class="a-band">'
        f'<div class="a-band-k">{calc.result.label}, with the uncertainty on '
        f'its inputs carried through</div>'
        f'<div class="a-band-v">{format_number(result, 4)}'
        f'<span>± {format_number(spread.sigma, 3)} {unit}</span></div>'
        f'<div class="a-band-r">between {format_number(low, 4)} and '
        f'{format_number(high, 4)} {unit}'
        + (f'  ·  ± {relative * 100:.1f}%' if relative is not None else "")
        + '</div></div>', unsafe_allow_html=True)

    rows = ["| Input | Its ± | Contributes | Share of the doubt |",
            "| --- | --- | --- | --- |"]
    for item in spread.contributions:
        rows.append(
            f"| {item.label} | ± {format_number(item.input_sigma, 3)} "
            f"{item.unit} | ± {format_number(item.result_sigma, 3)} {unit} | "
            f"{item.share * 100:.0f}% |")
    st.markdown("\n".join(rows))

    worst = spread.contributions[0]
    st.caption(
        f"{worst.label} accounts for {worst.share * 100:.0f}% of it. "
        "Narrowing that one input is worth more than narrowing all the others "
        "put together." if worst.share > 0.5 else
        f"The doubt is spread across {len(spread.contributions)} inputs, so no "
        "single measurement will tighten it much on its own.")
    st.caption("Terms are added in quadrature, not linearly, because "
               "independent errors partly cancel rather than all going the "
               "same way at once. That assumes the inputs are independent of "
               "each other and that the equation is near enough to straight "
               "across the width of each ±.")


def _influence_table(calc: Calculator, values: Inputs, result: float) -> None:
    """Which input actually drives this number, measured rather than asserted.

    Drawn as real bars rather than a column of block characters in a markdown
    table. The bar is the comparison - it is the whole reason the elasticities
    are worth ranking - and a row of U+2588 in a monospace cell quantises it to
    twelve steps and inherits the table's own alignment.
    """
    ranked = analysis.influences(calc, values, result)
    usable = [item for item in ranked if item.usable]
    if not usable:
        st.caption("No influence can be measured at this operating point - "
                   "an input or the result is zero here.")
        return

    st.markdown(
        '<div class="a-note">Each row is the percentage change in the result '
        'for a one percent change in that input, measured by nudging the input '
        'and recomputing. For a power law it is exactly the exponent, so a '
        'value of 2.00 means the result goes as the square of that input.</div>',
        unsafe_allow_html=True)

    strongest = abs(usable[0].elasticity)
    rows = []
    for position, item in enumerate(ranked):
        # Stagger down the list so the ranking reads in order rather than
        # arriving all at once. Capped so a page with many inputs does not
        # turn its most useful table into a wait.
        delay = f"{min(position, 7) * 45}ms"
        if not item.usable:
            rows.append(
                f'<li class="a-inf a-inf-off" style="--d:{delay}">'
                f'<span class="a-inf-k">{item.label}</span>'
                f'<span class="a-inf-v">not measurable</span>'
                f'<span class="a-inf-bar"></span>'
                f'<span class="a-inf-why">{item.reason}</span></li>')
            continue
        share = abs(item.elasticity) / strongest if strongest else 0.0
        sign = "+" if item.elasticity >= 0 else "\u2212"
        # A negative elasticity is not a smaller positive one - it moves the
        # result the other way - so it gets its own colour rather than a
        # shorter bar.
        direction = "up" if item.elasticity >= 0 else "down"
        rows.append(
            f'<li class="a-inf" style="--d:{delay};--w:{share * 100:.1f}%">'
            f'<span class="a-inf-k">{item.label}</span>'
            f'<span class="a-inf-v">{sign}{abs(item.elasticity):.2f}%</span>'
            f'<span class="a-inf-bar a-inf-{direction}"><i></i></span>'
            f'<span class="a-inf-why">per +1% change</span></li>')

    st.markdown(f'<ul class="a-inf-list">{"".join(rows)}</ul>',
                unsafe_allow_html=True)
    st.caption(analysis.describe(usable[0]) + "  That makes "
               f"{usable[0].label} the input worth getting right first.")


def _related(calc: Calculator, catalogue) -> None:
    """One-click jumps to the calculators this one leads to."""
    entries = [catalogue[slug] for slug in calc.related if slug in catalogue]
    if not entries:
        st.caption("No linked calculators yet.")
        return
    st.markdown('<div class="a-note">These answer the question this page '
                'raises next.</div>', unsafe_allow_html=True)
    per_row = 3
    for start in range(0, len(entries), per_row):
        chunk = entries[start:start + per_row]
        # Always ask for a full row of columns so a trailing pair does not
        # stretch to half the page each.
        for column, (category, other) in zip(st.columns(per_row), chunk):
            with column:
                if st.button(f"{other.name}  ·  {category}",
                             key=f"rel_{calc.prefix}_{other.slug}",
                             use_container_width=True):
                    navigate.request(other.slug)
                    st.rerun()


def _analysis(calc: Calculator, values: Inputs, result, catalogue,
              prefs: dict, project: dict) -> None:
    """Graphs, influence, reference data and links, in one tabbed block.

    Tabs rather than a stack because these are alternatives, not a sequence:
    you come here with one question, not four. The tab set is fixed by the
    spec, so it never changes shape as you type.
    """
    labels, drawers = [], []

    for index, sweep in enumerate(calc.graphs):
        labels.append(sweep.title.split(" (")[0][:34])
        drawers.append(("graph", (sweep, index)))
    spread = None
    if calc.compute is not None and result is not None:
        sigmas = project_store.uncertainties_for(project, calc)
        if sigmas:
            spread = analysis.uncertainty(calc, values, result, sigmas)
            if not spread.known:
                spread = None
    if spread is not None:
        labels.append("How sure is this")
        drawers.append(("uncertainty", spread))
    if calc.sensitivity and calc.compute is not None:
        labels.append("What drives this")
        drawers.append(("influence", None))
    for table in calc.references:
        labels.append(table.title[:34])
        drawers.append(("reference", table))
    if calc.related:
        labels.append("Related")
        drawers.append(("related", None))
    if not labels:
        return

    st.markdown('<div class="a-label">Explore</div>', unsafe_allow_html=True)
    for tab, (kind, payload) in zip(st.tabs(labels), drawers):
        with tab:
            if kind == "graph":
                if result is None:
                    st.caption("Fix the inputs above to draw this.")
                else:
                    _draw_graph(calc, values, result, payload[0], payload[1],
                                prefs.get("appearance", "Follow system"))
            elif kind == "uncertainty":
                _uncertainty_panel(calc, values, result, payload)
            elif kind == "influence":
                if result is None:
                    st.caption("Fix the inputs above to measure this.")
                else:
                    _influence_table(calc, values, result)
            elif kind == "reference":
                _reference_table(payload)
            else:
                _related(calc, catalogue)


def _reference_table(table) -> None:
    header = "| " + " | ".join(table.columns) + " |"
    divider = "| " + " | ".join("---" for _ in table.columns) + " |"
    body = ["| " + " | ".join(str(cell) for cell in row) for row in table.rows]
    body = [row + " |" for row in body]
    st.markdown("\n".join([header, divider] + body))
    if table.note:
        st.caption(table.note)


def _call_render(fn, prefs: dict, catalogue: dict) -> None:
    """Call an imperative page, passing only what it asks for.

    Most of these pages predate the renderer having anything to hand them and
    take no arguments at all. Inspecting the signature lets the live pages -
    which genuinely need preferences and the catalogue - opt in without a
    sweeping edit to every page that does not.
    """
    parameters = inspect.signature(fn).parameters
    kwargs = {}
    if "prefs" in parameters:
        kwargs["prefs"] = prefs
    if "catalogue" in parameters:
        kwargs["catalogue"] = catalogue
    fn(**kwargs)


def render(calc: Calculator, prefs=None, catalogue=None) -> None:
    """Draw a complete calculator page."""
    prefs = prefs or {}
    if calc.render is not None:          # imperative escape hatch
        _call_render(calc.render, prefs, catalogue or {})
        return

    # The header is outside the fragment: it is static for a given calculator,
    # and Reset deliberately triggers a full rerun so every widget rebuilds.
    starred = ui.page_header(calc.name, calc.latex, calc.explanation,
                             calc.prefix,
                             favourite=calc.slug in prefs.get("favourites", []))
    if starred:
        settings.toggle_favourite(calc.slug)
        st.rerun()
    _render_body(calc, prefs, catalogue or {})


def _link_panel(calc: Calculator, project: dict) -> None:
    """Link this page's inputs to project parameters.

    One collapsed control rather than a widget beside every field: on a page
    with five inputs the per-field version triples the chrome, and linking is
    something done once per project, not once per visit.
    """
    numeric = [f for f in calc.inputs
               if f.kind in ("float", "int", "slider") and
               project_store.compatible(project, f.unit)]
    linked = sum(1 for f in calc.inputs
                 if project_store.bound_value(project, calc.slug, f.key))
    if not numeric and not linked:
        return

    label = (f"Project  ·  {linked} linked" if linked
             else f"Project  ·  {len(numeric)} can be linked")
    with st.popover(label, use_container_width=False):
        st.markdown('<div class="a-note">A linked input takes its value from '
                    'the project and cannot be edited here, so the same '
                    'quantity cannot drift apart across pages.</div>',
                    unsafe_allow_html=True)
        # In a form, so several inputs can be linked in one go - a popover
        # closes on every rerun, so a selectbox that applied immediately would
        # shut the panel after each single change.
        with st.form(f"link_{calc.prefix}", border=False):
            changed = _link_fields(calc, project)
            if st.form_submit_button("Apply", type="primary") and changed:
                project_store.save(project)
                st.rerun()


def _link_fields(calc: Calculator, project: dict) -> bool:
    changed = False
    if True:
        for spec_field in calc.inputs:
            options = project_store.compatible(project, spec_field.unit)
            current = project_store.bound_value(project, calc.slug,
                                                spec_field.key)
            if not options and not current:
                continue
            names = ["Not linked"] + [p.label for p in options]
            index = (names.index(current.label)
                     if current and current.label in names else 0)
            chosen = st.selectbox(
                f"{spec_field.label} [{spec_field.unit}]" if spec_field.unit
                else spec_field.label,
                names, index=index,
                key=f"bind_{calc.prefix}_{spec_field.key}")
            wanted = next((p.key for p in options if p.label == chosen), None)
            if (current.key if current else None) != wanted:
                project_store.bind(project, calc.slug, spec_field.key, wanted)
                changed = True
    return changed


@st.fragment
def _render_body(calc: Calculator, prefs: dict, catalogue: dict) -> None:
    """Inputs, result and graph - the part that reruns as you type.

    Without this, changing one number reruns the whole script: sidebar, every
    category group, the header, everything. Streamlit also dims the entire page
    to 33% opacity once a rerun passes 500ms, which reads as a flicker.

    Inside a fragment only these elements re-execute and only these can go
    stale, which is what keeps an edit under the ~400ms that feels instant.
    """
    project = project_store.load()
    _link_panel(calc, project)
    values = collect_inputs(calc, project)

    # Reserved slots: these elements always exist, so nothing below them ever
    # shifts index and remounts. See the module docstring.
    error_slot = st.empty()
    result_slot = st.container(key=f"result_{calc.prefix}")
    note_slot = st.empty()
    check_slots = [st.empty() for _ in calc.checks]

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
        significant = prefs.get("significant_figures", calc.result.sig)
        with result_slot:
            ui.result(calc.result.label, result, calc.result.unit,
                      secondary=secondary, sig=significant)
        if calc.note is not None:
            caption = calc.note(values, result)
            if caption:
                note_slot.caption(caption)

    for check, slot in zip(calc.checks, check_slots):
        verdict = None
        if result is not None:
            try:
                verdict = check.fn(values, result)
            except (ValidationError, ZeroDivisionError, ValueError):
                verdict = None
        if verdict:
            level, message = verdict
            with slot:
                _LEVELS.get(level, st.info)(message)

    if result is not None:
        _copy_block(calc, values, result, secondary, significant)

    ui.assumptions(calc.assumptions)
    _analysis(calc, values, result, catalogue, prefs, project)

    if prefs.get("show_reference", True):
        ui.reference(calc.variables, calc.example,
                     show_example=prefs.get("show_examples", True))
