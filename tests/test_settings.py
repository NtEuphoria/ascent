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
    settings.save({"onboarded": True,
                   "appearance": "Follow system", "motion": "Full",
                   "significant_figures": 4, "show_reference": True})
    assert _headline(ROOT) == "12,403"

    settings.save({"onboarded": True,
                   "appearance": "Follow system", "motion": "Full",
                   "significant_figures": 6, "show_reference": True})
    assert _headline(ROOT) == "12,403.1"

    # Whole numbers are never truncated, so a lower setting cannot turn
    # 12,403 into 12,400. It affects decimals, not real precision.
    settings.save({"onboarded": True,
                   "appearance": "Follow system", "motion": "Full",
                   "significant_figures": 3, "show_reference": True})
    assert _headline(ROOT) == "12,403"


def test_reference_toggle_hides_the_reference_block(real_settings_file):
    from streamlit.testing.v1 import AppTest

    def rendered():
        at = AppTest.from_file(os.path.join(ROOT, "app.py"),
                               default_timeout=120)
        at.run()
        return " ".join(block.value for block in at.markdown)

    settings.save({"onboarded": True,
                   "appearance": "Follow system", "motion": "Full",
                   "significant_figures": 4, "show_reference": True})
    assert "Where this is used" in rendered()

    settings.save({"onboarded": True,
                   "appearance": "Follow system", "motion": "Full",
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


# --------------------------------------------------------------------------
# Expanded settings
# --------------------------------------------------------------------------
def test_every_accent_defines_both_modes():
    """A colour legible on white is rarely legible on near-black."""
    from utils import theme
    for name, modes in theme.ACCENTS.items():
        assert set(modes) == {"light", "dark"}, name
        for mode, values in modes.items():
            assert len(values) == 4, f"{name}/{mode} needs 4 accent tokens"
            assert values[0] != modes["dark" if mode == "light" else "light"][0], \
                f"{name} uses the same hex in both modes"


def test_accent_choice_changes_the_emitted_tokens():
    from utils import theme
    blue = theme._tokens("Light", "Full", "Blue", "Comfortable")
    amber = theme._tokens("Light", "Full", "Amber", "Comfortable")
    assert blue != amber
    assert "#1f4e79" in blue and "#8a5a00" in amber


def test_compact_density_only_touches_spacing_and_type():
    """Density must never shrink hit targets, only rhythm."""
    from utils import theme
    compact = set(theme.DENSITY["Compact"])
    assert compact <= set(theme.SCALE), "compact introduces unknown tokens"
    assert all(key.startswith(("s", "t-")) for key in compact)
    assert not any(key.startswith("r-") for key in compact)   # radii untouched


def test_invalid_accent_and_density_fall_back(settings_file):
    settings.save({"accent": "Neon", "density": "Enormous"})
    loaded = settings.load()
    assert loaded["accent"] == "Blue"
    assert loaded["density"] == "Comfortable"


def test_favourites_toggle_and_persist(settings_file):
    assert settings.toggle_favourite("aero.lift") is True
    assert settings.load()["favourites"] == ["aero.lift"]
    assert settings.toggle_favourite("aero.lift") is False
    assert settings.load()["favourites"] == []


def test_recents_are_most_recent_first_and_capped(settings_file):
    for slug in ("a.one", "b.two", "c.three", "d.four", "e.five", "f.six",
                 "g.seven", "h.eight"):
        settings.record_visit(slug)
    recents = settings.load()["recents"]
    assert recents[0] == "h.eight"
    assert len(recents) <= settings.MAX_RECENTS
    assert len(recents) == len(set(recents))


def test_revisiting_moves_a_calculator_to_the_front(settings_file):
    settings.record_visit("a.one")
    settings.record_visit("b.two")
    settings.record_visit("a.one")
    assert settings.load()["recents"][0] == "a.one"


def test_reset_keeps_favourites(settings_file):
    settings.toggle_favourite("aero.lift")
    settings.update(accent="Amber", density="Compact")
    settings.reset()
    loaded = settings.load()
    assert loaded["accent"] == "Blue"
    assert loaded["favourites"] == ["aero.lift"], "favourites are user data"


def test_corrupt_favourites_do_not_break_loading(settings_file):
    settings_file.write_text(json.dumps({"favourites": [1, None, "ok", "ok"]}),
                             encoding="utf-8")
    assert settings.load()["favourites"] == ["ok"]


def test_thousands_separator_setting():
    from utils.formatting import format_number, set_thousands_separator
    set_thousands_separator(True)
    assert format_number(12403.125) == "12,403"
    set_thousands_separator(False)
    assert format_number(12403.125) == "12403"
    set_thousands_separator(True)          # restore for other tests


# --------------------------------------------------------------------------
# Motion
# --------------------------------------------------------------------------
def _effective(css, token):
    """The value a browser would use: last declaration outside any @media."""
    import re
    outside = re.sub(r"@media[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", "", css)
    values = re.findall(rf"--a-{token}:([^;]+);", outside)
    return values[-1] if values else None


def test_motion_setting_scales_the_whole_system():
    """One setting has to govern every animation, not a subset."""
    from utils import theme
    assert _effective(theme._tokens("Light", "Full"), "d-slow") == "220ms"
    assert _effective(theme._tokens("Light", "Reduced"), "d-slow") == "110ms"
    assert _effective(theme._tokens("Light", "None"), "d-slow") == "0ms"


def test_system_reduce_motion_overrides_the_app_setting():
    """Someone who asked their machine to calm down gets no motion, period."""
    from utils import theme
    for choice in ("Full", "Reduced", "None"):
        css = theme._tokens("Light", choice)
        tail = css.split("prefers-reduced-motion")[-1]
        assert "--a-d-slow:0ms" in tail
        assert "--a-d-base:0ms" in tail


def test_no_animation_bypasses_the_duration_tokens():
    """A hardcoded duration is an animation the Motion setting cannot stop."""
    import re
    from utils import theme
    declarations = re.findall(r"(?:transition|animation):[^;]*;",
                              theme._COMPONENTS)
    hardcoded = [d for d in declarations
                 if re.search(r"\b\d+m?s\b", d) and "var(--a-d" not in d]
    assert not hardcoded, f"these bypass the motion setting: {hardcoded[:3]}"


def test_entrances_never_gate_visibility_on_an_animation():
    """If a frame never animates, the content still has to be there.

    A keyframe may start from opacity 0 - that is the animation. What must not
    exist is a plain rule leaving an element invisible at rest, waiting for an
    animation that might never fire.
    """
    import re
    from utils import theme

    body = theme._COMPONENTS
    # Remove whole at-rule blocks, not just their names: the `from{opacity:0}`
    # inside a keyframe is the animation, not a hidden element.
    body = re.sub(r"@(?:keyframes|starting-style)[^{]*\{(?:[^{}]|\{[^{}]*\})*\}",
                  "", body)
    # opacity:0 exactly - not the 0.45 of a dimmed stepper.
    risky = re.findall(r"[^{}]*\{[^{}]*opacity:0\s*[;}][^{}]*\}", body)
    assert not risky, f"content hidden at rest: {risky[:2]}"
    assert "@starting-style" in theme._COMPONENTS
