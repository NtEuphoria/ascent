"""The live plumbing, tested on a machine with nothing plugged into it.

The serial test is the interesting one. Rather than mocking pyserial - which
would prove only that the mock works - it opens a pseudo-terminal, hands the
slave end to the real SerialSource, and writes bytes into the master end. That
exercises the genuine open/readline/decode/parse path end to end, so a bug in
how the port is opened or how partial lines are handled would actually fail.
"""
from __future__ import annotations

import math
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


# --------------------------------------------------------------------------
# Recorded logs
# --------------------------------------------------------------------------
def test_a_recorded_log_becomes_a_source_like_any_other():
    """The section used to work only while hardware was attached. A file goes
    through the same parser, so every readout and chart works unchanged."""
    log = ("elapsed_s,voltage,current\n"
           "0.0,16.8,10.0\n0.5,16.6,12.0\n1.0,16.4,11.0\n")
    source = livesource.FileSource("bench.csv", log)
    assert source.running
    assert source.channels() == ["voltage", "current"]
    assert len(source.history()) == 3


def test_the_time_column_sets_the_spacing_and_is_not_plotted():
    """Otherwise a log recorded at 200 Hz and one at 2 Hz would look the same,
    and the clock would appear as a channel climbing steadily forever."""
    log = "elapsed_s,v\n0.0,1.0\n2.0,2.0\n"
    source = livesource.FileSource("x.csv", log)
    assert "elapsed_s" not in source.channels()
    assert source.duration() == pytest.approx(2.0, abs=1e-3)
    assert source.time_column == "elapsed_s"


def test_millis_are_read_as_milliseconds():
    """A ten-second log would otherwise play back as though it lasted three
    hours."""
    log = "millis,v\n0,1.0\n10000,2.0\n"
    source = livesource.FileSource("x.csv", log)
    assert source.duration() == pytest.approx(10.0, abs=1e-3)


def test_without_a_time_column_the_assumed_rate_is_used():
    log = "v\n1.0\n2.0\n3.0\n"
    source = livesource.FileSource("x.csv", log, assumed_hz=10.0)
    assert source.time_column is None
    assert source.duration() == pytest.approx(0.2, abs=1e-3)


def test_a_file_of_prose_yields_nothing_rather_than_guesses():
    source = livesource.FileSource("notes.txt", "hello\nthis is not data\n")
    assert source.history() == []
    assert not source.running
    assert source.skipped == 2


def test_boot_banners_in_a_captured_log_are_skipped():
    log = ("ESP-ROM:esp32s3\nrst:0x1 (POWERON)\n"
           "voltage,current\n16.8,10.0\n16.6,12.0\n")
    source = livesource.FileSource("capture.log", log)
    assert source.channels() == ["voltage", "current"]
    assert len(source.history()) == 2


def test_a_log_exported_by_this_app_reads_back_identically():
    """The round trip that matters: record a run, export it, open it again."""
    original = [(1000.0, {"a": 1.0, "b": 2.0}), (1000.5, {"a": 1.5, "b": 2.5})]
    text = livesource.to_csv(original)
    source = livesource.FileSource("roundtrip.csv", text)
    assert source.channels() == ["a", "b"]
    assert [values for _, values in source.history()] == \
        [{"a": 1.0, "b": 2.0}, {"a": 1.5, "b": 2.5}]
    assert source.duration() == pytest.approx(0.5, abs=1e-3)


def test_a_file_source_needs_no_thread_and_no_stopping():
    source = livesource.FileSource("x.csv", "v\n1.0\n2.0\n")
    source.start()
    source.stop()
    assert source.running          # still holds its data after being stopped


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------
def test_the_mean_and_spread_match_the_standard_library():
    import statistics as py

    values = [16.8, 16.6, 16.4, 16.2]
    samples = [(float(i), {"v": value}) for i, value in enumerate(values)]
    stats = livesource.statistics(samples, "v")
    assert stats.count == 4
    assert stats.mean == pytest.approx(py.mean(values))
    assert stats.sd == pytest.approx(py.stdev(values))
    assert (stats.low, stats.high) == (16.2, 16.8)


def test_the_spread_uses_n_minus_one():
    """These are samples of a signal, not the whole of it."""
    samples = [(0.0, {"v": 1.0}), (1.0, {"v": 3.0})]
    stats = livesource.statistics(samples, "v")
    assert stats.sd == pytest.approx(math.sqrt(2.0))     # not sqrt(1.0)


def test_a_single_sample_has_no_spread_rather_than_an_error():
    stats = livesource.statistics([(0.0, {"v": 5.0})], "v")
    assert stats.count == 1 and stats.sd == 0.0 and stats.mean == 5.0


def test_a_steady_channel_has_zero_spread():
    samples = [(float(i), {"v": 2.5}) for i in range(20)]
    assert livesource.statistics(samples, "v").sd == pytest.approx(0.0)


def test_statistics_of_an_absent_channel_are_none_not_zero():
    """Zero would read as a measurement of nothing rather than no measurement."""
    assert livesource.statistics([(0.0, {"a": 1.0})], "b") is None


def test_statistics_ignore_samples_that_lack_the_channel():
    samples = [(0.0, {"a": 1.0}), (1.0, {"b": 9.0}), (2.0, {"a": 3.0})]
    stats = livesource.statistics(samples, "a")
    assert stats.count == 2 and stats.mean == pytest.approx(2.0)
