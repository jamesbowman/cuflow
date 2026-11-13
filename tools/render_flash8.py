"""Render the generated FLASH8 manufacturing layers for visual inspection."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as PlotPath
from matplotlib.patches import PathPatch, Circle

from tools.pcb_topology import parse_cuflow_gerber, parse_excellon


def draw(ax, geometry, color, alpha=1):
    if geometry.is_empty:
        return
    if hasattr(geometry, "geoms"):
        for item in geometry.geoms:
            draw(ax, item, color, alpha)
        return
    vertices, codes = [], []
    for ring in (geometry.exterior, *geometry.interiors):
        points = list(ring.coords)
        vertices.extend(points)
        codes.extend([PlotPath.MOVETO] + [PlotPath.LINETO] * (len(points) - 2) + [PlotPath.CLOSEPOLY])
    ax.add_patch(PathPatch(PlotPath(vertices, codes), facecolor=color,
                           edgecolor="none", alpha=alpha))


def main():
    fig, axes = plt.subplots(2, 2, figsize=(13, 13), facecolor="#10202c")
    drills = parse_excellon(Path("flash8.TXT"))
    for ax, layer, title in zip(axes.flat,
            ("GTL", "GBL", "G2L", "G3L"),
            ("Top copper + silkscreen", "Bottom copper · viewed from top",
             "Inner layer 2 · GND", "Inner layer 3 · 3.3 V")):
        ax.set_facecolor("#164b3c")
        draw(ax, parse_cuflow_gerber(Path(f"flash8.{layer}")), "#d9ad59")
        if layer in ("GTL", "GBL"):
            mask = "GTS" if layer == "GTL" else "GBS"
            draw(ax, parse_cuflow_gerber(Path(f"flash8.{mask}")), "#dce6e7")
        if layer == "GTL":
            draw(ax, parse_cuflow_gerber(Path("flash8.GTO")), "#ffffff")
        for hit in drills:
            ax.add_patch(Circle(hit.xy, hit.diameter / 2, color="#10202c", linewidth=0))
        ax.set(xlim=(0, 49), ylim=(0, 49), aspect="equal")
        ax.set_title(title, color="white", fontsize=13, pad=12)
        ax.tick_params(colors="#c0d0d8", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#668080")
    fig.suptitle("FLASH8  |  49 × 49 mm  |  Four-layer SPI/QSPI validation fixture",
                 color="white", fontsize=16)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig("flash8-copper.png", dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    main()
