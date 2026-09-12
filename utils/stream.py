"""Turning whatever a microcontroller prints into named numeric channels.

Nothing in here talks to hardware. That is the point: the hard part of reading
a sensor is not opening the port, it is guessing what the bytes mean, and that
guessing is pure text processing which can be tested exhaustively without
owning the device.

Four shapes cover almost everything people actually print from an Arduino,
an ESP32, a flight controller in debug mode, or a Python script:

    {"pitch": 1.4, "roll": -0.2}        JSON, one object per line
    pitch=1.4,roll=-0.2                 key=value pairs
    pitch,roll                          a header line...
    1.4,-0.2                            ...followed by bare CSV
    1.4 -0.2                            whitespace-separated numbers
    1.4                                 a single number

The parser is deliberately conservative. A line it cannot read confidently is
discarded rather than coerced, because a plot of misparsed numbers is worse
than an empty plot - it looks like data.
"""
from __future__ import annotations

import json
import math
import re
from typing import Dict, List, Optional

# A column name we are willing to accept from a header line. Deliberately
# strict: it stops a stray line of prose being mistaken for a header.
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\- ]{0,30}$")

# Split on comma, semicolon, tab, or runs of whitespace.
_SPLIT = re.compile(r"[,;\t]|\s+")

MAX_CHANNELS = 32
"""Beyond this a line is almost certainly not telemetry, and building a chart
with hundreds of series would lock the page up."""


def _number(text: str) -> Optional[float]:
    """A float, or None. Rejects NaN and infinity, which break every chart."""
    text = text.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _tokens(line: str) -> List[str]:
    return [token for token in _SPLIT.split(line.strip()) if token != ""]


def parse_json(line: str) -> Optional[Dict[str, float]]:
    """{"a": 1, "b": 2} -> {"a": 1.0, "b": 2.0}, ignoring non-numeric fields."""
    line = line.strip()
    if not (line.startswith("{") and line.endswith("}")):
        return None
    try:
        raw = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    out = {}
    for key, value in raw.items():
        # bool is a subclass of int; a flag is not a measurement, but it does
        # plot usefully as 0/1, so it is converted explicitly rather than by
        # accident.
        if isinstance(value, bool):
            out[str(key)] = 1.0 if value else 0.0
        elif isinstance(value, (int, float)) and math.isfinite(value):
            out[str(key)] = float(value)
    return out or None


def parse_pairs(line: str) -> Optional[Dict[str, float]]:
    """pitch=1.4, roll=-0.2   or   pitch: 1.4 roll: -0.2"""
    found = re.findall(r"([A-Za-z_][A-Za-z0-9_.\-]*)\s*[=:]\s*"
                       r"(-?\d+\.?\d*(?:[eE][-+]?\d+)?)", line)
    if not found:
        return None
    out = {}
    for name, text in found:
        value = _number(text)
        if value is not None:
            out[name] = value
    return out or None


def parse_numbers(line: str, names: Optional[List[str]] = None
                  ) -> Optional[Dict[str, float]]:
    """A row of bare numbers, named by `names` if a header has been seen."""
    tokens = _tokens(line)
    if not tokens or len(tokens) > MAX_CHANNELS:
        return None
    values = [_number(token) for token in tokens]
    if any(value is None for value in values):
        return None          # one non-numeric token means this is not a data row
    if names and len(names) == len(values):
        return dict(zip(names, values))
    if len(values) == 1:
        return {"value": values[0]}
    return {f"ch{index + 1}": value for index, value in enumerate(values)}


def parse_header(line: str) -> Optional[List[str]]:
    """A line of plausible column names, e.g. `time,pitch,roll`."""
    tokens = _tokens(line)
    if not 1 <= len(tokens) <= MAX_CHANNELS:
        return None
    if any(_number(token) is not None for token in tokens):
        return None          # any number in it and it is data, not a header
    if not all(_NAME.match(token) for token in tokens):
        return None
    if len(set(tokens)) != len(tokens):
        return None          # duplicate column names would silently collide
    return tokens


class StreamParser:
    """Reads a device's lines and remembers what it learned about their shape.

    Held as an object rather than a function because CSV is only interpretable
    with memory: `1.4,-0.2` means nothing until an earlier `pitch,roll` said
    what the columns are. The header is dropped as soon as a row of a different
    width arrives, rather than being misapplied to it.
    """

    def __init__(self) -> None:
        self.header: Optional[List[str]] = None
        self.lines_seen = 0
        self.lines_parsed = 0
        self.last_unparsed: Optional[str] = None

    @property
    def format_name(self) -> str:
        """What the stream looks like so far, for showing to the user."""
        if self.lines_parsed == 0:
            return "unknown"
        if self.header:
            return "CSV with header: " + ", ".join(self.header)
        return "recognised"

    def feed(self, line: str) -> Optional[Dict[str, float]]:
        """One line in, one sample out - or None if the line carried no data."""
        line = line.strip()
        if not line:
            return None
        self.lines_seen += 1

        for parse in (parse_json, parse_pairs):
            sample = parse(line)
            if sample:
                self.lines_parsed += 1
                return sample

        sample = parse_numbers(line, self.header)
        if sample:
            # A row whose width no longer matches the header means the device
            # changed what it prints; the old names would mislabel it.
            if self.header and len(sample) != len(self.header):
                self.header = None
            self.lines_parsed += 1
            return sample

        names = parse_header(line)
        if names:
            self.header = names
            return None

        self.last_unparsed = line[:120]
        return None
