"""Unit tests of the R2 analysis code (aiwq/r2.py, aiwq/research_lag.py).  Run:  python tests/test_r2.py

Synthetic arrays are only used to check the algebra; no result in results/ comes from them.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from aiwq import calib, r1, r2  # noqa: E402

PASSED = []


def check(name, cond, detail=""):
    if not cond:
        raise AssertionError(f"FAILED: {name} {detail}")
    PASSED.append(name)
    print(f"  ok  {name} {detail}")


def test_gauss_and_tilt():
    print("\n[r2-1] Gaussian-shift prior and tilt")
    mu = np.zeros((3, 7), np.float32); s = np.ones((3, 7), np.float32)
    g = r2.gauss_probs(mu, s)
    check("no shift gives 0.2 in every quintile", np.allclose(g, 0.2, atol=1e-6), f"max dev {np.abs(g - 0.2).max():.1e}")
    g = r2.gauss_probs(mu + 0.5, s * 0.8)
    check("probabilities sum to one", np.allclose(g.sum(axis=-2), 1, atol=1e-6))
    check("a warm shift moves probability to the top quintile", bool((g[:, 4] > g[:, 0]).all()))
    rng = np.random.default_rng(0)
    p = rng.dirichlet(np.ones(5), size=(3, 7)).transpose(0, 2, 1).astype(np.float32)
    check("tilting by the uniform prior changes nothing", np.allclose(r2.tilt(p, np.full_like(p, 0.2)), p, atol=1e-6))
    t = r2.tilt(np.full_like(p, 0.2), g)
    check("tilting the uniform prior returns g", np.allclose(t, g, atol=1e-6))


def test_rps_and_onehot():
    print("\n[r2-2] categories and RPS")
    b = np.array([[0.0], [1.0], [2.0], [3.0]], np.float32)
    x = np.array([-1.0, 0.0, 1.5, 3.0, 9.0], np.float32)
    oh = np.stack([r2.onehot(np.array([v], np.float32), b)[:, 0] for v in x])
    check("official tie rules (x == boundary goes up)", list(oh.argmax(1)) == [0, 1, 2, 4, 4])
    rng = np.random.default_rng(1)
    p = rng.dirichlet(np.ones(5), size=6).astype(np.float32)[:, :, None]
    o = np.eye(5, dtype=np.uint8)[rng.integers(0, 5, 6)][:, :, None]
    ref = np.sum((np.cumsum(p[:, :, 0], 1) - np.cumsum(o[:, :, 0], 1)) ** 2, axis=1)
    check("RPS matches the definition", np.allclose(r2.rps(p, o)[:, 0], ref, atol=1e-6))
    # reliability term: perfectly reliable forecasts have (almost) none
    f = rng.uniform(0, 1, 200000)
    obs = (rng.uniform(0, 1, f.size) < f).astype(float)
    P = np.stack([1 - f, f * 0, f * 0, f * 0, f], 1)  # cumulative threshold 1 = 1 - f
    O = np.stack([1 - obs, obs * 0, obs * 0, obs * 0, obs], 1)
    rel = r2.rps_reliability(P, O, np.ones(f.size))
    check("reliable forecasts have a small reliability term", rel[0] / f.size < 1e-3, f"{rel[0] / f.size:.1e}")
    P2 = np.stack([1 - np.clip(f * 1.6 - 0.3, 0, 1), f * 0, f * 0, f * 0, np.clip(f * 1.6 - 0.3, 0, 1)], 1)
    rel2 = r2.rps_reliability(P2, O, np.ones(f.size))
    check("overconfident forecasts have a larger one", rel2[0] > 10 * rel[0])


def test_weekly_climate():
    print("\n[r2-3] leave-own-year-out climatology")
    days = pd.date_range("2004-01-01", "2008-12-31", freq="D")
    x = (np.arange(len(days)) % 365).astype(np.float32)[:, None] + (days.year.to_numpy() - 2004)[:, None] * 100
    d = r2.Daily(days, x.astype(np.float32), np.array([0]))
    starts, wk = r2.weekly_means(d)
    check("7-day means", np.isclose(wk[0, 0], x[:7, 0].mean()))
    clim = r2.WeeklyClimate(starts, wk, range(2004, 2009))
    s = pd.Timestamp("2006-03-06")
    smp = clim.sample(s, 2006)
    check("own year excluded, 4 other years x 5 offsets", smp.shape[0] == 20)
    years_in = sorted({int(v // 100) for v in smp[:, 0]})
    check("sample years", 2 not in years_in, str(years_in))


def test_fit_state_recovers_slope():
    print("\n[r2-4] leave-one-year-out regression recovers a known slope")
    rng = np.random.default_rng(3)
    inits = pd.date_range("2005-01-06", "2016-12-29", freq="W-THU")
    N, P = len(inits), 4
    n34 = np.sin(np.arange(N) / 30.0) * 1.5
    beta = np.array([0.5, -0.3, 0.0, 0.2])
    z = (n34[:, None] * beta[None] + rng.normal(scale=0.8, size=(N, P))).astype(np.float32)
    start = inits + pd.Timedelta(days=18)
    cases = r2.Cases(inits, np.ones(N, int), start, np.array([r2.enso_year(d) for d in inits]),
                     np.zeros((N, 5, P), np.uint8), z, n34, np.full(N, np.nan))
    pts = np.array([0, 40, 80, 120]) + 60 * 240  # four equator points
    f = r2.fit_state(cases, ["nino34"], pts, sigma_space=0.0)
    est = np.array([np.polyfit(n34, f.mu[:, k], 1)[0] for k in range(P)])
    check("slope recovered", np.allclose(est, beta, atol=0.12), np.round(est, 2).tolist())
    check("residual spread below 1", bool(np.all(f.s < 1.0)))
    train = np.asarray(start + pd.Timedelta(days=7) <= pd.Timestamp("2014-12-31"))
    mu, s, B = r2.fit_predict(cases, ["nino34"], pts, train, [100], np.array([[1.0]]), sigma_space=0.0)
    check("fit_predict slope", np.allclose(B[0, 0], beta, atol=0.15), np.round(B[0, 0], 2).tolist())


def test_year_bootstrap_and_subsample():
    print("\n[r2-5] year bootstrap and learning-curve folds")
    groups = np.repeat(np.arange(10), 5)
    a = np.ones(50); b = a * 0.9; c = np.full(50, 2.0)
    bs = r2.year_bootstrap(a, b, c, groups, n_boot=500)
    check("constant gain has a zero-width interval", np.isclose(bs["lo90"], 0.05) and np.isclose(bs["hi90"], 0.05))
    from test_r1 import synthetic_terms  # noqa: E402
    T = synthetic_terms(n_combo=2, N=16, seed=5)
    mon = np.arange(16) * 7
    sch = r1.Scheme("bands", r1.band_basis())
    full = r1.cv_scores(T, mon, 21, sch)
    rps, clim = r2.cv_subsample(T, mon, 21, sch, 11, np.random.default_rng(0))
    elig = min((np.abs(mon - m) >= 21).sum() for m in mon)
    check("subsample of all eligible weeks equals leave-one-out",
          elig != 11 or np.allclose(rps, full.rps), f"min eligible {elig}")
    rps2, _ = r2.cv_subsample(T, mon, 21, sch, 6, np.random.default_rng(0))
    check("fewer weeks scored without error", np.isfinite(rps2).all())


def test_lag_paths():
    print("\n[r2-6] lagged-run cache is separate from the operational cache")
    from aiwq import research_lag
    from aiwq.config import load_config
    cfg = load_config(ROOT / "config.toml")
    p = research_lag.lag_path(cfg, dt.date(2026, 11, 12), 3, "tas")
    check("lagged files live outside data/ens", cfg.ens_dir.resolve() not in p.resolve().parents, str(p.parent))
    check("file name records the lag", p.name == "20261112_lag3_tas.nc")


sys.path.insert(0, str(ROOT / "tests"))

if __name__ == "__main__":
    test_gauss_and_tilt()
    test_rps_and_onehot()
    test_weekly_climate()
    test_fit_state_recovers_slope()
    test_year_bootstrap_and_subsample()
    test_lag_paths()
    print(f"\nAll {len(PASSED)} R2 checks passed.")
