"""The live plumbing, tested on a machine with nothing plugged into it.

The serial test is the interesting one. Rather than mocking pyserial - which
would prove only that the mock works - it opens a pseudo-terminal, hands the
slave end to the real SerialSource, and writes bytes into the master end. That
exercises the genuine open/readline/decode/parse path end to end, so a bug in
how the port is opened or how partial lines are handled would actually fail.
"""
from __future__ import annotations

import os
import time

import pytest

from utils import livesource
from utils.livesource import DemoSource, SerialSource, to_csv


def _wait_for(predicate, timeout=4.0, interval=0.02):
    """Threads are involved, so poll rather than sleeping a fixed amount."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# --------------------------------------------------------------------------
# Demo source
# --------------------------------------------------------------------------
def test_the_demo_source_produces_named_channels():
    source = DemoSource(rate_hz=200.0)
    source.start()
    try:
        assert _wait_for(lambda: len(source.history()) > 5)
        assert set(source.latest()) == {"voltage", "current", "accel_z",
                                        "esc_temp"}
    finally:
        source.stop()
    assert not source.running


def test_the_demo_source_is_labelled_as_simulated():
    """A live view quietly showing invented numbers would be the worst bug
    this app could have."""
    assert "imulated" in DemoSource().label


def test_history_is_bounded():
    source = DemoSource()
    for index in range(livesource.HISTORY + 250):
        source._record({"x": float(index)})
    assert len(source.history()) == livesource.HISTORY
    # The oldest were dropped, not the newest.
    assert source.latest()["x"] == float(livesource.HISTORY + 249)


def test_rate_is_reported_in_hz():
    source = DemoSource(rate_hz=100.0)
    source.start()
    try:
        assert _wait_for(lambda: source.rate_hz() > 20.0)
    finally:
        source.stop()


# --------------------------------------------------------------------------
# Real serial, over a pseudo-terminal
# --------------------------------------------------------------------------
@pytest.fixture
def pty_pair():
    try:
        master, slave = os.openpty()
    except OSError:                        # pragma: no cover - not on macOS/Linux
        pytest.skip("no pseudo-terminal available")
    yield master, os.ttyname(slave)
    for fd in (master, slave):
        try:
            os.close(fd)
        except OSError:
            pass


def test_serial_source_reads_and_parses_real_bytes(pty_pair):
    master, device = pty_pair
    source = SerialSource(device, baud=115200)
    source.start()
    try:
        os.write(master, b"pitch,roll\r\n")
        os.write(master, b"1.4,-0.2\r\n")
        os.write(master, b'{"pitch": 2.5, "roll": 0.1}\r\n')
        assert _wait_for(lambda: len(source.history()) >= 2)
        samples = [values for _, values in source.history()]
        assert samples[0] == {"pitch": 1.4, "roll": -0.2}
        assert samples[1] == {"pitch": 2.5, "roll": 0.1}
    finally:
        source.stop()


def test_a_partial_first_line_does_not_poison_the_stream(pty_pair):
    """Opening a port mid-transmission is the normal case, not an edge one."""
    master, device = pty_pair
    source = SerialSource(device)
    source.start()
    try:
        os.write(master, b'itch": 9.9}\r\n')          # tail of a lost line
        os.write(master, b'{"pitch": 1.0}\r\n')
        assert _wait_for(lambda: len(source.history()) >= 1)
        assert source.latest() == {"pitch": 1.0}
    finally:
        source.stop()


def test_undecodable_bytes_do_not_end_the_stream(pty_pair):
    """A wrong baud rate produces garbage; the fix is to change the baud rate,
    not to have the reader die."""
    master, device = pty_pair
    source = SerialSource(device)
    source.start()
    try:
        os.write(master, b"\xff\xfe\x00 rubbish\r\n")
        os.write(master, b"42.0\r\n")
        assert _wait_for(lambda: len(source.history()) >= 1)
        assert source.latest() == {"value": 42.0}
    finally:
        source.stop()


def test_a_port_that_does_not_exist_reports_instead_of_raising():
    source = livesource.connect(SerialSource("/dev/tty.nonexistent-ascent"))
    try:
        assert source.error is not None
        assert not source.running
    finally:
        livesource.disconnect()


def test_connecting_replaces_the_previous_connection():
    first = livesource.connect(DemoSource())
    second = livesource.connect(DemoSource())
    try:
        assert livesource.active() is second
        assert not first.running          # the old port was released
    finally:
        livesource.disconnect()
    assert livesource.active() is None


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def test_csv_has_a_header_an_elapsed_column_and_one_row_per_sample():
    samples = [(1000.0, {"a": 1.0, "b": 2.0}), (1000.5, {"a": 1.5, "b": 2.5})]
    lines = to_csv(samples).strip().split("\n")
    assert lines[0] == "time_s,elapsed_s,a,b"
    assert lines[1].startswith("1000.000000,0.000000,1,2")
    assert lines[2].startswith("1000.500000,0.500000,1.5,2.5")


def test_csv_leaves_a_gap_where_a_channel_was_missing():
    """Devices drop fields. An empty cell is honest; a zero is a measurement
    that never happened."""
    samples = [(0.0, {"a": 1.0, "b": 2.0}), (1.0, {"a": 3.0})]
    assert to_csv(samples).strip().split("\n")[2].endswith(",3,")


def test_csv_of_nothing_is_still_valid_csv():
    assert to_csv([]).strip() == "time_s,elapsed_s"


def test_available_ports_never_raises():
    for device, description in livesource.available_ports():
        assert isinstance(device, str) and isinstance(description, str)
