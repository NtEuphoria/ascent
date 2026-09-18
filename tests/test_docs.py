"""The documentation has to agree with the app.

Every number in this project's prose has been wrong at least once. The welcome
screen said seventy-eight calculators while the sidebar, the command palette
and the About tab all counted eighty-five. The README claimed sixty-eight
across thirteen categories, and 206 tests when there were several hundred more.
The slug catalogue listed one studio when six had shipped. The README's roadmap
promised three calculators that already existed, and its Limitations section
said Breguet range was deliberately left out while a Breguet page sat in the
Drones category.

None of that is caught by a test that renders a page, because every one of
those statements is perfectly valid prose. So the counts are asserted here
instead, against the registry rather than against each other.
"""
from __future__ import annotations

import inspect
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import CATEGORIES, MODES  # noqa: E402
from utils.spec import normalise  # noqa: E402

README = (ROOT / "README.md").read_text(encoding="utf-8")
SLUGS = (ROOT / "docs" / "SLUGS.md").read_text(encoding="utf-8")

TABLE = dict(re.findall(r"^\| \*\*([^*]+)\*\* \| (.+) \|$", README, re.MULTILINE))


def all_pages():
    for category, entries in CATEGORIES.items():
        for calc in normalise(entries, category):
            yield category, calc


def page_count() -> int:
    return sum(1 for _ in all_pages())


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------

def test_readme_states_the_real_number_of_calculators():
    """The headline claim under "What is included"."""
    match = re.search(r"\*\*(\d+) calculators across (\d+) categories\*\*", README)
    assert match, "the README no longer states a count in the expected form"
    assert int(match.group(1)) == page_count()
    assert int(match.group(2)) == len(CATEGORIES)


def test_readme_states_the_real_size_of_the_calculators_section():
    """The sidebar splits the app into three sections; the README says how big
    the largest one is, and that number is separate from the total."""
    match = re.search(r"\*\*Calculators\*\* — (\d+) pages", README)
    assert match, "the README no longer states the Calculators section size"
    expected = sum(len(normalise(CATEGORIES[c], c)) for c in MODES["Calculators"])
    assert int(match.group(1)) == expected


def test_readme_test_count_is_not_out_of_date():
    """Exact would mean editing the README on every test added, which is how it
    came to say 206. A floor keeps it honest without making it a chore."""
    match = re.search(r"(\d+) tests:", README)
    assert match, "the README no longer states a test count"
    collected = 0
    for path in (ROOT / "tests").glob("test_*.py"):
        collected += len(re.findall(r"^def test_", path.read_text(encoding="utf-8"),
                                    re.MULTILINE))
    # Parametrised cases mean the real total is well above the number of test
    # functions, so the claim must at least not undercut that floor.
    assert int(match.group(1)) >= collected, (
        "README claims %s tests but there are already %d test functions"
        % (match.group(1), collected))


# ---------------------------------------------------------------------------
# The slug catalogue
# ---------------------------------------------------------------------------

def test_every_slug_is_documented():
    """`related=[...]` is written by hand against this file, so a slug missing
    from it is a cross-link nobody will think to make."""
    listed = set(re.findall(r"`([^`]+)`", SLUGS))
    missing = sorted(calc.slug for _, calc in all_pages()
                     if calc.slug not in listed)
    assert not missing, "undocumented slugs: %s" % missing


def test_the_catalogue_lists_nothing_that_has_been_removed():
    """A slug that no longer exists is worse than one that is missing: it looks
    like a valid cross-link target right up until the page cannot be found."""
    real = {calc.slug for _, calc in all_pages()}
    listed = {token for token in re.findall(r"`([^`]+)`", SLUGS)
              if "." in token and " " not in token and "=" not in token}
    gone = sorted(listed - real)
    assert not gone, "slugs documented but gone: %s" % gone


def test_the_readme_category_table_matches_the_registry():
    """Every category gets a row, and every row names a real category."""
    for category in CATEGORIES:
        assert category in TABLE, "%s is missing from the README table" % category
    for name in TABLE:
        assert name in CATEGORIES, "README table lists a gone category: %s" % name


@pytest.mark.parametrize("category", list(CATEGORIES))
def test_each_table_row_lists_that_categorys_pages(category):
    listed = [part.strip() for part in TABLE[category].split(",")]
    for calc in normalise(CATEGORIES[category], category):
        if "," in calc.name:
            continue            # a comma in the name would split the cell
        assert calc.name in listed, (
            "%s / %s missing from the README table" % (category, calc.name))


# ---------------------------------------------------------------------------
# Claims that contradict shipped pages
# ---------------------------------------------------------------------------

def test_nothing_claims_a_shipped_calculator_is_missing():
    """Limitations said Breguet range was deliberately left out while
    calculators/drones.py had a Breguet page in it."""
    names = {calc.name.lower() for _, calc in all_pages()}
    assert any("range" in name for name in names), (
        "this guard assumes a range page exists; if it was removed, delete it")
    sources = ((README, "README"),
               ((ROOT / "calculators" / "flight.py").read_text(encoding="utf-8"),
                "flight.py"))
    for text, where in sources:
        lowered = text.lower()
        for claim in ("not included yet", "deliberately left out of version 1",
                      "deliberately not included"):
            assert claim not in lowered, (
                "%s still says a calculator is missing (%r) that now ships"
                % (where, claim))


def test_the_gatekeeper_instructions_are_the_ones_that_work():
    """Apple removed the right-click-to-Open bypass in macOS 15. Telling people
    to use it sends them round a loop that cannot succeed."""
    install = README[README.index("## Install"):README.index("## Run")]
    assert "Privacy & Security" in install
    assert "Open Anyway" in install
    # It may be mentioned as the outdated advice it is, but not given as the fix.
    assert "To allow it, **right-click" not in install


def test_the_streamlit_config_comment_is_true():
    """The README described config.toml as setting a light theme and an accent.
    The file says the opposite, at length: defining any [theme] key pins the
    app to one appearance and breaks following macOS."""
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    described = re.search(r"config\.toml\s+#\s*(.+)", README)
    assert described, "the README no longer describes config.toml"
    if re.search(r"^\[theme\]", config, re.MULTILINE) is None:
        claim = described.group(1).lower()
        assert "no [theme]" in claim or "deliberately" in claim, (
            "README says config.toml sets a theme; the file defines none")


# ---------------------------------------------------------------------------
# The first-run copy
# ---------------------------------------------------------------------------

def test_onboarding_does_not_hardcode_a_count():
    """It said "Seventy-eight" long enough for the number to be wrong in two
    separate panels. Whatever it says now has to come from the registry."""
    source = (ROOT / "utils" / "onboarding.py").read_text(encoding="utf-8")
    # The run() docstring explains the old bug; the panels themselves must not
    # contain a spelled-out number.
    panels = source[source.index("def _welcome"):source.index("def run(")]
    for spelled in ("seventy", "eighty", "sixty", "ninety"):
        assert spelled not in panels.lower(), (
            "a spelled-out count is back in the onboarding copy: %r" % spelled)


def test_every_onboarding_panel_takes_the_count():
    """The dispatch table calls them all with one signature, so a panel that
    forgot the parameter would raise only on the step that reaches it."""
    from utils import onboarding
    for step in onboarding.STEPS:
        params = list(inspect.signature(onboarding._PANELS[step]).parameters)
        assert params == ["prefs", "count"], "%s takes %s" % (step, params)


# ---------------------------------------------------------------------------
# Cross-links
#
# utils/render.py builds the Related tab with
#   [catalogue[slug] for slug in calc.related if slug in catalogue]
# so a slug naming no page is skipped in silence. Six of them had been dead for
# a while, pointing at electrical___robotics.* slugs from before that module
# took explicit ones - the links simply stopped appearing and nothing said so.
# ---------------------------------------------------------------------------

def test_every_cross_link_points_at_a_real_page():
    real = {calc.slug for _, calc in all_pages()}
    broken = sorted((calc.slug, target) for _, calc in all_pages()
                    for target in (calc.related or ()) if target not in real)
    assert not broken, "related= targets that name no page: %s" % broken


def test_no_page_links_to_itself():
    """A Related tab offering the page you are already on is noise."""
    loops = sorted(calc.slug for _, calc in all_pages()
                   if calc.slug in (calc.related or ()))
    assert not loops, "pages linking to themselves: %s" % loops


def test_cross_links_are_not_repeated():
    repeats = []
    for _, calc in all_pages():
        seen = set()
        for target in (calc.related or ()):
            if target in seen:
                repeats.append((calc.slug, target))
            seen.add(target)
    assert not repeats, "duplicated related= targets: %s" % repeats


def test_the_structure_tree_does_not_claim_unbuilt_features():
    """The tree described navigate.py as handling "deep links". It stages an
    in-app jump in session state; st.query_params appears nowhere in the app,
    so there is no URL to deep link with. A one-word description is still a
    claim."""
    tree = README[README.index("ascent/\n"):]
    tree = tree[:tree.index("```")]
    if "deep link" in tree.lower():
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "utils").glob("*.py"))
        assert "query_params" in sources, (
            "the structure tree promises deep links; nothing reads a URL parameter")
