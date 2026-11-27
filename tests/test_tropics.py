"""Checks for aiwq/tropics.py against the official evaluation code (no network, synthetic data).

Run: python tests/test_tropics.py
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiwq import tropics as T  # noqa: E402
from AI_WQ_package import forecast_evaluation as FE  # noqa: E402

fails = 0


def check(cond, text):
    global fails
    print(("  ok  " if cond else "  FAIL ") + text)
    fails += not cond


rng = np.random.default_rng(0)

# 1. Category rule identical to the official conditional_obs_probs, including ties.
bounds_cases = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (0.0, 4.0), (2.0, 5.0), (0.0, 0.9999999999999858)]
same = True
for lo, hi in bounds_cases:
    qb = xr.DataArray([lo, hi], dims=["tercile"], coords={"tercile": [1 / 3, 2 / 3]})
    for x in range(0, 8):
        off = FE.conditional_obs_probs(xr.DataArray(float(x)), qb).values
        mine = T.ts_category(np.array(float(x)), np.array(lo), np.array(hi))
        same &= np.array_equal(off, mine, equal_nan=True)
check(same, "TS categories match AI_WQ_package.conditional_obs_probs, including the NaN mask for tied bounds")

# 2. RPS and RPSS match the package's TS functions.
f = np.array([0.1, 0.5, 0.4]); o = np.array([0.0, 0.0, 1.0])
fa = xr.DataArray(f, dims=["tercile"], coords={"tercile": [1 / 3, 2 / 3, 1.0]})
oa = xr.DataArray(o, dims=["tercile"], coords={"tercile": [1 / 3, 2 / 3, 1.0]})
import contextlib, io  # noqa: E401,E402
with contextlib.redirect_stdout(io.StringIO()):
    rpss_off = float(FE.calculate_RPSS_TS(fa, oa))
check(abs((1 - T.rps(f, o) / T.rps(np.full(3, 1 / 3), o)) - rpss_off) < 1e-12, "TS RPSS matches calculate_RPSS_TS")
fm = rng.dirichlet(np.ones(9)); om = np.eye(9)[3]
bs_off = float(FE.calculate_MJO_brier_score(xr.DataArray(fm, dims=["MJO_phase"]), xr.DataArray(om, dims=["MJO_phase"])))
check(abs(T.brier(fm, om) - bs_off) < 1e-12, "MJO Brier score matches calculate_MJO_brier_score")

# 3. Synthetic storm-day series: sample size, bounds, forecast sums to one and equals category frequencies.
days = pd.date_range("1980-01-01", "2026-12-31")
ts = pd.DataFrame(rng.poisson([0.3, 2.0, 1.5, 1.0], size=(len(days), 4)), index=days, columns=list(T.BASINS))
tgt = dt.date(2026, 12, 14)
s, yrs = T.ts_sample(ts, tgt)
check(s.shape == (100, 4) and yrs.min() == 2006 and yrs.max() == 2025, "official sample: 100 weeks from the 20 previous years")
p = T.ts_forecast(ts, tgt)
check(p.shape == (3, 4) and np.allclose(p.sum(axis=0), 1), "TS forecast is (3, 4) and sums to one per basin")
lo, hi = T.ts_bounds(s)
freq = np.nan_to_num(T.ts_category(s.T, lo[:, None], hi[:, None])).mean(axis=2)
freq[:, lo == hi] = 1 / 3
check(np.allclose(p, freq), "TS forecast equals the category frequencies of the official sample")
check(np.all(p[0][(lo == 0) & (hi > 0)] == 0), "category '< 0' gets zero probability when the lower bound is 0")
check(np.allclose(p[:, lo == hi], 1 / 3), "basins with tied bounds (not scored) get 1/3 each")
# the target week itself never enters its own sample
check(not any(pd.Timestamp(tgt).year == y for y in yrs), "the target year is not in its own sample")

# 4. MJO: phase convention, climatology and analogue forecast shape; no future data used.
check(T.mjo_category(-1.5, -0.1) == 1 and T.mjo_category(0.1, -1.5) == 3 and T.mjo_category(1.5, 0.1) == 5
      and T.mjo_category(-0.1, 1.5) == 7 and T.mjo_category(0.3, 0.3) == 0, "Wheeler-Hendon phase convention")
ang = np.cumsum(np.full(len(days), 2 * np.pi / 45))  # 45-day eastward cycle
amp = 1.2 + 0.5 * np.sin(np.arange(len(days)) / 200)
m = pd.DataFrame({"RMM1": amp * np.cos(ang + np.pi), "RMM2": amp * np.sin(ang + np.pi), "amplitude": amp}, index=days)
m["phase"] = [T.mjo_category(a, b) or 1 for a, b in zip(m.RMM1, m.RMM2)]
m["cat"] = np.where(m.amplitude < 1, 0, m.phase).astype(int)
init = dt.date(2026, 11, 26)
st = T.TropicsSettings(mjo_bandwidth=0.3)
sd = init - dt.timedelta(days=1)
mm = m[m.index <= pd.Timestamp(init)]
fc = T.mjo_forecast(mm, init, tuple(mm.loc[pd.Timestamp(sd), ["RMM1", "RMM2"]]), sd, st)
check(fc.shape == (9, 4) and np.allclose(fc.sum(axis=0), 1), "MJO forecast is (9, 4) and sums to one")
truth = [m["cat"][pd.Timestamp(init + dt.timedelta(days=lag))] for lag in T.MJO_LAGS]
check(all(fc[c, k] > 0.5 for k, c in enumerate(truth)), "a perfectly periodic MJO is forecast correctly by analogues")
c = T.mjo_clim(m, init + dt.timedelta(days=21))
check(np.isclose(c.sum(), 1), "MJO climatology sums to one")

print(f"\n{'ALL TROPICS CHECKS PASSED' if not fails else f'{fails} CHECK(S) FAILED'}")
sys.exit(1 if fails else 0)
