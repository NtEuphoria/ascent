"""Parsing a device's output, without a device.

Every shape here is something a real board actually prints. The failure mode
this guards against is not crashing - it is confidently misreading a line and
plotting the result, which looks exactly like working telemetry.
"""
from __future__ import annotations

from utils.stream import (MAX_CHANNELS, StreamParser, parse_header, parse_json,
                          parse_numbers, parse_pairs)


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------
def test_json_object_becomes_channels():
    assert parse_json('{"pitch": 1.4, "roll": -0.2}') == {"pitch": 1.4,
                                                          "roll": -0.2}


def test_json_drops_non_numeric_fields_but_keeps_the_rest():
    assert parse_json('{"t": 5, "state": "armed"}') == {"t": 5.0}


def test_json_booleans_plot_as_zero_and_one():
    assert parse_json('{"armed": true, "gps": false}') == {"armed": 1.0,
                                                           "gps": 0.0}


def test_json_nan_is_rejected_not_plotted():
    """json.loads accepts NaN by default; a chart does not."""
    assert parse_json('{"a": NaN}') is None


def test_a_truncated_json_line_is_not_guessed_at():
    """The first line off a serial port is very often a partial one."""
    assert parse_json('{"pitch": 1.4, "rol') is None


def test_a_json_array_is_not_a_sample():
    assert parse_json("[1, 2, 3]") is None


# --------------------------------------------------------------------------
# key=value
# --------------------------------------------------------------------------
def test_equals_pairs():
    assert parse_pairs("pitch=1.4,roll=-0.2") == {"pitch": 1.4, "roll": -0.2}


def test_colon_pairs_with_spaces():
    assert parse_pairs("pitch: 1.4  roll: -0.2") == {"pitch": 1.4, "roll": -0.2}


def test_pairs_read_scientific_notation():
    assert parse_pairs("current=1.5e-3") == {"current": 0.0015}


def test_prose_is_not_a_pair():
    assert parse_pairs("Initialising IMU, please wait") is None


# --------------------------------------------------------------------------
# Bare numbers
# --------------------------------------------------------------------------
def test_a_single_number_is_one_channel():
    assert parse_numbers("21.5") == {"value": 21.5}


def test_unnamed_columns_are_numbered_from_one():
    assert parse_numbers("1.4,-0.2,9.81") == {"ch1": 1.4, "ch2": -0.2,
                                              "ch3": 9.81}


def test_whitespace_separated_numbers_work_too():
    assert parse_numbers("1.4  -0.2") == {"ch1": 1.4, "ch2": -0.2}


def test_a_row_with_any_text_in_it_is_refused():
    """Half-parsing `1.4,ERROR,9.81` into two channels would silently drop a
    fault the device was trying to report."""
    assert parse_numbers("1.4,ERROR,9.81") is None


def test_a_header_names_the_columns():
    assert parse_numbers("1.4,-0.2", ["pitch", "roll"]) == {"pitch": 1.4,
                                                            "roll": -0.2}


def test_a_header_of_the_wrong_width_is_ignored_rather_than_misapplied():
    assert parse_numbers("1.4,-0.2,9.81", ["pitch", "roll"]) == {
        "ch1": 1.4, "ch2": -0.2, "ch3": 9.81}


def test_absurdly_wide_lines_are_refused():
    assert parse_numbers(",".join("1" * 1 for _ in range(MAX_CHANNELS + 1))) is None


# --------------------------------------------------------------------------
# Headers
# --------------------------------------------------------------------------
def test_a_plausible_header_is_accepted():
    assert parse_header("time,pitch,roll") == ["time", "pitch", "roll"]


def test_a_line_containing_a_number_is_data_not_a_header():
    assert parse_header("1.4,pitch") is None


def test_duplicate_column_names_are_refused():
    """Two columns called `temp` would collide into one channel and the second
    would silently win."""
    assert parse_header("temp,temp") is None


# --------------------------------------------------------------------------
# The stateful stream
# --------------------------------------------------------------------------
def test_header_then_rows_is_the_common_arduino_case():
    parser = StreamParser()
    assert parser.feed("time,pitch,roll") is None
    assert parser.feed("0.0,1.4,-0.2") == {"time": 0.0, "pitch": 1.4,
                                           "roll": -0.2}
    assert parser.feed("0.1,1.5,-0.3") == {"time": 0.1, "pitch": 1.5,
                                           "roll": -0.3}


def test_a_changed_row_width_retires_the_old_header():
    parser = StreamParser()
    parser.feed("pitch,roll")
    parser.feed("1.4,-0.2")
    # The sketch was reflashed and now prints three columns.
    assert parser.feed("1.4,-0.2,9.81") == {"ch1": 1.4, "ch2": -0.2,
                                            "ch3": 9.81}
    assert parser.header is None


def test_boot_banners_are_skipped_without_disturbing_the_stream():
    parser = StreamParser()
    parser.feed("ESP-ROM:esp32s3-20210327")
    parser.feed("rst:0x1 (POWERON),boot:0x8")
    assert parser.feed('{"t": 1}') == {"t": 1.0}
    assert parser.last_unparsed is not None


def test_blank_lines_are_not_counted_as_traffic():
    parser = StreamParser()
    parser.feed("")
    parser.feed("   ")
    assert parser.lines_seen == 0


def test_the_parser_reports_how_much_it_understood():
    parser = StreamParser()
    parser.feed("hello there")
    parser.feed("1.0")
    assert parser.lines_seen == 2 and parser.lines_parsed == 1


def test_json_wins_over_a_number_lookalike():
    parser = StreamParser()
    assert parser.feed('{"1": 2}') == {"1": 2.0}
