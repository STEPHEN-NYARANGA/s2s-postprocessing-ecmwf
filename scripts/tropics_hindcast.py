"""Hindcast of the MJO/TS model for 25 DJF periods (2001-2025), scored as the Quest scores them.

Usage: python scripts/tropics_hindcast.py   (writes results/tropics/hindcast_*.csv and summary.json)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiwq.config import load_config  # noqa: E402
from aiwq import tropics as T  # noqa: E402

cfg = load_config()
out = Path("results/tropics")
out.mkdir(parents=True, exist_ok=True)
summary = {}

ts = T.load_ts(cfg)
H = T.hindcast_ts(ts)
H.to_csv(out / "hindcast_ts.csv", index=False)
for b in T.BASINS:
    r = H[H.basin == b]
    summary[f"TS_{b}_RPSS"] = round(1 - r.rps.mean() / r.rps_ref.mean(), 4)
act = H[H.basin.isin(["SWIO", "SEIO"])]
wk = act.groupby(["init", "period"]).agg(rps=("rps", "mean"), ref=("rps_ref", "mean"))
summary["TS_DJF_active_RPSS"] = round(1 - act.rps.mean() / act.rps_ref.mean(), 4)
summary["TS_DJF_weekly_RPSS_mean"] = round(float(np.mean(1 - wk.rps / wk.ref)), 4)
by_year = act.groupby("year").apply(lambda r: 1 - r.rps.mean() / r.rps_ref.mean(), include_groups=False)
summary["TS_DJF_years_positive"] = f"{int((by_year > 0).sum())}/{len(by_year)}"
summary["TS_DJF_worst_year_RPSS"] = round(float(by_year.min()), 4)
print({k: v for k, v in summary.items() if k.startswith("TS")})

m = T.load_mjo(cfg)
bom = T.read_bom_rmm(cfg)
grid = []
for bw in (0.35, 0.5, 0.75):
    for sw in (20, 30, 45):
        st = T.TropicsSettings(mjo_bandwidth=bw, mjo_season_days=sw)
        M = T.hindcast_mjo(m, bom, st, state_lag=1)
        r = {lag: 1 - M[M.lag == lag].bs.mean() / M[M.lag == lag].bs_ref.mean() for lag in T.MJO_LAGS}
        grid.append(dict(bw=bw, sw=sw, **{f"BSS_day{lag + 1}": round(v, 4) for lag, v in r.items()}))
        print(grid[-1], flush=True)
G = pd.DataFrame(grid)
G.to_csv(out / "hindcast_mjo_grid.csv", index=False)
summary["MJO_grid"] = grid
(out / "summary.json").write_text(json.dumps(summary, indent=1))
