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
    "ink-muted": "rgba(22,27,34,0.64)",
    "ink-faint": "rgba(22,27,34,0.45)",
    "accent": "#1f4e79",
    "accent-ink": "#1f4e79",
    "accent-soft": "rgba(31,78,121,0.07)",
    "accent-line": "rgba(31,78,121,0.22)",
    "positive": "#1a7f4b",
    "warning": "#8a5a00",
    "danger": "#b3261e",
    "danger-soft": "rgba(179,38,30,0.07)",
    "grid": "#dfe4ec",
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
    "ink-faint": "rgba(230,237,246,0.44)",
    "accent": "#7ab3e8",
    "accent-ink": "#9ccbf5",
    "accent-soft": "rgba(122,179,232,0.10)",
    "accent-line": "rgba(122,179,232,0.28)",
    "positive": "#4ac98a",
    "warning": "#e0a83d",
    "danger": "#ff6b60",
    "danger-soft": "rgba(255,107,96,0.10)",
    "grid": "rgba(255,255,255,0.08)",
    "shadow": "0 0 0 1px rgba(255,255,255,0.04)",
    "shadow-lift": "0 0 0 1px rgba(255,255,255,0.08), 0 12px 32px rgba(0,0,0,0.45)",
}

# A missing token in one mode is a bug that only shows up in that mode, which
# is exactly the sort of thing nobody notices until a user reports it.
assert set(LIGHT) == set(DARK), (
    f"palette mismatch: {set(LIGHT) ^ set(DARK)}")

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
    # Shape
    "r-sm": "6px", "r-md": "10px", "r-lg": "14px",
    # Motion - referenced by every animation in the app
    "d-fast": "80ms",
    "d-base": "140ms",
    "d-slow": "220ms",
    "d-slower": "360ms",
    "ease": "cubic-bezier(.2,.7,.3,1)",
    "ease-out": "cubic-bezier(.16,1,.3,1)",
}


def _block(palette) -> str:
    return "".join(f"--a-{name}:{value};" for name, value in palette.items())


# Forcing a theme against the OS means Streamlit's own chrome - which follows
# prefers-color-scheme and cannot be reconfigured at runtime - would otherwise
# stay in the other mode. These rules put our tokens in charge of the surfaces
# Streamlit paints itself, so "Dark" on a light Mac is actually dark.
_CHROME_OVERRIDE = """
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{
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
"""

_MOTION_OVERRIDES = {
    # Halved: still legible as motion, but out of the way.
    "Reduced": ("--a-d-fast:40ms;--a-d-base:70ms;--a-d-slow:110ms;"
                "--a-d-slower:160ms;"),
    "None": "--a-d-fast:0ms;--a-d-base:0ms;--a-d-slow:0ms;--a-d-slower:0ms;",
}


def _tokens(appearance: str = "Follow system", motion: str = "Full") -> str:
    """Build the token block for the chosen appearance.

    The mode is baked in server-side rather than toggled with an attribute,
    because the page cannot run JavaScript of its own - st.html strips both
    <script> and inline handlers - so there is no way to set a data attribute
    on the document at runtime.
    """
    scale = "".join(f"--a-{name}:{value};" for name, value in SCALE.items())

    if appearance == "Light":
        css = f":root{{{_block(LIGHT)}{scale}}}" + _CHROME_OVERRIDE
    elif appearance == "Dark":
        css = f":root{{{_block(DARK)}{scale}}}" + _CHROME_OVERRIDE
    else:
        # Follow the OS, matching how Streamlit's own frontend decides, so the
        # app chrome and our components cannot drift apart.
        css = (f":root{{{_block(LIGHT)}{scale}}}"
               f"@media (prefers-color-scheme: dark)"
               f"{{:root{{{_block(DARK)}}}}}")

    override = _MOTION_OVERRIDES.get(motion)
    if override:
        css += f":root{{{override}}}"

    # The system preference always wins over the app's own motion setting.
    css += ("@media (prefers-reduced-motion: reduce){:root{"
            "--a-d-fast:0ms;--a-d-base:0ms;--a-d-slow:0ms;--a-d-slower:0ms;}}")
    return css


_COMPONENTS = """
.block-container{max-width:1180px;padding-top:var(--a-s5);
  padding-bottom:var(--a-s7);}

/* ---- App header ---- */
.a-title{font-size:var(--a-t-xl);font-weight:700;letter-spacing:0.08em;
  color:var(--a-accent-ink);margin:0 0 2px 0;line-height:1.1;}
.a-spine{font-size:var(--a-t-xs);font-weight:600;letter-spacing:0.1em;
  text-transform:uppercase;color:var(--a-ink-faint);margin:0 0 var(--a-s2) 0;}
.a-sub{font-size:var(--a-t-base);color:var(--a-ink-muted);margin:0;
  line-height:1.5;}

/* ---- Calculator page ---- */
.a-calc-title{font-size:var(--a-t-lg);font-weight:640;color:var(--a-ink);
  margin:0;letter-spacing:-0.01em;}
.a-note{font-size:var(--a-t-base);color:var(--a-ink-muted);line-height:1.6;}
.a-eyebrow{font-size:var(--a-t-xs);text-transform:uppercase;
  letter-spacing:0.09em;color:var(--a-ink-faint);font-weight:600;
  margin:var(--a-s5) 0 var(--a-s2) 0;}

/* ---- Result card: the one thing the eye should land on ---- */
.a-result{border:1px solid var(--a-accent-line);
  border-left:3px solid var(--a-accent);
  border-radius:var(--a-r-md);padding:var(--a-s3) var(--a-s4) var(--a-s4);
  background:var(--a-accent-soft);box-shadow:var(--a-shadow);
  margin:var(--a-s1) 0 var(--a-s2) 0;
  animation:a-result-in var(--a-d-slow) var(--a-ease-out) both;}
.a-result-label{font-size:var(--a-t-xs);text-transform:uppercase;
  letter-spacing:0.09em;color:var(--a-ink-faint);font-weight:600;}
.a-result-value{font-size:var(--a-t-display);font-weight:640;line-height:1.15;
  color:var(--a-ink);font-variant-numeric:tabular-nums;letter-spacing:-0.02em;
  margin-top:2px;}
.a-result-unit{font-size:var(--a-t-md);font-weight:500;color:var(--a-ink-muted);
  margin-left:var(--a-s2);letter-spacing:0;}
.a-sec{display:flex;flex-wrap:wrap;gap:var(--a-s5);margin-top:var(--a-s3);
  padding-top:var(--a-s3);border-top:1px solid var(--a-accent-line);}
.a-sec-k{font-size:var(--a-t-xs);color:var(--a-ink-faint);}
.a-sec-v{font-size:var(--a-t-md);font-weight:580;color:var(--a-ink);
  font-variant-numeric:tabular-nums;}
.a-sec-u{font-size:var(--a-t-sm);font-weight:400;color:var(--a-ink-muted);}

/* The value re-renders on every input change, so this fires naturally as a
   change cue rather than needing to be triggered. */
@keyframes a-result-in{
  from{opacity:0;transform:translateY(4px);}
  to{opacity:1;transform:none;}}

/* ---- Lists ---- */
ul.a-tight{margin:2px 0 0 0;padding-left:var(--a-s4);
  font-size:var(--a-t-sm);color:var(--a-ink-muted);line-height:1.65;}
ul.a-tight li{margin-bottom:2px;}

/* ---- Inputs: considered states, on nodes Streamlit reuses across reruns ---- */
[data-testid="stNumberInput"] input,[data-testid="stNumberInputField"]{
  font-variant-numeric:tabular-nums;
  transition:border-color var(--a-d-base) var(--a-ease),
             box-shadow var(--a-d-base) var(--a-ease);}
[data-testid="stNumberInput"]:hover{--a-hover:1;}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums;}

/* ---- Sidebar ---- */
[data-testid="stSidebar"]{border-right:1px solid var(--a-border);}

/* ---- Tables ---- */
.stMarkdown table{font-size:var(--a-t-sm);border-collapse:collapse;}
.stMarkdown table td,.stMarkdown table th{
  border-color:var(--a-border)!important;padding:6px 10px;}
.stMarkdown table th{color:var(--a-ink-faint);font-weight:600;
  text-transform:uppercase;font-size:var(--a-t-xs);letter-spacing:0.06em;}

/* ---- Entrance ---- */
@keyframes a-rise{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:none;}}

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


def inject(appearance: str = "Follow system", motion: str = "Full") -> None:
    """Emit the stylesheet for the chosen appearance and motion level.

    `st.html` routes style-only content to Streamlit's event container, so this
    costs no slot in the page layout - unlike `st.markdown`, which creates a
    real (empty) element that participates in index-based reconciliation.
    """
    st.html(f"<style>{_tokens(appearance, motion)}{_COMPONENTS}</style>")
