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
