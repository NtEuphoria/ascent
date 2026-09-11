"""User settings: persistence, validation, and their effect on the app."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils import settings  # noqa: E402


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """Point the settings module at a temporary file."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "SUPPORT_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "SETTINGS_PATH", str(path))
    return path


def test_defaults_when_no_file(settings_file):
    assert settings.load() == settings.DEFAULTS


def test_round_trip(settings_file):
    assert settings.save({"appearance": "Dark", "motion": "Reduced",
                          "significant_figures": 6, "show_reference": False})
    loaded = settings.load()
    assert loaded["appearance"] == "Dark"
    assert loaded["motion"] == "Reduced"
    assert loaded["significant_figures"] == 6
    assert loaded["show_reference"] is False


def test_invalid_values_fall_back_to_defaults(settings_file):
    settings.save({"appearance": "Neon", "motion": "Warp",
                   "significant_figures": 99, "show_reference": "yes"})
    loaded = settings.load()
    assert loaded == settings.DEFAULTS


def test_corrupt_file_does_not_raise(settings_file):
    settings_file.write_text("{not valid json at all", encoding="utf-8")
    assert settings.load() == settings.DEFAULTS


def test_unknown_keys_are_dropped(settings_file):
    settings_file.write_text(json.dumps({"appearance": "Dark",
                                         "secret_flag": True}), encoding="utf-8")
    loaded = settings.load()
    assert loaded["appearance"] == "Dark"
    assert "secret_flag" not in loaded


def test_reset_restores_defaults(settings_file):
    settings.save({"appearance": "Dark", "significant_figures": 6})
    settings.reset()
    assert settings.load() == settings.DEFAULTS


def test_assumptions_cannot_be_switched_off(settings_file):
    """Stating assumptions is an accuracy guarantee, not a preference."""
    assert "show_assumptions" not in settings.DEFAULTS
    settings_file.write_text(json.dumps({"show_assumptions": False}),
                             encoding="utf-8")
    assert "show_assumptions" not in settings.load()


def test_unwritable_location_reports_failure(tmp_path, monkeypatch):
    """A read-only settings folder must be reported, not silently swallowed."""
    monkeypatch.setattr(settings, "SUPPORT_DIR", "/proc/nonexistent/ascent")
    monkeypatch.setattr(settings, "SETTINGS_PATH",
                        "/proc/nonexistent/ascent/settings.json")
    assert settings.save(dict(settings.DEFAULTS)) is False


# --------------------------------------------------------------------------
# Effect on the rendered app
# --------------------------------------------------------------------------
def test_theme_css_follows_appearance_setting():
    from utils import theme
    system = theme._tokens("Follow system", "Full")
    forced = theme._tokens("Dark", "Full")
    # Following the system keys off the media query and leaves Streamlit alone.
    assert "@media (prefers-color-scheme: dark)" in system
    assert ".stApp" not in system
    # Forcing a mode has to take over the chrome Streamlit paints itself.
    assert "@media (prefers-color-scheme: dark)" not in forced.split(
        "@media (prefers-reduced-motion")[0]
    assert ".stApp" in forced


def test_motion_setting_shortens_durations():
    from utils import theme
    assert "--a-d-base:0ms" in theme._tokens("Light", "None")
    assert "--a-d-base:70ms" in theme._tokens("Light", "Reduced")
    # The system preference always wins, whatever the app setting says.
    assert "prefers-reduced-motion" in theme._tokens("Light", "Full")


@pytest.fixture
def real_settings_file():
    """Swap the app's real settings file, restoring it afterwards.

    The app loads settings from a fixed path at start-up, so an end-to-end
    check has to go through that file rather than a monkeypatched module.
    """
    import shutil
    path = settings.SETTINGS_PATH
    backup = path + ".test-backup"
    existed = os.path.exists(path)
    if existed:
        shutil.copy2(path, backup)
    yield path
    if existed:
        shutil.move(backup, path)
    elif os.path.exists(path):
        os.remove(path)


def _headline(app_root):
    import re
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(app_root, "app.py"), default_timeout=120)
    at.run()
    html = " ".join(block.value for block in at.markdown)
    match = re.search(r'a-result-value">(.*?)<span', html)
    return match.group(1) if match else None


def test_significant_figures_change_the_displayed_result(real_settings_file):
    """The setting must actually reach the rendered number."""
    settings.save({"appearance": "Follow system", "motion": "Full",
                   "significant_figures": 4, "show_reference": True})
    assert _headline(ROOT) == "12,403"

    settings.save({"appearance": "Follow system", "motion": "Full",
                   "significant_figures": 6, "show_reference": True})
    assert _headline(ROOT) == "12,403.1"

    # Whole numbers are never truncated, so a lower setting cannot turn
    # 12,403 into 12,400. It affects decimals, not real precision.
    settings.save({"appearance": "Follow system", "motion": "Full",
                   "significant_figures": 3, "show_reference": True})
    assert _headline(ROOT) == "12,403"


def test_reference_toggle_hides_the_reference_block(real_settings_file):
    from streamlit.testing.v1 import AppTest

    def rendered():
        at = AppTest.from_file(os.path.join(ROOT, "app.py"),
                               default_timeout=120)
        at.run()
        return " ".join(block.value for block in at.markdown)

    settings.save({"appearance": "Follow system", "motion": "Full",
                   "significant_figures": 4, "show_reference": True})
    assert "Where this is used" in rendered()

    settings.save({"appearance": "Follow system", "motion": "Full",
                   "significant_figures": 4, "show_reference": False})
    shown = rendered()
    assert "Where this is used" not in shown
    # Assumptions must survive, whatever else is hidden.
    assert "Assumptions" in shown


# --------------------------------------------------------------------------
# Regressions from forcing a theme against the system
# --------------------------------------------------------------------------
def test_forced_theme_covers_html_and_body():
    """Overriding only .stApp leaves the document background in the other mode.

    It shows through on overscroll and is what the web view composites
    against, so a forced Light theme still looked dark around the edges.
    """
    from utils import theme
    for mode in ("Light", "Dark"):
        css = theme._tokens(mode, "Full")
        assert "html,body" in css.replace(" ", ""), f"{mode} misses html/body"


def test_sidebar_controls_are_token_coloured():
    """Streamlit draws these near-white, which vanishes on a light page.

    With no visible control there is no way to bring the sidebar back.
    """
    from utils import theme
    assert "stExpandSidebarButton" in theme._COMPONENTS
    assert "stSidebarCollapseButton" in theme._COMPONENTS
    # Applied always, not only when a theme is forced - the icon has to be
    # legible whichever mode the app ends up in.
    assert "stExpandSidebarButton" not in theme._CHROME_OVERRIDE


def test_charts_take_over_when_a_theme_is_forced():
    """Streamlit themes charts from its frontend, which follows the OS.

    Following the system is correct when the app follows it too, and wrong the
    moment the user forces a mode - the chart keeps the other mode's colours.
    """
    from utils import charts
    assert set(charts._CHART_LIGHT) == set(charts._CHART_DARK)
    for key in ("text", "title", "grid", "domain"):
        assert charts._CHART_LIGHT[key] != charts._CHART_DARK[key]


def test_matplotlib_plots_are_mode_neutral():
    """The remaining matplotlib plots cannot adapt after they are rasterised.

    They are drawn transparent with a mid-grey ink that reads on both a white
    and a near-black page instead.
    """
    from utils import plotting
    assert plotting.FACE == "none"
    assert plotting.INK == plotting.MUTED
