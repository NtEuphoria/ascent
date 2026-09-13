"""Where live samples come from, and the one place that holds the connection.

A Streamlit script reruns top to bottom on every interaction, so anything that
must survive between reruns cannot live in the script. An open serial port
certainly cannot: reopening it each rerun would drop bytes, and on macOS would
often fail outright because the previous handle had not been released yet.

So the connection lives here, at module scope, and the page merely asks what
the current one is. That makes this a singleton, which is the right shape for
exactly one reason: there is one physical Mac with one set of USB ports and
one person looking at it.

Reading happens on a background thread because `readline()` blocks. The thread
only ever appends to a bounded deque under a lock; the page only ever takes a
snapshot. No other shared state crosses that boundary.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from .stream import StreamParser

Sample = Tuple[float, Dict[str, float]]

HISTORY = 20000
"""Samples kept in memory. At a brisk 100 Hz that is a little over three
minutes of scrollback, and about 3 MB - bounded so a device left plugged in
overnight cannot exhaust memory."""

DEFAULT_BAUD = 115200
BAUD_RATES = (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600)


class Source:
    """A stream of timestamped samples. Subclasses supply the transport."""

    kind = "none"

    def __init__(self, label: str) -> None:
        self.label = label
        self.parser = StreamParser()
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self._history: deque = deque(maxlen=HISTORY)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._open()
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"ascent-{self.kind}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
        self._close()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- data --------------------------------------------------------------
    def _record(self, values: Dict[str, float]) -> None:
        with self._lock:
            self._history.append((time.time(), values))

    def history(self) -> List[Sample]:
        """A snapshot. Copied under the lock so the reader thread can keep
        appending while the page renders."""
        with self._lock:
            return list(self._history)

    def channels(self) -> List[str]:
        """Every channel name seen, in the order first encountered."""
        seen: Dict[str, None] = {}
        for _, values in self.history():
            for name in values:
                seen.setdefault(name, None)
        return list(seen)

    def latest(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._history[-1][1]) if self._history else {}

    def rate_hz(self, window: float = 3.0) -> float:
        """Samples per second over the last few seconds."""
        now = time.time()
        recent = [t for t, _ in self.history() if now - t <= window]
        if len(recent) < 2:
            return 0.0
        span = recent[-1] - recent[0]
        return (len(recent) - 1) / span if span > 0 else 0.0

    # -- subclass hooks ----------------------------------------------------
    def _open(self) -> None:
        pass

    def _close(self) -> None:
        pass

    def _run(self) -> None:      # pragma: no cover - overridden
        raise NotImplementedError


class DemoSource(Source):
    """A synthetic four-channel stream, so the page works with nothing plugged
    in - and so this file can be tested on a machine with no USB devices.

    It is labelled as simulated everywhere it appears. A live-data view that
    quietly shows made-up numbers would be the worst possible bug in a tool
    whose entire promise is accuracy.
    """

    kind = "demo"

    def __init__(self, rate_hz: float = 20.0) -> None:
        super().__init__("Simulated signal (no hardware)")
        self.rate_hz_target = rate_hz

    def _run(self) -> None:
        period = 1.0 / self.rate_hz_target
        start = time.time()
        while not self._stop.is_set():
            t = time.time() - start
            # A plausible little airframe: a battery sagging under a varying
            # load, an accelerometer with a vibration peak, a warming ESC.
            load = 12.0 + 6.0 * math.sin(t / 4.0)
            self._record({
                "voltage": round(16.8 - 0.02 * t - 0.045 * load, 3),
                "current": round(load, 3),
                "accel_z": round(9.81 + 0.6 * math.sin(2 * math.pi * 7.0 * t), 3),
                "esc_temp": round(24.0 + 18.0 * (1 - math.exp(-t / 45.0)), 2),
            })
            self._stop.wait(period)


class SerialSource(Source):
    """A USB serial device: Arduino, ESP32, STM32, an FTDI cable, a flight
    controller printing telemetry."""

    kind = "serial"

    def __init__(self, port: str, baud: int = DEFAULT_BAUD) -> None:
        super().__init__(f"{port} @ {baud} baud")
        self.port = port
        self.baud = baud
        self._handle = None

    def _open(self) -> None:
        import serial                      # imported late: optional dependency
        # A short read timeout rather than a blocking read, so stop() is
        # responsive instead of waiting for the next byte that may never come.
        self._handle = serial.Serial(self.port, self.baud, timeout=0.2)

    def _close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:               # pragma: no cover - close is best effort
                pass
            self._handle = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                raw = self._handle.readline()
            except Exception as exc:        # unplugged mid-stream is normal
                self.error = f"Lost the connection: {exc}"
                return
            if not raw:
                continue
            # Devices emit stray bytes at reset and when the baud rate is
            # wrong; decoding strictly would end the stream on the first one.
            line = raw.decode("utf-8", errors="replace").strip()
            values = self.parser.feed(line)
            if values:
                self._record(values)


class FileSource(Source):
    """A log that was recorded earlier, read through the same parser.

    The single largest limitation of this section was that it only worked
    while hardware was attached: you could watch a test and then had nothing
    to look at afterwards. A file is a Source like any other, so every
    readout, statistic and chart works on it unchanged.

    Timestamps come from a time column when the file has one - the CSV this
    app exports does - so a log recorded at 200 Hz and one recorded at 2 Hz
    do not both play back as though they were the same. Without one the
    samples are spaced evenly at `assumed_hz`, and the page says so.
    """

    kind = "file"

    TIME_COLUMNS = ("elapsed_s", "time_s", "time", "t", "timestamp", "millis")

    def __init__(self, name: str, text: str, assumed_hz: float = 50.0) -> None:
        super().__init__(f"{name} (recorded)")
        self.name = name
        self.assumed_hz = max(float(assumed_hz), 1e-3)
        self.time_column: Optional[str] = None
        self.skipped = 0
        self._load(text)

    def _load(self, text: str) -> None:
        rows: List[Dict[str, float]] = []
        for line in text.splitlines():
            values = self.parser.feed(line)
            if values:
                rows.append(values)
            elif line.strip():
                self.skipped += 1
        if not rows:
            return

        self.time_column = next(
            (name for name in self.TIME_COLUMNS if name in rows[0]), None)
        start = time.time()
        for index, values in enumerate(rows):
            if self.time_column is not None:
                offset = values[self.time_column]
                # A millis column is in milliseconds; everything else in
                # seconds. Guessing from the name is crude but it is what the
                # column is called, and the alternative is silently playing a
                # ten-second log back as though it lasted three hours.
                if self.time_column == "millis":
                    offset /= 1000.0
            else:
                offset = index / self.assumed_hz
            stamp = start + float(offset)
            # Every known clock column is dropped, not only the one chosen
            # for spacing: the CSV this app exports carries both time_s and
            # elapsed_s, and the unused one would otherwise appear as a
            # channel climbing steadily forever.
            plotted = {k: v for k, v in values.items()
                       if k not in self.TIME_COLUMNS}
            if plotted:
                self._history.append((stamp, plotted))

    def start(self) -> None:
        """Nothing to start: the file was read when it was opened."""
        self.started_at = self.started_at or time.time()

    def stop(self) -> None:
        pass

    @property
    def running(self) -> bool:
        return bool(self._history)

    def duration(self) -> float:
        samples = self.history()
        return samples[-1][0] - samples[0][0] if len(samples) > 1 else 0.0


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
class Stats(NamedTuple):
    """What a channel did over a window, rather than what it is right now."""

    count: int
    mean: float
    sd: float
    low: float
    high: float

    @property
    def span(self) -> float:
        return self.high - self.low


def statistics(samples: Sequence[Sample], channel: str) -> Optional[Stats]:
    """Mean, spread and extremes for one channel.

    A single live number is a glimpse: it is whatever the channel happened to
    be at the instant the page drew. A mean over a window with its standard
    deviation beside it is a measurement, and is the difference between a
    figure worth pinning into a design and one worth nothing.

    The spread is the sample standard deviation, with n-1 in the denominator,
    because these are samples of a signal rather than the whole of it.
    """
    series = [values[channel] for _, values in samples if channel in values]
    if not series:
        return None
    count = len(series)
    mean = sum(series) / count
    if count > 1:
        variance = sum((value - mean) ** 2 for value in series) / (count - 1)
        sd = math.sqrt(variance)
    else:
        sd = 0.0
    return Stats(count, mean, sd, min(series), max(series))


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------
def available_ports() -> List[Tuple[str, str]]:
    """(device, description) for every serial port, likeliest first.

    On macOS a USB device appears as both /dev/cu.* and /dev/tty.*; pyserial
    reports the cu form, which is the one that does not block waiting for a
    carrier signal. Bluetooth and debug ports are listed last because they are
    almost never what someone means by "plugged in".
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    found = []
    for port in list_ports.comports():
        description = (port.description or "").strip()
        if port.manufacturer and port.manufacturer not in description:
            description = f"{description} - {port.manufacturer}".strip(" -")
        found.append((port.device, description or "serial port"))
    found.sort(key=lambda item: _port_rank(item[0]))
    return found


def _port_rank(device: str) -> Tuple[int, str]:
    lowered = device.lower()
    if "bluetooth" in lowered or "debug-console" in lowered:
        return (2, device)
    if "usb" in lowered or "modem" in lowered:
        return (0, device)          # a real plugged-in board
    return (1, device)


def serial_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("serial") is not None


# ---------------------------------------------------------------------------
# The one live connection
# ---------------------------------------------------------------------------
_active: Optional[Source] = None


def active() -> Optional[Source]:
    return _active


def connect(source: Source) -> Source:
    """Replace whatever was connected. Always closes the old port first."""
    global _active
    disconnect()
    try:
        source.start()
    except Exception as exc:
        # A port that is busy, missing, or refused by the OS is an ordinary
        # thing to happen; it belongs on the page, not in a traceback.
        source.error = str(exc)
    _active = source
    return source


def disconnect() -> None:
    global _active
    if _active is not None:
        _active.stop()
    _active = None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def to_csv(samples: Sequence[Sample], channels: Optional[Sequence[str]] = None
           ) -> str:
    """Recorded samples as CSV, with an absolute and an elapsed time column.

    Elapsed seconds are included because that is what anyone plotting this
    afterwards actually wants, and recomputing it from unix time is a step
    people get wrong.
    """
    if not samples:
        return "time_s,elapsed_s\n"
    if channels is None:
        seen: Dict[str, None] = {}
        for _, values in samples:
            for name in values:
                seen.setdefault(name, None)
        channels = list(seen)
    first = samples[0][0]
    rows = ["time_s,elapsed_s," + ",".join(channels)]
    for stamp, values in samples:
        cells = ["" if name not in values else format(values[name], ".10g")
                 for name in channels]
        rows.append(f"{stamp:.6f},{stamp - first:.6f}," + ",".join(cells))
    return "\n".join(rows) + "\n"
