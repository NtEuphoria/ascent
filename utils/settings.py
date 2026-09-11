"""User settings, persisted between launches.

Stored as JSON in the app's support directory - the same folder the native
shell already uses for its logs and Python environment - because settings that
vanish when you quit are worse than no settings at all.

Reads are tolerant by design: a missing file, unreadable file, corrupt JSON or
an unknown value all fall back to defaults rather than failing. A preferences
file is never worth crashing an app over.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/ASCENT")
SETTINGS_PATH = os.path.join(SUPPORT_DIR, "settings.json")

APPEARANCE_OPTIONS = ["Follow system", "Light", "Dark"]
MOTION_OPTIONS = ["Full", "Reduced", "None"]
SIGNIFICANT_FIGURE_OPTIONS = [3, 4, 5, 6]

DEFAULTS: Dict[str, Any] = {
    "appearance": "Follow system",
    "motion": "Full",
    "significant_figures": 4,
    "show_reference": True,
}
# Note: there is deliberately no setting to hide assumptions. Stating the
# assumptions under every result is an accuracy requirement of this app, not a
# preference - a calculator that quietly drops its caveats is worse than one
# that never had them.


def _coerce(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only known keys with valid values; everything else reverts."""
    settings = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return settings
    if raw.get("appearance") in APPEARANCE_OPTIONS:
        settings["appearance"] = raw["appearance"]
    if raw.get("motion") in MOTION_OPTIONS:
        settings["motion"] = raw["motion"]
    if raw.get("significant_figures") in SIGNIFICANT_FIGURE_OPTIONS:
        settings["significant_figures"] = raw["significant_figures"]
    if isinstance(raw.get("show_reference"), bool):
        settings["show_reference"] = raw["show_reference"]
    return settings


def load() -> Dict[str, Any]:
    """Current settings, falling back to defaults on any problem."""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as handle:
            return _coerce(json.load(handle))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(settings: Dict[str, Any]) -> bool:
    """Write settings. Returns False if the file could not be written."""
    try:
        os.makedirs(SUPPORT_DIR, exist_ok=True)
        # Write and replace, so an interrupted write cannot leave a truncated
        # file that would silently reset every preference.
        temporary = SETTINGS_PATH + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(_coerce(settings), handle, indent=2)
        os.replace(temporary, SETTINGS_PATH)
        return True
    except OSError:
        return False


def reset() -> bool:
    """Restore every setting to its default."""
    return save(dict(DEFAULTS))


# ---------------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------------

OPEN_KEY = "_settings_open"


def request_open() -> None:
    import streamlit as st
    st.session_state[OPEN_KEY] = True


def close() -> None:
    import streamlit as st
    st.session_state[OPEN_KEY] = False


def panel() -> None:
    """The settings dialog, opened from the sidebar.

    Re-invoked on every rerun while open, for the same reason as the command
    palette: a dialog body only re-executes when its function is called, so
    driving it straight off the button would freeze its contents.
    """
    import streamlit as st

    if not st.session_state.get(OPEN_KEY):
        return

    @st.dialog("Settings", width="large", on_dismiss=close)
    def _dialog() -> None:
        current = load()

        st.markdown("**Appearance**")
        appearance = st.segmented_control(
            "Appearance", APPEARANCE_OPTIONS, key="set_appearance",
            default=current["appearance"], label_visibility="collapsed")
        st.caption("Following the system matches macOS. Choosing Light or Dark "
                   "overrides it for this app only.")

        st.markdown("**Motion**")
        motion = st.segmented_control(
            "Motion", MOTION_OPTIONS, key="set_motion",
            default=current["motion"], label_visibility="collapsed")
        st.caption("Animations throughout the app. Your system's "
                   "Reduce Motion setting always wins over this.")

        st.markdown("**Result precision**")
        figures = st.segmented_control(
            "Result precision", SIGNIFICANT_FIGURE_OPTIONS,
            key="set_figures", default=current["significant_figures"],
            format_func=lambda n: f"{n} digits",
            label_visibility="collapsed")
        st.caption("How many digits results are shown to. Whole numbers are "
                   "never truncated - 12,403 N stays 12,403 N even at the "
                   "lowest setting - so this mainly affects decimals. The "
                   "calculation itself is always full precision.")

        st.markdown("**Reference sections**")
        show_reference = st.toggle(
            "Show variable definitions and worked examples",
            value=current["show_reference"], key="set_reference")
        st.caption("Assumptions are always shown under the result and cannot "
                   "be hidden.")

        st.divider()
        left, right = st.columns([1, 1])
        with left:
            if st.button("Save", type="primary", use_container_width=True,
                         key="set_save"):
                ok = save({
                    "appearance": appearance or current["appearance"],
                    "motion": motion or current["motion"],
                    "significant_figures": (figures
                                            or current["significant_figures"]),
                    "show_reference": show_reference,
                })
                if ok:
                    close()
                    st.rerun()
                else:
                    st.error(f"Could not write settings to {SETTINGS_PATH}. "
                             "Changes will apply until you quit.")
        with right:
            if st.button("Reset to defaults", use_container_width=True,
                         key="set_reset"):
                reset()
                for key in ("set_appearance", "set_motion", "set_figures",
                            "set_reference"):
                    st.session_state.pop(key, None)
                close()
                st.rerun()

        st.caption(f"Stored in {SETTINGS_PATH}")

    _dialog()
