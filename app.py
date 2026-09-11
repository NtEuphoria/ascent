"""Aerospace & Robotics Engineering Toolkit.

Run with:  streamlit run app.py

This file does two things only: it owns the navigation registry, and it draws
the shell (header + sidebar). Everything else lives in calculators/ and utils/.

To add a new equation, see the "Adding a new equation" section of README.md.
"""
from __future__ import annotations

import streamlit as st

from calculators import (aerodynamics, controls, drones, electrical, flight,
                         materials, mechanical, reference, rotational, units)
from utils import render as renderer
from utils import ui
from utils.spec import normalise

TITLE = "ASCENT"
ACRONYM = "Aerospace · Structures · Controls · Electronics · Numerics · Toolkit"
SUBTITLE = ("Interactive engineering calculators for aerospace, robotics, "
            "mechanical systems, autonomy, electronics, and materials.")

# Sidebar category -> {menu label: render function}. Order is preserved.
CATEGORIES = {
    "Aerodynamics": aerodynamics.CALCULATORS,
    "Flight performance": flight.CALCULATORS,
    "Drones": drones.CALCULATORS,
    "Mechanical": mechanical.CALCULATORS,
    "Rotational mechanics": rotational.CALCULATORS,
    "Materials": materials.CALCULATORS,
    "Electrical / robotics": electrical.CALCULATORS,
    "Control systems": controls.CALCULATORS,
    "Unit converter": units.CALCULATORS,
    "Constants / reference": reference.CALCULATORS,
}


def main() -> None:
    st.set_page_config(
        page_title=f"{TITLE} - Engineering Toolkit",
        page_icon="✈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    ui.inject_css()

    with st.sidebar:
        st.markdown("### Categories")
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

    ui.app_header(TITLE, ACRONYM, SUBTITLE)
    renderer.render(by_name[name])


main()
