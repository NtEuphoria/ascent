"""ASCENT design system: tokens, palettes and component styles.

Replaces the hardcoded CSS string that v1.0.0 used. Three things matter here:

1. **Light and dark are one stylesheet.** Both palettes declare the identical
   set of token names (enforced below), so a colour can never exist in one mode
   and be missing in the other.

2. **The theme signal is `prefers-color-scheme`, not Python.** Streamlit's own
   frontend calls `matchMedia("(prefers-color-scheme: dark)")`, so keying our
   tokens off the same media query means the app chrome and our components can
   never disagree. `st.context.theme` is explicitly documented as unreliable on
   first load, so it is deliberately not used for styling.

3. **Motion is a token, not a magic number.** Every transition in the app draws
   its duration and easing from here, so the whole interface moves with one
   vocabulary - and all of it collapses to 0ms under `prefers-reduced-motion`.
"""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Colour: semantic roles, not raw names
# ---------------------------------------------------------------------------

LIGHT = {
    "bg": "#ffffff",
    "surface": "#ffffff",
    "raised": "#f6f8fb",
    "sunken": "#eef2f7",
    "border": "rgba(16,24,40,0.10)",
    "border-strong": "rgba(16,24,40,0.20)",
    "ink": "#161b22",
    "ink-muted": "rgba(22,27,34,0.74)",
    "ink-faint": "rgba(22,27,34,0.62)",   # see tests/test_design.py
    "accent": "#1f4e79",
    "accent-ink": "#1f4e79",
    "accent-soft": "rgba(31,78,121,0.07)",
    "accent-line": "rgba(31,78,121,0.22)",
    "positive": "#1a7f4b",
    "warning": "#8a5a00",
    "danger": "#b3261e",
    "danger-soft": "rgba(179,38,30,0.07)",
    "grid": "#dfe4ec",
    "edge": "rgba(255,255,255,0.90)",
    "mark": "#1f4e79",
    "shadow": "0 1px 2px rgba(16,24,40,0.04), 0 2px 8px rgba(16,24,40,0.06)",
    "shadow-lift": "0 2px 4px rgba(16,24,40,0.06), 0 8px 24px rgba(16,24,40,0.10)",
}

# Dark is not "light inverted". Accents lift so they stay legible on a dark
# ground, and elevation reads through lighter borders rather than shadows,
# which turn to mud against a dark background.
DARK = {
    "bg": "#0f1319",
    "surface": "#141922",
    "raised": "#1a212c",
    "sunken": "#0b0e13",
    "border": "rgba(255,255,255,0.10)",
    "border-strong": "rgba(255,255,255,0.20)",
    "ink": "#e6edf6",
    "ink-muted": "rgba(230,237,246,0.64)",
    "ink-faint": "rgba(230,237,246,0.60)",  # 6.4:1 on the dark ground
    "accent": "#7ab3e8",
    "accent-ink": "#9ccbf5",
    "accent-soft": "rgba(122,179,232,0.10)",
    "accent-line": "rgba(122,179,232,0.28)",
    "positive": "#4ac98a",
    "warning": "#e0a83d",
    "danger": "#ff6b60",
    "danger-soft": "rgba(255,107,96,0.10)",
    "grid": "rgba(255,255,255,0.08)",
    "edge": "rgba(255,255,255,0.055)",
    "mark": "#7ab3e8",
    "shadow": "0 0 0 1px rgba(255,255,255,0.04)",
    "shadow-lift": "0 0 0 1px rgba(255,255,255,0.08), 0 12px 32px rgba(0,0,0,0.45)",
}

# A missing token in one mode is a bug that only shows up in that mode, which
# is exactly the sort of thing nobody notices until a user reports it.
assert set(LIGHT) == set(DARK), (
    f"palette mismatch: {set(LIGHT) ^ set(DARK)}")

# ---------------------------------------------------------------------------
# Accents
# ---------------------------------------------------------------------------
# Each accent carries its own light and dark pair. Dark values are lifted, not
# the same hex: a colour legible on white is rarely legible on near-black.
# Every one of these clears 4.5:1 against its own background (tested).

ACCENTS = {
    "Blue": {
        "light": ("#1f4e79", "#1f4e79", "rgba(31,78,121,0.07)",
                  "rgba(31,78,121,0.22)"),
        "dark": ("#7ab3e8", "#9ccbf5", "rgba(122,179,232,0.10)",
                 "rgba(122,179,232,0.28)"),
    },
    "Teal": {
        "light": ("#0f6257", "#0f6257", "rgba(15,98,87,0.07)",
                  "rgba(15,98,87,0.22)"),
        "dark": ("#4fc7ba", "#7ad9cf", "rgba(79,199,186,0.10)",
                 "rgba(79,199,186,0.28)"),
    },
    "Violet": {
        "light": ("#5b3fa8", "#5b3fa8", "rgba(91,63,168,0.07)",
                  "rgba(91,63,168,0.22)"),
        "dark": ("#b49bf0", "#c9b8f6", "rgba(180,155,240,0.10)",
                 "rgba(180,155,240,0.28)"),
    },
    "Amber": {
        "light": ("#8a5a00", "#8a5a00", "rgba(138,90,0,0.08)",
                  "rgba(138,90,0,0.24)"),
        "dark": ("#e0a83d", "#eec06a", "rgba(224,168,61,0.10)",
                 "rgba(224,168,61,0.28)"),
    },
    "Slate": {
        "light": ("#3d4754", "#3d4754", "rgba(61,71,84,0.06)",
                  "rgba(61,71,84,0.20)"),
        "dark": ("#9aa6b5", "#c2cbd6", "rgba(154,166,181,0.10)",
                 "rgba(154,166,181,0.26)"),
    },
}

# ---------------------------------------------------------------------------
# Density
# ---------------------------------------------------------------------------
# Compact tightens vertical rhythm and type without changing the grid, for
# people working on a laptop screen who would rather see the graph without
# scrolling. It touches spacing and type only - never hit targets.

DENSITY = {
    "Comfortable": {},
    "Compact": {
        "s3": "9px", "s4": "12px", "s5": "18px", "s6": "24px", "s7": "34px",
        "t-base": "0.86rem", "t-md": "1.0rem", "t-lg": "1.2rem",
        "t-xl": "1.7rem", "t-display": "2.2rem",
    },
}


def _accent_block(accent: str, mode: str) -> str:
    """Accent tokens for one accent name in one mode."""
    values = ACCENTS.get(accent, ACCENTS["Blue"])[mode]
    names = ("accent", "accent-ink", "accent-soft", "accent-line")
    return "".join(f"--a-{n}:{v};" for n, v in zip(names, values))

# ---------------------------------------------------------------------------
# Scale: type, space, radius, motion. Mode-independent.
# ---------------------------------------------------------------------------

SCALE = {
    # Type - one scale, no ad-hoc sizes
    "t-xs": "0.72rem",
    "t-sm": "0.81rem",
    "t-base": "0.9rem",
    "t-md": "1.05rem",
    "t-lg": "1.3rem",
    "t-xl": "1.9rem",
    "t-display": "2.6rem",
    # Space - 4px grid
    "s1": "4px", "s2": "8px", "s3": "12px", "s4": "16px",
    "s5": "24px", "s6": "32px", "s7": "48px",
    # Families. No webfonts: the app must work offline, and macOS already
    # ships the two faces this needs. Numbers get a true monospace because
    # this is an instrument whose entire output is figures - digits that
    # shift width as a value changes read as unstable.
    "font-ui": ('-apple-system, BlinkMacSystemFont, "SF Pro Text", '
                '"Helvetica Neue", sans-serif'),
    "font-num": ('ui-monospace, "SF Mono", SFMono-Regular, Menlo, '
                 'monospace'),
    # Shape
    "r-sm": "6px", "r-md": "10px", "r-lg": "14px",
    # Motion - referenced by every animation in the app
    "d-fast": "80ms",
    "d-base": "140ms",
    "d-slow": "220ms",
    "d-slower": "360ms",
    "d-draw": "620ms",
    "ease": "cubic-bezier(.2,.7,.3,1)",
    "ease-out": "cubic-bezier(.16,1,.3,1)",
    "ease-quart": "cubic-bezier(.25,1,.5,1)",     # snappy, for press feedback
    "ease-expo": "cubic-bezier(.16,1,.3,1)",      # long tail, for entrances
}


def _block(palette) -> str:
    return "".join(f"--a-{name}:{value};" for name, value in palette.items())


# Forcing a theme against the OS means Streamlit's own chrome - which follows
# prefers-color-scheme and cannot be reconfigured at runtime - would otherwise
# stay in the other mode. These rules put our tokens in charge of the surfaces
# Streamlit paints itself, so "Dark" on a light Mac is actually dark.
_CHROME_OVERRIDE = """
/* html and body sit behind everything Streamlit paints. Overriding only
   .stApp leaves the document background in the other mode, which shows through
   on overscroll and is what the web view composites against. */
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{
  background:var(--a-bg)!important;}
[data-testid="stSidebar"],[data-testid="stSidebarContent"]{
  background:var(--a-raised)!important;}
[data-testid="stHeader"]{background:transparent!important;}
.stApp,.stMarkdown,.stMarkdown p,.stMarkdown li,.stMarkdown td,
[data-testid="stWidgetLabel"] p,h1,h2,h3,h4{color:var(--a-ink)!important;}

/* Widgets are the fiddly part. Streamlit styles these through Base Web with
   its own light/dark values, which our token block does not reach - so
   forcing only the page colours leaves dark fields with dark text on them.
   Everything a widget paints has to be reclaimed explicitly. */
.stApp input,.stApp textarea,[data-testid="stDialog"] input,
.stApp [data-baseweb="input"],.stApp [data-baseweb="base-input"],
.stApp [data-baseweb="select"] > div,
[data-testid="stNumberInputContainer"],
[data-testid="stDialog"] [data-baseweb="input"]{
  background-color:var(--a-surface)!important;color:var(--a-ink)!important;}

.stApp button,[data-testid="stDialog"] button{
  background-color:var(--a-surface)!important;color:var(--a-ink)!important;
  border-color:var(--a-border)!important;}
/* The primary action keeps its accent - it should still read as the default. */
.stApp button[kind="primary"],[data-testid="stDialog"] button[kind="primary"]{
  background-color:var(--a-accent)!important;color:#ffffff!important;
  border-color:var(--a-accent)!important;}

[data-testid="stRadio"] label,[data-testid="stRadio"] p,
[data-testid="stCheckbox"] label,[data-testid="stCheckbox"] p,
[data-testid="stDialog"],[data-testid="stDialog"] p,
[data-testid="stDialog"] label,[data-baseweb="popover"] li{
  color:var(--a-ink)!important;}
[data-testid="stDialog"],[data-baseweb="popover"] ul{
  background-color:var(--a-surface)!important;}

/* Stepper chevrons and the dropdown arrow are drawn as SVG. */
[data-testid="stNumberInputStepUp"] svg,[data-testid="stNumberInputStepDown"] svg,
.stApp [data-baseweb="select"] svg{fill:var(--a-ink-muted)!important;}

[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{
  color:var(--a-ink-muted)!important;}

/* An unselected radio keeps the fill from the mode we are overriding away
   from, which shows as a solid dark disc on a light page. */
[data-testid="stRadio"] label:has(input:not(:checked)) > div:first-child{
  background-color:var(--a-surface)!important;
  border:1px solid var(--a-border-strong)!important;}
[data-testid="stRadio"] label:has(input:not(:checked)) > div:first-child > div{
  background-color:transparent!important;}

/* A checkbox leaks the same way, and worse: the box keeps the fill of the
   mode we are overriding away from, so on a light page "Show graph" is a
   solid black square whose tick is white-on-white when you check it. Base Web
   puts the box in the first span of the label, before the input. */
[data-testid="stCheckbox"] label[data-baseweb="checkbox"] > span:first-child{
  background-color:var(--a-surface)!important;
  border-color:var(--a-border-strong)!important;}
"""

# Every duration token has to appear in both overrides. A token missing from
# them is an animation the Motion setting cannot reach, which is how the
# mark's draw kept playing with motion switched off - see
# tests/test_design.py::test_every_duration_token_is_scaled_by_the_setting.
_MOTION_OVERRIDES = {
    # Halved: still legible as motion, but out of the way.
    "Reduced": ("--a-d-fast:40ms;--a-d-base:70ms;--a-d-slow:110ms;"
                "--a-d-slower:160ms;--a-d-draw:300ms;"),
    "None": ("--a-d-fast:0ms;--a-d-base:0ms;--a-d-slow:0ms;"
             "--a-d-slower:0ms;--a-d-draw:0ms;"),
}


def _tokens(appearance: str = "Follow system", motion: str = "Full",
            accent: str = "Blue", density: str = "Comfortable") -> str:
    """Build the token block for the chosen appearance.

    The mode is baked in server-side rather than toggled with an attribute,
    because the page cannot run JavaScript of its own - st.html strips both
    <script> and inline handlers - so there is no way to set a data attribute
    on the document at runtime.
    """
    scale_values = dict(SCALE)
    scale_values.update(DENSITY.get(density, {}))
    scale = "".join(f"--a-{name}:{value};" for name, value in scale_values.items())
    light_accent = _accent_block(accent, "light")
    dark_accent = _accent_block(accent, "dark")

    if appearance == "Light":
        css = (f":root{{{_block(LIGHT)}{light_accent}{scale}}}"
               + _CHROME_OVERRIDE)
    elif appearance == "Dark":
        css = (f":root{{{_block(DARK)}{dark_accent}{scale}}}"
               + _CHROME_OVERRIDE)
    else:
        # Follow the OS, matching how Streamlit's own frontend decides, so the
        # app chrome and our components cannot drift apart.
        css = (f":root{{{_block(LIGHT)}{light_accent}{scale}}}"
               f"@media (prefers-color-scheme: dark)"
               f"{{:root{{{_block(DARK)}{dark_accent}}}}}")

    override = _MOTION_OVERRIDES.get(motion)
    if override:
        css += f":root{{{override}}}"

    # The system preference always wins over the app's own motion setting.
    css += ("@media (prefers-reduced-motion: reduce){:root{"
            "--a-d-fast:0ms;--a-d-base:0ms;--a-d-slow:0ms;"
            "--a-d-slower:0ms;--a-d-draw:0ms;}}")
    return css


_COMPONENTS = """
.block-container{max-width:1180px;padding-top:var(--a-s5);
  padding-bottom:var(--a-s7);}

/* A checked box is the one piece of Streamlit chrome that paints its own
   brand colour. Left alone it is #FF4B4B, so the app is blue everywhere
   except the control the user just clicked. This has to live outside the
   forced-mode override: in "Follow system" that block never runs. */
[data-testid="stCheckbox"]
  label[data-baseweb="checkbox"]:has(input:checked) > span:first-child{
  background-color:var(--a-accent)!important;
  border-color:var(--a-accent)!important;}

/* ---- App header ---- */
/* The mark appears in the app, not only on the icon. Drawn inline so it takes
   the accent colour and needs no asset to load. */
.a-brand{display:flex;align-items:center;gap:var(--a-s3);
  margin:0 0 var(--a-s1) 0;}
.a-brand svg{width:22px;height:22px;flex:none;display:block;}
.a-brand svg path{fill:var(--a-mark);}
.a-title{font-size:var(--a-t-xl);font-weight:680;letter-spacing:0.11em;
  color:var(--a-accent-ink);margin:0;line-height:1;
  font-family:var(--a-font-ui);}
.a-spine{font-size:var(--a-t-xs);font-weight:450;letter-spacing:0.055em;
  color:var(--a-ink-faint);margin:0 0 var(--a-s2) 0;}
.a-spine b{color:var(--a-accent-ink);font-weight:680;}
.a-sub{font-size:var(--a-t-base);color:var(--a-ink-muted);margin:0;
  line-height:1.5;max-width:72ch;}

/* ---- Calculator page ---- */
.a-crumb{font-size:var(--a-t-xs);color:var(--a-ink-faint);
  margin:0 0 2px 0;letter-spacing:0.02em;}
.a-calc-title{font-size:var(--a-t-lg);font-weight:640;color:var(--a-ink);
  margin:0;letter-spacing:-0.015em;text-wrap:balance;}
.a-note{font-size:var(--a-t-base);color:var(--a-ink-muted);line-height:1.65;
  max-width:72ch;text-wrap:pretty;}
.a-label{display:flex;align-items:center;gap:var(--a-s3);
  font-size:var(--a-t-sm);color:var(--a-ink-muted);font-weight:560;
  margin:var(--a-s5) 0 var(--a-s2) 0;}
.a-label::after{content:"";flex:1;height:1px;background:var(--a-border);}

/* The equation is the subject of the page, so it gets a surface of its own
   rather than floating in the margin. */
[data-testid="stMarkdownContainer"] .katex-display{
  margin:var(--a-s4) 0!important;padding:var(--a-s4) var(--a-s5);
  background:var(--a-raised);border:1px solid var(--a-border);
  border-radius:var(--a-r-md);overflow-x:auto;overflow-y:hidden;
  box-shadow:inset 0 1px 0 var(--a-edge);}

/* ---- Result ---- */
/* The one number the page exists to produce. Monospace and tabular so it
   holds its shape while you type, with the unit clearly subordinate. */
.a-result{border:1px solid var(--a-accent-line);
  border-radius:var(--a-r-md);padding:var(--a-s4) var(--a-s5) var(--a-s5);
  background:var(--a-accent-soft);
  box-shadow:inset 0 1px 0 var(--a-edge);
  margin:var(--a-s1) 0 var(--a-s2) 0;
  animation:a-rise var(--a-d-slow) var(--a-ease-expo) both;}
.a-result-label{font-size:var(--a-t-sm);color:var(--a-ink-muted);
  font-weight:500;letter-spacing:0;}
.a-result-value{font-family:var(--a-font-num);
  font-size:var(--a-t-display);font-weight:600;line-height:1.1;
  color:var(--a-ink);font-variant-numeric:tabular-nums;
  letter-spacing:-0.025em;margin-top:var(--a-s1);
  display:flex;align-items:baseline;gap:var(--a-s2);flex-wrap:wrap;}
.a-result-unit{font-family:var(--a-font-ui);font-size:var(--a-t-md);
  font-weight:500;color:var(--a-ink-muted);margin:0;letter-spacing:0;}

/* Supporting values line up on a grid, not a wrapped row of odd gaps. */
.a-sec{display:grid;
  grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:var(--a-s3) var(--a-s5);margin-top:var(--a-s4);
  padding-top:var(--a-s3);border-top:1px solid var(--a-accent-line);}
.a-sec-k{font-size:var(--a-t-xs);color:var(--a-ink-faint);
  margin-bottom:1px;}
.a-sec-v{font-family:var(--a-font-num);font-size:var(--a-t-md);
  font-weight:550;color:var(--a-ink);font-variant-numeric:tabular-nums;
  letter-spacing:-0.01em;}
.a-sec-u{font-family:var(--a-font-ui);font-size:var(--a-t-sm);
  font-weight:400;color:var(--a-ink-muted);letter-spacing:0;}

/* A live readout. Smaller than the result headline - there are several of
   them and none is the answer - but the same instrument face, and tabular so
   a changing value does not shuffle sideways twice a second. */
.a-live-value{font-family:var(--a-font-num);font-size:var(--a-t-lg);
  font-weight:600;color:var(--a-ink);font-variant-numeric:tabular-nums;
  letter-spacing:-0.015em;line-height:1.25;}

/* ---- Influence table ---- */
/* A grid rather than a table: four columns that stay aligned down the list,
   with the bar as the thing the eye actually compares. */
.a-inf-list{list-style:none;margin:var(--a-s3) 0 0 0;padding:0;
  display:flex;flex-direction:column;gap:2px;}
.a-inf{display:grid;
  grid-template-columns:minmax(8rem,1.4fr) 4.6rem minmax(4rem,1fr) auto;
  align-items:center;gap:var(--a-s3);
  padding:7px var(--a-s2);border-radius:var(--a-r-sm);
  animation:a-rise var(--a-d-slow) var(--a-ease-expo) both;
  animation-delay:var(--d,0ms);
  transition:background-color var(--a-d-fast) var(--a-ease);}
.a-inf:hover{background:var(--a-raised);}
.a-inf-k{font-size:var(--a-t-sm);color:var(--a-ink);}
.a-inf-v{font-family:var(--a-font-num);font-size:var(--a-t-sm);
  font-weight:600;font-variant-numeric:tabular-nums;
  letter-spacing:-0.01em;color:var(--a-ink);text-align:right;}
.a-inf-why{font-size:var(--a-t-xs);color:var(--a-ink-faint);
  white-space:nowrap;}

/* The track is always full width so the bars share one scale; only the fill
   varies. Without the track the eye has nothing to measure against. */
.a-inf-bar{position:relative;height:7px;border-radius:999px;
  background:var(--a-sunken);overflow:hidden;}
.a-inf-bar i{position:absolute;inset:0 auto 0 0;display:block;
  border-radius:999px;width:var(--w,0%);
  transform-origin:left center;
  animation:a-bar-grow var(--a-d-slower) var(--a-ease-expo) both;
  animation-delay:var(--d,0ms);
  transition:width var(--a-d-slow) var(--a-ease-expo);}
.a-inf-up i{background:var(--a-accent);}
/* A negative elasticity moves the result the other way. That is a different
   fact, not a smaller one, so it reads as a different colour rather than a
   shorter bar. */
.a-inf-down i{background:var(--a-warning);}
.a-inf-off{opacity:.62;}
.a-inf-off .a-inf-v{font-family:var(--a-font-ui);font-weight:400;
  color:var(--a-ink-faint);font-size:var(--a-t-xs);text-align:right;}

/* Scale rather than width: width is a layout property and animating it on
   every row forces a reflow per frame. */
@keyframes a-bar-grow{from{transform:scaleX(0);}to{transform:scaleX(1);}}

/* ---- Explore tabs ---- */
/* Switching tabs is a change of subject, so the new panel arrives rather than
   replacing the old one in place. */
[data-testid="stTabs"] [role="tabpanel"]{
  animation:a-panel-in var(--a-d-slow) var(--a-ease-expo) both;}
@keyframes a-panel-in{from{opacity:0;transform:translateY(4px);}
  to{opacity:1;transform:none;}}
[data-testid="stTabs"] button[role="tab"]{
  transition:color var(--a-d-base) var(--a-ease),
             background-color var(--a-d-fast) var(--a-ease);}

/* ---- Regime checks ---- */
/* A Check is the page telling you the model has stopped being true. It should
   arrive noticeably, but never by moving anything below it - the slot is
   reserved whether or not it fires. */
[data-testid="stAlert"]{
  animation:a-check-in var(--a-d-slow) var(--a-ease-expo) both;}
@keyframes a-check-in{from{opacity:0;transform:translateY(-3px) scale(.995);}
  to{opacity:1;transform:none;}}

/* ---- Live readouts ---- */
/* The value itself is never animated between numbers - a readout that tweens
   through values it never measured is inventing data. Only the frame reacts. */
.a-live{padding:var(--a-s2) 0;}
.a-live-value{transition:color var(--a-d-base) var(--a-ease);
  display:flex;align-items:baseline;gap:var(--a-s2);}
.a-live-trend{font-size:0.55em;line-height:1;font-family:var(--a-font-ui);
  transition:opacity var(--a-d-base) var(--a-ease),
             color var(--a-d-base) var(--a-ease);}
.a-live-up{color:var(--a-positive);}
.a-live-down{color:var(--a-warning);}
.a-spark{display:block;width:100%;height:26px;margin:var(--a-s1) 0 2px;
  overflow:visible;}
.a-spark polyline{fill:none;stroke:var(--a-accent);stroke-width:1.5;
  stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke;
  opacity:.85;}
.a-live-extent{font-size:var(--a-t-xs);color:var(--a-ink-faint);
  font-family:var(--a-font-num);font-variant-numeric:tabular-nums;}

/* ---- The mark ---- */
/* The dart draws itself on first paint, the same gesture the splash makes, so
   launching the app and landing in it are one continuous motion. */
.a-brand svg path{
  animation:a-mark-draw var(--a-d-draw) var(--a-ease-expo) both;}
@keyframes a-mark-draw{
  from{opacity:0;transform:translateY(2px) scale(.86);}
  to{opacity:1;transform:none;}}
.a-brand svg{transform-box:fill-box;transform-origin:center;}

/* ---- Lists ---- */
ul.a-tight{margin:2px 0 0 0;padding-left:var(--a-s4);
  font-size:var(--a-t-sm);color:var(--a-ink-muted);line-height:1.65;}
ul.a-tight li{margin-bottom:2px;}

/* ---- Inputs: considered states, on nodes Streamlit reuses across reruns ---- */
[data-testid="stNumberInput"] input,[data-testid="stNumberInputField"]{
  font-family:var(--a-font-num);font-variant-numeric:tabular-nums;
  letter-spacing:-0.01em;
  transition:border-color var(--a-d-base) var(--a-ease),
             box-shadow var(--a-d-base) var(--a-ease);}
[data-testid="stNumberInput"]:hover{--a-hover:1;}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums;}

/* ---- Sidebar ---- */
[data-testid="stSidebar"]{border-right:1px solid var(--a-border);}

/* ---- Tables ---- */
.stMarkdown table{font-size:var(--a-t-sm);border-collapse:collapse;}
.stMarkdown table td:last-child{font-family:var(--a-font-num);
  font-variant-numeric:tabular-nums;color:var(--a-ink-muted);}
.stMarkdown table td,.stMarkdown table th{
  border-color:var(--a-border)!important;padding:6px 10px;}
.stMarkdown table th{color:var(--a-ink-muted);font-weight:600;
  font-size:var(--a-t-xs);}

/* ======================================================================
   MOTION
   Every duration below resolves through the --a-d-* tokens, so the Motion
   setting (Full / Reduced / None) and the system's Reduce Motion preference
   both govern all of it from one place.

   Entrances animate from a visible default rather than gating visibility on a
   class: if an animation never fires - a headless render, a hidden tab - the
   content must still be there.
   ====================================================================== */

@keyframes a-rise{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:none;}}
@keyframes a-fade{from{opacity:0;}to{opacity:1;}}
@keyframes a-mark-in{from{transform:scale(.35);opacity:.3;}
  to{transform:scale(1);opacity:1;}}
@keyframes a-value-in{from{opacity:.3;transform:translateY(3px);}
  to{opacity:1;transform:none;}}

/* ---- Press feedback -------------------------------------------------- */
/* Buttons take a real press: a small scale under the finger, released on a
   quart curve so it feels mechanical rather than rubbery. */
[data-testid="stButton"] button,[data-testid="stPopover"] button{
  transition:background-color var(--a-d-base) var(--a-ease),
             border-color var(--a-d-base) var(--a-ease),
             color var(--a-d-base) var(--a-ease),
             box-shadow var(--a-d-base) var(--a-ease),
             transform var(--a-d-fast) var(--a-ease-quart);}
[data-testid="stButton"] button:active,
[data-testid="stPopover"] button:active{transform:scale(.972);}
[data-testid="stButton"] button:focus-visible,
[data-testid="stPopover"] button:focus-visible{
  outline:none;box-shadow:0 0 0 3px var(--a-accent-soft),
  0 0 0 1px var(--a-accent);}

/* The favourite star earns a little more: it is a moment of intent. */
[class*="st-key-fav--"] button{
  transition:color var(--a-d-base) var(--a-ease),
             background-color var(--a-d-base) var(--a-ease),
             transform var(--a-d-base) var(--a-ease-quart);}
[class*="st-key-fav--"] button:hover{transform:scale(1.14) rotate(-6deg);}
[class*="st-key-fav--"] button:active{transform:scale(.9);}

/* ---- Selection ------------------------------------------------------- */
/* The chosen marker scales in rather than appearing, so the eye can follow
   which option took the selection. */
[data-testid="stRadio"] label:has(input:checked) > div:first-child > div{
  animation:a-mark-in var(--a-d-base) var(--a-ease-quart);}
[data-testid="stRadio"] label{
  transition:background-color var(--a-d-fast) var(--a-ease),
             color var(--a-d-fast) var(--a-ease);}

/* Toggles and checkboxes: the track colour and the knob travel together. */
[data-testid="stCheckbox"] [data-baseweb="checkbox"] div,
[data-testid="stCheckbox"] [role="checkbox"],
[data-testid="stCheckbox"] [role="switch"] *{
  transition:background-color var(--a-d-base) var(--a-ease),
             transform var(--a-d-base) var(--a-ease-quart),
             border-color var(--a-d-base) var(--a-ease)!important;}

/* Segmented controls and tabs slide their selection. */
button[kind="segmented_controlActive"],button[kind="pillsActive"],
button[kind="segmented_control"],button[kind="pills"]{
  transition:background-color var(--a-d-base) var(--a-ease),
             color var(--a-d-base) var(--a-ease),
             border-color var(--a-d-base) var(--a-ease);}
[data-baseweb="tab-highlight"]{
  transition:all var(--a-d-slow) var(--a-ease-expo)!important;}

/* ---- The result ------------------------------------------------------ */
/* The card rises in when the page opens; the value itself re-animates on
   every change, which doubles as the "this number just updated" cue. */
.a-result{animation:a-rise var(--a-d-slow) var(--a-ease-expo) both;}
.a-result-value{animation:a-value-in var(--a-d-slow) var(--a-ease-expo);}
.a-sec > div{animation:a-fade var(--a-d-slower) var(--a-ease-expo) both;}
.a-sec > div:nth-child(2){animation-delay:40ms;}
.a-sec > div:nth-child(3){animation-delay:80ms;}
.a-sec > div:nth-child(4){animation-delay:120ms;}

/* Assumptions arrive as a list, so they stagger as a list. */
ul.a-tight li{animation:a-fade var(--a-d-slow) var(--a-ease-expo) both;}
ul.a-tight li:nth-child(2){animation-delay:35ms;}
ul.a-tight li:nth-child(3){animation-delay:70ms;}
ul.a-tight li:nth-child(4){animation-delay:105ms;}
ul.a-tight li:nth-child(5){animation-delay:140ms;}
ul.a-tight li:nth-child(n+6){animation-delay:175ms;}

/* ---- Overlays -------------------------------------------------------- */
/* @starting-style defines where the entrance begins without ever hiding the
   element by default - so a frame that never animates still shows content. */
[data-testid="stDialog"] > div,[data-baseweb="popover"] > div{
  transition:opacity var(--a-d-slow) var(--a-ease-expo),
             transform var(--a-d-slow) var(--a-ease-expo);}
@starting-style{
  [data-testid="stDialog"] > div{opacity:0;transform:translateY(10px) scale(.985);}
  [data-baseweb="popover"] > div{opacity:0;transform:translateY(-4px);}
}

/* ---- Inputs ---------------------------------------------------------- */
[data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"]{
  transition:opacity var(--a-d-base) var(--a-ease),
             background-color var(--a-d-fast) var(--a-ease);}

/* ---- Charts ---------------------------------------------------------- */
[data-testid="stVegaLiteChart"],[data-testid="stImage"]{
  animation:a-fade var(--a-d-slower) var(--a-ease-expo) both;}

/* Sidebar destinations feel like a list you move through. */
[data-testid="stSidebar"] [class*="st-key-fav"] button,
[data-testid="stSidebar"] [class*="st-key-rec"] button{
  transition:color var(--a-d-fast) var(--a-ease),
             background-color var(--a-d-fast) var(--a-ease),
             padding-left var(--a-d-base) var(--a-ease-quart);}
[data-testid="stSidebar"] [class*="st-key-fav"] button:hover,
[data-testid="stSidebar"] [class*="st-key-rec"] button:hover{
  padding-left:var(--a-s3);}

/* ---- Widget chrome ----------------------------------------------------
   Streamlit's [theme] config keys (baseRadius, showWidgetBorder, primaryColor)
   would normally supply this, but using any of them pins the app to one mode
   and breaks system dark mode. So shape, borders, focus and accent are applied
   here instead, where they can follow prefers-color-scheme like everything
   else. See .streamlit/config.toml for the full reasoning.                  */

html{font-size:15px;}

[data-testid="stNumberInputContainer"],
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] input{
  border-radius:var(--a-r-sm)!important;
  border:1px solid var(--a-border)!important;
  transition:border-color var(--a-d-base) var(--a-ease),
             box-shadow var(--a-d-base) var(--a-ease),
             background-color var(--a-d-base) var(--a-ease);}

[data-testid="stNumberInputContainer"]:hover,
[data-testid="stSelectbox"] > div > div:hover{
  border-color:var(--a-border-strong)!important;}

[data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stSelectbox"] > div > div:focus-within{
  border-color:var(--a-accent)!important;
  box-shadow:0 0 0 3px var(--a-accent-soft)!important;}

/* Steppers: quiet until the field is engaged, so a row of inputs reads calmly */
[data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"]{
  opacity:0.45;transition:opacity var(--a-d-base) var(--a-ease);}
[data-testid="stNumberInputContainer"]:hover [data-testid="stNumberInputStepUp"],
[data-testid="stNumberInputContainer"]:hover [data-testid="stNumberInputStepDown"],
[data-testid="stNumberInputContainer"]:focus-within [data-testid="stNumberInputStepUp"],
[data-testid="stNumberInputContainer"]:focus-within [data-testid="stNumberInputStepDown"]{
  opacity:1;}

[data-testid="stWidgetLabel"] p{
  font-size:var(--a-t-sm)!important;color:var(--a-ink-muted)!important;
  font-weight:500;}

[data-testid="stButton"] button{
  border-radius:var(--a-r-sm);border:1px solid var(--a-border-strong);
  font-size:var(--a-t-sm);font-weight:540;
  transition:background-color var(--a-d-base) var(--a-ease),
             border-color var(--a-d-base) var(--a-ease),
             transform var(--a-d-fast) var(--a-ease);}
[data-testid="stButton"] button:hover{
  border-color:var(--a-accent);color:var(--a-accent-ink);
  background:var(--a-accent-soft);}
[data-testid="stButton"] button:active{transform:translateY(1px);}

/* Accent -----------------------------------------------------------------
   config.toml cannot set primaryColor without pinning the app to one light or
   dark mode, so Streamlit falls back to its default red for every selected
   control. These rules put the ASCENT accent back. Selected and unselected
   states are separated with :has(), which this WebKit supports. */
/* Scoped to the marker itself: `label div div` also matches the wrapper that
   holds the label text, which paints an accent block across the words. */
/* Base Web fills the outer ring with the primary colour and nests a smaller
   disc inside, so both have to be reclaimed or a red rim shows around the
   accent dot. */
[data-testid="stRadio"] label:has(input:checked) > div:first-child,
[data-testid="stRadio"] label:has(input:checked) > div:first-child > div,
[data-testid="stSlider"] [role="slider"]{
  background-color:var(--a-accent)!important;
  border-color:var(--a-accent)!important;}
button[kind="primary"]{background-color:var(--a-accent)!important;
  border-color:var(--a-accent)!important;color:#ffffff!important;}

/* Segmented controls, pills and tabs draw their selected state from
   primaryColor too, which is Streamlit's red here. Same reclaim. */
button[kind="segmented_controlActive"],
button[kind="pillsActive"],
[data-testid="stBaseButton-segmented_controlActive"],
[data-testid="stBaseButton-pillsActive"]{
  color:var(--a-accent-ink)!important;
  border-color:var(--a-accent)!important;
  background-color:var(--a-accent-soft)!important;}
[data-baseweb="tab-highlight"]{background-color:var(--a-accent)!important;}
[role="tab"][aria-selected="true"],
[role="tab"][aria-selected="true"] *{color:var(--a-accent-ink)!important;}
[role="tab"]{color:var(--a-ink-muted)!important;}
[role="tab"]:hover{color:var(--a-ink)!important;}

/* Sidebar ----------------------------------------------------------------
   Streamlit gives every button full padding and every block a 1rem gap, which
   turned six recent items into a screenful of mostly nothing. Quick links are
   single-line rows in a collapsed group; the section headings carry a count so
   the panel reads as structure rather than a stack of identical pills. */

[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:0.4rem;}
[data-testid="stSidebarUserContent"]{padding-top:var(--a-s2);}

.a-side-head{display:flex;align-items:baseline;justify-content:space-between;
  font-size:var(--a-t-xs);font-weight:600;color:var(--a-ink-faint);
  margin:var(--a-s4) 0 var(--a-s1) 0;padding:0 var(--a-s1);
  border-bottom:1px solid var(--a-border);padding-bottom:var(--a-s1);}
.a-side-head span{font-weight:500;font-variant-numeric:tabular-nums;
  opacity:.75;}

/* Collapse the group so rows sit directly under one another. */
[class*="st-key-quick_"] [data-testid="stVerticalBlock"]{gap:0!important;}
[class*="st-key-quick_"] [data-testid="stElementContainer"]{margin:0!important;}

[data-testid="stSidebar"] [class*="st-key-fav--"] button,
[data-testid="stSidebar"] [class*="st-key-rec--"] button{
  justify-content:flex-start;text-align:left;border:none;
  background:transparent;font-weight:500;font-size:var(--a-t-sm);
  color:var(--a-ink-muted);min-height:0;height:auto;
  padding:5px var(--a-s2);border-radius:var(--a-r-sm);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
[data-testid="stSidebar"] [class*="st-key-fav--"] button:hover,
[data-testid="stSidebar"] [class*="st-key-rec--"] button:hover{
  color:var(--a-accent-ink);background:var(--a-accent-soft);}

/* Search reads as a field, not a button. */
.st-key-palette_open_visible button{
  justify-content:flex-start;color:var(--a-ink-faint);
  font-size:var(--a-t-sm);font-weight:450;
  border:1px solid var(--a-border);background:var(--a-surface);
  padding:6px var(--a-s3);min-height:0;}
.st-key-palette_open_visible button:hover{
  color:var(--a-ink-muted);border-color:var(--a-border-strong);}

/* The equation list is the working surface: tighter, with a clear current row. */
[data-testid="stSidebar"] [data-testid="stRadio"] label{
  padding:3px var(--a-s2);margin:0;font-size:var(--a-t-sm);}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){
  background:var(--a-accent-soft);}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p{
  color:var(--a-accent-ink)!important;font-weight:560;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"]{display:none;}

/* The favourite star sits in the page header beside Reset. */
[class*="st-key-fav--"] button{border-color:transparent;
  background:transparent;font-size:1.05rem;color:var(--a-ink-faint);}
[class*="st-key-fav--"] button:hover{color:var(--a-warning);
  background:var(--a-accent-soft);}

/* Sidebar show/hide ------------------------------------------------------
   Streamlit draws these icons in its own theme colour - near-white - which
   disappears completely on a light page, leaving no visible way to bring the
   sidebar back. Token-driven so they are legible in both modes, with enough
   weight to read as a control rather than a stray glyph. */
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"]{
  border-radius:var(--a-r-sm);
  transition:background-color var(--a-d-base) var(--a-ease);}
[data-testid="stExpandSidebarButton"] *,
[data-testid="stSidebarCollapseButton"] *{
  color:var(--a-ink-muted)!important;fill:var(--a-ink-muted)!important;}
[data-testid="stExpandSidebarButton"]:hover,
[data-testid="stSidebarCollapseButton"]:hover{
  background:var(--a-accent-soft);}
[data-testid="stExpandSidebarButton"]:hover *,
[data-testid="stSidebarCollapseButton"]:hover *{
  color:var(--a-accent-ink)!important;fill:var(--a-accent-ink)!important;}

/* Settings lives at the bottom of the sidebar, where macOS apps, Claude and
   ChatGPT all put it. The sidebar body becomes a flex column so the button can
   be pushed down with margin-top:auto rather than guessed at with padding. */
[data-testid="stSidebarUserContent"]{display:flex;flex-direction:column;
  min-height:calc(100vh - 7rem);}
.st-key-settings_open{margin-top:auto;padding-top:var(--a-s3);}
.st-key-settings_open button{justify-content:flex-start;
  color:var(--a-ink-muted);border-color:transparent;background:transparent;
  font-size:var(--a-t-sm);}
.st-key-settings_open button:hover{color:var(--a-accent-ink);
  background:var(--a-accent-soft);border-color:var(--a-accent-line);}

/* Command palette -------------------------------------------------------
   The trigger is moved off-screen rather than display:none, so the native
   Cmd-K menu item can still click it through evaluateJavaScript.          */
.st-key-palette_trigger{position:absolute!important;left:-9999px!important;
  width:1px!important;height:1px!important;overflow:hidden!important;}

.st-key-palette_open_visible button{
  justify-content:flex-start;color:var(--a-ink-muted);
  font-size:var(--a-t-sm);}
.st-key-palette_open_visible button:hover{color:var(--a-accent-ink);}

[data-testid="stDialog"] [data-testid="stButton"] button{
  justify-content:flex-start;text-align:left;border-color:transparent;
  background:transparent;font-weight:500;}
[data-testid="stDialog"] [data-testid="stButton"] button:hover{
  background:var(--a-accent-soft);border-color:var(--a-accent-line);}

/* Sidebar navigation: the item you are on should be obvious at a glance */
[data-testid="stSidebar"] [data-testid="stRadio"] label{
  border-radius:var(--a-r-sm);padding:2px var(--a-s2);
  transition:background-color var(--a-d-fast) var(--a-ease);}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover{
  background:var(--a-accent-soft);}
"""


def stylesheet(appearance: str = "Follow system", motion: str = "Full",
               accent: str = "Blue", density: str = "Comfortable") -> str:
    """The complete sheet the page receives, tokens first then components.

    Separate from `inject` so a test can assert on exactly what ships rather
    than reassembling the pieces itself and drifting from the real order.
    """
    return _tokens(appearance, motion, accent, density) + _COMPONENTS


def inject(appearance: str = "Follow system", motion: str = "Full",
           accent: str = "Blue", density: str = "Comfortable") -> None:
    """Emit the stylesheet for the chosen appearance and motion level.

    `st.html` routes style-only content to Streamlit's event container, so this
    costs no slot in the page layout - unlike `st.markdown`, which creates a
    real (empty) element that participates in index-based reconciliation.
    """
    st.html(f"<style>{stylesheet(appearance, motion, accent, density)}</style>")
