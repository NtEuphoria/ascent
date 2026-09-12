"""Jumping to another calculator from anywhere on the page.

Streamlit refuses to let you write a widget's session-state key once that
widget has been built for this run, so a "go to Drag" button rendered in the
main area cannot drive the sidebar radio directly - the sidebar was built
first. The command palette gets away with it only because it runs before the
sidebar does.

So a request is staged instead, and applied at the top of the next run before
any navigation widget exists. One indirection, and every part of the app can
link to every other part.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import streamlit as st

_REQUEST = "_nav_goto"


def request(slug: str) -> None:
    """Ask to be on `slug` after the next rerun."""
    st.session_state[_REQUEST] = slug


def pending() -> bool:
    return _REQUEST in st.session_state


def apply(by_slug: Dict[str, Tuple[str, object]],
          modes: Optional[Dict[str, str]] = None) -> None:
    """Consume a staged request. Call before building navigation widgets.

    The section is set as well as the category, so a link from a studio to a
    calculator - or a command-palette jump - lands on the page rather than
    quietly switching the category underneath a section that does not contain
    it.
    """
    slug = st.session_state.pop(_REQUEST, None)
    if slug is None:
        return
    entry = by_slug.get(slug)
    if entry is None:
        return                    # a stale link: stay where we are
    category, calc = entry
    if modes and category in modes:
        st.session_state["nav_mode"] = modes[category]
    st.session_state["nav_category"] = category
    st.session_state[f"nav_equation::{category}"] = calc.name
