"""The Studios introduction card.

The behaviour that matters is that it goes away and stays away. An
announcement that reappears is an advertisement, and this one sits in the
sidebar of a tool people open every day.
"""
from __future__ import annotations

import os


from conftest import goto
from utils import announce, settings


# --------------------------------------------------------------------------
# When it shows
# --------------------------------------------------------------------------
def test_a_fresh_install_sees_it():
    assert announce.needed({})
    assert announce.needed({"studios_announced": False})


def test_it_never_returns_once_read():
    assert not announce.needed({"studios_announced": True})


def test_dismissing_it_persists(real_settings_file):
    settings.save({"onboarded": True, "studios_announced": False})
    announce.dismiss()
    assert settings.load()["studios_announced"] is True


def test_resetting_settings_does_not_bring_it_back(real_settings_file):
    """Reset restores preferences. Having already read an announcement is not
    a preference, and being shown it again for changing an accent would be
    exactly the behaviour that makes people stop reading them."""
    settings.save({"onboarded": True, "studios_announced": True})
    settings.reset()
    assert settings.load()["studios_announced"] is True


# --------------------------------------------------------------------------
# The hero
# --------------------------------------------------------------------------
def test_the_hero_is_a_local_file_never_a_url():
    """The app is expected to run offline, so the card cannot depend on a
    request succeeding."""
    path = announce.hero_path()
    if path is not None:
        assert not path.startswith(("http://", "https://"))
        assert os.path.isfile(path)


def test_no_hero_when_none_is_supplied(monkeypatch):
    """The card still works with no artwork - it just carries its own
    headline instead."""
    monkeypatch.setattr(announce, "HERO_PNG", "/nonexistent/hero.png")
    assert announce.hero_path() is None


def test_a_supplied_image_is_used(tmp_path, monkeypatch):
    """Dropping a real photograph in is meant to need no code change."""
    path = tmp_path / "studios-hero.png"
    path.write_bytes(b"pretend png")
    monkeypatch.setattr(announce, "HERO_PNG", str(path))
    assert announce.hero_path() == str(path)


def test_the_headline_is_not_printed_twice(tmp_path, monkeypatch):
    """The supplied artwork already carries the name, so repeating it in text
    underneath says the same thing twice. Without artwork the card needs a
    headline of its own."""
    source = open(announce.__file__, encoding="utf-8").read()
    assert 'heading = "" if picture' in source


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------
def test_it_says_what_a_studio_actually_is():
    """The reason the card exists: the icon says where Studios is and nothing
    says what it is for."""
    body = announce.BODY.lower()
    assert "calculator" in body and "studio" in body
    assert "verdict" in body


def test_the_card_is_short_enough_for_a_sidebar():
    assert len(announce.BODY) < 320, "too long to read in a 220px column"


# --------------------------------------------------------------------------
# In the app
# --------------------------------------------------------------------------
def test_the_card_appears_in_the_sidebar_when_pending(real_settings_file):
    settings.save({"onboarded": True, "studios_announced": False})
    at = goto("Aerodynamics")
    labels = [button.label for button in at.sidebar.button]
    assert "Open Studios" in labels and "Not now" in labels


def test_the_card_is_absent_once_read(real_settings_file):
    settings.save({"onboarded": True, "studios_announced": True})
    at = goto("Aerodynamics")
    labels = [button.label for button in at.sidebar.button]
    assert "Open Studios" not in labels
