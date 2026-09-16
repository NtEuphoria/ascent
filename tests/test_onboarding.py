"""First-run setup.

The thing that must never break here is the exit: an onboarding flow that can
strand someone, or that reappears after it was completed, is worse than no
onboarding at all.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

from utils import announce, onboarding, settings  # noqa: E402
from utils.onboarding import DISCIPLINES, MAX_PINNED, pinned_for  # noqa: E402

APP_PATH = os.path.join(ROOT, "app.py")


def _first_run(settings_path):
    """An app started with no settings file at all.

    That is what a real first launch looks like: the native shell creates the
    support directory for its log before Python starts, so the directory is
    there and the file is not. Every other test in this suite runs with
    onboarded already true, which is why none of them can catch a first run
    that has stopped working.
    """
    if os.path.exists(settings_path):
        os.remove(settings_path)
    at = AppTest.from_file(APP_PATH, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def _finish_setup(at):
    """Click straight through setup, accepting every default."""
    for step in range(len(onboarding.STEPS)):
        forward = [b for b in at.button if b.key == "ob_next_%d" % step]
        assert forward, "step %d has no forward button; found %s" % (
            step, [b.key for b in at.button])
        forward[0].click().run()
        assert not at.exception, at.exception
    return at


# --------------------------------------------------------------------------
# When it runs
# --------------------------------------------------------------------------
def test_a_fresh_install_gets_setup():
    assert onboarding.needed({})
    assert onboarding.needed({"onboarded": False})


def test_it_never_comes_back_once_finished():
    assert not onboarding.needed({"onboarded": True})


def test_resetting_settings_does_not_resurrect_it(real_settings_file):
    """Reset restores preferences. Never having opened the app is not a
    preference, and being marched back through setup for changing your mind
    about an accent would be infuriating."""
    settings.save({"onboarded": True, "accent": "Amber"})
    settings.reset()
    assert settings.load()["onboarded"] is True
    assert settings.load()["accent"] == "Blue"


def test_the_flag_survives_a_save_and_load_round_trip(real_settings_file):
    settings.save({"onboarded": True})
    assert settings.load()["onboarded"] is True


# --------------------------------------------------------------------------
# What the discipline step actually does
# --------------------------------------------------------------------------
def test_picking_nothing_pins_nothing():
    assert pinned_for([]) == []


def test_one_discipline_pins_its_own_calculators():
    pins = pinned_for(["Structures & materials"])
    assert pins and all(p.startswith(("struct.", "materials.")) for p in pins)


def test_several_disciplines_are_interleaved_not_concatenated():
    """Picking three fields should give a spread across all three, not the
    whole of the first followed by the whole of the second."""
    pins = pinned_for(["Aerodynamics & flight", "Robotics & control",
                       "Electronics & power"])
    assert pins[0].startswith("aero.")
    assert pins[1].startswith("robot.")
    assert pins[2].startswith("elec.")


def test_the_shortlist_stays_short():
    """Favourites are meant to be glanced at. Past about eight they are a
    second navigation tree."""
    assert len(pinned_for(list(DISCIPLINES))) <= MAX_PINNED


def test_overlapping_disciplines_do_not_pin_a_duplicate():
    """Several fields share a calculator - motor constants belongs to both
    propulsion and electronics."""
    pins = pinned_for(["Propulsion & rockets", "Electronics & power"])
    assert len(pins) == len(set(pins))


def test_an_unknown_discipline_is_ignored_rather_than_raising():
    assert pinned_for(["Underwater basket weaving"]) == []


# --------------------------------------------------------------------------
# Every pinned slug must exist
# --------------------------------------------------------------------------
def test_every_discipline_pins_only_real_calculators():
    """A favourite pointing at a slug that does not exist is a dead row in the
    sidebar, and the user has no way to tell why."""
    import app
    from utils.spec import normalise

    real = {calc.slug for category, entry in app.CATEGORIES.items()
            for calc in normalise(entry, category)}
    for discipline, slugs in DISCIPLINES.items():
        missing = [slug for slug in slugs if slug not in real]
        assert not missing, f"{discipline} pins non-existent {missing}"


@pytest.mark.parametrize("discipline", sorted(DISCIPLINES))
def test_every_discipline_offers_something(discipline):
    assert len(DISCIPLINES[discipline]) >= 3


def test_the_panels_cover_every_declared_step():
    assert set(onboarding._PANELS) == set(onboarding.STEPS)


def test_setup_pins_exactly_as_many_as_the_sidebar_shows():
    """It promised eight and the sidebar displayed five. A count on the last
    screen of setup is the first number the app ever tells you."""
    assert MAX_PINNED == settings.SIDEBAR_FAVOURITES
    assert len(pinned_for(list(DISCIPLINES))) == settings.SIDEBAR_FAVOURITES


def test_setup_can_be_run_again_from_settings(real_settings_file):
    """Otherwise it is a screen you see once, on a machine you have already
    configured, with no way back to a choice made in twenty seconds."""
    settings.save({"onboarded": True})
    settings.update(onboarded=False)
    assert onboarding.needed(settings.load())
    assert "set_onboard" in open("utils/settings.py", encoding="utf-8").read()


# --------------------------------------------------------------------------
# The whole first run, end to end
#
# These are the only tests in the suite that start from no settings file.
# conftest writes onboarded=True before every other test, which is what makes
# the app testable at all - and what makes a broken first run invisible.
# --------------------------------------------------------------------------
def test_a_brand_new_user_gets_setup(real_settings_file):
    at = _first_run(real_settings_file)
    assert "Welcome to ASCENT" in " ".join(b.value for b in at.markdown)


def test_setup_is_the_only_thing_on_screen(real_settings_file):
    """Two first-run interruptions must not stack. The sidebar is not drawn
    during setup, so the Studios card cannot appear behind or beside it."""
    at = _first_run(real_settings_file)
    keys = {b.key for b in at.button}
    assert "ann_open" not in keys, "the Studios card is competing with setup"
    assert "settings_open" not in keys, "the sidebar is being drawn during setup"


def test_finishing_setup_leads_to_the_studios_card(real_settings_file):
    """The point of the whole exercise: a new user sees setup, and then sees
    what Studios is. The card is drawn by app.py, so this breaks if the call
    site is moved or lost - which no unit test on announce.needed would show."""
    at = _finish_setup(_first_run(real_settings_file))
    keys = {b.key for b in at.button}
    assert "ann_open" in keys, "no Studios card after setup; found %s" % sorted(
        k for k in keys if k)
    assert "ann_dismiss" in keys


def test_setup_does_not_come_back_after_it_is_finished(real_settings_file):
    at = _finish_setup(_first_run(real_settings_file))
    assert "Welcome to ASCENT" not in " ".join(b.value for b in at.markdown)
    assert {b.key for b in at.button} & {"settings_open"}, "the app did not draw"


def test_finishing_setup_does_not_silently_dismiss_the_announcement(
        real_settings_file):
    """_finish() writes onboarded and favourites. If it ever wrote the whole
    settings dict instead, it would take studios_announced with it and the
    card would never be shown to anyone who completed setup."""
    _finish_setup(_first_run(real_settings_file))
    saved = json.load(open(real_settings_file, encoding="utf-8"))
    assert saved["onboarded"] is True
    assert saved["studios_announced"] is False
    assert announce.needed(saved)


def test_the_card_stays_gone_once_dismissed(real_settings_file):
    """An announcement that reappears is an advertisement."""
    at = _finish_setup(_first_run(real_settings_file))
    [b for b in at.button if b.key == "ann_dismiss"][0].click().run()
    assert not at.exception, at.exception
    assert "ann_open" not in {b.key for b in at.button}
    saved = json.load(open(real_settings_file, encoding="utf-8"))
    assert saved["studios_announced"] is True

    # And not on the next launch either.
    again = AppTest.from_file(APP_PATH, default_timeout=120)
    again.run()
    assert not again.exception
    assert "ann_open" not in {b.key for b in again.button}


def test_the_card_needs_its_artwork_to_be_shipped():
    """The hero image lives outside the Python packages, so it is copied into
    the bundle by a separate rule in build.sh. Without it the card still draws,
    but as text - which is not what was designed."""
    assert announce.hero_path(), (
        "assets/studios-hero.png is missing from the source tree")
