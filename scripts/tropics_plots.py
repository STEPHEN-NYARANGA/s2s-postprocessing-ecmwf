"""Plots for UtabiriTropics, drawn from the submitted files and the hindcast tables in results/.

Run: python scripts/tropics_plots.py
Writes results/<date>/tropics/quicklook_tropics_<date>.png for each init (unless it exists)
and results/tropics/hindcast_skill.png.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
BASINS = ["ATL", "NWP", "SWIO", "SEIO"]
TERC = ["below", "normal", "above"]
COL = ["#4c78a8", "#bab0ac", "#e45756"]


def quicklook(folder: Path, force=False):
    init = folder.parent.name
    out = folder / f"quicklook_tropics_{init}.png"
    if out.exists() and not force:
        return None
    meta = json.loads((folder / "tropics_forecast.json").read_text())
    d0 = dt.datetime.strptime(init, "%Y%m%d").date()
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
    for i, p in enumerate(("1", "2")):
        da = xr.open_dataarray(folder / f"TS_{init}_p{p}_UtabiriBora_UtabiriTropics.nc")
        v = da.transpose("tercile", "basin").values
        start = d0 + dt.timedelta(days=18 if p == "1" else 25)
        x = np.arange(4); bottom = np.zeros(4)
        for k in range(3):
            ax[i].bar(x, v[k], bottom=bottom, color=COL[k], label=TERC[k])
            for j in range(4):
                if v[k, j] >= 0.08:
                    ax[i].text(x[j], bottom[j] + v[k, j] / 2, f"{v[k, j]:.2f}", ha="center", va="center", fontsize=9)
            bottom += v[k]
        lb, hb = np.array(meta[f"TS_p{p}_bounds"])
        ax[i].set_xticks(x, [f"{b}\n[{lb[j]:g}, {hb[j]:g}]" for j, b in enumerate(BASINS)])
        ax[i].set_ylim(0, 1); ax[i].set_ylabel("probability")
        ax[i].set_title(f"TS storm days, week {start:%d %b} to {start + dt.timedelta(days=6):%d %b} (p{p})\n"
                        "tercile bounds in brackets; DJF scores SWIO and SEIO", fontsize=10)
    ax[0].legend(loc="upper left", fontsize=8)
    da = xr.open_dataarray(folder / f"MJO_{init}_p1_UtabiriBora_UtabiriTropics.nc").transpose("MJO_phase", "valid_time")
    im = ax[2].imshow(da.values, aspect="auto", cmap="Blues", vmin=0, vmax=max(0.5, float(da.max())))
    for r in range(9):
        for c in range(4):
            ax[2].text(c, r, f"{da.values[r, c]:.2f}", ha="center", va="center", fontsize=8,
                       color="white" if da.values[r, c] > 0.3 else "black")
    ax[2].set_xticks(range(4), [f"day {k + 1}\n{d0 + dt.timedelta(days=k):%d %b}" + (" *" if k >= 21 else "")
                                for k in (7, 14, 21, 28)])
    ax[2].set_yticks(range(9), ["inactive"] + [f"phase {k}" for k in range(1, 9)])
    s = meta["mjo_state"]
    ax[2].set_title(f"MJO category probabilities (* = scored)\nstart state {s['date']}: "
                    f"RMM1 {s['rmm1']:.2f}, RMM2 {s['rmm2']:.2f}, category {s['category']}", fontsize=10)
    fig.colorbar(im, ax=ax[2], fraction=0.04)
    fig.suptitle(f"UtabiriBora / UtabiriTropics, init {d0:%d %b %Y}", fontweight="bold")
    fig.tight_layout(); fig.savefig(out, dpi=120); plt.close(fig)
    return out


def hindcast():
    ts = pd.read_csv(RES / "tropics" / "hindcast_ts.csv")
    ts = ts[ts.basin.isin(["SWIO", "SEIO"])]
    yr = ts.groupby("year")[["rps", "rps_ref"]].sum()
    yr["rpss"] = 1 - yr.rps / yr.rps_ref
    g = pd.read_csv(RES / "tropics" / "hindcast_mjo_grid.csv")
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.4))
    ax[0].bar(yr.index, yr.rpss, color=np.where(yr.rpss > 0, "#54a24b", "#e45756"))
    tot = 1 - yr.rps.sum() / yr.rps_ref.sum()
    ax[0].axhline(tot, color="k", ls="--", lw=1, label=f"all seasons {tot:+.3f}")
    ax[0].set_xlabel("DJF season starting in year"); ax[0].set_ylabel("RPSS vs uniform 1/3")
    ax[0].set_title("TS hindcast, SWIO + SEIO (scored basins in DJF)\nobserved storm days, ECMWF training data", fontsize=10)
    ax[0].legend()
    for lead, mk in (("BSS_day22", "o"), ("BSS_day29", "s")):
        for sw, sub in g.groupby("sw"):
            ax[1].plot(sub.bw, sub[lead], marker=mk, label=f"{lead[4:]}, season +/-{sw} d")
    ax[1].axvline(0.75, color="grey", ls=":"); ax[1].axhline(0, color="k", lw=0.8)
    ax[1].set_xlabel("analogue kernel width (RMM units)"); ax[1].set_ylabel("Brier skill vs official climatology")
    ax[1].set_title("MJO hindcast (BoM RMM start state, past data only)\ndotted line = chosen width 0.75, season +/-45 d", fontsize=10)
    ax[1].legend(fontsize=7, ncol=2)
    fig.tight_layout(); out = RES / "tropics" / "hindcast_skill.png"; fig.savefig(out, dpi=120); plt.close(fig)
    return out


if __name__ == "__main__":
    force = "--force" in sys.argv
    for f in sorted(RES.glob("2*/tropics")):
        print(quicklook(f, force) or f"{f}: quicklook exists, kept")
    print(hindcast())
