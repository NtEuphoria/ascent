"""Aerospace & Robotics Engineering Toolkit.

Run with:  streamlit run app.py

This file does two things only: it owns the navigation registry, and it draws
the shell (header + sidebar). Everything else lives in calculators/ and utils/.

To add a new equation, see the "Adding a new equation" section of README.md.
"""
from __future__ import annotations

import streamlit as st

from calculators import (aerodynamics, controls, drones, electrical, flight,
                         live, materials, mechanical, project,
                         propulsion, reference, robotics, rotational,
                         structures, units)
from studios import (control_tuning, drivetrain, drone_powertrain,
                     lift_arm, structure, wing)
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
    # First, because it is the thing the rest hangs off: a value defined here
    # is the same value on every page that links it.
    "Project": project.CALCULATORS,
    # Ordered by how often someone reaches for them, not alphabetically.
    "Studios": (drone_powertrain.CALCULATORS + drivetrain.CALCULATORS
                + lift_arm.CALCULATORS + wing.CALCULATORS
                + structure.CALCULATORS + control_tuning.CALCULATORS),
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


# Three things this app is for, kept apart because they are different kinds of
# work: looking one number up, carrying a design through, and watching
# hardware. Mixing them into a single list of categories made the fastest of
# the three - open a page, read a figure - scroll past everything else.
MODES = {
    "Calculators": [name for name in CATEGORIES
                    if name not in ("Project", "Studios", "Live data")],
    "Studios": ["Studios", "Project"],
    "Live": ["Live data"],
}

# The visible label is the section name, hidden from sight by CSS and replaced
# with a drawn icon. Material Symbols is a webfont and this app runs offline,
# so the icon-font route rendered the ligature names as plain text.

MODE_BLURB = {
    "Calculators": "One equation at a time.",
    "Studios": "Carry a design through end to end.",
    "Live": "Read a device that is plugged in.",
}


def mode_of_category():
    """category -> mode. One category belongs to exactly one mode."""
    return {category: mode
            for mode, categories in MODES.items() for category in categories}


def all_calculators():
    """Every calculator in the app, paired with its category.

    Built fresh each run rather than cached: the specs hold lambdas, which do
    not survive Streamlit's cache, and 54 dataclasses cost nothing to walk.
    """
    return [(category, calc)
            for category, entry in CATEGORIES.items()
            for calc in normalise(entry, category)]


def _reconcile_mode(modes) -> None:
    if st.session_state.get("nav_mode") not in MODES:
        st.session_state["nav_mode"] = list(MODES)[0]
    category = st.session_state.get("nav_category")
    if category in modes and st.session_state.get("nav_mode") != modes[category]:
        st.session_state["nav_mode"] = modes[category]


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
    modes = mode_of_category()

    # Restore the last calculator on the first run of a session, before the
    # navigation widgets are built - which is the only point at which their
    # session-state keys can still be set.
    # Not if something has already decided the page. A deep link, a palette
    # jump or a restored section should win over "reopen where you left off" -
    # otherwise arriving at a specific page silently lands you on the last one
    # instead.
    if ("nav_restored" not in st.session_state
            and "nav_category" not in st.session_state):
        st.session_state["nav_restored"] = True
        last = prefs.get("last_page", "")
        if prefs.get("start_page") == "Where I left off" and last in by_slug:
            category, calc = by_slug[last]
            st.session_state["nav_mode"] = modes.get(category, "Calculators")
            st.session_state["nav_category"] = category
            st.session_state[f"nav_equation::{category}"] = calc.name

    # Both of these write navigation widget keys, so both must run before the
    # sidebar builds those widgets.
    navigate.apply(by_slug, modes)
    # The section always follows the category. A restored last page, a deep
    # link or a palette jump sets the category; leaving the section showing a
    # list that does not contain it would show a sidebar with nothing
    # selected in it. Done before the widgets are built, which is the only
    # point at which their keys can still be written.
    _reconcile_mode(modes)
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

        # Buttons rather than st.segmented_control. The widget looks right
        # but AppTest cannot serialise its state between runs - a second run
        # raises KeyError while indexing the selection - which would make
        # every end-to-end navigation test impossible to write. Buttons are
        # fully supported, keep nav_mode as plain session state rather than a
        # widget key, and leave the radio indices the tests address untouched.
        mode = st.session_state.get("nav_mode", list(MODES)[0])
        with st.container(key="modeswitch"):
            for column, name in zip(st.columns(len(MODES)), MODES):
                with column:
                    if st.button(name, key=f"mode_{name}",
                                 help=f"{name} — {MODE_BLURB[name]}",
                                 use_container_width=True,
                                 type="primary" if name == mode
                                 else "secondary"):
                        # The category has to move with the section, or
                        # _reconcile_mode immediately drags the section back
                        # to wherever the old category lives and the switch
                        # appears to do nothing. Returning to the category
                        # last used in that section, rather than always its
                        # first, is what makes switching back and forth feel
                        # like two places instead of two resets.
                        remembered = st.session_state.get(f"nav_last::{name}")
                        st.session_state["nav_mode"] = name
                        st.session_state["nav_category"] = (
                            remembered if remembered in MODES[name]
                            else MODES[name][0])
                        st.rerun()
        st.markdown(f'<div class="a-mode-name">{mode}'
                    f'<span>{MODE_BLURB[mode]}</span></div>',
                    unsafe_allow_html=True)

        names = MODES[mode]
        if len(names) == 1:
            # One category in this section: a dropdown of one is a control that
            # cannot do anything.
            category = names[0]
        else:
            category = st.selectbox("Category", names, key="nav_category",
                                    label_visibility="collapsed")
        st.session_state[f"nav_last::{mode}"] = category
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


# Guarded, so importing this module to read CATEGORIES does not also draw the
# entire app. Streamlit runs the script with __name__ == "__main__", so this
# still executes normally.
#
# It was unguarded until a form appeared on the default landing page. Running
# main() at import time in bare mode left Streamlit's global form state open,
# and every widget in the next real run then raised "st.button() can't be used
# in an st.form()" - an import side effect that had simply never had anything
# to break.
if __name__ == "__main__":
    main()
