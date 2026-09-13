"""The update check.

Split into the part that can be wrong (comparing versions, reading a response,
deciding whether to ask again) and the part that needs a network, which is
faked. Nothing in this file makes a real request - see conftest for why that
matters for the suite as a whole.
"""
import json
import os
import plistlib
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

from utils import update  # noqa: E402

APP_PATH = os.path.join(ROOT, "app.py")


# --------------------------------------------------------------------------
# Reading a version
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("1.1.0", (1, 1, 0)),
    ("v1.1.0", (1, 1, 0)),          # git tags carry the v, Info.plist does not
    ("  v2.0.1  ", (2, 0, 1)),
    ("1.2", (1, 2, 0)),             # a two-part version is a .0 patch
    ("v1.2.3-rc1", (1, 2, 3)),
    ("1.2.3+build7", (1, 2, 3)),
    ("10.20.30", (10, 20, 30)),     # not compared as strings: 10 beats 9
])
def test_parse_reads_version(text, expected):
    assert update.parse(text) == expected


@pytest.mark.parametrize("text", [
    None, "", "   ", "latest", "v", "1", "1.x.0", "version 1.2.3",
    "1.1.0.1.2", "-1.0.0",
])
def test_parse_rejects_nonsense(text):
    assert update.parse(text) is None


def test_ten_is_newer_than_nine():
    """The failure a string comparison would produce: "1.9.0" > "1.10.0"."""
    assert update.is_newer("1.10.0", "1.9.0")
    assert not update.is_newer("1.9.0", "1.10.0")


@pytest.mark.parametrize("candidate,current", [
    ("1.2.0", "1.1.0"),
    ("2.0.0", "1.9.9"),
    ("1.1.1", "1.1.0"),
    ("v1.2.0", "1.1.0"),
])
def test_is_newer_offers_an_upgrade(candidate, current):
    assert update.is_newer(candidate, current)


@pytest.mark.parametrize("candidate,current", [
    ("1.1.0", "1.1.0"),             # equal is not newer
    ("1.0.0", "1.1.0"),             # never offer a downgrade
    ("1.1.0", "1.2.0"),             # a dev machine ahead of the release
    (None, "1.1.0"),
    ("garbage", "1.1.0"),
    ("1.2.0", "garbage"),
])
def test_is_newer_stays_quiet(candidate, current):
    assert not update.is_newer(candidate, current)


# --------------------------------------------------------------------------
# Reading GitHub's answer
# --------------------------------------------------------------------------

def test_tag_from_payload_finds_the_tag():
    body = json.dumps({"tag_name": "v1.2.0", "name": "ASCENT 1.2.0",
                       "assets": [{"name": "ASCENT-1.2.0.dmg"}]})
    assert update.tag_from_payload(body) == "v1.2.0"


@pytest.mark.parametrize("body", [
    "", "not json", "[]", "null", '"a string"',
    '{"message": "Not Found"}',      # what GitHub sends for an unknown repo
    '{"tag_name": null}',
    '{"tag_name": ""}',
    '{"tag_name": 12}',
    '{"tag_name": "v1.2.0"',        # truncated mid-response
])
def test_tag_from_payload_rejects_anything_else(body):
    assert update.tag_from_payload(body) is None


# --------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------

@pytest.fixture
def cache(tmp_path, monkeypatch):
    """Point the module at a throwaway cache file."""
    path = str(tmp_path / "update-check.json")
    monkeypatch.setattr(update, "CACHE_PATH", path)
    return path


def test_cache_round_trip(cache):
    assert update.write_cache("v1.4.0", checked_at=1000.0)
    assert update.read_cache() == {"latest": "v1.4.0", "checked_at": 1000.0}


def test_cache_records_a_failed_check(cache):
    """A failure must still stamp the time, or an offline machine retries
    on every rerun forever."""
    assert update.write_cache(None, checked_at=1000.0)
    stored = update.read_cache()
    assert stored["latest"] is None
    assert stored["checked_at"] == 1000.0


def test_missing_cache_is_empty_not_an_error(cache):
    assert update.read_cache() == {}


@pytest.mark.parametrize("content", [
    "", "{", "not json", "[1, 2, 3]", "null",
])
def test_corrupt_cache_is_empty_not_an_error(cache, content):
    with open(cache, "w", encoding="utf-8") as handle:
        handle.write(content)
    assert update.read_cache() == {}


def test_cache_with_wrong_types_falls_back(cache):
    with open(cache, "w", encoding="utf-8") as handle:
        json.dump({"latest": 42, "checked_at": "yesterday"}, handle)
    assert update.read_cache() == {"latest": None, "checked_at": 0.0}


def test_is_stale():
    now = 1_000_000.0
    assert update.is_stale({}, now=now)
    assert update.is_stale({"checked_at": 0.0}, now=now)
    assert update.is_stale({"checked_at": now - update.CHECK_INTERVAL}, now=now)
    assert not update.is_stale({"checked_at": now - 60}, now=now)
    assert not update.is_stale({"checked_at": now}, now=now)


# --------------------------------------------------------------------------
# The request, faked
# --------------------------------------------------------------------------

class _Response:
    def __init__(self, body, status=200):
        self._body = body.encode("utf-8")
        self.status = status

    def read(self, amount=None):
        return self._body[:amount] if amount else self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_reads_the_tag(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["agent"] = request.get_header("User-agent")
        return _Response(json.dumps({"tag_name": "v1.3.0"}))

    monkeypatch.setattr(update.urllib.request, "urlopen", fake_urlopen)
    assert update.fetch("1.1.0") == "v1.3.0"
    assert seen["url"] == update.API_URL
    # GitHub rejects requests with no User-Agent outright.
    assert seen["agent"] == "ASCENT/1.1.0"


@pytest.mark.parametrize("boom", [
    update.urllib.error.URLError("offline"),
    OSError("connection reset"),
    TimeoutError("timed out"),
])
def test_fetch_is_silent_when_the_network_fails(monkeypatch, boom):
    def fake_urlopen(request, timeout=None):
        raise boom
    monkeypatch.setattr(update.urllib.request, "urlopen", fake_urlopen)
    assert update.fetch("1.1.0") is None


def test_fetch_is_silent_on_a_rate_limit(monkeypatch):
    """403 with a body that is valid JSON but not a release."""
    def fake_urlopen(request, timeout=None):
        return _Response(json.dumps({"message": "API rate limit exceeded"}),
                         status=403)
    monkeypatch.setattr(update.urllib.request, "urlopen", fake_urlopen)
    assert update.fetch("1.1.0") is None


def test_fetch_bounds_what_it_reads(monkeypatch):
    """A redirect to something enormous must not be pulled into memory."""
    captured = {}

    def fake_urlopen(request, timeout=None):
        response = _Response(json.dumps({"tag_name": "v1.3.0"}))
        original = response.read

        def read(amount=None):
            captured["amount"] = amount
            return original(amount)
        response.read = read
        return response

    monkeypatch.setattr(update.urllib.request, "urlopen", fake_urlopen)
    update.fetch("1.1.0")
    assert captured["amount"] is not None and captured["amount"] <= 64 * 1024


# --------------------------------------------------------------------------
# What the page asks for
# --------------------------------------------------------------------------

def test_available_offers_a_newer_release(cache):
    update.write_cache("v1.2.0", checked_at=time.time())
    assert update.available("1.1.0") == "v1.2.0"


def test_available_is_silent_when_current(cache):
    update.write_cache("v1.1.0", checked_at=time.time())
    assert update.available("1.1.0") is None


def test_available_respects_the_setting(cache, monkeypatch):
    """Turned off means no answer and, more importantly, no request."""
    update.write_cache("v1.2.0", checked_at=0.0)      # stale as well as newer
    started = []
    monkeypatch.setattr(update, "start_refresh",
                        lambda version: started.append(version))
    assert update.available("1.1.0", enabled=False) is None
    assert started == []


def test_available_does_not_ask_again_while_fresh(cache, monkeypatch):
    """The rate-limit guard: Streamlit reruns constantly, GitHub allows 60
    anonymous requests an hour."""
    update.write_cache(None, checked_at=time.time())
    started = []
    monkeypatch.setattr(update, "start_refresh",
                        lambda version: started.append(version))
    for _ in range(50):
        update.available("1.1.0")
    assert started == []


def test_available_asks_once_the_cache_is_stale(cache, monkeypatch):
    update.write_cache(None, checked_at=time.time() - update.CHECK_INTERVAL - 1)
    started = []
    monkeypatch.setattr(update, "start_refresh",
                        lambda version: started.append(version))
    update.available("1.1.0")
    assert started == ["1.1.0"]


def test_start_refresh_runs_one_at_a_time(monkeypatch):
    """Streamlit fires several reruns while a page settles; each must not
    start its own thread."""
    monkeypatch.setattr(update, "fetch", lambda version, timeout=None: None)
    monkeypatch.setattr(update, "write_cache",
                        lambda latest, checked_at=None: True)
    update._in_flight = True
    try:
        assert update.start_refresh("1.1.0") is False
    finally:
        update._in_flight = False


# --------------------------------------------------------------------------
# The button itself
# --------------------------------------------------------------------------

def _store():
    return os.environ["ASCENT_SETTINGS_DIR"]


def _seed_cache(latest):
    with open(os.path.join(_store(), "update-check.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"latest": latest, "checked_at": time.time()}, handle)


def _render():
    at = AppTest.from_file(APP_PATH, default_timeout=120)
    at.run()
    assert not at.exception
    return at


def test_sidebar_offers_the_update():
    _seed_cache("v9.9.9")
    at = _render()
    buttons = at.get("link_button")
    assert len(buttons) == 1
    assert "9.9.9" in buttons[0].label
    assert buttons[0].url == update.RELEASES_URL


def test_sidebar_says_nothing_when_current():
    from app import VERSION
    _seed_cache(VERSION)
    at = _render()
    assert at.get("link_button") == []


def test_sidebar_says_nothing_when_the_check_failed():
    _seed_cache(None)
    at = _render()
    assert at.get("link_button") == []


def test_sidebar_respects_the_setting():
    """Turning the check off hides the button even with an update cached."""
    _seed_cache("v9.9.9")
    settings_path = os.path.join(_store(), "settings.json")
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump({"onboarded": True, "check_for_updates": False}, handle)
    at = _render()
    assert at.get("link_button") == []


# --------------------------------------------------------------------------
# The thing most likely to rot
# --------------------------------------------------------------------------

def test_app_version_matches_the_bundle():
    """app.VERSION is what the check compares against; Info.plist is what the
    release is named after. If they drift, the app compares the wrong number
    and either nags forever or never offers anything again - silently, because
    both halves still look perfectly correct on their own.
    """
    from app import VERSION
    with open(os.path.join(ROOT, "macos", "Info.plist"), "rb") as handle:
        plist = plistlib.load(handle)
    assert VERSION == plist["CFBundleShortVersionString"]


def test_release_url_points_at_the_same_repo_as_the_api():
    assert update.OWNER_REPO in update.API_URL
    assert update.OWNER_REPO in update.RELEASES_URL
