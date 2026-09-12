"""The project: shared parameters and a requirements board.

This is the page that turns a set of calculators into a design study. It is
imperative rather than declarative because it is not an equation - there is no
single headline number, and the content is a table the user edits.
"""
from __future__ import annotations

import streamlit as st

from utils import project as store
from utils import ui
from utils.formatting import format_number
from utils.spec import Calculator

_BADGE = {
    store.MET: ("a-ok", "Meets"),
    store.NOT_MET: ("a-bad", "Does not meet"),
    store.NOT_EVALUATED: ("a-unknown", "Not evaluated"),
    store.OUTSIDE_MODEL: ("a-warn", "Outside model"),
}


def _parameters(project, catalogue) -> None:
    st.markdown('<div class="a-label">Shared parameters</div>',
                unsafe_allow_html=True)
    params = store.parameters(project)

    if not params:
        st.markdown(
            '<div class="a-note">Nothing defined yet. A parameter is a value '
            'you use in more than one place - a vehicle mass, a supply '
            'voltage, a wing area. Define it once here and link it on any '
            'calculator page, and the same quantity can never quietly differ '
            'between two of them.</div>', unsafe_allow_html=True)

    for param in params:
        uses = store.usage(project, param.key)
        row = st.container(key=f"param_{param.key}")
        with row:
            left, middle, right = st.columns([3, 2, 1],
                                             vertical_alignment="center")
            with left:
                st.markdown(
                    f'<div class="a-param-k">{param.label}</div>'
                    f'<div class="a-param-src">{param.source.lower()}'
                    f'{" · " + param.note if param.note else ""}</div>',
                    unsafe_allow_html=True)
            with middle:
                st.markdown(
                    f'<div class="a-param-v">{format_number(param.value, 6)}'
                    f'<span>{param.unit}</span></div>'
                    f'<div class="a-param-src">'
                    f'{_usage_text(uses, catalogue)}</div>',
                    unsafe_allow_html=True)
            with right:
                if st.button("Remove", key=f"del_{param.key}",
                             use_container_width=True):
                    store.remove_parameter(project, param.key)
                    store.save(project)
                    st.rerun()

    # A form, not loose widgets. A Streamlit popover closes on every rerun and
    # a text input reruns the moment it is committed, so loose fields shut the
    # popover before the submit button could ever be reached. A form batches
    # them and reruns once, on submit.
    with st.popover("Add a parameter", use_container_width=False):
        with st.form("new_parameter", clear_on_submit=True, border=False):
            label = st.text_input("Name", placeholder="Vehicle mass")
            value_col, unit_col = st.columns(2)
            with value_col:
                value = st.number_input("Value", value=1.0, format="%.6g")
            with unit_col:
                unit = st.text_input(
                    "Unit", placeholder="kg",
                    help="Must match the unit shown on the calculator input "
                         "you want to link it to, exactly as written there.")
            source = st.selectbox(
                "Where this came from", store.SOURCES,
                help="Kept with the value, because a measured number and a "
                     "guessed one are not the same input even when they are "
                     "the same digits.")
            note = st.text_input("Note", placeholder="optional")
            if st.form_submit_button("Add", type="primary"):
                if not label.strip():
                    st.warning("Give it a name.")
                else:
                    store.add_parameter(project, label.strip(), value,
                                        unit.strip(), source, note.strip())
                    store.save(project)
                    st.rerun()


def _usage_text(uses, catalogue) -> str:
    if not uses:
        return "not linked to anything yet"
    names = []
    for slug, _field in uses:
        entry = catalogue.get(slug)
        if entry:
            names.append(entry[1].name if isinstance(entry, tuple)
                         else entry.name)
    if not names:
        return "not linked to anything yet"
    unique = sorted(set(names))
    shown = ", ".join(unique[:3])
    return f"used by {shown}" + (f" and {len(unique) - 3} more"
                                 if len(unique) > 3 else "")


def _requirements(project, catalogue) -> None:
    st.markdown('<div class="a-label">Requirements</div>',
                unsafe_allow_html=True)
    reqs = store.requirements(project)

    if not reqs:
        st.markdown(
            '<div class="a-note">A requirement is what would make this design '
            'good enough: a mass ceiling, a stress limit, a minimum '
            'endurance. Each one is checked against a calculator every time '
            'you change a parameter.</div>', unsafe_allow_html=True)

    for requirement in reqs:
        verdict = store.evaluate(project, requirement, catalogue)
        style, text = _BADGE[verdict.status]
        entry = catalogue.get(requirement.slug)
        page = (entry[1].name if isinstance(entry, tuple) else "?") if entry \
            else "missing calculator"
        measured = (f"{format_number(verdict.value, 4)} {verdict.unit}"
                    if verdict.value is not None else "—")

        with st.container(key=f"req_{requirement.key}"):
            head, right = st.columns([5, 1], vertical_alignment="center")
            with head:
                st.markdown(
                    f'<div class="a-req">'
                    f'<span class="a-badge {style}">{text}</span>'
                    f'<span class="a-req-label">{requirement.label}</span>'
                    f'<span class="a-req-rule">{page} {requirement.op} '
                    f'{format_number(requirement.target, 6)}  ·  now '
                    f'{measured}</span></div>', unsafe_allow_html=True)
            with right:
                if st.button("Remove", key=f"delreq_{requirement.key}",
                             use_container_width=True):
                    store.remove_requirement(project, requirement.key)
                    store.save(project)
                    st.rerun()
            if verdict.unpinned:
                st.caption("Still using page defaults for: "
                           + ", ".join(verdict.unpinned)
                           + ". Link those to project parameters to get a "
                             "verdict.")
            elif verdict.detail and verdict.status != store.MET:
                st.caption(verdict.detail)

    targets = sorted(
        ((entry[1] if isinstance(entry, tuple) else entry) for entry
         in catalogue.values()),
        key=lambda c: c.name)
    targets = [c for c in targets if c.compute is not None and c.result]
    names = {f"{c.name}  ·  {c.result.label}": c.slug for c in targets}
    with st.popover("Add a requirement", use_container_width=False):
        with st.form("new_requirement", clear_on_submit=True, border=False):
            label = st.text_input("What it is",
                                  placeholder="Arm must lift the payload")
            chosen = st.selectbox("Measured by", sorted(names))
            op_col, target_col = st.columns(2)
            with op_col:
                op = st.selectbox("Must be", list(store.OPERATORS))
            with target_col:
                target = st.number_input("Target", value=1.0, format="%.6g")
            if st.form_submit_button("Add", type="primary"):
                if not label.strip():
                    st.warning("Give it a name.")
                else:
                    store.add_requirement(project, label.strip(),
                                          names[chosen], op, target)
                    store.save(project)
                    st.rerun()


def render(prefs=None, catalogue=None) -> None:
    catalogue = catalogue or {}
    project = store.load()

    ui.page_header(
        "Project",
        r"\text{parameters} \;\rightarrow\; \text{calculations} \;\rightarrow\;"
        r" \text{requirements}",
        "Define a value once and link it wherever it is used, then state what "
        "would make the design good enough. Every requirement is re-checked "
        "against the live calculators whenever a parameter changes.",
        "project")

    counts = store.summary(project, catalogue)
    total = sum(counts.values())
    if total:
        cells = "".join(
            f'<div><div class="a-sec-k">{label}</div>'
            f'<div class="a-sec-v">{counts[key]}</div></div>'
            for key, label in ((store.MET, "Meets"),
                               (store.NOT_MET, "Does not meet"),
                               (store.OUTSIDE_MODEL, "Outside model"),
                               (store.NOT_EVALUATED, "Not evaluated")))
        st.markdown(f'<div class="a-result"><div class="a-result-label">'
                    f'Requirements</div><div class="a-sec">{cells}</div></div>',
                    unsafe_allow_html=True)

    _requirements(project, catalogue)
    st.write("")
    _parameters(project, catalogue)

    ui.assumptions([
        "A requirement is only ever reported as met when every numeric input "
        "of its calculator is linked to a project parameter. While any input "
        "is still a page default, the status is 'not evaluated' - missing "
        "information must not become a green tick.",
        "A calculator whose own regime checks are firing reports 'outside "
        "model applicability' rather than a pass or a fail. A number the "
        "model cannot support is not evidence either way.",
        "Every requirement is recomputed from the current parameters each "
        "time this page is drawn. Nothing here is a stored answer that could "
        "have gone stale.",
        "Parameters are matched to inputs by unit text, so the unit must be "
        "written exactly as the calculator writes it. No conversion is "
        "performed.",
        "The source label on a parameter is recorded, not verified. Marking a "
        "guess as 'measured' makes it look like evidence without making it "
        "any more true.",
    ])


CALCULATORS = [
    Calculator(slug="project.board", name="Project", latex="", explanation="",
               render=render,
               keywords=("project", "requirements", "parameters", "shared",
                         "study", "design", "constraints", "board")),
]
