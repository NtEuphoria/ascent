"""Matplotlib helpers.

One place to set the plot style so every graph in the app looks the same.
Figures are given an explicit light background so they match the app theme.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # no GUI backend; Streamlit renders the figure as an image

import matplotlib.pyplot as plt  # noqa: E402  (must follow the backend call)
import streamlit as st  # noqa: E402

PRIMARY = "#4a90d9"     # legible on white and on near-black
ACCENT = "#e0603f"
MUTED = "#8a94a6"
# Transparent figures with a mid-grey ink, so the few remaining matplotlib
# plots (the PID response and the ISA profile) read correctly in light and dark
# without needing to know which one is active. A raster cannot adapt after it
# is drawn, and the server cannot reliably tell which theme the browser chose.
FACE = "none"
INK = "#8a94a6"


def new_figure(rows: int = 1, height: float = 3.1):
    """Create a styled figure. Returns (fig, axes) with axes always a list."""
    fig, axes = plt.subplots(rows, 1, figsize=(7.2, height * rows), sharex=(rows > 1))
    axes = [axes] if rows == 1 else list(axes)
    fig.patch.set_alpha(0.0)
    for ax in axes:
        ax.patch.set_alpha(0.0)
        ax.grid(True, color=MUTED, alpha=0.25, linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(MUTED)
        ax.tick_params(colors=INK, labelsize=9)
        ax.xaxis.label.set_color(INK)
        ax.yaxis.label.set_color(INK)
        ax.xaxis.label.set_size(10)
        ax.yaxis.label.set_size(10)
    return fig, axes


def mark_point(ax, x: float, y: float, label: str) -> None:
    """Highlight the user's current operating point on a curve.

    The label is placed away from whichever edge the point is nearest. Always
    putting it up-and-right reads fine mid-curve and badly at the corners: at
    the ISA page's default altitude of 0 m the point sits top-left, and the
    label lands on top of the chart title.
    """
    ax.plot([x], [y], "o", color=ACCENT, markersize=6, zorder=5)
    fx, fy = _axes_fraction(ax, x, y)
    dx, ha = (-7, "right") if fx > 0.80 else (7, "left")
    dy, va = (-9, "top") if fy > 0.78 else (9, "bottom")
    ax.annotate(
        label,
        xy=(x, y),
        xytext=(dx, dy),
        textcoords="offset points",
        fontsize=9,
        color=ACCENT,
        ha=ha,
        va=va,
        zorder=6,
    )


def _axes_fraction(ax, x: float, y: float):
    """Where a data point falls in the axes box, 0-1 from bottom left.

    Routed through transData rather than transLimits so log axes - which the
    gear-ratio and power-loading sweeps use - are placed correctly too.
    """
    try:
        # Limits are only recomputed at draw time, and mark_point is called
        # immediately after plotting - without this the transform still holds
        # the default 0-1 box and every point looks like it is off the top
        # right corner.
        ax.autoscale_view()
        return tuple(ax.transAxes.inverted().transform(
            ax.transData.transform((x, y))))
    except (ValueError, TypeError):
        return (0.0, 0.0)  # degenerate axes: fall back to the old placement


def show(fig) -> None:
    """Render and release the figure (matplotlib figures are not garbage
    collected on their own, and Streamlit reruns this code on every input)."""
    fig.tight_layout()
    st.pyplot(fig, transparent=True)
    plt.close(fig)
