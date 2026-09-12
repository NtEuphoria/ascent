"""First-run setup.

The thing that must never break here is the exit: an onboarding flow that can
strand someone, or that reappears after it was completed, is worse than no
onboarding at all.
"""
from __future__ import annotations

import pytest

from utils import onboarding, settings
from utils.onboarding import DISCIPLINES, MAX_PINNED, pinned_for


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
