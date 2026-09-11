"""Matplotlib helpers.

One place to set the plot style so every graph in the app looks the same.
Figures are given an explicit light background so they match the app theme.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # no GUI backend; Streamlit renders the figure as an image

import matplotlib.pyplot as plt  # noqa: E402  (must follow the backend call)
import streamlit as st  # noqa: E402

PRIMARY = "#1f4e79"
ACCENT = "#c0392b"
MUTED = "#8a94a6"
FACE = "#ffffff"
INK = "#1b2430"


def new_figure(rows: int = 1, height: float = 3.1):
    """Create a styled figure. Returns (fig, axes) with axes always a list."""
    fig, axes = plt.subplots(rows, 1, figsize=(7.2, height * rows), sharex=(rows > 1))
    axes = [axes] if rows == 1 else list(axes)
    fig.patch.set_facecolor(FACE)
    for ax in axes:
        ax.set_facecolor(FACE)
        ax.grid(True, color="#dfe3ea", linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#c3c9d4")
        ax.tick_params(colors=INK, labelsize=9)
        ax.xaxis.label.set_color(INK)
        ax.yaxis.label.set_color(INK)
        ax.xaxis.label.set_size(10)
        ax.yaxis.label.set_size(10)
    return fig, axes


def mark_point(ax, x: float, y: float, label: str) -> None:
    """Highlight the user's current operating point on a curve."""
    ax.plot([x], [y], "o", color=ACCENT, markersize=6, zorder=5)
    ax.annotate(
        label,
        xy=(x, y),
        xytext=(6, 8),
        textcoords="offset points",
        fontsize=9,
        color=ACCENT,
    )


def show(fig) -> None:
    """Render and release the figure (matplotlib figures are not garbage
    collected on their own, and Streamlit reruns this code on every input)."""
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
