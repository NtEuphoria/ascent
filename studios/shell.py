"""The parts every studio is built from.

A studio is a sequence of steps, each with inputs and a row of derived
figures, ending in a verdict board. Those pieces live here so five studios
look like one product rather than five people's idea of a studio - and so a
change to how a step reads is one edit rather than five.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

import streamlit as st

from utils import project as store
from utils.formatting import format_number

Figure = Tuple[str, float, str]
"""(label, value, unit) for one derived number."""


def step(number: int, title: str, blurb: str) -> None:
    """A numbered heading. A studio is an order of operations, so the number
    is what lets someone scrolling back find where they were."""
    st.markdown(f'<div class="a-step"><span>{number}</span>'
                f'<div><b>{title}</b><i>{blurb}</i></div></div>',
                unsafe_allow_html=True)


def figures(items: Iterable[Figure], significant: int = 4) -> None:
    """A row of derived values, in the same treatment as a result card."""
    cells = "".join(
        f'<div><div class="a-sec-k">{label}</div>'
        f'<div class="a-sec-v">{format_number(value, significant)}'
        f'<span class="a-sec-u"> {unit}</span></div></div>'
        for label, value, unit in items)
    st.markdown(f'<div class="a-result"><div class="a-sec">{cells}</div></div>',
                unsafe_allow_html=True)


def check(label: str, ok: bool, margin: float, detail: str) -> dict:
    """One verdict. `margin` is how many times over the limit it is, so 1.0 is
    exactly at it and below 1.0 fails - the same reading on every studio."""
    return {"label": label, "ok": bool(ok), "margin": float(margin),
            "detail": detail}


def verdict_board(checks: Sequence[dict]) -> int:
    """Draw every check and return how many passed."""
    passing = 0
    for item in checks:
        passing += 1 if item["ok"] else 0
        style = "a-ok" if item["ok"] else "a-bad"
        text = "Passes" if item["ok"] else "Fails"
        margin = item["margin"]
        margin_text = (format_number(margin, 3) + "x"
                       if margin == margin and abs(margin) != float("inf")
                       else "—")
        st.markdown(
            f'<div class="a-req"><span class="a-badge {style}">{text}</span>'
            f'<span class="a-req-label">{item["label"]}</span>'
            f'<span class="a-req-rule">{item["detail"]}  ·  {margin_text}'
            f'</span></div>', unsafe_allow_html=True)

    if passing == len(checks):
        st.success("Every check passes. The margins above are what you have "
                   "to spend on the things this studio does not model.")
    else:
        st.warning(f"{len(checks) - passing} of {len(checks)} checks fail. "
                   "The headroom figures say how far off each one is.")
    return passing


def send_to_project(key: str, items: Sequence[Figure],
                    note: str = "") -> None:
    """Offer this studio's quantities as shared project parameters.

    A form inside the popover, because a popover closes on every rerun and a
    field that commits on Enter would shut it before the submit button could
    be reached.
    """
    st.write("")
    with st.popover("Send to project", use_container_width=False):
        st.markdown('<div class="a-note">Adds these as shared parameters, so '
                    'the same values drive every calculator page you link '
                    'them on.</div>', unsafe_allow_html=True)
        with st.form(f"{key}_toproject", border=False):
            source = st.selectbox("Mark them as", store.SOURCES, index=2)
            if st.form_submit_button("Add to project", type="primary"):
                project = store.load()
                for label, value, unit in items:
                    store.add_parameter(project, label, float(value), unit,
                                        source, note)
                store.save(project)
                st.success("Added. Open Project to see where they are used.")


def summarise(checks: Sequence[dict]) -> List[str]:
    """Labels of the checks that failed, for a caption or a test."""
    return [item["label"] for item in checks if not item["ok"]]
