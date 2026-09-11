"""Command palette search and ranking."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import CATEGORIES  # noqa: E402
from utils import palette  # noqa: E402
from utils.spec import normalise  # noqa: E402


def catalogue():
    return [(category, calc)
            for category, entry in CATEGORIES.items()
            for calc in normalise(entry, category)]


def names(results):
    return [calc.name for _, calc in results]


def test_empty_query_returns_everything():
    items = catalogue()
    assert palette.search(items, "") == items
    assert palette.search(items, "   ") == items


def test_finds_by_name_fragment():
    found = names(palette.search(catalogue(), "hov"))
    assert "Hover thrust per motor" in found


def test_prefix_match_ranks_above_buried_match():
    """Typing 'drag' should offer Drag before Lift-to-drag ratio."""
    found = names(palette.search(catalogue(), "drag"))
    assert found.index("Drag") < found.index("Lift-to-drag ratio")


def test_finds_by_keyword_not_in_the_name():
    # "aerofoil" appears only in the Lift spec's keywords.
    assert "Lift" in names(palette.search(catalogue(), "aerofoil"))
    # "vstall" is a keyword on Stall speed.
    assert "Stall speed" in names(palette.search(catalogue(), "vstall"))


def test_finds_by_category():
    found = palette.search(catalogue(), "materials")
    assert found and all(category == "Materials" for category, _ in found)


def test_case_insensitive():
    assert names(palette.search(catalogue(), "REYNOLDS")) == \
        names(palette.search(catalogue(), "reynolds"))


def test_no_match_returns_nothing():
    assert palette.search(catalogue(), "zzzznotathing") == []


def test_every_calculator_is_reachable():
    """Typing a calculator's own name must always surface it."""
    items = catalogue()
    for category, calc in items:
        found = names(palette.search(items, calc.name.lower()))
        assert calc.name in found, f"{calc.name} unreachable from the palette"


def test_palette_navigation_mechanism():
    """Selecting a palette result must actually change the page.

    The palette navigates by writing the nav widgets' session-state keys before
    those widgets are rebuilt. This checks that contract end to end rather than
    trusting it, since a rename of either key would break the palette silently
    while every other test still passed.
    """
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120)
    at.run()

    # Exactly what utils/palette.open_dialog does on a result click.
    at.session_state["nav_category"] = "Rotational mechanics"
    at.session_state["nav_equation::Rotational mechanics"] = "Centripetal force"
    at.run()

    assert not at.exception
    assert at.sidebar.selectbox[0].value == "Rotational mechanics"
    assert at.sidebar.radio[0].value == "Centripetal force"
    rendered = " ".join(block.value for block in at.markdown)
    assert "Centripetal force" in rendered
