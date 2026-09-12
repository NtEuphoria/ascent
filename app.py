"""Aerospace & Robotics Engineering Toolkit.

Run with:  streamlit run app.py

This file does two things only: it owns the navigation registry, and it draws
the shell (header + sidebar). Everything else lives in calculators/ and utils/.

To add a new equation, see the "Adding a new equation" section of README.md.
"""
from __future__ import annotations

import streamlit as st

from calculators import (aerodynamics, controls, drones, electrical, flight,
                         live, materials, mechanical, propulsion, reference,
                         robotics, rotational, structures, units)
from utils import navigate, onboarding, palette
from utils import render as renderer
from utils import settings as user_settings
from utils import ui
from utils.spec import normalise

VERSION = "1.1.0"
TITLE = "ASCENT"
ACRONYM = "Aerospace · Structures · Controls · Electronics · Numerics · Toolkit"
SUBTITLE = ("Interactive engineering calculators for aerospace, robotics, "
            "mechanical systems, autonomy, electronics, and materials.")

# Sidebar category -> {menu label: render function}. Order is preserved.
CATEGORIES = {
    "Aerodynamics": aerodynamics.CALCULATORS,
    "Flight performance": flight.CALCULATORS,
    "Drones": drones.CALCULATORS,
    "Propulsion": propulsion.CALCULATORS,
    "Mechanical": mechanical.CALCULATORS,
    "Rotational mechanics": rotational.CALCULATORS,
    "Structures": structures.CALCULATORS,
    "Materials": materials.CALCULATORS,
    "Robotics": robotics.CALCULATORS,
    "Electrical / robotics": electrical.CALCULATORS,
    "Control systems": controls.CALCULATORS,
    "Live data": live.CALCULATORS,
    "Unit converter": units.CALCULATORS,
    "Constants / reference": reference.CALCULATORS,
}


def all_calculators():
    """Every calculator in the app, paired with its category.

    Built fresh each run rather than cached: the specs hold lambdas, which do
    not survive Streamlit's cache, and 54 dataclasses cost nothing to walk.
    """
    return [(category, calc)
            for category, entry in CATEGORIES.items()
            for calc in normalise(entry, category)]


def _quick_links(heading: str, slugs, by_slug, key_prefix: str,
                 marker: str = "",
                 limit: int = user_settings.SIDEBAR_FAVOURITES) -> None:
    """A short list of one-click jumps at the top of the sidebar.

    Favourites and recents are what stop a growing catalogue from making the
    common case slower - which is the whole risk of adding calculators. They
    only earn their space if they stay short and dense, so both are capped and
    the rows are collapsed to a single line each.
    """
    entries = [by_slug[slug] for slug in slugs if slug in by_slug][:limit]
    if not entries:
        return
    st.markdown(f'<div class="a-side-head">{heading}'
                f'<span>{len(entries)}</span></div>', unsafe_allow_html=True)
    with st.container(key=f"quick_{key_prefix}"):
        for category, calc in entries:
            if st.button(f"{marker}{calc.name}", key=f"{key_prefix}::{calc.slug}",
                         use_container_width=True, help=category):
                st.session_state["nav_category"] = category
                st.session_state[f"nav_equation::{category}"] = calc.name
                st.rerun()


def main() -> None:
    st.set_page_config(
        page_title=f"{TITLE} - Engineering Toolkit",
        page_icon="✈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    prefs = user_settings.load()
    ui.inject_css(prefs)

    # First run takes over the whole page. Returning here rather than drawing
    # the app behind it keeps the sidebar, the palette trigger and the
    # navigation widgets from being built at all, so nothing in setup can be
    # knocked out of place by them.
    if onboarding.needed(prefs):
        onboarding.run(prefs)
        return

    catalogue = all_calculators()
    by_slug = {calc.slug: (category, calc) for category, calc in catalogue}

    # Restore the last calculator on the first run of a session, before the
    # navigation widgets are built - which is the only point at which their
    # session-state keys can still be set.
    if "nav_restored" not in st.session_state:
        st.session_state["nav_restored"] = True
        last = prefs.get("last_page", "")
        if prefs.get("start_page") == "Where I left off" and last in by_slug:
            category, calc = by_slug[last]
            st.session_state["nav_category"] = category
            st.session_state[f"nav_equation::{category}"] = calc.name

    # Both of these write navigation widget keys, so both must run before the
    # sidebar builds those widgets.
    navigate.apply(by_slug)
    palette.trigger(catalogue)          # hidden; the Cmd-K menu item clicks it

    with st.sidebar:
        if st.button(f"Search  ·  {len(catalogue)} calculators",
                     key="palette_open_visible", use_container_width=True,
                     help="Or press Cmd-K"):
            palette.request_open()
            st.rerun()

        _quick_links("Favourites", prefs.get("favourites", []), by_slug,
                     "fav", marker="★  ",
                     limit=user_settings.SIDEBAR_FAVOURITES)
        _quick_links("Recent", [slug for slug in prefs.get("recents", [])
                                if slug not in prefs.get("favourites", [])],
                     by_slug, "rec", limit=4)

        st.markdown('<div class="a-side-head">Browse</div>',
                    unsafe_allow_html=True)
        category = st.selectbox("Category", list(CATEGORIES.keys()),
                                key="nav_category", label_visibility="collapsed")
        calculators = normalise(CATEGORIES[category], category)
        by_name = {calc.name: calc for calc in calculators}
        # The radio key includes the category so each category keeps its own
        # selection, and switching category can never leave a stale value.
        name = st.radio("Equation", list(by_name.keys()),
                        key=f"nav_equation::{category}")
        st.divider()
        st.caption(ui.DISCLAIMER)

        # Pinned to the bottom of the sidebar by CSS, where a settings entry is
        # conventionally found.
        if st.button("⚙  Settings", key="settings_open",
                     use_container_width=True):
            user_settings.request_open()
            st.rerun()

    user_settings.panel(len(catalogue), len(CATEGORIES), VERSION)

    ui.app_header(TITLE, ACRONYM, SUBTITLE)
    chosen = by_name[name]
    user_settings.record_visit(chosen.slug)
    renderer.render(chosen, prefs, by_slug)


main()
