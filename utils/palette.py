"""Command palette: jump to any calculator in two keystrokes.

Past a few dozen calculators a flat list stops being navigable - Hick's
law says
decision time grows with the number of options, and scanning ten category
groups to find "hover thrust" is slower than typing "hov".

Streamlit cannot capture a Cmd-K keypress itself: the page runs no JavaScript
of its own, and `st.html` strips both <script> and inline handlers. So the
native app owns the shortcut and clicks a hidden trigger button in the page,
which is a normal Streamlit interaction over the existing websocket - no page
reload, no query-parameter round trip.
"""
from __future__ import annotations

from typing import List, Tuple

import streamlit as st

from . import navigate

from .spec import Calculator

TRIGGER_KEY = "palette_trigger"
OPEN_KEY = "_palette_open"


def _score(calc: Calculator, category: str, query: str) -> int:
    """Rank matches so the obvious answer is first.

    A prefix match on the name beats a match buried in a keyword, which beats
    a category match. Returns -1 for no match.
    """
    name = calc.name.lower()
    if name.startswith(query):
        return 0
    if query in name:
        return 1
    if query in calc.search_text():
        return 2
    if query in category.lower():
        return 3
    return -1


def search(items: List[Tuple[str, Calculator]], query: str
           ) -> List[Tuple[str, Calculator]]:
    """Filter and rank. An empty query returns everything, unranked."""
    query = (query or "").strip().lower()
    if not query:
        return items
    scored = []
    for category, calc in items:
        rank = _score(calc, category, query)
        if rank >= 0:
            scored.append((rank, category, calc))
    scored.sort(key=lambda row: (row[0], row[2].name))
    return [(category, calc) for _, category, calc in scored]


def close() -> None:
    """Forget that the palette is open."""
    st.session_state[OPEN_KEY] = False
    st.session_state.pop("palette_query", None)


def open_dialog(items: List[Tuple[str, Calculator]]) -> None:
    """Show the palette. Selecting an entry navigates and closes it.

    Must be called on EVERY rerun while the palette is open, not just on the
    click that opened it. A dialog body only re-executes when its function is
    invoked, so calling it once would leave the results frozen at whatever the
    query was when it opened - typing would filter nothing.
    """

    @st.dialog("Go to calculator", width="large", on_dismiss=close)
    def _dialog() -> None:
        query = st.text_input(
            "Search", key="palette_query", label_visibility="collapsed",
            placeholder="Search calculators…  try 'hover', 'stall', 'torque'")
        matches = search(items, query)

        if not matches:
            st.caption("Nothing matches that. Try a shorter word.")
            return

        st.caption(f"{len(matches)} of {len(items)} calculators")
        for category, calc in matches[:12]:
            if st.button(f"{calc.name}   ·   {category}",
                         key=f"palette_go::{calc.slug}",
                         use_container_width=True):
                # Staged rather than written directly, so the one place that
                # knows how to set every navigation key - section, category
                # and equation - stays the one place. Setting only the
                # category here left the palette able to jump to a page in a
                # section the sidebar was not showing.
                navigate.request(calc.slug)
                close()
                st.rerun()
        if len(matches) > 12:
            st.caption(f"…and {len(matches) - 12} more. Keep typing to narrow.")

    _dialog()


def request_open() -> None:
    """Mark the palette as open, so it survives subsequent reruns."""
    st.session_state[OPEN_KEY] = True


def trigger(items: List[Tuple[str, Calculator]]) -> None:
    """The hidden button the native Cmd-K menu item clicks, plus the dialog.

    The button is positioned off-screen rather than display:none so it stays a
    real, clickable element for the native shell's evaluateJavaScript call.

    Opening is tracked in session state rather than driven straight off the
    button: typing in the search box causes a rerun in which the button reads
    False, and the dialog has to be re-invoked on that rerun to filter.
    """
    if st.button("Open command palette", key=TRIGGER_KEY):
        request_open()
    if st.session_state.get(OPEN_KEY):
        open_dialog(items)
