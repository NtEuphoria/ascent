"""End-to-end render tests.

Streamlit's AppTest runs app.py headlessly and executes every widget call, so
these catch layout errors, bad widget arguments, broken imports and plotting
failures that a pure-function test cannot see.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

from app import CATEGORIES  # noqa: E402
from utils.spec import normalise  # noqa: E402


def calculator_names(category):
    """The menu labels for a category.

    Derived through the same normalise() the app uses, so these tests do not
    care whether a module has been converted to declarative specs yet.
    """
    return [calc.name for calc in normalise(CATEGORIES[category], category)]

APP_PATH = os.path.join(ROOT, "app.py")


def _fresh_app():
    at = AppTest.from_file(APP_PATH, default_timeout=120)
    at.run()
    return at


def test_app_starts_without_error():
    at = _fresh_app()
    assert not at.exception
    rendered = " ".join(block.value for block in at.markdown)
    assert "ASCENT" in rendered
    assert "Aerospace" in rendered and "Structures" in rendered


@pytest.mark.parametrize("category", list(CATEGORIES.keys()))
def test_every_calculator_in_category_renders(category):
    """Select each equation in turn and confirm the page renders cleanly."""
    at = _fresh_app()
    at.sidebar.selectbox[0].set_value(category).run()
    assert not at.exception, f"selecting category {category} raised"

    for name in calculator_names(category):
        at.sidebar.radio[0].set_value(name).run()
        assert not at.exception, f"{category} / {name} raised an exception"
        assert not at.error, f"{category} / {name} reported an input error " \
                             f"with default values: {[e.value for e in at.error]}"


@pytest.mark.parametrize("category", list(CATEGORIES.keys()))
def test_graphs_render(category):
    """Tick every 'Show graph' checkbox and confirm the plot code runs."""
    at = _fresh_app()
    at.sidebar.selectbox[0].set_value(category).run()
    for name in calculator_names(category):
        at.sidebar.radio[0].set_value(name).run()
        for checkbox in at.checkbox:
            if checkbox.label == "Show graph":
                checkbox.set_value(True).run()
                assert not at.exception, f"graph for {category} / {name} raised"


def test_reset_button_restores_defaults():
    at = _fresh_app()          # opens on Aerodynamics / Lift
    velocity = at.number_input(key="aero_lift_v")
    assert velocity.value == pytest.approx(50.0)

    at.number_input(key="aero_lift_v").set_value(123.0).run()
    assert at.number_input(key="aero_lift_v").value == pytest.approx(123.0)

    at.button(key="reset::aero_lift").click().run()
    assert at.number_input(key="aero_lift_v").value == pytest.approx(50.0)


def test_invalid_input_shows_message_not_a_number():
    """A zero wing area must produce an error message, never a bogus result."""
    at = _fresh_app()
    at.number_input(key="aero_lift_s").set_value(0.0).run()
    assert not at.exception
    assert at.error, "expected a validation message for zero wing area"
    assert "greater than zero" in at.error[0].value


def test_switching_category_keeps_navigation_valid():
    at = _fresh_app()
    for category in list(CATEGORIES.keys()):
        at.sidebar.selectbox[0].set_value(category).run()
        assert not at.exception
        assert at.sidebar.radio[0].value in calculator_names(category)
