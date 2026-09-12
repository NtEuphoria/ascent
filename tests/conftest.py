"""Test-wide setup.

The settings store is redirected before anything imports utils.settings, so
the suite never reads or writes the real one. Without this, a headless render
picks up whatever appearance, accent and last page the person running the
tests happened to leave the app on - and once first-run setup existed, a
fresh machine failed every AppTest by showing the welcome screen instead of
the app.
"""
from __future__ import annotations

import json
import os
import tempfile

_STORE = tempfile.mkdtemp(prefix="ascent-test-settings-")
os.environ["ASCENT_SETTINGS_DIR"] = _STORE

# A known starting state: defaults, already past setup.
with open(os.path.join(_STORE, "settings.json"), "w", encoding="utf-8") as handle:
    json.dump({"onboarded": True}, handle)


import pytest  # noqa: E402

# Imported after ASCENT_SETTINGS_DIR is set above, so it resolves the
# redirected path rather than the real one.
from utils import settings  # noqa: E402


@pytest.fixture(autouse=True)
def clean_project():
    """Every test starts with no project.

    Without this, a test that saves parameters and bindings leaves them in the
    shared store, and every later end-to-end render draws a different page -
    bound inputs instead of number boxes, plus a link panel - which shifts
    every widget index the app tests address by position.
    """
    path = os.path.join(_STORE, "project.json")
    if os.path.exists(path):
        os.remove(path)
    # Visiting a page records it as the last one, in the same shared store, so
    # one test's navigation would decide where the next test starts.
    settings_path = os.path.join(_STORE, "settings.json")
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump({"onboarded": True}, handle)
    yield
    if os.path.exists(path):
        os.remove(path)


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


def goto(category, app_path=None):
    """A fresh AppTest already navigated to `category`.

    Fresh rather than mutating a running one. AppTest serialises the previous
    run's widgets before each new run, so pointing an existing test at a
    category outside the currently-rendered section raises while validating the
    stale category dropdown - which no longer even exists in a section holding
    one category.

    Only the section and the category are set; the equation follows from them,
    the same way a restored page or a deep link works in the app.
    """
    import os

    from streamlit.testing.v1 import AppTest

    import app

    if app_path is None:
        app_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app.py")
    at = AppTest.from_file(app_path, default_timeout=120)
    at.session_state["nav_mode"] = app.mode_of_category().get(category,
                                                              "Calculators")
    at.session_state["nav_category"] = category
    at.run()
    return at
