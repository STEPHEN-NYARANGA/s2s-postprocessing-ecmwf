"""Quick-look figures (latitude/longitude axes)."""

from __future__ import annotations

import datetime as dt

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .config import VARIABLES, WINDOWS  # noqa: E402
from .grid import LAT, LON  # noqa: E402

_NAMES = {"tas": "2 m temperature", "mslp": "Mean sea level pressure", "pr": "Precipitation"}


def _to_pm180(field):
    lon = np.where(LON >= 180, LON - 360, LON)
    order = np.argsort(lon)
    return lon[order], field[:, order]


def _coastlines(ax):
    try:
        import cartopy.feature as cfeature
        for geom in cfeature.COASTLINE.with_scale("110m").geometries():
            for line in getattr(geom, "geoms", [geom]):
                x, y = line.xy
                ax.plot(x, y, color="0.25", lw=0.4)
    except Exception:
        pass  # no cartopy or no Natural Earth download: plot without coastlines


def quicklook(cfg, init: dt.date, probs: dict, path):
    """P(upper quintile) minus P(lower quintile) for each variable and window."""
    fig, axes = plt.subplots(len(VARIABLES), len(WINDOWS), figsize=(13, 10), constrained_layout=True)
    im = None
    for i, var in enumerate(VARIABLES):
        for j, w in enumerate(WINDOWS):
            ax = axes[i, j]
            p = probs.get((var, w))
            if p is None:
                ax.set_axis_off()
                continue
            lon, f = _to_pm180(100.0 * (p[4] - p[0]))
            im = ax.pcolormesh(lon, LAT, f, cmap="RdBu_r", vmin=-50, vmax=50, shading="nearest")
            _coastlines(ax)
            ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
            ax.set_xticks(range(-180, 181, 60)); ax.set_yticks(range(-90, 91, 30))
            ax.set_xlabel("Longitude (degrees)"); ax.set_ylabel("Latitude (degrees)")
            ax.set_title(f"{_NAMES[var]}, days {19 if w == 1 else 26}-{25 if w == 1 else 32}", fontweight="bold")
    if im is not None:
        fig.colorbar(im, ax=axes, shrink=0.6, label="P(upper quintile) - P(lower quintile) (%)")
    fig.suptitle(f"{cfg.teamname} / {cfg.modelname}: initialisation {init:%d %b %Y}", fontweight="bold")
    fig.savefig(path, dpi=110)
    plt.close(fig)


def weekly_rpss_plot(params: dict, path):
    fig, axes = plt.subplots(len(VARIABLES), 1, figsize=(10, 9), sharex=True, constrained_layout=True)
    for ax, var in zip(axes, VARIABLES):
        for w, color in zip(WINDOWS, ("tab:blue", "tab:orange")):
            p = params.get(var, {}).get(str(w))
            if not p:
                continue
            d = [dt.date.fromisoformat(x) for x in p["weekly"]["inits"]]
            ax.plot(d, p["weekly"]["rpss_final"], "-o", ms=3, color=color, label=f"SeasonBlend, window {w}")
            ax.plot(d, p["weekly"]["rpss_raw"], ":", color=color, alpha=0.7, label=f"Raw ensemble, window {w}")
        ax.axhline(0, color="k", lw=0.8)
        ax.set_ylabel("RPSS")
        ax.set_title(_NAMES[var], fontweight="bold")
        ax.set_ylim(-0.6, 0.6)
    axes[0].legend(ncol=2, fontsize=8)
    axes[-1].set_xlabel("Initialisation date")
    fig.savefig(path, dpi=110)
    plt.close(fig)
