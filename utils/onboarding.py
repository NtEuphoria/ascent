"""First run: a short setup flow, shown once.

Modelled on the way a new Mac sets itself up, and specifically on the part of
that which is easy to miss - every screen asks something that actually
configures the machine. A welcome sequence that only shows off is a toll gate
between the user and the thing they downloaded.

So each panel here writes a real setting, and the two that change how the app
looks apply immediately: choosing Dark repaints the page underneath the
question. The last panel asks what the user works on and pins matching
calculators to their sidebar, which is the one step that makes the app
measurably different afterwards.

It runs instead of the app, not on top of it. No sidebar, no navigation, one
decision per screen.
"""
from __future__ import annotations

from typing import Dict, List

import streamlit as st

from . import backdrop
from . import settings as user_settings
from . import theme, ui

STEP_KEY = "_onboard_step"
PICKS_KEY = "_onboard_disciplines"

STEPS = ("welcome", "appearance", "accent", "work", "ready")

APPEARANCES = (
    ("Follow system", "Match macOS, and change when it does."),
    ("Light", "A bright page, whatever the system is doing."),
    ("Dark", "A dark page, whatever the system is doing."),
)

ACCENTS = (
    ("Blue", "The default."),
    ("Teal", "Cooler, lower contrast."),
    ("Violet", "Distinct without shouting."),
    ("Amber", "Warm, and the most visible on a dark page."),
    ("Slate", "Nearly monochrome."),
)

# What each discipline pins. Chosen as the pages someone in that field opens
# first, not as a full index of the category - a sidebar with thirty
# favourites is the same as one with none.
DISCIPLINES: Dict[str, List[str]] = {
    "Aerodynamics & flight": [
        "aero.lift", "aero.drag", "aero.lift_to_drag", "flight.stall_speed",
        "flight.glide"],
    "Drones & multirotors": [
        "drone.hover_thrust", "drone.flight_time", "drone.twr",
        "drone.battery_sag", "prop.momentum_theory"],
    "Propulsion & rockets": [
        "prop.momentum_theory", "prop.rocket_equation", "prop.motor_constants",
        "prop.advance_ratio"],
    "Robotics & control": [
        "robot.differential_drive", "robot.reflected_inertia",
        "robot.servo_torque", "ctrl.pid", "ctrl.second_order"],
    "Structures & materials": [
        "struct.beam_bending", "struct.second_moment", "struct.buckling",
        "materials.factor_of_safety", "materials.normal_stress"],
    "Electronics & power": [
        "elec.ohms_law", "elec.power", "elec.voltage_drop",
        "elec.battery_energy", "prop.motor_constants"],
}

MAX_PINNED = user_settings.SIDEBAR_FAVOURITES
"""However many disciplines are chosen, pin exactly what the sidebar shows.
Favourites are a shortlist - past about five they become a second navigation
tree - and pinning more than are displayed makes the count on the last setup
screen a promise the app does not keep."""


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
def needed(prefs: dict) -> bool:
    return not prefs.get("onboarded", False)


def _step() -> int:
    return int(st.session_state.get(STEP_KEY, 0))


def _go(delta: int) -> None:
    st.session_state[STEP_KEY] = max(0, min(len(STEPS) - 1, _step() + delta))
    st.rerun()


def pinned_for(chosen) -> List[str]:
    """Favourites for a set of disciplines: round-robin, de-duplicated.

    Taken one at a time from each discipline rather than the whole of the
    first and then the whole of the second, so picking three fields gives a
    spread across all three instead of everything from one.
    """
    lists = [DISCIPLINES[name] for name in chosen if name in DISCIPLINES]
    out: List[str] = []
    for index in range(max((len(item) for item in lists), default=0)):
        for item in lists:
            if index < len(item) and item[index] not in out:
                out.append(item[index])
                if len(out) >= MAX_PINNED:
                    return out
    return out


# ---------------------------------------------------------------------------
# Pieces
# ---------------------------------------------------------------------------
def _progress(active: int) -> str:
    dots = "".join(
        f'<span class="a-ob-dot{" on" if index <= active else ""}"></span>'
        for index in range(len(STEPS)))
    return f'<div class="a-ob-dots">{dots}</div>'


def _heading(title: str, body: str, step: int) -> None:
    st.markdown(
        f'<div class="a-ob-head" style="--s:0ms">'
        f'<h1 class="a-ob-title">{title}</h1>'
        f'<p class="a-ob-body">{body}</p></div>',
        unsafe_allow_html=True)


def _choice_row(label: str, description: str, selected: bool, key: str,
                index: int) -> bool:
    """One option: name and description in a single row.

    The whole row is Streamlit's own button rather than a styled div, because
    it is the only version that is focusable, operable from the keyboard and
    announced as a control. The name and description go inside its label - a
    separate caption above would print the name twice.
    """
    with st.container(key=f"obopt_{key}_{'on' if selected else 'off'}"):
        # Streamlit unwraps unsupported Markdown in a button label, so a
        # two-line row with a subtitle inside the control is not available -
        # the line break and the colour directive both vanish. The description
        # goes underneath instead, which at least reads in the right order.
        clicked = st.button(
            ("\u2713  " if selected else "") + label,
            key=f"ob_{key}", use_container_width=True,
            type="primary" if selected else "secondary")
        st.markdown(f'<div class="a-ob-desc" style="--s:{60 + index * 45}ms">'
                    f'{description}</div>', unsafe_allow_html=True)
        return clicked


def _footer(step: int, forward: str = "Continue",
            can_advance: bool = True) -> None:
    """Progress, then the one action, then the way back.

    The forward action is centred and wide because it is what the screen is
    for; Back sits under it, quiet, because it is a correction rather than a
    choice. Putting them side by side gives a decision equal weight to an undo.
    """
    st.markdown(_progress(step), unsafe_allow_html=True)
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        if st.button(forward, key=f"ob_next_{step}", type="primary",
                     use_container_width=True, disabled=not can_advance):
            if step >= len(STEPS) - 1:
                _finish()
            else:
                _go(1)
        if step > 0:
            with st.container(key=f"obback_{step}"):
                if st.button("Back", key=f"ob_back_{step}",
                             use_container_width=True):
                    _go(-1)


def _finish() -> None:
    chosen = st.session_state.get(PICKS_KEY, [])
    user_settings.update(onboarded=True, favourites=pinned_for(chosen))
    st.session_state.pop(STEP_KEY, None)
    st.rerun()


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------
def _welcome(prefs: dict, count: int) -> None:
    st.markdown(f'<div class="a-ob-mark">{ui.MARK}</div>',
                unsafe_allow_html=True)
    _heading("Welcome to ASCENT",
             f"{count} engineering calculators for aerospace, robotics, "
             "structures and electronics - each one showing its equation, its "
             "assumptions and what actually drives the answer."
             "<br><br>This takes about twenty seconds.", 0)
    _footer(0, "Set up ASCENT")


def _appearance(prefs: dict, count: int) -> None:
    _heading("How should it look?",
             "This applies straight away, so you can see it. Everything here "
             "can be changed later in Settings.", 1)
    current = prefs.get("appearance", "Follow system")
    for index, (name, description) in enumerate(APPEARANCES):
        if _choice_row(name, description, current == name,
                       f"appearance_{index}", index):
            user_settings.update(appearance=name)
            st.rerun()
    _footer(1)


def _accent(prefs: dict, count: int) -> None:
    _heading("Pick an accent.",
             "It colours the result card, the selected page and every "
             "highlight. The mark itself stays blue.", 2)
    current = prefs.get("accent", "Blue")
    for index, (name, description) in enumerate(ACCENTS):
        if _choice_row(name, description, current == name,
                       f"accent_{index}", index):
            user_settings.update(accent=name)
            st.rerun()
    _footer(2)


def _work(prefs: dict, count: int) -> None:
    _heading("What do you work on?",
             "Pick any number. The calculators you are most likely to want get "
             "pinned to the top of your sidebar - you can change them any time "
             "with the star on a page.", 3)
    chosen = list(st.session_state.get(PICKS_KEY, []))
    for index, name in enumerate(DISCIPLINES):
        selected = name in chosen
        if _choice_row(name, f"{len(DISCIPLINES[name])} calculators",
                       selected, f"work_{index}", index):
            if selected:
                chosen.remove(name)
            else:
                chosen.append(name)
            st.session_state[PICKS_KEY] = chosen
            st.rerun()
    if chosen:
        st.caption(f"{len(pinned_for(chosen))} calculators will be pinned.")
    _footer(3)


def _ready(prefs: dict, count: int) -> None:
    chosen = st.session_state.get(PICKS_KEY, [])
    pins = pinned_for(chosen)
    st.markdown(f'<div class="a-ob-mark a-ob-mark-small">{ui.MARK}</div>',
                unsafe_allow_html=True)
    _heading("You're set.",
             f"Press Command-K at any time to search all {count} "
             "calculators. Every result shows its assumptions underneath - "
             "they are never hidden, because a calculator that drops its "
             "caveats is worse than one that never had them.", 4)

    rows = [("Appearance", prefs.get("appearance", "Follow system")),
            ("Accent", prefs.get("accent", "Blue"))]
    if pins:
        rows.append(("Pinned", f"{len(pins)} calculators"))
    st.markdown(
        '<div class="a-ob-summary">' + "".join(
            f'<div><span>{label}</span><b>{value}</b></div>'
            for label, value in rows) + "</div>",
        unsafe_allow_html=True)
    _footer(4, "Start using ASCENT")


_PANELS = {"welcome": _welcome, "appearance": _appearance, "accent": _accent,
           "work": _work, "ready": _ready}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _backdrop(prefs: dict) -> None:
    """The field behind the panel.

    Colours are resolved here rather than inside the iframe because the iframe
    is a separate document and cannot see the parent's custom properties. The
    appearance is read the same way the charts read it, so a forced Light or
    Dark is honoured rather than the OS being asked.
    """
    appearance = prefs.get("appearance", "Follow system")
    mode = "light" if appearance == "Light" else "dark"
    if appearance == "Follow system":
        detected = getattr(getattr(st, "context", None), "theme", None)
        mode = "light" if getattr(detected, "type", "dark") == "light" else "dark"
    accent = theme.ACCENTS.get(prefs.get("accent", "Blue"),
                               theme.ACCENTS["Blue"])[mode][0]
    ink = (theme.LIGHT if mode == "light" else theme.DARK)["ink"]
    with st.container(key="backdrop"):
        backdrop.render(accent, ink, prefs.get("motion", "Full"))


def run(prefs: dict, count: int) -> None:
    """Draw the current panel. Called instead of the app, never alongside it.

    `count` is how many calculators the app actually has, passed in rather than
    written into the copy: the welcome screen claimed seventy-eight while the
    sidebar, the command palette and the About tab all counted the real total.
    """
    # The sidebar is empty during setup but Streamlit still reserves its
    # column, which leaves the panel off-centre on the page.
    # Streamlit reserves the sidebar column even when nothing is put in it,
    # which leaves the panel off-centre; and the default top padding strands
    # a short panel at the top of a tall window.
    st.html("<style>[data-testid='stSidebar']{display:none!important;}"
            "[data-testid='stMain'] .block-container{max-width:540px;"
            "min-height:94vh;display:flex;flex-direction:column;"
            "padding-top:var(--a-s5);padding-bottom:var(--a-s5);}"
            # Two things at once. Streamlit's vertical block is flex:1, so it
            # stretches to fill the container and leaves the container's
            # centring nothing to centre - a short panel ends up pinned to the
            # top of a tall window. And the centring is done with auto margins
            # rather than justify-content, because a flex item centred that way
            # overflows equally in both directions once it is taller than the
            # viewport, putting the heading above the top edge where it cannot
            # be scrolled back into view. The six-option panel is that tall.
            "[data-testid='stMain'] .block-container "
            "> [data-testid='stVerticalBlock']{flex:0 1 auto;"
            "margin-top:auto;margin-bottom:auto;}"
            + backdrop.LAYER_CSS + "</style>")
    _backdrop(prefs)
    with st.container(key="onboarding"):
        _PANELS[STEPS[_step()]](prefs, count)
