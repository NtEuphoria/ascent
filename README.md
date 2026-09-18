# ASCENT

**A**erospace · **S**tructures · **C**ontrols · **E**lectronics · **N**umerics · **T**oolkit


Interactive engineering calculators for aerospace, robotics, mechanical systems,
autonomy, electronics, and materials — in one Streamlit app, so you can switch
between equations instantly instead of opening a different tool for each one.

Every calculator shows the equation, defines every variable, states its
assumptions underneath the result, and gives one real example of where the
equation is used.

> **For education and preliminary engineering calculations. Critical designs
> must be independently verified.**

---

## Platform support

**macOS 11 or newer**, Apple Silicon and Intel (the app ships as a universal
binary). Windows and Linux are planned — the calculators themselves are pure
Python and already portable; only the native window is macOS-specific.

## Install

### Download the installer

Grab `ASCENT-1.1.0.dmg` from the
[latest release](../../releases/latest), open it, and drag **ASCENT** into your
Applications folder.

**On first open, macOS will refuse to launch it.** ASCENT is not signed with a
paid Apple Developer certificate, so Gatekeeper blocks it like any app from an
independent developer.

To allow it, try to open ASCENT once and let it be blocked, then go to
**System Settings → Privacy & Security**, scroll to the bottom, and click
**Open Anyway**. You only do this once.

> Older guides say to right-click the app and choose *Open*. Apple removed that
> shortcut in macOS 15, so on macOS 15 and later the System Settings route
> above is the one that works.

<details>
<summary>If you see "ASCENT is damaged and can't be opened"</summary>

That message is Gatekeeper's quarantine flag, not actual damage. Run:

```bash
xattr -dr com.apple.quarantine /Applications/ASCENT.app
```
</details>

### Staying up to date

ASCENT asks GitHub once a day whether a newer release exists. When there is
one, an **Update** button appears at the bottom of the sidebar and opens the
releases page in your browser; updating is still a matter of downloading the
new DMG and dragging it over. Nothing happens automatically and nothing is
installed behind your back.

The check sends no information about you or your machine - it is a single
request for the latest release tag, and the only network request the app makes
at all. Turn it off under **Settings -> About** if you would rather it made
none.

### Or build it yourself

```bash
git clone https://github.com/NtEuphoria/ascent.git
cd ascent && ./install.sh
```

Building requires Apple's command line tools (`xcode-select --install`).

### First launch

**The first launch takes about a minute.** ASCENT builds its own Python
environment in `~/Library/Application Support/ASCENT` and shows you its
progress while it works. Every launch after that is instant.

It needs **Python 3.9+** on your Mac. macOS does not always include it — if
ASCENT cannot find one, it tells you exactly what to run. An internet
connection is required for the first launch only.

Nothing else is needed. The app is self-contained; you can delete the source
folder after installing and it keeps working.

## Run

Open **ASCENT** from Launchpad, Applications or Spotlight. It opens as a real
macOS app: its own window, Dock icon and menu bar. No browser, no tab, no
address bar.

- `Cmd-Q` quits, and shuts the calculation engine down with it
- `Cmd-R` reloads, `Cmd +/-/0` zoom
- The window remembers its size and position
- **⌘K** opens a searchable palette over every calculator
- **⚙ Settings**, bottom-left, for appearance, motion, result precision and
  reference sections — stored in the support folder and kept between launches
- **ASCENT → Show Logs & Data Folder** opens the support folder

Under the hood it is a native Cocoa app wrapping a WKWebView around a local
Streamlit server — the same approach Slack, Notion and VS Code use. The server
binds to `127.0.0.1` only and is never reachable from your network.

### Uninstalling

Drag `ASCENT.app` to the Trash, and delete
`~/Library/Application Support/ASCENT` to remove its Python environment.

---

## Developing

Run the calculators directly, without the native wrapper:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Run the tests:

```bash
.venv/bin/pip install pytest && .venv/bin/python -m pytest tests/ -q
```

751 tests: hand-worked known values for every equation, rejection tests for bad
inputs, headless renders of every page, end-to-end checks that each page's
headline number is what it should be, contrast measured programmatically in
every theme, and the stream parser exercised over a real pseudo-terminal.

### Build scripts

| Script | What it does |
| --- | --- |
| `./build.sh` | Compiles the Swift window and assembles `dist/ASCENT.app` |
| `./install.sh` | Builds, then installs to `/Applications` |
| `./package.sh` | Builds, then produces `dist/ASCENT-<version>.dmg` |
| `./publish.sh` | Creates the GitHub repo, pushes, and publishes a release with the installer attached |

The native window's source is `macos/main.swift`; its icon is generated by
`macos/make_icon.py`. `Stop ASCENT.command` force-kills a server left running
by `streamlit run` — the app itself cleans up after itself on quit.

---

## What is included

**85 calculators across 16 categories**, in three sections you switch between
in the sidebar:

- **Calculators** — 76 pages, one equation at a time.
- **Studios** — a guided run through a whole design, carrying one set of
  numbers from end to end.
- **Live** — read a device over a serial port, or replay a log.

Every calculator shows its equation, defines each variable, states its
assumptions under the result, and gives a real example of where it is used.

| Category | Pages |
| --- | --- |
| **Project** | Project |
| **Studios** | Drone powertrain, Robot drivetrain, Lift and arm, Wing study, Structure, Control tuning |
| **Aerodynamics** | Lift, Drag, Dynamic pressure, Lift-to-drag ratio, Wing loading, Aspect ratio, Reynolds number |
| **Flight performance** | Thrust-to-weight ratio, Power-to-weight ratio, Stall speed, Rate of climb, Glide performance |
| **Drones** | Total thrust, Thrust-to-weight ratio, Hover thrust per motor, Flight time (estimate), Electrical power, Battery energy, Battery sag & internal resistance, Electric range & endurance |
| **Propulsion** | Momentum theory (hover), Hover power & endurance, Propeller advance ratio, Motor constants (Kv, Kt, back-EMF), Rocket equation, Rocket thrust & mass flow |
| **Mechanical** | Force (F = ma), Torque, Work, Power, Linear momentum, Kinetic energy, Potential energy, Mechanical advantage, Gear ratio |
| **Rotational mechanics** | Angular velocity (RPM to rad/s), Rotational power, Centripetal force, Moment of inertia, Rotational kinetic energy |
| **Structures** | Second moment of area, Beam bending, Torsion of a shaft, Column buckling, Elastic constants (E, ν, G, K) |
| **Materials** | Normal stress, Strain, Young's modulus, Factor of safety, Density, Specific strength |
| **Robotics** | Differential drive kinematics, Gear train: reflected inertia, Servo / arm holding torque, Encoder resolution, Two-link arm: inverse kinematics |
| **Electrical / robotics** | Ohm's law, Electrical power, Resistors in series, Resistors in parallel, Battery energy, Wire voltage drop |
| **Control systems** | Control error, PID simulator, Second-order step response, Ziegler–Nichols tuning |
| **Live data** | Live monitor, Live calculation |
| **Unit converter** | Length, Velocity, Mass, Force, Pressure, Energy, Power, Temperature |
| **Constants / reference** | Engineering constants, Standard atmosphere (ISA) |

Graphs are **interactive** — hover for a readout anywhere on the curve, drag to
pan, scroll to zoom — and follow light and dark automatically.

---

## Project structure

```
ascent/
├── app.py                  # Navigation registry + page shell. Nothing else.
├── build.sh                # -> dist/ASCENT.app
├── install.sh              # -> /Applications/ASCENT.app
├── package.sh              # -> dist/ASCENT-<version>.dmg, window and all
├── publish.sh              # -> a GitHub release with the DMG attached
├── requirements.txt
├── LICENSE
├── README.md
├── macos/                  # The native macOS app
│   ├── main.swift          # Cocoa window + WKWebView + engine lifecycle
│   ├── Info.plist
│   ├── AppIcon.icns
│   ├── make_icon.py        # Generates AppIcon.icns
│   ├── dmg_background.py   # Generates the installer backdrop
│   └── dmg-background*.png # ...its committed output, 1x and 2x
├── .streamlit/
│   └── config.toml         # Deliberately no [theme]: see the file
├── assets/
│   └── studios-hero.png
├── docs/
│   ├── BACKDROP.md         # What the first-run field is, and why
│   ├── EXPANSION.md
│   └── SLUGS.md
├── calculators/            # One module per category
│   ├── aerodynamics.py     flight.py         drones.py
│   ├── propulsion.py       robotics.py       structures.py
│   ├── mechanical.py       rotational.py     materials.py
│   ├── electrical.py       controls.py       units.py
│   ├── reference.py        live.py           project.py
├── studios/                # Guided end-to-end designs
│   ├── shell.py            # step / figures / check / verdict board
│   ├── drone_powertrain.py drivetrain.py     lift_arm.py
│   └── wing.py             structure.py      control_tuning.py
├── plugins/
│   └── ascent-engineering/ # Agents and skills for working on this repo
├── utils/
│   ├── spec.py             # Calculator / Field / Output - a page as data
│   ├── render.py           # The one renderer that turns a spec into a page
│   ├── theme.py            # Design tokens, light + dark, motion
│   ├── analysis.py         # Elasticity, influence, uncertainty propagation
│   ├── project.py          # Shared parameters and the requirements board
│   ├── stream.py           # Parses whatever a device prints into channels
│   ├── livesource.py       # Serial, log playback, demo; and statistics
│   ├── backdrop.py         # The generative field behind first-run setup
│   ├── onboarding.py       # First-run setup
│   ├── announce.py         # The Studios introduction card
│   ├── update.py           # Asks GitHub once a day if there is a newer build
│   ├── charts.py           # Interactive Altair charts
│   ├── palette.py          # Command palette search and ranking
│   ├── navigate.py         # In-app jumps between pages and sections
│   ├── settings.py         # User preferences, persisted as JSON
│   ├── constants.py        # g, rho_0, p_0, ... each with a source note
│   ├── validation.py       # ValidationError + positive/non_zero/in_range...
│   ├── conversions.py      # Unit tables (SI base unit as the pivot)
│   ├── formatting.py       # Significant-digit number formatting
│   ├── plotting.py         # Matplotlib style, for the remaining custom plots
│   └── ui.py               # Page scaffolding: header, inputs, result, notes
└── tests/                  # 712 of them
    ├── test_calculations.py    # Physics, hand-checked known values
    ├── test_rendered_values.py # Every page's headline number, end to end
    ├── test_design.py          # Contrast, motion tokens, stylesheet invariants
    ├── test_analysis.py        # Elasticity and uncertainty identities
    ├── test_stream.py          # Every line shape a device might print
    ├── test_update.py          # Version comparison, caching, the button
    ├── test_studios.py         # ...and one file per studio
    ├── test_packaging.py       # What has to be inside the .app
    └── test_app.py             # Renders every page headlessly
```

### How each calculator module is laid out

Two halves, always in this order:

1. **Pure functions** at the top. No Streamlit. Each one validates its own
   inputs and returns a number in SI units. These are what the tests exercise.
2. **`render_*` functions** below. Layout only — they read widgets, call the
   pure functions, and display the result.

At the bottom, a `CALCULATORS` dict maps the sidebar label to its render
function. `app.py` collects those dicts into `CATEGORIES`.

---

## Adding a new equation

Copy the shape of an existing one — `calculators/aerodynamics.py` → `render_lift`
is the reference example.

A calculator is **data**, not layout code: you describe its inputs, equation
and assumptions, and one renderer draws the page. Pages that need unusual
controls can still take over with `render=`.

**1. Write the calculation** (in the matching module, or a new one):

```python
def glide_ratio(altitude: float, distance: float) -> float:
    """Glide ratio = horizontal distance / height lost   [-]"""
    altitude = v.positive(altitude, "Height lost", "m")
    distance = v.non_negative(distance, "Distance covered", "m")
    return distance / altitude
```

Validate every input here, not in the UI. Use `utils.validation`:
`positive`, `non_negative`, `non_zero`, `in_range`, `positive_int`, `finite`.

**2. Write the page:**

```python
def render_glide_ratio() -> None:
    p = "aero_glide"                       # unique prefix for this page's keys
    ui.page_header(
        "Glide ratio",                     # 1. name
        r"\frac{L}{D} = \frac{d}{h}",      # 2. equation (LaTeX)
        "How far you travel per unit of height lost with no power.",  # 3. summary
        p,
    )
    c1, c2 = st.columns(2)                 # 4. inputs, units in every label
    with c1:
        distance = ui.number("Distance covered d", "m", f"{p}_d", 15000.0,
                             min_value=0.0)
    with c2:
        altitude = ui.number("Height lost h", "m", f"{p}_h", 1000.0,
                             min_value=0.0)

    value = ui.compute(lambda: glide_ratio(altitude, distance))   # 5. + 6.
    if value is not None:
        ui.result("Glide ratio", value, "-",
                  secondary=[("Glide angle", ..., "°")])
    ui.assumptions([                       # 8. shown under the result
        "Still air - wind changes the ground distance but not the air distance.",
    ])
    if ui.graph_toggle(p):                 # optional graph
        fig, (ax,) = new_figure()
        ...
        show(fig)
    ui.reference(                          # 3. + 9.
        variables=[("$d$", "Horizontal distance", "m"),
                   ("$h$", "Height lost", "m")],
        example="Planning a dead-stick landing from 1000 m.",
    )
```

**3. Register it** at the bottom of the module:

```python
CALCULATORS = {
    ...
    "Glide ratio": render_glide_ratio,
}
```

It appears in the sidebar immediately. A **new category** means one new module
plus one line in `CATEGORIES` in `app.py`.

**4. Add a test** in `tests/test_calculations.py` with a value you worked out by
hand, and one that confirms a bad input is rejected:

```python
def test_glide_ratio():
    assert aero.glide_ratio(1000.0, 15000.0) == pytest.approx(15.0)

def test_glide_ratio_rejects_zero_height():
    with pytest.raises(ValidationError):
        aero.glide_ratio(0.0, 15000.0)
```

### Key naming

Every widget key starts with the page's prefix (`aero_lift_v`, `aero_lift_s`).
The Reset button deletes all session-state keys beginning with that prefix,
which makes each widget fall back to the default declared in its own call — so
defaults are defined in exactly one place. Keep the prefix unique per page.

---

## Accuracy conventions

These are deliberate, and worth keeping if you extend the app:

- **SI internally, always.** Friendlier units (mm², gram-force, MPa, RPM, mAh)
  are converted at the input and again at the output. Nothing downstream has to
  guess what unit it is holding.
- **Mass and weight are never mixed.** Weight is a force in newtons, computed as
  `W = m × g` with `g = 9.80665 m/s²`. Anywhere weight is needed,
  `ui.weight_inputs()` offers kg or N and shows the conversion on screen.
- **Validation lives in the pure functions.** A division by zero, a negative
  area or a temperature below absolute zero produces a clear message, never a
  number.
- **Assumptions are shown, not hidden.** They sit directly under the result.
- **Estimates are labelled as estimates.** Flight time and stall speed say so;
  exact definitions (lift, Ohm's law, unit conversions) say that too.
- **Four significant digits** by default, switching to scientific notation
  outside 10⁻³–10⁶.

## Roadmap

- The calculators still outstanding from the v1.1 plan: drag polar, airspeed
  and density altitude, turn performance.
- No plain equation is left on the imperative path: 61 of 85 pages are
  declarative specs, and the 24 that are not each have a structural reason -
  guided studios, the moment-of-inertia shape picker, Ohm's law switching which
  quantity is the headline, resistor networks taking a variable-length list,
  the PID simulation, live streaming, and the conversion and lookup tables.
- **Windows and Linux builds.** The calculators are pure Python and already
  run anywhere Streamlit does; only the native window needs porting.
- **Notarisation.** Until then Gatekeeper blocks the app on first open and
  everyone has to go through System Settings to allow it.
- Aerofoil polar lookup, so lift and drag coefficients stop being guesses.

## Limitations

- Aerodynamics assumes incompressible flow (below roughly Mach 0.3).
- The PID page simulates a first-order plant with perfect measurement and no
  time delay. It builds intuition; it does not model your hardware.
- The ISA model covers 0–20 km geopotential altitude, dry air only.
- Range and endurance use the constant-weight (electric) Breguet form. A
  fuel-burning aircraft gets lighter as it flies and needs the log-mass-ratio
  form instead; the page says so rather than quietly giving a wrong answer.
- The app is not notarised by Apple, so macOS blocks it on first open.
