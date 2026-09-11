"""Interactive, theme-aware charts.

v1.0.0 drew graphs as matplotlib PNGs with a hardcoded white background. Once
the app followed macOS dark mode those became glaring white rectangles on a
dark page - a raster image cannot adapt after it is drawn.

Altair charts are vector, and Streamlit themes them from the frontend, so they
follow light and dark for free. They are also interactive: hover for a readout
at any point on the curve, drag to pan, scroll to zoom. Altair and pandas both
ship as Streamlit dependencies, so this adds nothing to install and works
offline.

Colours here are chosen to read on both a white and a near-black ground, since
the series colour is the one thing Streamlit's theme does not override.
"""
from __future__ import annotations

from typing import Optional

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

LINE = "#4a90d9"      # legible on white and on #0e1117
MARKER = "#e0603f"    # operating point
GUIDE = "#8a94a6"     # crosshair / reference lines

# Streamlit themes charts from its frontend, which follows the OS. That is
# right when the app is following the OS too, and wrong the moment the user
# forces Light or Dark - the chart would keep the other mode's colours. These
# palettes take over in exactly that case.
_CHART_LIGHT = {"text": "#4a5463", "title": "#161b22",
                "grid": "#dfe4ec", "domain": "#c3c9d4"}
_CHART_DARK = {"text": "#98a4b3", "title": "#e6edf6",
               "grid": "#262d38", "domain": "#39424f"}

_HEIGHT = 300


def sweep_chart(xs, ys, x_label: str, y_label: str, title: str,
                point_x: Optional[float] = None,
                point_y: Optional[float] = None,
                log_y: bool = False,
                appearance: str = "Follow system") -> None:
    """Draw one curve with a hover readout and the current operating point.

    Column names are deliberately neutral ("x"/"y") because Altair treats
    brackets and dots in field names as path syntax - and almost every axis
    label here contains a unit in brackets.
    """
    frame = pd.DataFrame({"x": np.asarray(xs, dtype=float),
                          "y": np.asarray(ys, dtype=float)}).dropna()
    if frame.empty:
        st.caption("No valid points to plot across this range.")
        return

    y_scale = alt.Scale(type="log") if log_y else alt.Scale(zero=False, nice=True)
    base = alt.Chart(frame)

    line = base.mark_line(color=LINE, strokeWidth=2.5,
                          interpolate="monotone").encode(
        x=alt.X("x:Q", title=x_label, scale=alt.Scale(nice=True)),
        y=alt.Y("y:Q", title=y_label, scale=y_scale),
    )

    # Crosshair that snaps to the nearest sample, so any point on the curve can
    # be read off directly instead of estimated against the axis.
    hover = alt.selection_point(nearest=True, on="pointerover", fields=["x"],
                                empty=False)
    crosshair = base.mark_rule(color=GUIDE, strokeWidth=1).encode(
        x=alt.X("x:Q"),
        opacity=alt.condition(hover, alt.value(0.45), alt.value(0.0)),
        tooltip=[alt.Tooltip("x:Q", title=x_label, format=".4~g"),
                 alt.Tooltip("y:Q", title=y_label, format=".4~g")],
    ).add_params(hover)

    layers = [line, crosshair]

    if point_x is not None and point_y is not None and np.isfinite(point_y):
        current = pd.DataFrame({"x": [float(point_x)], "y": [float(point_y)]})
        layers.append(
            alt.Chart(current).mark_point(
                color=MARKER, size=90, filled=True, opacity=1.0).encode(
                x="x:Q", y="y:Q",
                tooltip=[alt.Tooltip("x:Q", title=x_label, format=".4~g"),
                         alt.Tooltip("y:Q", title=y_label, format=".4~g")]))
        layers.append(
            alt.Chart(current).mark_text(
                text="current", color=MARKER, dy=-14, fontSize=11,
                fontWeight=600).encode(x="x:Q", y="y:Q"))

    chart = (alt.layer(*layers)
             .properties(height=_HEIGHT, title=title, background="transparent")
             .interactive())        # drag to pan, scroll to zoom

    if appearance in ("Light", "Dark"):
        # Take over completely: Streamlit's own chart theme would still be
        # following the operating system.
        palette = _CHART_LIGHT if appearance == "Light" else _CHART_DARK
        chart = (chart
                 .configure_title(fontSize=13, anchor="start", fontWeight=600,
                                  color=palette["title"])
                 .configure_view(strokeWidth=0)
                 .configure_axis(labelColor=palette["text"],
                                 titleColor=palette["title"],
                                 gridColor=palette["grid"],
                                 domainColor=palette["domain"],
                                 tickColor=palette["domain"]))
        st.altair_chart(chart, use_container_width=True, theme=None)
        return

    chart = (chart
             .configure_title(fontSize=13, anchor="start", fontWeight=600)
             .configure_view(strokeWidth=0))
    st.altair_chart(chart, use_container_width=True)
