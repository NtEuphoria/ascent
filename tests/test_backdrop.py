"""The generative backdrop.

Most of this is a canvas in an iframe and cannot be asserted on from Python.
What can be checked is everything that would quietly break the app rather than
the artwork: an external request that fails offline, a layer that swallows
clicks, motion that ignores the setting, and the physics being wrong in a way
that looks fine until someone who knows fluid mechanics sees it.
"""
from __future__ import annotations

import math
import re

from utils import backdrop, theme


def _doc(motion="Full"):
    return backdrop._document("#4a90d9", "#e6edf6", motion == "None")


# --------------------------------------------------------------------------
# It has to work on a machine that has never been online
# --------------------------------------------------------------------------
def test_the_backdrop_loads_nothing_from_the_network():
    """The app builds its environment on first launch and is expected to run
    offline afterwards. A CDN script tag here would leave a blank rectangle on
    a plane, at a conference, or behind a firewall."""
    doc = _doc()
    assert "http://" not in doc and "https://" not in doc
    assert "cdn" not in doc.lower()
    assert doc.count("<script>") == 1 and "src=" not in doc


def test_no_library_is_required():
    for library in ("three", "p5", "d3", "gsap", "anime"):
        assert f"{library}.min.js" not in _doc()


# --------------------------------------------------------------------------
# It must not take the app's input
# --------------------------------------------------------------------------
def test_the_panel_still_receives_clicks():
    """The backdrop needs pointer events to be a probe rather than a picture,
    which means turning them off on the app container - and that would make
    every button on the setup screen dead if the panel were not turned back
    on."""
    assert '[data-testid="stMain"]{pointer-events:none;}' in backdrop.LAYER_CSS
    assert '.block-container{pointer-events:auto;}' in backdrop.LAYER_CSS


def test_the_backdrop_takes_no_space_in_the_layout():
    """Streamlit reserves the height an element asks for. Left alone, the
    iframe pushes the panel down the page by its own height."""
    assert backdrop.HEIGHT <= 1
    assert "height:0" in backdrop.LAYER_CSS
    assert "position:fixed" in backdrop.LAYER_CSS


def test_it_sits_behind_the_content():
    assert "z-index:0" in backdrop.LAYER_CSS


# --------------------------------------------------------------------------
# Motion
# --------------------------------------------------------------------------
def test_motion_none_renders_one_static_frame():
    assert "STILL = true;" in _doc("None")
    assert "STILL = false;" in _doc("Full")


def test_the_system_preference_is_honoured_even_on_full():
    """A slower drift is still drift. The honest answer to reduce-motion is to
    stop, and the OS preference wins over the app's own setting."""
    doc = _doc("Full")
    assert "prefers-reduced-motion" in doc
    assert "requestAnimationFrame(frame)" in doc
    reduced = doc.split("if (reduce)", 1)[1].split("else", 1)[0]
    assert "draw()" in reduced and "requestAnimationFrame" not in reduced


# --------------------------------------------------------------------------
# The physics
# --------------------------------------------------------------------------
def test_the_vortex_uses_the_coefficient_from_the_potential():
    """w = (i*Gamma/2pi)ln(z) gives a swirl of Gamma/(2*pi*r^2). It shipped as
    Gamma/2 first - pi times too strong - and circulation then overwhelmed the
    free stream, so the field read as a vortex instead of flow past a body."""
    coefficient = float(re.search(r"var swirl = GAMMA \* ([\d.]+) \* inv;",
                                  _doc()).group(1))
    assert coefficient == round(1.0 / (2.0 * math.pi), 7)


def test_the_stagnation_points_stay_on_the_body():
    """The real constraint on circulation, and the one that decides whether
    this looks like a lifting body or a detached vortex.

    For a cylinder with circulation the stagnation points sit at
    sin(theta) = -Gamma/(4*pi*U*a). Past Gamma = 4*pi*U*a there is no solution
    on the surface, both points leave the body, and the picture stops being
    flow past anything. Staying well below it also keeps the asymmetry between
    the upper and lower streamlines visible - and that asymmetry is the lift.
    """
    doc = _doc()
    u = float(re.search(r"var U = ([\d.]+)", doc).group(1))
    gamma = float(re.search(r"GAMMA = ([\d.]+)", doc).group(1))
    a = float(re.search(r"A = ([\d.]+)", doc).group(1))
    critical = 4 * math.pi * u * a
    assert gamma < critical, "circulation past critical: no stagnation point"
    # Comfortably inside, but strong enough that the asymmetry reads.
    assert 0.15 < gamma / critical < 0.60


def test_the_singularity_is_floored_at_the_body_radius():
    """1/r^2 runs away inside the body. A particle that strayed in took one
    enormous step and drew a straight line across the whole screen."""
    doc = _doc()
    assert "var floor = a * a;" in doc
    assert "if (r2 < floor) r2 = floor;" in doc
    assert "cap / speed" in doc          # and a second limit on step length


def test_depth_is_a_perspective_divide_not_a_layer_trick():
    """Radius, opacity and parallax all come off one distance term, which is
    what makes it read as a volume rather than as stacked planes."""
    doc = _doc()
    assert "FOCAL / (FOCAL + z)" in doc or "FOCAL / (FOCAL + p.z)" in doc
    assert "(s * s)" in doc              # opacity falls off with distance


def test_the_pointer_probe_decays():
    """A disturbance that never relaxes is a smear that accumulates."""
    doc = _doc()
    decay = float(re.search(r"probe\.strength \*= ([\d.]+);", doc).group(1))
    assert 0.90 < decay < 0.99


# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------
def test_the_decorative_frame_carries_no_tooltip():
    """Streamlit titles its component iframe "st.iframe".

    The backdrop covers the whole viewport with pointer events enabled, so that
    title surfaced as a native tooltip reading "st.iframe" whenever the pointer
    sat anywhere outside the panel - on the first screen anyone ever sees. The
    frame is decoration, so the title is dropped rather than reworded, and it
    is taken out of the accessibility tree instead.
    """
    doc = backdrop._document("#7ab3e8", "#e6edf6", False)
    assert "removeAttribute('title')" in doc
    assert "aria-hidden" in doc
    assert "tabindex" in doc


def test_the_tooltip_fix_cannot_take_the_backdrop_down_with_it():
    """It reaches into the parent document, which is exactly the kind of thing
    that throws when a browser decides the frame is cross-origin. Wrapped, and
    placed so a failure cannot stop the canvas being set up."""
    doc = backdrop._document("#7ab3e8", "#e6edf6", False)
    # The access itself, not the comment above it explaining why it is there.
    fix = doc.index("window.frameElement")
    assert "try {" in doc[:fix], "the frameElement access is not inside a try"
    assert "catch" in doc[fix:doc.index("getElementById('c')")], (
        "no catch between the frameElement access and the canvas setup")
    # The canvas still has to be built after it, or the artwork never appears.
    assert doc.index("getElementById('c')") > fix


def test_colours_are_injected_because_an_iframe_cannot_read_them():
    """A separate document cannot see the parent's custom properties, so the
    resolved values have to be passed in."""
    doc = backdrop._document("#abcdef", "#123456", False)
    assert "'#abcdef'" in doc and "'#123456'" in doc


def test_every_accent_can_drive_it():
    for name, modes in theme.ACCENTS.items():
        for mode in ("light", "dark"):
            colour = modes[mode][0]
            assert f"'{colour}'" in backdrop._document(colour, "#000000", False)
