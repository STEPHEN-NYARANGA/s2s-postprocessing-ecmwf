"""Offline end-to-end test on a synthetic world.  Run:  python tests/test_end_to_end.py

Checks
 1. quintile counting matches AI_WQ_package.conditional_obs_probs (incl. tied boundaries)
 2. RPSS bookkeeping matches AI_WQ_package.work_out_RPSS (land mask, deserts)
 3. weekly aggregation picks exactly days 19-25 / 26-32 and fixes grid order and units
 4. the fit beats the raw ensemble and climatology on data with known skill
 5. forecast files are valid submissions and pass the package's own checks
 6. the real submission functions run against a fake ECBox and the files arrive
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["AIWQ_FAKE_TODAY"] = "2026-11-14"
os.environ["AIWQ_PASSWORD"] = "test-password"

import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402

import fake_env as fe  # noqa: E402
from aiwq import calib  # noqa: E402
from aiwq.dates import thursdays  # noqa: E402

INIT = dt.date(2026, 11, 12)
INITS = thursdays(dt.date(2026, 3, 5), INIT)

fe.install_fake_sites()
fe.install_fake_dynamical(INITS)

from AI_WQ_package import forecast_evaluation as fev  # noqa: E402

from aiwq.cli import main  # noqa: E402
from aiwq.config import load_config  # noqa: E402
from aiwq.ens import load_members  # noqa: E402
from aiwq.grid import LAT, LON, area_weights, band_index  # noqa: E402

PASSED = []


def check(name, cond, detail=""):
    if not cond:
        raise AssertionError(f"FAILED: {name} {detail}")
    PASSED.append(name)
    print(f"  ok  {name} {detail}")


def test_categorize_and_rpss():
    print("\n[1-2] categorize and RPSS against the official package")
    rng = np.random.default_rng(0)
    B = fe.bounds("pr").astype(np.float32)
    obs = fe.obs_week("pr", dt.date(2026, 6, 1)).astype(np.float32)
    obs[fe.SHIFT > 0.5] = 0.0  # force zero rain where lower boundaries are tied at 0
    bda = xr.DataArray(B, dims=("quantile", "latitude", "longitude"),
                       coords=dict(quantile=[0.2, 0.4, 0.6, 0.8], latitude=LAT, longitude=LON))
    oda = xr.DataArray(obs, dims=("latitude", "longitude"), coords=dict(latitude=LAT, longitude=LON))
    official = fev.conditional_obs_probs(oda, bda).values.astype(float)
    mine = calib.obs_onehot(obs, B)
    same = np.allclose(np.nan_to_num(official, nan=-1), np.nan_to_num(mine, nan=-1))
    n_tied = int(((B[0] == B[1]) & (B[1] < B[3])).sum())
    check("obs categories identical to conditional_obs_probs", same, f"({n_tied} points with tied boundaries)")

    X = fe.ens_week("pr", INIT.toordinal(), dt.date(2026, 6, 1).toordinal()).astype(np.float32)
    p = calib.smooth_probs(calib.categorize(X, B), 1.0)
    check("probabilities sum to 1", np.allclose(p.sum(0), 1.0))
    fda = xr.DataArray(p, dims=("quintile", "latitude", "longitude"),
                       coords=dict(quintile=np.arange(1, 6) / 5, latitude=LAT, longitude=LON))
    lsm = xr.DataArray(fe.LSM, dims=("latitude", "longitude"), coords=dict(latitude=LAT, longitude=LON))
    obs_pbs = fev.conditional_obs_probs(oda, bda)
    off = float(fev.work_out_RPSS(fda, obs_pbs, "pr", lsm).compute())
    W = area_weights() * (fe.LSM >= 0.5)
    t = calib.rps_terms(p, np.full_like(p, 0.2), mine, W, band_index([[90, -90]]), 1)
    ours = calib.rpss_from_terms(t, [1.0], [0.0])
    check("RPSS identical to work_out_RPSS (pr, land, deserts)", abs(off - ours) < 1e-6, f"(package {off:.6f}, ours {ours:.6f})")

    # blend solver: optimum is never worse than any corner
    a, c = calib.solve_blend(t[0])
    corners = [calib.rps_of(t[0], *x) for x in [(0, 0), (1, 0), (0, 1), (0.5, 0.25)]]
    check("blend solver beats corners", calib.rps_of(t[0], a, c) <= min(corners) + 1e-9, f"(a={a:.2f}, c={c:.2f})")


def test_pipeline(workdir: Path):
    cfg_text = (ROOT / "config.toml").read_text()
    cfg_text = cfg_text.replace('first_init = "2026-01-01"', 'first_init = "2026-03-05"')
    cfg_text = cfg_text.replace('first_monday = "2024-01-15"', 'first_monday = "2025-01-06"')
    cfg_text = cfg_text.replace("lambdas = [0.0, 0.5, 0.75, 1.0]", "lambdas = [0.0, 0.5, 1.0]")
    cfg_text = cfg_text.replace("spreads = [1.0, 1.25, 1.5, 1.75, 2.0]", "spreads = [1.0, 1.5, 2.0, 2.5]")
    cfg_text = cfg_text.replace("prob_smooth_sigmas = [0.0, 1.0, 2.0]", "prob_smooth_sigmas = [0.0, 1.5]")
    (workdir / "config.toml").write_text(cfg_text)
    conf = str(workdir / "config.toml")

    print("\n[3] fetch-ens (synthetic dynamical.org)")
    main(["--config", conf, "fetch-ens", "--init", INIT.isoformat()])
    cfg = load_config(conf)
    for var in ("tas", "mslp", "pr"):
        for w, off in ((1, 18), (2, 25)):
            got = load_members(cfg, INITS[3], var, w)
            exp = fe.ens_week(var, INITS[3].toordinal(), (INITS[3] + dt.timedelta(days=off)).toordinal())
            tol = {"tas": 0.01, "mslp": 0.6, "pr": 0.06}[var]
            err = float(np.nanmax(np.abs(got - exp)))
            check(f"{var} window {w} weekly values, lead mapping and grid order", err < tol, f"(max error {err:.4f})")

    print("\n[3b] fetch-obs (real AI_WQ_package functions on fake ECBox)")
    main(["--config", conf, "fetch-obs"])
    from aiwq.obs import available_weeks, get_clim, get_obs
    wk = available_weeks(cfg, "pr")
    check("obs weeks cached", len(wk) > 80, f"({len(wk)} weeks, last {wk[-1]})")
    o = get_obs(cfg, dt.date(2026, 6, 1), "tas", download=False)
    check("obs read back on competition grid", o.shape == (121, 240) and np.allclose(o, fe.obs_week("tas", dt.date(2026, 6, 1)), atol=1e-3))
    b = get_clim(cfg, dt.date(2026, 6, 1), "pr", download=False)
    check("boundaries read back (lat/lon renamed)", b.shape == (4, 121, 240) and np.allclose(b, fe.bounds("pr"), atol=1e-3))

    print("\n[4] fit")
    main(["--config", conf, "fit"])
    import json
    params = json.loads(cfg.params_path.read_text())
    for var in ("tas", "mslp", "pr"):
        for w in ("1", "2"):
            s = params[var][w]["scores"]
            check(f"{var} window {w}: final beats raw ensemble and climatology",
                  s["final"] > s["raw_ensemble"] and s["final"] > 0,
                  f"(raw {s['raw_ensemble']:+.3f}, final {s['final']:+.3f}, spread {params[var][w]['s']}, lambda {params[var][w]['lam']})")
    check("backtest report written", (cfg.output_dir / "backtest" / "backtest_report.md").exists())

    print("\n[5] forecast")
    main(["--config", conf, "forecast", "--init", INIT.isoformat()])
    from aiwq.forecast import load_forecast
    for var in ("tas", "mslp", "pr"):
        for w in (1, 2):
            p = load_forecast(cfg, INIT, var, w)
            check(f"{var} p{w} valid", p.shape == (5, 121, 240) and np.isfinite(p).all() and
                  np.allclose(p.sum(0), 1.0) and p.min() >= 0 and p.max() <= 1)
    p = load_forecast(cfg, INIT, "tas", 1)
    check("tas forecast leans warm (trend learned)", p[4].mean() > p[0].mean(), f"(P top {p[4].mean():.2f} vs bottom {p[0].mean():.2f})")
    check("quick-look map written", (cfg.output_dir / "20261112" / "quicklook_20261112.png").exists())

    print("\n[6] submit (dry run, then fake ECBox upload)")
    main(["--config", conf, "submit", "--init", INIT.isoformat(), "--dry-run"])
    main(["--config", conf, "submit", "--init", INIT.isoformat()])
    names = sorted(k for k in fe.UPLOADS if k.endswith(".nc"))
    check("six files uploaded with official names", len(names) == 6, f"{[n.split('/')[-1] for n in names]}")
    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as f:
        f.write(fe.UPLOADS[[n for n in names if "/tas_" in n and "_p1_" in n][0]])
    up = xr.open_dataarray(f.name)
    check("uploaded tas p1 equals our forecast", np.allclose(up.values, load_forecast(cfg, INIT, "tas", 1)))
    up.close(); os.unlink(f.name)

    print("\n[7] weekly command (no upload)")
    main(["--config", conf, "weekly", "--init", INIT.isoformat(), "--no-submit", "--skip-fit"])
    main(["--config", conf, "status", "--remote"])
    check("weekly command runs end to end", True)
    return cfg


if __name__ == "__main__":
    test_categorize_and_rpss()
    tmp = Path(tempfile.mkdtemp(prefix="aiwq_test_"))
    try:
        cfg = test_pipeline(tmp)
        keep = ROOT / "tests" / "last_run_outputs"
        if keep.exists():
            shutil.rmtree(keep)
        shutil.copytree(cfg.output_dir, keep)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nALL {len(PASSED)} CHECKS PASSED")
