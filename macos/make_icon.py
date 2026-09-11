"""Generate a 1024px app icon: deep-blue rounded square with a white dart."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon
import sys

S = 1024
fig = plt.figure(figsize=(S / 100, S / 100), dpi=100)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, S); ax.set_ylim(0, S); ax.axis("off")
fig.patch.set_alpha(0.0)

pad = 40
ax.add_patch(FancyBboxPatch(
    (pad + 180, pad + 180), S - 2 * pad - 360, S - 2 * pad - 360,
    boxstyle="round,pad=180,rounding_size=190",
    linewidth=0, facecolor="#1f4e79"))
ax.add_patch(Polygon([(512, 812), (806, 236), (512, 380), (218, 236)],
                     closed=True, facecolor="#ffffff", linewidth=0))
fig.savefig(sys.argv[1], transparent=True, dpi=100)
print("icon written:", sys.argv[1])
