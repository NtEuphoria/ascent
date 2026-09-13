"""Identity and colour invariants.

The colour work in this app has been done by eye once and corrected by
measurement twice. These tests do the measuring, so a token can never again be
nudged to a value that looks fine on this screen and fails WCAG AA on another.
"""
from __future__ import annotations

import re

import pytest

from utils import theme, ui

AA_SMALL = 4.5  # WCAG 2.2 contrast minimum for body-sized text


# ---------------------------------------------------------------------------
# Colour maths
# ---------------------------------------------------------------------------
def _parse(colour: str):
    """-> (r, g, b, a) with channels 0-255 and alpha 0-1."""
    colour = colour.strip()
    if colour.startswith("#"):
        h = colour[1:]
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    nums = [float(n) for n in re.findall(r"[\d.]+", colour)]
    r, g, b = nums[:3]
    return (r, g, b, nums[3] if len(nums) > 3 else 1.0)


def _over(fg: str, bg):
    """Composite a possibly-translucent colour over an opaque one."""
    fr, fg_, fb, fa = _parse(fg)
    br, bg_, bb, _ = bg
    return (fr * fa + br * (1 - fa),
            fg_ * fa + bg_ * (1 - fa),
            fb * fa + bb * (1 - fa), 1.0)


def _luminance(rgb):
    def channel(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg, bg):
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


# Every surface real text sits on, and what it sits on in turn. The result
# card is the subtle one: accent-soft is translucent, so its true background
# depends on the page beneath it.
def _surfaces(palette, accent_soft):
    page = _parse(palette["bg"])
    return {
        "bg": page,
        "raised": _over(palette["raised"], page),
        "sunken": _over(palette["sunken"], page),
        "accent-soft": _over(accent_soft, page),
    }


MODES = ("light", "dark")
INKS = ("ink", "ink-muted", "ink-faint")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("accent", sorted(theme.ACCENTS))
@pytest.mark.parametrize("ink", INKS)
def test_every_ink_clears_aa_on_every_surface(mode, accent, ink):
    palette = theme.LIGHT if mode == "light" else theme.DARK
    accent_soft = theme.ACCENTS[accent][mode][2]
    for name, bg in _surfaces(palette, accent_soft).items():
        ratio = _contrast(_over(palette[ink], bg), bg)
        assert ratio >= AA_SMALL, (
            f"{ink} on {name} in {mode}/{accent} is {ratio:.2f}:1")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("accent", sorted(theme.ACCENTS))
def test_accent_text_clears_aa(mode, accent):
    """accent-ink carries the wordmark, the spine initials and every heading
    marker, all of them at small sizes."""
    palette = theme.LIGHT if mode == "light" else theme.DARK
    _, accent_ink, accent_soft, _ = theme.ACCENTS[accent][mode]
    for name, bg in _surfaces(palette, accent_soft).items():
        ratio = _contrast(_over(accent_ink, bg), bg)
        assert ratio >= AA_SMALL, (
            f"accent-ink on {name} in {mode}/{accent} is {ratio:.2f}:1")


# ---------------------------------------------------------------------------
# The mark
# ---------------------------------------------------------------------------
def test_the_in_app_mark_is_the_same_shape_the_splash_draws():
    """One dart, three surfaces - icon, splash, and the header inside the app,
    all filled. If the Swift path is retouched and the SVG is not, the app you
    launch stops matching the app you land in."""
    swift = open("macos/main.swift", encoding="utf-8").read()
    body = swift[swift.index("let path = CGMutablePath()"):]
    body = body[:body.index("closeSubpath()")]
    appkit = [(float(x), float(y)) for x, y in
              re.findall(r"CGPoint\(x: ([\d.]+) \* s, y: ([\d.]+) \* s\)", body)]

    d = re.search(r'\sd="([^"]+)"', ui.MARK).group(1)
    svg = [(float(x), float(y)) for x, y in
           re.findall(r"([\d.]+) ([\d.]+)", d)]

    assert len(appkit) == 4 and len(svg) == 4
    # AppKit's y grows upward, SVG's grows downward, over the same 1024 box.
    assert svg == [(x, 1024 - y) for x, y in appkit]


def test_the_spine_spells_the_name():
    """The subtitle is not decoration - its initials are the wordmark."""
    import app

    spelled = ui._spell(app.ACRONYM)
    assert "".join(re.findall(r"<b>(.)</b>", spelled)) == app.TITLE


def test_light_and_dark_define_the_same_tokens():
    assert set(theme.LIGHT) == set(theme.DARK)


# ---------------------------------------------------------------------------
# Chart annotation placement
# ---------------------------------------------------------------------------
def _placement(x, y):
    """Where mark_point puts its label for a point on a 0-10 / 0-10 axes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from utils.plotting import mark_point

    fig, ax = plt.subplots()
    ax.plot([0, 10], [0, 10])
    mark_point(ax, x, y, "current")
    text = [a for a in ax.texts if a.get_text() == "current"][0]
    plt.close(fig)
    return text.get_ha(), text.get_va(), text.get_position()


def test_a_point_in_the_middle_labels_up_and_right():
    ha, va, (dx, dy) = _placement(5, 5)
    assert (ha, va) == ("left", "bottom") and dx > 0 and dy > 0


def test_a_point_at_the_top_labels_downward():
    """The ISA page's default altitude of 0 m lands here, under the title."""
    _, va, (_, dy) = _placement(0.2, 9.8)
    assert va == "top" and dy < 0


def test_a_point_at_the_right_edge_labels_leftward():
    ha, _, (dx, _) = _placement(9.8, 0.2)
    assert ha == "right" and dx < 0


def test_the_checkbox_accent_applies_in_every_appearance():
    """The forced-mode override does not run in "Follow system", so a rule
    that only lives there leaves checked boxes Streamlit red on a blue app."""
    rule = 'label[data-baseweb="checkbox"]:has(input:checked) > span:first-child'
    for appearance in ("Follow system", "Light", "Dark"):
        css = theme.stylesheet(appearance, "Full", "Blue", "Comfortable")
        assert rule in css, appearance
        block = css.split(rule, 1)[1].split("}", 1)[0]
        assert "var(--a-accent)" in block, appearance


def test_the_mark_never_follows_the_accent_setting():
    """An accent is a preference; a mark is an identity. Changing Amber in
    Settings must not repaint the dart amber."""
    blues = set()
    for accent in theme.ACCENTS:
        css = theme.stylesheet("Light", "Full", accent, "Comfortable")
        blues.add(css.split("--a-mark:", 1)[1].split(";", 1)[0])
    assert blues == {theme.LIGHT["mark"]}
    assert ".a-brand svg path{fill:var(--a-mark);}" in theme._COMPONENTS


# ---------------------------------------------------------------------------
# Widget keys
# ---------------------------------------------------------------------------
def test_two_graphs_over_the_same_input_get_distinct_keys():
    """Drag vs velocity and power-required vs velocity are both legitimate
    graphs of the same page over the same input. Keying the download button on
    the swept field alone made Streamlit refuse to render the page at all."""
    from utils.render import _download_series
    from utils.spec import Calculator, Sweep

    calc = Calculator(slug="a.b", name="n", latex="", explanation="")
    sweeps = [Sweep(over="v", y_label="y", title="one"),
              Sweep(over="v", y_label="y", title="two")]
    keys = set()
    for index, sweep in enumerate(sweeps):
        captured = {}

        def fake(label, data, file_name, mime, key):
            captured["key"] = key

        import streamlit as st
        original, st.download_button = st.download_button, fake
        try:
            _download_series(calc, sweep, None, [0.0, 1.0], [0.0, 1.0], index)
        finally:
            st.download_button = original
        keys.add(captured["key"])
    assert len(keys) == 2


# ---------------------------------------------------------------------------
# Motion reach
# ---------------------------------------------------------------------------
def _duration_tokens(css):
    """Every --a-d-* token declared in the base :root block."""
    base = css.split("}", 1)[0]
    return set(re.findall(r"(--a-d-[a-z]+):", base))


def test_every_duration_token_is_scaled_by_the_setting():
    """A token the Motion setting does not name is an animation the setting
    cannot stop. --a-d-draw shipped that way: the mark kept drawing itself
    with motion switched off, because only the four original tokens were
    listed in the overrides."""
    declared = _duration_tokens(theme._tokens("Dark", "Full"))
    assert declared, "no duration tokens found - the parser is wrong"
    for setting in ("Reduced", "None"):
        css = theme._tokens("Dark", setting)
        for token in declared:
            override = css.rsplit(f"{token}:", 1)[1].split(";")[0]
            assert override != "", f"{token} unset under Motion={setting}"
        if setting == "None":
            for token in declared:
                assert css.rsplit(f"{token}:", 1)[1].split(";")[0] == "0ms", \
                    f"{token} still animates with Motion=None"


def test_system_reduce_motion_reaches_every_duration_token():
    """The OS preference must win over the app setting for all of them, not
    just the ones that existed when the media query was written."""
    css = theme._tokens("Dark", "Full")
    declared = _duration_tokens(css)
    block = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    block = block.split("}", 1)[0]
    for token in declared:
        assert f"{token}:0ms" in block, f"{token} survives system reduce-motion"


# ---------------------------------------------------------------------------
# The influence bars
# ---------------------------------------------------------------------------
def _lift_influence_html():
    """Render the influence block for the Lift page and return its markup."""
    import streamlit as st

    from calculators import aerodynamics
    from utils.render import _influence_table
    from utils.spec import Inputs

    calc = next(c for c in aerodynamics.CALCULATORS if c.slug == "aero.lift")
    values = Inputs({f.key: f.default for f in calc.inputs})
    captured = []
    original_md, original_cap = st.markdown, st.caption
    st.markdown = lambda body, **kw: captured.append(body)
    st.caption = lambda body, **kw: captured.append(body)
    try:
        _influence_table(calc, values, calc.compute(values))
    finally:
        st.markdown, st.caption = original_md, original_cap
    return "".join(captured)


def test_the_influence_bars_are_drawn_not_typed():
    """They were a row of U+2588 in a markdown cell, which quantises the
    comparison to twelve steps and inherits the table's alignment."""
    html = _lift_influence_html()
    assert "█" not in html
    assert "a-inf-bar" in html and "--w:" in html


def test_the_bar_widths_are_proportional_to_the_elasticities():
    """Velocity is quadratic in the lift equation and everything else linear,
    so its bar must be exactly twice the others."""
    html = _lift_influence_html()
    widths = [float(w) for w in re.findall(r"--w:([\d.]+)%", html)]
    assert widths[0] == 100.0
    assert all(w == 50.0 for w in widths[1:])


def test_a_negative_influence_reads_as_a_direction_not_a_smaller_bar():
    """An input that pushes the result the other way is a different fact, not
    a weaker one - 43 pages in the catalogue have at least one."""
    assert ".a-inf-down i{background:var(--a-warning);}" in theme._COMPONENTS
    assert ".a-inf-up i{background:var(--a-accent);}" in theme._COMPONENTS


def test_bars_animate_by_transform_not_width():
    """Animating width reflows the page on every frame, once per row."""
    block = theme._COMPONENTS.split("@keyframes a-bar-grow", 1)[1].split("}", 1)[0]
    assert "scaleX" in block and "width" not in block


# ---------------------------------------------------------------------------
# The stylesheet is served inside a style element
# ---------------------------------------------------------------------------
def test_the_stylesheet_contains_no_less_than_sign():
    """A "less than" inside a style element ends it, as far as the HTML parser
    is concerned. Writing an img tag inside a CSS comment silently deleted
    everything after it: the app lost its entire stylesheet, rendered in
    Streamlit's defaults, and showed no sidebar at all - with no error
    anywhere, because the Python was perfectly valid.

    A "greater than" is fine; it is the CSS child combinator.
    """
    for appearance in ("Follow system", "Light", "Dark"):
        for accent in sorted(theme.ACCENTS):
            css = theme.stylesheet(appearance, "Full", accent, "Comfortable")
            assert "<" not in css, (
                f"{appearance}/{accent}: the stylesheet contains '<', which "
                f"terminates the style element and drops everything after it")


def test_the_stylesheet_has_no_style_tags_of_its_own():
    """inject() wraps it in one; a second opening tag inside would nest."""
    css = theme.stylesheet("Dark", "Full", "Blue", "Comfortable")
    assert "style>" not in css
