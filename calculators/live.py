"""Live data: read a device that is actually plugged in.

Everything else in ASCENT answers "what would happen if". These two pages
answer "what is happening", and then let the two meet: a channel coming off a
board can be fed straight into any equation in the app, so a measured current
becomes a predicted flight time while you watch.

Both pages use the imperative `render=` escape hatch. They are not equations -
there is no single headline number, the content changes twice a second, and
the controls are a connection rather than a set of values - so the declarative
spec would have to grow a dialect that exists for two pages.

The transport lives in utils/livesource.py and the parsing in utils/stream.py;
this file is only the screen.
"""
from __future__ import annotations

import time

import streamlit as st

from utils import charts, livesource
from utils import project as store
from utils import ui
from utils.formatting import format_number
from utils.spec import Calculator, Inputs

REFRESH_SECONDS = 0.5
"""How often the live view redraws. Fast enough to feel continuous, slow
enough that the page is not permanently mid-rerun - Streamlit dims the whole
page once a rerun passes 500 ms, and a view that redraws faster than it
renders never stops flickering."""

WINDOW_CHOICES = {"Last 10 s": 10.0, "Last 30 s": 30.0, "Last 2 min": 120.0,
                  "Last 10 min": 600.0, "Everything": None}


# ---------------------------------------------------------------------------
# Connection controls (outside the auto-refreshing fragment)
# ---------------------------------------------------------------------------
def _connection_panel() -> None:
    source = livesource.active()

    if source is not None and source.running:
        left, right = st.columns([3, 1], vertical_alignment="bottom")
        with left:
            st.markdown(f'<div class="a-note">Connected to '
                        f'<b>{source.label}</b>.</div>', unsafe_allow_html=True)
        with right:
            if st.button("Disconnect", key="live_disconnect",
                         use_container_width=True):
                livesource.disconnect()
                st.rerun()
        return

    ports = livesource.available_ports()
    if not livesource.serial_available():
        st.warning(
            "Serial support is not installed in this environment, so only the "
            "simulated signal is available. Reinstall the app, or run "
            "`pip install pyserial` in its environment.")
    elif not ports:
        st.info(
            "No serial device found. Plug in a board over USB and press "
            "Rescan. On macOS a board usually appears as `/dev/cu.usbmodem…` "
            "or `/dev/cu.usbserial…`; you may need the CH340 or CP210x driver "
            "for some clone boards.")

    port_column, baud_column, connect_column = st.columns([2.4, 1, 1],
                                                          vertical_alignment="bottom")
    with port_column:
        labels = [f"{device}  ·  {description}" for device, description in ports]
        chosen = st.selectbox("Serial port", labels or ["No device found"],
                              key="live_port",
                              disabled=not ports,
                              help="The device to read from.")
    with baud_column:
        baud = st.selectbox("Baud", livesource.BAUD_RATES,
                            index=livesource.BAUD_RATES.index(
                                livesource.DEFAULT_BAUD),
                            key="live_baud",
                            help="Must match the value in the device's "
                                 "Serial.begin(). A wrong rate reads as "
                                 "garbage, not as silence.")
    with connect_column:
        if st.button("Connect", key="live_connect", type="primary",
                     disabled=not ports, use_container_width=True):
            device = ports[labels.index(chosen)][0]
            livesource.connect(livesource.SerialSource(device, int(baud)))
            st.rerun()

    rescan, demo = st.columns([1, 1])
    with rescan:
        if st.button("Rescan ports", key="live_rescan",
                     use_container_width=True):
            st.rerun()
    with demo:
        if st.button("Use a simulated signal", key="live_demo",
                     use_container_width=True,
                     help="A synthetic four-channel stream, so the page can be "
                          "tried with nothing plugged in."):
            livesource.connect(livesource.DemoSource())
            st.rerun()

    if source is not None and source.error:
        st.error(f"Could not read that port: {source.error}")

    _open_recording()


def _open_recording() -> None:
    """Open a log recorded earlier.

    Until this existed the page only worked while hardware was attached: you
    could watch a test and then had nothing to look at afterwards. A file goes
    through the same parser as the serial port, so every readout, statistic
    and chart works on it unchanged.
    """
    with st.expander("Open a recorded log"):
        st.markdown(
            '<div class="a-note">A CSV or plain log, in any of the formats '
            'this page already reads. A time column - <code>elapsed_s</code>, '
            '<code>time_s</code> or <code>millis</code> - is used for spacing '
            'if there is one; the file this page exports has one.</div>',
            unsafe_allow_html=True)
        upload = st.file_uploader("Log file", type=["csv", "txt", "log", "tsv"],
                                  key="live_upload", label_visibility="collapsed")
        assumed = st.number_input(
            "Sample rate to assume if the file has no time column [Hz]",
            value=50.0, min_value=0.1, step=10.0, key="live_assumed")
        if upload is not None and st.button("Open it", key="live_openfile",
                                            type="primary"):
            text = upload.getvalue().decode("utf-8", errors="replace")
            source = livesource.FileSource(upload.name, text, assumed)
            if not source.history():
                st.error("Nothing in that file parsed as data. It needs "
                         "numbers in one of the formats listed above.")
            else:
                livesource.connect(source)
                st.rerun()


def _sparkline(series, width: int = 108, height: int = 26) -> str:
    """An inline SVG trace of one channel's recent history.

    Drawn as SVG rather than as another Altair chart because there is one of
    these per channel, redrawn twice a second: a full chart spec each would
    cost more to build than the whole rest of the page.
    """
    if len(series) < 2:
        return ""
    low, high = min(series), max(series)
    span = high - low
    if span <= 0:
        # A flat channel is real data, not an error - draw it on the centre
        # line rather than dividing by zero or hiding it.
        points = " ".join(
            f"{index / (len(series) - 1) * width:.1f},{height / 2:.1f}"
            for index in range(len(series)))
    else:
        points = " ".join(
            f"{index / (len(series) - 1) * width:.1f},"
            f"{height - 2 - (value - low) / span * (height - 4):.1f}"
            for index, value in enumerate(series))
    return (f'<svg class="a-spark" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{points}"/></svg>')


def _readouts(source, window: float = 30.0) -> None:
    """One large number per channel, with where it has been and where it is
    going. A single number updating twice a second tells you its value and
    nothing else; the trend is most of the information."""
    latest = source.latest()
    if not latest:
        return

    cutoff = time.time() - window
    recent = [values for stamp, values in source.history() if stamp >= cutoff]
    names = list(latest)

    for start in range(0, len(names), 4):
        for column, name in zip(st.columns(4), names[start:start + 4]):
            series = [v[name] for v in recent if name in v][-120:]
            with column:
                st.markdown(_readout(name, latest[name], series),
                            unsafe_allow_html=True)


# Lifted out of the f-string below: Python 3.9 refuses a backslash escape
# inside an f-string expression, and this app targets the system interpreter.
_ARROWS = {"up": "\u25b2", "down": "\u25bc"}


def _trend(series) -> str:
    """"up", "down" or "" for a channel's direction across the window shown.

    Measured by comparing the mean of the first fifth of the window with the
    mean of the last fifth, not by differencing the last two samples. A
    difference of consecutive samples is mostly noise, so an arrow driven by
    it flickers between up and down several times a second and says nothing.

    Averaging the ends instead makes the arrow mean the same thing as the
    range printed beside it: where this channel has gone over the window you
    are looking at.
    """
    if len(series) < 10:
        return ""
    edge = max(2, len(series) // 5)
    before = sum(series[:edge]) / edge
    after = sum(series[-edge:]) / edge
    spread = max(series) - min(series)
    if spread <= 0:
        return ""
    # A tenth of the window's own range: below that the channel is flat on the
    # scale the user is actually looking at.
    if abs(after - before) < spread * 0.10:
        return ""
    return "up" if after > before else "down"


def _readout(name: str, value: float, series) -> str:
    direction = _trend(series)
    trend = ""
    if direction:
        trend = (f'<span class="a-live-trend a-live-{direction}">'
                 f'{_ARROWS[direction]}</span>')

    extent = ""
    if len(series) >= 2 and max(series) > min(series):
        extent = (f'<span class="a-live-extent">'
                  f'{format_number(min(series), 4)} to '
                  f'{format_number(max(series), 4)}</span>')

    return (f'<div class="a-live">'
            f'<div class="a-sec-k">{name}</div>'
            f'<div class="a-live-value">{format_number(value, 5)}{trend}</div>'
            f'{_sparkline(series)}'
            f'{extent}</div>')


def _status_line(source) -> None:
    samples = source.history()
    rate = source.rate_hz()
    elapsed = time.time() - source.started_at if source.started_at else 0.0
    parsed = source.parser.lines_parsed
    seen = source.parser.lines_seen
    bits = [f"{len(samples):,} samples",
            f"{rate:.1f} Hz",
            f"{elapsed:.0f} s connected"]
    if seen:
        bits.append(f"{parsed}/{seen} lines understood")
    st.caption("  ·  ".join(bits))
    if seen and parsed == 0:
        st.warning(
            "Lines are arriving but none of them parse. The usual cause is a "
            "baud rate that does not match the device. Print numbers as CSV "
            "(`1.4,-0.2`), as `name=value` pairs, or as one JSON object per "
            f"line. Last line seen: `{source.parser.last_unparsed}`")


@st.fragment(run_every=REFRESH_SECONDS)
def _live_view(prefs: dict) -> None:
    """The part that redraws on its own.

    Kept in a fragment so the twice-a-second refresh reruns this block only.
    A whole-page rerun at this rate would rebuild the sidebar, every category
    and the header 120 times a minute.
    """
    source = livesource.active()
    if source is None or not source.running:
        st.markdown('<div class="a-note">Not connected. Choose a port above, '
                    'or start the simulated signal to see how this works.</div>',
                    unsafe_allow_html=True)
        return

    _status_line(source)

    window_label = st.session_state.get("live_window", "Last 30 s")
    seconds = WINDOW_CHOICES.get(window_label, 30.0)
    _readouts(source, seconds if seconds is not None else 600.0)

    channels = source.channels()
    if not channels:
        st.caption("Waiting for the first sample…")
        return

    samples = source.history()
    if seconds is not None:
        cutoff = time.time() - seconds
        samples = [pair for pair in samples if pair[0] >= cutoff]

    selected = [name for name in channels
                if st.session_state.get(f"live_ch_{name}", True)]
    charts.stream_chart(samples, selected,
                        prefs.get("appearance", "Follow system"))

    st.markdown('<div class="a-label">Over this window</div>',
                unsafe_allow_html=True)
    _statistics(source, seconds)
    _export(source)


def _statistics(source, seconds) -> None:
    """What each channel did over the window, rather than what it is now.

    A single live number is whatever the channel happened to be at the instant
    the page drew. A mean with its spread beside it is a measurement, and that
    is the difference between a figure worth pinning into a design and one
    worth nothing.
    """
    samples = source.history()
    if seconds is not None:
        cutoff = time.time() - seconds
        samples = [pair for pair in samples if pair[0] >= cutoff]
    channels = source.channels()
    if not samples or not channels:
        return

    rows = ["| Channel | n | Mean | Spread (1σ) | Lowest | Highest |",
            "| --- | --- | --- | --- | --- | --- |"]
    for name in channels:
        stats = livesource.statistics(samples, name)
        if stats is None:
            continue
        rows.append(
            f"| {name} | {stats.count} | {format_number(stats.mean, 5)} | "
            f"± {format_number(stats.sd, 3)} | {format_number(stats.low, 5)} | "
            f"{format_number(stats.high, 5)} |")
    st.markdown("\n".join(rows))
    st.caption("Sample standard deviation, over the window shown above. It is "
               "the spread of the signal, not the accuracy of the instrument "
               "that measured it - a steady reading from a badly calibrated "
               "sensor has a small spread and is still wrong.")

    _measure_into_project(samples, channels)


def _measure_into_project(samples, channels) -> None:
    """Turn a channel's mean into a project parameter.

    This is the point of the whole section. A number measured on the bench
    becomes the number every linked calculator uses, carrying its provenance -
    how many samples it came from and how much it moved - rather than being
    retyped from memory as an assumption.
    """
    with st.popover("Send a measurement to the project"):
        with st.form("live_to_project", border=False):
            channel = st.selectbox("Channel", channels)
            label = st.text_input("Call it", value=channel.replace("_", " ")
                                  .capitalize())
            unit = st.text_input("Unit", placeholder="V",
                                 help="Must match the unit on the calculator "
                                      "input you want to link it to, exactly "
                                      "as written there.")
            if st.form_submit_button("Add to project", type="primary"):
                stats = livesource.statistics(samples, channel)
                if stats is None or not label.strip():
                    st.warning("Pick a channel with data and give it a name.")
                else:
                    project = store.load()
                    store.add_parameter(
                        project, label.strip(), stats.mean, unit.strip(),
                        "Measured",
                        f"mean of {stats.count} samples, "
                        f"1σ ± {format_number(stats.sd, 3)}")
                    store.save(project)
                    st.success(f"Added {label.strip()} = "
                               f"{format_number(stats.mean, 5)}. Open Project "
                               f"to link it.")


def _export(source) -> None:
    """The CSV button has to live inside the refreshing fragment.

    Streamlit builds a download button's payload at render time, so one drawn
    outside this fragment keeps whatever history existed on the first run -
    which was one sample. It offered "Download all 1 samples" beside a readout
    saying 147, and would have handed over a one-row file.
    """
    everything = source.history()
    if not everything:
        return
    st.download_button(
        f"Download all {len(everything):,} samples (CSV)",
        data=livesource.to_csv(everything).encode("utf-8"),
        file_name=f"ascent-{source.kind}-"
                  f"{time.strftime('%Y%m%d-%H%M%S')}.csv",
        mime="text/csv",
        key="live_download")


# ---------------------------------------------------------------------------
# Page 1 - the monitor
# ---------------------------------------------------------------------------
def render_monitor(prefs=None) -> None:
    prefs = prefs or {}
    ui.page_header(
        "Live monitor",
        r"\text{device} \;\longrightarrow\; \text{channels}(t)",
        "Read a board that is plugged into this Mac over USB and plot what it "
        "sends. Print numbers from your sketch as CSV, as <code>name=value</code> "
        "pairs, or as one JSON object per line, and they are picked up and "
        "named automatically - a header row like <code>pitch,roll</code> names "
        "the columns for everything after it.",
        "live_monitor")

    _connection_panel()
    st.write("")

    source = livesource.active()
    if source is not None and source.running:
        channels = source.channels()
        if channels:
            st.markdown('<div class="a-label">Display</div>',
                        unsafe_allow_html=True)
            window_column, channel_column = st.columns([1, 3])
            with window_column:
                st.selectbox("Time window", list(WINDOW_CHOICES),
                             index=1, key="live_window",
                             label_visibility="collapsed")
            with channel_column:
                for column, name in zip(st.columns(min(len(channels), 6)),
                                        channels[:6]):
                    with column:
                        st.checkbox(name, value=True, key=f"live_ch_{name}")

    _live_view(prefs)

    ui.assumptions([
        "Samples are timestamped when this Mac receives them, not when the "
        "device measured them. USB buffering means the two differ by a few "
        "milliseconds, and by much more if the device sends in bursts.",
        "The sample rate shown is the rate lines arrive and parse, which is "
        "a lower bound on the device's own loop rate - dropped or unparsed "
        "lines do not appear.",
        "Only lines that parse cleanly are plotted. A line containing any "
        "non-numeric field is discarded rather than half-read, so a value "
        "missing from the chart means it was never understood.",
        "Channels share one y axis. A signal in volts and one in degrees will "
        "squash each other; switch channels off to read one clearly.",
        f"History is capped at {livesource.HISTORY:,} samples. Older samples "
        "are dropped, including from the CSV export, so download long runs "
        "before they scroll off.",
        "The simulated signal is synthetic. It is there to demonstrate the "
        "page and is never a measurement of anything.",
        "A recorded log is spaced by its own time column when it has one - "
        "elapsed_s, time_s or millis. Without one the samples are spread "
        "evenly at the rate you assume, so the shape is right but the time "
        "axis is only as good as that guess.",
        "The spread shown for each channel is the sample standard deviation "
        "of the signal over the window. It says how much the reading moved, "
        "not how accurate it was: a steady reading from a badly calibrated "
        "sensor has a small spread and is still wrong.",
        "A measurement sent to the project carries the mean over the window "
        "and how many samples it came from. Choosing a window where the "
        "signal was doing something other than what you meant to measure is "
        "not something this page can detect.",
    ])

    ui.reference(
        variables=[
            ("CSV", "1.4,-0.2  - named by an earlier header row if one was sent",
             "-"),
            ("Pairs", "pitch=1.4,roll=-0.2  - names come from the line itself",
             "-"),
            ("JSON", '{"pitch": 1.4, "roll": -0.2}  - one object per line', "-"),
            ("Single", "21.5  - becomes a channel called `value`", "-"),
        ],
        example=(
            "An ESP32 logging a battery under load. The sketch prints "
            "<code>Serial.println(String(v) + \",\" + String(i));</code> after "
            "a one-off <code>Serial.println(\"voltage,current\");</code>, and "
            "both channels appear named. Watch the pack sag as current rises, "
            "then export the run and compare it against the voltage-sag "
            "calculator."),
    )


# ---------------------------------------------------------------------------
# Page 2 - live data driving an equation
# ---------------------------------------------------------------------------
def _numeric_inputs(calc: Calculator):
    return [field for field in calc.inputs
            if field.kind in ("float", "int", "slider")]


def render_bridge(prefs=None, catalogue=None) -> None:
    """Map live channels onto a calculator's inputs and watch the result."""
    prefs = prefs or {}
    catalogue = catalogue or {}
    ui.page_header(
        "Live calculation",
        r"\text{channel}(t) \;\longrightarrow\; f(\ldots) \;\longrightarrow\; "
        r"\text{result}(t)",
        "Point a live channel at any equation in the app and the answer updates "
        "as the data arrives. A measured current becomes a predicted endurance; "
        "a measured airspeed becomes lift. Inputs you do not map keep their "
        "typed value, so only what you are actually measuring has to come from "
        "the device.",
        "live_bridge")

    source = livesource.active()
    if source is None or not source.running:
        st.info("Nothing is connected. Open **Live monitor** to connect a "
                "device or start the simulated signal, then come back.")
        return

    usable = [(slug, entry) for slug, entry in catalogue.items()
              if entry[1].compute is not None and _numeric_inputs(entry[1])]
    if not usable:
        st.caption("No calculators are available to drive.")
        return

    labels = {f"{entry[1].name}  ·  {entry[0]}": slug for slug, entry in usable}
    chosen_label = st.selectbox("Equation to drive", sorted(labels),
                                key="bridge_calc")
    calc = catalogue[labels[chosen_label]][1]

    channels = source.channels()
    if not channels:
        st.caption("Waiting for the first sample…")
        return

    st.markdown('<div class="a-label">Map channels onto inputs</div>',
                unsafe_allow_html=True)
    fields = _numeric_inputs(calc)
    mapping = {}
    typed = {}
    for row_start in range(0, len(fields), 2):
        for column, field in zip(st.columns(2), fields[row_start:row_start + 2]):
            with column:
                source_choice = st.selectbox(
                    f"{field.label} [{field.unit}]" if field.unit
                    else field.label,
                    ["Use a typed value"] + channels,
                    key=f"bridge_{calc.prefix}_{field.key}")
                if source_choice == "Use a typed value":
                    typed[field.key] = st.number_input(
                        f"{field.label} value", value=float(field.default),
                        key=f"bridge_val_{calc.prefix}_{field.key}",
                        label_visibility="collapsed", format="%.6g")
                else:
                    mapping[field.key] = source_choice
                    st.caption(f"from `{source_choice}`")

    for field in calc.inputs:
        if field.key not in typed and field.key not in mapping:
            # Choice and weight inputs are not mappable from a numeric stream;
            # they fall back to the spec's own default so the page still runs.
            typed[field.key] = field.default

    if not mapping:
        st.caption("Map at least one input to a channel to make this live.")

    st.write("")
    _bridge_result(calc, mapping, typed, prefs)

    ui.assumptions([
        "Units are not converted. The channel must already be in the unit the "
        "input asks for - a current in milliamps fed into an input expecting "
        "amps is wrong by a thousand, and nothing here can detect that.",
        "Each update uses the most recent sample only. It is an instantaneous "
        "reading, not an average, so a noisy channel gives a noisy result.",
        "Inputs left unmapped hold the value shown next to them. They do not "
        "track anything.",
        "The equation's own assumptions still apply in full. Live data makes "
        "the inputs real; it does not make the model more valid.",
    ])


@st.fragment(run_every=REFRESH_SECONDS)
def _bridge_result(calc: Calculator, mapping, typed, prefs: dict) -> None:
    source = livesource.active()
    if source is None or not source.running:
        st.caption("Disconnected.")
        return
    latest = source.latest()
    values = dict(typed)
    missing = []
    for key, channel in mapping.items():
        if channel in latest:
            values[key] = float(latest[channel])
        else:
            missing.append(channel)

    if missing:
        st.caption("Waiting for: " + ", ".join(sorted(set(missing))))
        return

    try:
        result = calc.compute(Inputs(values))
    except Exception as exc:
        st.error(f"{exc}")
        return

    secondary = []
    for item in calc.secondary:
        try:
            secondary.append((item.label, item.fn(Inputs(values), result),
                              item.unit))
        except Exception:
            continue
    ui.result(calc.result.label, result, calc.result.unit,
              secondary=secondary,
              sig=prefs.get("significant_figures", calc.result.sig))
    st.caption("Live · updating " + f"{1 / REFRESH_SECONDS:.0f} times a second "
               "from " + ", ".join(f"`{c}`" for c in sorted(set(mapping.values()))))


CALCULATORS = [
    Calculator(slug="live.monitor", name="Live monitor", latex="",
               explanation="", render=render_monitor,
               keywords=("serial", "usb", "telemetry", "arduino", "esp32",
                         "sensor", "plot", "log", "record", "live", "data")),
    Calculator(slug="live.bridge", name="Live calculation", latex="",
               explanation="", render=render_bridge,
               keywords=("live", "sensor", "drive", "telemetry", "real time",
                         "measured", "bridge")),
]
