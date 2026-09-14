"""Generate the disk-image backdrop: one still frame of the onboarding field.

    ./.venv/bin/python macos/dmg_background.py macos/dmg-background

writes `<out>.png` (640x420) and `<out>@2x.png` (1280x840). Run by hand and
commit the result, the same way macos/make_icon.py produces AppIcon.icns -
packaging must not depend on numpy and matplotlib being installed.

This is not a lookalike of the first-run backdrop. It is the same equations:
particles advected through potential flow past a lifting cylinder, projected
in perspective, with the constants lifted directly from utils/backdrop.py. A
DMG background has to be a static image - Finder cannot animate one - so this
integrates the field until it has settled and draws the trails where they are.

Two things about the composition are deliberate rather than lucky:

The body sits at the centre of the window, which is exactly where the arrow
between the two icons belongs. Particles that stray inside the body are
reseeded, so the field carves its own elliptical void there - the arrow is
framed by an absence in the flow rather than stamped on top of it.

The arrow is the ASCENT dart from the app icon, rotated to point at the
Applications folder. A generic chevron would have done the job; the mark does
the job and says whose installer this is.
"""
import sys

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon
from PIL import Image

# ---------------------------------------------------------------------------
# Field constants - keep these identical to utils/backdrop.py
# ---------------------------------------------------------------------------
U, A, GAMMA = 0.62, 0.34, 0.95
DEPTH, FOCAL, COUNT, TRAIL = 2.6, 1.9, 640, 18

W, H = 1280, 840
"""The @2x size. The window Finder opens is half this, in points."""

SEED = 7
"""Fixed, so regenerating produces the same image and a rebuilt DMG does not
show up as a spurious binary diff."""

SETTLE = 520
"""Integration steps before drawing. The field starts as a uniform scatter and
needs to be carried through the body before it looks like flow rather than
like noise."""

DT = 0.016

# The app's *light* palette, and this is not a style preference.
#
# Finder draws icon labels in near-black in a disk image window whatever the
# system appearance is - measured at rgb(3,3,4) on a dark backdrop, about
# 1.2:1 against it, which is unreadable. The window cannot restyle its own
# labels, so the backdrop has to be the thing that changes. Light it is.
TOP = "#ffffff"         # --a-surface, light
BOTTOM = "#e9eff7"      # a shade under --a-sunken, so the field has somewhere
                        # to sit without touching pure white
ACCENT = "#1f4e79"      # --a-mark in the light theme: the same fixed blue
INK = "#16212e"
MUTED = "#5d6b7d"       # 5.6:1 on the lightest part of the wash

ALPHA = 0.26
"""Global scale on trail opacity. The first-run backdrop sits behind text at
0.50; this sits behind two icons people need to find immediately, and dark
strokes on a light ground read far stronger than light ones on dark, so it is
quieter again. Raising this is the fastest way to make the DMG look cheap."""

SAFE_BOTTOM = 0.80
"""Nothing important below this fraction of the image.

Finder's window `bounds` include the title bar, so the content area is ~33pt
shorter than the number set - and that figure is not promised to stay the same
across macOS releases. Rather than chase it, the artwork keeps its bottom strip
empty so a crop of a few tens of points is invisible."""


def velocity(x, y, z):
    """Uniform stream + doublet + bound vortex. Ported from backdrop.py."""
    a = A * (1.0 - 0.22 * z / DEPTH)
    r2 = x * x + y * y
    # Floored at the body's radius, not at an epsilon: inside the body the
    # potential is meaningless and 1/r^2 runs away.
    r2 = np.maximum(r2, a * a)
    inv = 1.0 / r2
    a2 = a * a
    ux = U * (1 - a2 * (x * x - y * y) * inv * inv)
    uy = U * (-a2 * 2 * x * y * inv * inv)
    # GAMMA/(2*pi) straight from the potential - the circulation term is what
    # makes this a lifting body rather than just an obstacle.
    swirl = GAMMA * 0.1591549 * inv
    return ux + swirl * y, uy - swirl * x


def reseed(rng, n, fresh):
    """Starting positions. Fresh particles fill the volume; later ones enter
    from upstream so the field refills without a visible seam."""
    x = (rng.random(n) * 3.2 - 1.6) if fresh else np.full(n, -1.68)
    t = rng.random(n) * 2 - 1
    y = np.sign(t) * np.abs(t) ** 1.7 * 1.15
    z = rng.random(n) * DEPTH + 0.25
    life = rng.random(n) if fresh else np.zeros(n)
    return x, y, z, life


def simulate():
    """-> (trails, z, life) with trails shaped (COUNT, TRAIL, 2)."""
    rng = np.random.default_rng(SEED)
    x, y, z, life = reseed(rng, COUNT, True)
    trails = np.zeros((COUNT, TRAIL, 2))
    trails[:, :, 0] = x[:, None]
    trails[:, :, 1] = y[:, None]

    for _ in range(SETTLE):
        ux, uy = velocity(x, y, z)
        # However the field is tuned, no particle may move further in one step
        # than a trail segment can sensibly represent.
        speed = np.sqrt(ux * ux + uy * uy)
        cap = 2.2 * U
        over = speed > cap
        if np.any(over):
            scale = np.where(over, cap / np.maximum(speed, 1e-9), 1.0)
            ux, uy = ux * scale, uy * scale
        x = x + ux * DT
        y = y + uy * DT
        trails = np.roll(trails, -1, axis=1)
        trails[:, -1, 0] = x
        trails[:, -1, 1] = y
        life = life + DT * 0.22

        body = A * (1.0 - 0.22 * z / DEPTH)
        gone = ((x > 1.65) | (life > 1.0) | (np.abs(y) > 1.25)
                | (x * x + y * y < body * body))
        if np.any(gone):
            n = int(gone.sum())
            nx, ny, nz, nlife = reseed(rng, n, False)
            x[gone], y[gone], z[gone], life[gone] = nx, ny, nz, nlife
            # A reseeded particle must not drag its old trail across the frame.
            trails[gone, :, 0] = nx[:, None]
            trails[gone, :, 1] = ny[:, None]
    return trails, z, life


def project(px, py, z):
    """World -> pixels, matching backdrop.py's perspective exactly."""
    s = FOCAL / (FOCAL + z)
    span = max(W, H) * 0.62
    return W * 0.5 + px * span * s, H * 0.5 + py * span * s, s


def _rgba(hex_colour, alpha):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return (r, g, b, float(np.clip(alpha, 0, 1)))


def gradient_background(ax):
    """A vertical wash, brightest where the icons and their labels sit.

    The gradient runs light-to-slightly-darker downward, and a broad soft
    highlight is laid over the middle band so the two icon labels always have
    near-white underneath them however the flow happens to fall.
    """
    yy = np.linspace(0, 1, 256)[:, None]
    top = np.array([int(TOP[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
    bottom = np.array([int(BOTTOM[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
    wash = top + (bottom - top) * yy
    ax.imshow(np.tile(wash[:, None, :], (1, 2, 1)), extent=(0, W, H, 0),
              aspect="auto", interpolation="bilinear", zorder=0)

    # Highlight band centred on the icon row. Without it a dense patch of
    # streamlines can drift under a label and take its contrast down with it.
    gx, gy = np.meshgrid(np.linspace(0, 1, 240), np.linspace(0, 1, 160))
    band = np.exp(-(((gy - 0.50) / 0.26) ** 2)) * np.exp(-(((gx - 0.5) / 0.85) ** 2))
    glow = np.ones(band.shape + (4,))
    glow[..., 3] = band * 0.55
    # Above the trails so it can soften them, below the dart so it cannot
    # wash the one element that has to stay crisp.
    ax.imshow(glow, extent=(0, W, H, 0), aspect="auto",
              interpolation="bilinear", zorder=2.5)


def draw_trails(ax, trails, z, life):
    """Each particle as one fading polyline, nearer ones brighter and wider."""
    segments, colours, widths = [], [], []
    for i in range(COUNT):
        s = FOCAL / (FOCAL + z[i])
        # Fade in and out over a particle's life so nothing pops.
        fade = min(1.0, life[i] * 6) * min(1.0, (1 - life[i]) * 6)
        if fade <= 0:
            continue
        alpha = ALPHA * fade * (s * s)
        if alpha < 0.004:
            continue
        px, py, _ = project(trails[i, :, 0], trails[i, :, 1], z[i])
        # A trail spanning most of the frame is a particle reseeded mid-stride;
        # drawing it draws a line straight across the image.
        if np.ptp(px) > W * 0.5 or np.ptp(py) > H * 0.5:
            continue
        segments.append(np.column_stack([px, py]))
        # One in seven in ink rather than accent, at half strength: it keeps
        # the field from reading as a single flat colour.
        ink = (i % 7 == 0)
        colours.append(_rgba(INK if ink else ACCENT,
                             alpha * (0.5 if ink else 1.0)))
        widths.append(max(0.9, 3.2 * s))
    ax.add_collection(LineCollection(segments, colors=colours,
                                     linewidths=widths, capstyle="round",
                                     zorder=2))


def draw_mark_arrow(ax, cx, cy, size):
    """The ASCENT dart, rotated a quarter turn to point at Applications.

    Same polygon as macos/make_icon.py, normalised about its own centre so the
    rotation does not shift it off the window's midline.
    """
    dart = np.array([(512, 812), (806, 236), (512, 380), (218, 236)],
                    dtype=float)
    dart = (dart - np.array([512, 512])) / 512.0      # -> roughly -1..1
    # Canvas y runs downward, so this swap points the apex to the right.
    rotated = np.column_stack([dart[:, 1], dart[:, 0]])

    # A soft halo first, so the dart reads against whatever streamline happens
    # to pass behind it.
    for spread, alpha in ((1.55, 0.05), (1.3, 0.07), (1.12, 0.09)):
        ax.add_patch(Polygon((rotated * size * spread) + np.array([cx, cy]),
                             closed=True, linewidth=0,
                             facecolor=_rgba(ACCENT, alpha), zorder=3))
    ax.add_patch(Polygon((rotated * size) + np.array([cx, cy]), closed=True,
                         linewidth=0, facecolor=_rgba(ACCENT, 0.92), zorder=4))


def render(out_base):
    trails, z, life = simulate()

    fig = plt.figure(figsize=(W / 100.0, H / 100.0), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)            # canvas orientation: y downward
    ax.axis("off")

    gradient_background(ax)
    draw_trails(ax, trails, z, life)

    # Dead centre horizontally: the icons sit either side of it, and the
    # field's body carves its void here.
    draw_mark_arrow(ax, W * 0.5, H * 0.478, W * 0.052)

    # Both lines sit above SAFE_BOTTOM, so the title-bar crop cannot eat them.
    ax.text(W * 0.5, H * 0.700, "Drag ASCENT into your Applications folder",
            color=INK, fontsize=13.5, ha="center", va="center",
            family="sans-serif", zorder=5)
    ax.text(W * 0.5, H * 0.760,
            "First open:  System Settings  ·  Privacy & Security  ·  Open Anyway",
            color=MUTED, fontsize=10.5, ha="center", va="center",
            family="sans-serif", zorder=5)

    retina = out_base + "@2x.png"
    fig.savefig(retina, dpi=100)
    plt.close(fig)

    # The 1x is a downsample rather than a second render, so the two can never
    # drift apart.
    standard = out_base + ".png"
    image = Image.open(retina).convert("RGB")
    image.resize((W // 2, H // 2), Image.LANCZOS).save(standard)
    image.save(retina)
    print("wrote %s (%dx%d) and %s (%dx%d)"
          % (standard, W // 2, H // 2, retina, W, H))


if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else "macos/dmg-background")
