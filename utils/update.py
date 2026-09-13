"""Noticing that a newer ASCENT has been released.

The app is installed by downloading a DMG, so there is no package manager to
tell anyone that the copy they are running is six months old. This asks GitHub
once a day and, if there is something newer, shows a quiet button.

Three properties matter more than the feature itself:

*Never block.* Streamlit re-runs the whole script on every keystroke. A network
call in the page body would stall the render for as long as the request takes,
which on a bad connection is seconds, on every character typed. The fetch runs
on a background thread and writes its answer to disk; the page only ever reads
what is already there.

*Never spam.* GitHub allows 60 anonymous requests an hour per address. One
rerun per keystroke would exhaust that in under a minute and start returning
403s. The answer is cached on disk with a timestamp, so the interval survives
quitting the app - an in-memory cache would re-check on every launch.

*Never nag.* A failed check, no network, a rate-limited response or a garbled
answer all mean "no update to show" and are otherwise invisible. Being told
that the internet is unavailable is not why anyone opened a calculator.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from utils.settings import SUPPORT_DIR

OWNER_REPO = "NtEuphoria/ascent"

API_URL = "https://api.github.com/repos/{}/releases/latest".format(OWNER_REPO)
"""GitHub's "latest release" endpoint, which excludes drafts and pre-releases.
That is load-bearing: tagging a beta will not offer it to everyone."""

RELEASES_URL = "https://github.com/{}/releases/latest".format(OWNER_REPO)
"""Where the button sends people. The human page, not the API."""

CACHE_PATH = os.path.join(SUPPORT_DIR, "update-check.json")

CHECK_INTERVAL = 24 * 60 * 60
"""Seconds between checks. Daily is frequent enough to notice a release within
a day and rare enough that the rate limit is never in sight."""

TIMEOUT = 4.0
"""Seconds to wait on the network. Generous for a 2 KB JSON response, and short
enough that a hung connection cannot keep a thread alive all session."""

_lock = threading.Lock()
_in_flight = False
"""One check at a time. Without this, the handful of reruns that Streamlit
fires while a page settles would each start their own thread."""


# --------------------------------------------------------------------------
# Version comparison
# --------------------------------------------------------------------------

_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?$")


def parse(text: Optional[str]) -> Optional[Tuple[int, int, int]]:
    """"v1.2" or "1.2.3" or "1.2.3-rc1" -> (1, 2, 3). None if unreadable.

    Tolerates the leading "v" because git tags conventionally carry one and
    `CFBundleShortVersionString` never does, so the two sides of every
    comparison are spelled differently.
    """
    match = _VERSION.match((text or "").strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    return (int(major), int(minor), int(patch or 0))


def is_newer(candidate: Optional[str], current: Optional[str]) -> bool:
    """True only when `candidate` is a strictly higher released version.

    Unparseable input on either side is False rather than an exception: the
    consequence of a wrong answer here is offering a downgrade, which is worse
    than staying quiet.
    """
    new, old = parse(candidate), parse(current)
    if new is None or old is None:
        return False
    return new > old


# --------------------------------------------------------------------------
# The cache on disk
# --------------------------------------------------------------------------

def read_cache() -> Dict[str, Any]:
    """What the last check found. Empty on any problem at all."""
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    checked_at = raw.get("checked_at")
    latest = raw.get("latest")
    return {
        "latest": latest if isinstance(latest, str) else None,
        "checked_at": (float(checked_at)
                       if isinstance(checked_at, (int, float)) else 0.0),
    }


def write_cache(latest: Optional[str],
                checked_at: Optional[float] = None) -> bool:
    """Record the result. A failed check still writes, stamping the time.

    Stamping a failure is the point: without it, an offline machine would
    start a fresh thread on every single rerun, forever.
    """
    payload = {"latest": latest,
               "checked_at": time.time() if checked_at is None else checked_at}
    try:
        os.makedirs(SUPPORT_DIR, exist_ok=True)
        temporary = CACHE_PATH + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(temporary, CACHE_PATH)
        return True
    except OSError:
        return False


def is_stale(cache: Dict[str, Any], now: Optional[float] = None) -> bool:
    """Has enough time passed to justify asking again?"""
    now = time.time() if now is None else now
    return (now - float(cache.get("checked_at") or 0.0)) >= CHECK_INTERVAL


# --------------------------------------------------------------------------
# Talking to GitHub
# --------------------------------------------------------------------------

def tag_from_payload(text: str) -> Optional[str]:
    """Pull `tag_name` out of a releases response. None if it is not there.

    Split out from the request so the parsing - the part that can be wrong -
    is testable without a network, and so a changed or truncated response is
    handled by the same path as no response at all.
    """
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    tag = raw.get("tag_name")
    return tag if isinstance(tag, str) and tag.strip() else None


def fetch(version: str, timeout: float = TIMEOUT) -> Optional[str]:
    """Ask GitHub for the latest release tag. None on any failure.

    `version` only names this app in the User-Agent header, which GitHub
    requires; nothing about the machine or the person using it is sent.
    """
    request = urllib.request.Request(
        API_URL,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "ASCENT/{}".format(version)},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                return None
            # Bounded read. A redirect to something enormous should not be
            # pulled into memory in full.
            body = response.read(64 * 1024).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return tag_from_payload(body)


def _refresh(version: str) -> None:
    """Body of the background thread.

    Touches no Streamlit API by design - a thread with no script run context
    warns or raises the moment it does.
    """
    global _in_flight
    try:
        write_cache(fetch(version))
    finally:
        with _lock:
            _in_flight = False


def start_refresh(version: str) -> bool:
    """Begin a check unless one is running. Returns whether it started one."""
    global _in_flight
    with _lock:
        if _in_flight:
            return False
        _in_flight = True
    thread = threading.Thread(target=_refresh, args=(version,),
                              name="ascent-update-check", daemon=True)
    # Daemon, so a hung request can never keep the app from quitting.
    thread.start()
    return True


# --------------------------------------------------------------------------
# What the page asks
# --------------------------------------------------------------------------

def available(version: str, enabled: bool = True) -> Optional[str]:
    """The newer version to offer, or None.

    Cheap enough to call on every rerun: it reads one small file and, at most
    once a day, starts a thread. A freshly fetched answer appears on the next
    rerun rather than this one, because the page has already drawn by the time
    the request finishes - a one-interaction delay on a once-a-day event, which
    is not worth a spinner.
    """
    if not enabled:
        return None
    cache = read_cache()
    if is_stale(cache):
        start_refresh(version)
    latest = cache.get("latest")
    return latest if is_newer(latest, version) else None
