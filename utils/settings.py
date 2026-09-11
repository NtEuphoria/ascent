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

import streamlit as st

SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/ASCENT")
SETTINGS_PATH = os.path.join(SUPPORT_DIR, "settings.json")

APPEARANCE_OPTIONS = ["Follow system", "Light", "Dark"]
ACCENT_OPTIONS = ["Blue", "Teal", "Violet", "Amber", "Slate"]
DENSITY_OPTIONS = ["Comfortable", "Compact"]
MOTION_OPTIONS = ["Full", "Reduced", "None"]
SIGNIFICANT_FIGURE_OPTIONS = [3, 4, 5, 6]
START_PAGE_OPTIONS = ["Where I left off", "First calculator"]

MAX_RECENTS = 6

DEFAULTS: Dict[str, Any] = {
    # Appearance
    "appearance": "Follow system",
    "accent": "Blue",
    "density": "Comfortable",
    "motion": "Full",
    # Results
    "significant_figures": 4,
    "thousands_separator": True,
    # Page content
    "show_reference": True,
    "show_examples": True,
    # Navigation
    "start_page": "Where I left off",
    "favourites": [],
    "recents": [],
    "last_page": "",
}
# Note: there is deliberately no setting to hide assumptions. Stating the
# assumptions under every result is an accuracy requirement of this app, not a
# preference - a calculator that quietly drops its caveats is worse than one
# that never had them.

_CHOICES = {
    "appearance": APPEARANCE_OPTIONS,
    "accent": ACCENT_OPTIONS,
    "density": DENSITY_OPTIONS,
    "motion": MOTION_OPTIONS,
    "significant_figures": SIGNIFICANT_FIGURE_OPTIONS,
    "start_page": START_PAGE_OPTIONS,
}
_FLAGS = ("thousands_separator", "show_reference", "show_examples")
_SLUG_LISTS = ("favourites", "recents")


def _coerce(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only known keys with valid values; everything else reverts.

    Driven by a table rather than a chain of ifs, so adding a setting means
    adding one row instead of remembering to validate it in two places.
    """
    settings = dict(DEFAULTS)
    settings["favourites"] = []
    settings["recents"] = []
    if not isinstance(raw, dict):
        return settings

    for key, allowed in _CHOICES.items():
        if raw.get(key) in allowed:
            settings[key] = raw[key]
    for flag in _FLAGS:
        if isinstance(raw.get(flag), bool):
            settings[flag] = raw[flag]
    for key in _SLUG_LISTS:
        value = raw.get(key)
        if isinstance(value, list):
            # Slugs only, de-duplicated, order preserved.
            seen, clean = set(), []
            for item in value:
                if isinstance(item, str) and item and item not in seen:
                    seen.add(item)
                    clean.append(item)
            settings[key] = clean[:MAX_RECENTS * 4]
    if isinstance(raw.get("last_page"), str):
        settings["last_page"] = raw["last_page"]
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
    """Restore every setting to its default, keeping favourites."""
    current = load()
    fresh = dict(DEFAULTS)
    fresh["favourites"] = current.get("favourites", [])
    return save(fresh)


def update(**changes) -> bool:
    """Merge changes into the stored settings."""
    current = load()
    current.update(changes)
    return save(current)


def toggle_favourite(slug: str) -> bool:
    """Star or unstar a calculator. Returns True if it is now a favourite."""
    current = load()
    favourites = list(current.get("favourites", []))
    starred = slug not in favourites
    if starred:
        favourites.append(slug)
    else:
        favourites.remove(slug)
    save({**current, "favourites": favourites})
    return starred


def record_visit(slug: str) -> None:
    """Remember this calculator as the most recent one."""
    current = load()
    recents = [s for s in current.get("recents", []) if s != slug]
    recents.insert(0, slug)
    if recents[:MAX_RECENTS] == current.get("recents", [])[:MAX_RECENTS] \
            and current.get("last_page") == slug:
        return          # nothing changed; skip the disk write
    save({**current, "recents": recents[:MAX_RECENTS], "last_page": slug})


# ---------------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------------

OPEN_KEY = "_settings_open"


def request_open() -> None:
    st.session_state[OPEN_KEY] = True


def close() -> None:
    st.session_state[OPEN_KEY] = False


def _apply(widget_key: str, setting: str):
    """Persist one control's value the moment it changes.

    Settings apply immediately rather than behind a Save button: a preferences
    pane that needs confirming is a preferences pane where people change
    something, see nothing happen, and conclude it is broken.
    """
    def handler() -> None:
        value = st.session_state.get(widget_key)
        if value is not None:
            update(**{setting: value})
    return handler


_ACCENT_SWATCH = {"Blue": "🔵", "Teal": "🟢", "Violet": "🟣",
                  "Amber": "🟠", "Slate": "⚪"}


def panel(calculator_count: int = 0, category_count: int = 0,
          version: str = "1.1.0") -> None:
    """The settings dialog, opened from the bottom of the sidebar.

    Re-invoked on every rerun while open, for the same reason as the command
    palette: a dialog body only re-executes when its function is called.
    """
    if not st.session_state.get(OPEN_KEY):
        return

    @st.dialog("Settings", width="large", on_dismiss=close)
    def _dialog() -> None:
        current = load()
        appearance, results, content, about = st.tabs(
            ["Appearance", "Results", "Content", "About"])

        with appearance:
            st.caption("Theme")
            st.segmented_control(
                "Theme", APPEARANCE_OPTIONS, key="set_appearance",
                default=current["appearance"], label_visibility="collapsed",
                on_change=_apply("set_appearance", "appearance"))
            st.caption("Following the system matches macOS. Light or Dark "
                       "overrides it for this app only.")

            st.caption("Accent")
            st.segmented_control(
                "Accent", ACCENT_OPTIONS, key="set_accent",
                default=current["accent"], label_visibility="collapsed",
                format_func=lambda name: f"{_ACCENT_SWATCH.get(name, '')} {name}",
                on_change=_apply("set_accent", "accent"))
            st.caption("Used for the result, selected items and focus rings. "
                       "Every accent is checked for contrast in both themes.")

            left, right = st.columns(2)
            with left:
                st.caption("Density")
                st.segmented_control(
                    "Density", DENSITY_OPTIONS, key="set_density",
                    default=current["density"], label_visibility="collapsed",
                    on_change=_apply("set_density", "density"))
                st.caption("Compact tightens spacing and type to fit more on "
                           "a laptop screen.")
            with right:
                st.caption("Motion")
                st.segmented_control(
                    "Motion", MOTION_OPTIONS, key="set_motion",
                    default=current["motion"], label_visibility="collapsed",
                    on_change=_apply("set_motion", "motion"))
                st.caption("Your system's Reduce Motion setting always wins "
                           "over this.")

        with results:
            st.caption("Precision")
            st.segmented_control(
                "Precision", SIGNIFICANT_FIGURE_OPTIONS, key="set_figures",
                default=current["significant_figures"],
                format_func=lambda n: f"{n} digits",
                label_visibility="collapsed",
                on_change=_apply("set_figures", "significant_figures"))
            st.caption("Whole numbers are never truncated - 12,403 N stays "
                       "12,403 N at the lowest setting - so this mainly "
                       "affects decimals. The calculation itself is always "
                       "full precision.")

            st.toggle("Thousands separators",
                      value=current["thousands_separator"],
                      key="set_thousands",
                      on_change=_apply("set_thousands", "thousands_separator"),
                      help="12,403 rather than 12403.")

            st.divider()
            st.caption("**Assumptions are always shown under the result and "
                       "cannot be hidden.** Stating them is part of what makes "
                       "a number trustworthy.")

        with content:
            st.toggle("Variable definitions and worked examples",
                      value=current["show_reference"], key="set_reference",
                      on_change=_apply("set_reference", "show_reference"),
                      help="The reference block at the foot of each page.")
            st.toggle("'Where this is used' examples",
                      value=current["show_examples"], key="set_examples",
                      on_change=_apply("set_examples", "show_examples"),
                      help="Turn off once the equations are familiar.")

            st.divider()
            st.caption("On opening")
            st.segmented_control(
                "On opening", START_PAGE_OPTIONS, key="set_start",
                default=current["start_page"], label_visibility="collapsed",
                on_change=_apply("set_start", "start_page"))

            favourites = current.get("favourites", [])
            st.caption(
                f"{len(favourites)} favourite"
                f"{'' if len(favourites) == 1 else 's'}. Star a calculator "
                "from its page to pin it to the top of the sidebar.")

        with about:
            st.markdown(f"**ASCENT {version}**")
            st.caption(
                f"{calculator_count} calculators across {category_count} "
                "categories. For education and preliminary engineering "
                "calculations - critical designs must be independently "
                "verified.")
            st.divider()
            st.caption("Keyboard")
            st.markdown(
                "- `⌘K` — search every calculator\n"
                "- `⌘\\` — show or hide the sidebar\n"
                "- `⌘R` — reload · `⌘ +` / `⌘ -` — zoom")
            st.divider()
            st.caption(f"Settings and logs: `{SUPPORT_DIR}`")
            if st.button("Reset all settings", key="set_reset",
                         use_container_width=True):
                reset()
                for key in ("set_appearance", "set_accent", "set_density",
                            "set_motion", "set_figures", "set_thousands",
                            "set_reference", "set_examples", "set_start"):
                    st.session_state.pop(key, None)
                close()
                st.rerun()
            st.caption("Favourites are kept.")

    _dialog()
