"""Independent sanity checks of one week's submission files, written as a Markdown report.

Run before sending or uploading:  python run.py crosscheck --init YYYY-MM-DD
It re-reads the files from disk and checks them without the calibration code:
  1. file format: dimensions, grid, probabilities in [0, 1] summing to 1, no missing values,
     and the AI-WQ-package data checks;
  2. dates: Thursday initialisation, windows starting on the Mondays of days 19 and 26;
  3. units: the raw ensemble mean sits inside the ERA5 climatology for that week;
  4. signal: the final probabilities point the same way as a plain count of the raw members in
     the official quintiles, and as the most recent observed week (persistence).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import xarray as xr

from .config import VARIABLES, WINDOWS, Config
from .dates import window_monday, ymd
from .ens import load_members
from .forecast import load_forecast
from .grid import LAT, LON, area_weights
from .obs import available_weeks, clim_file, get_lsm, obs_file, read_clim, read_obs

NAMES = {"tas": "2 m temperature", "mslp": "Mean sea level pressure", "pr": "Precipitation"}
UNITS = {"tas": "K", "mslp": "hPa", "pr": "mm/week"}


def _raw_counts(X: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Plain member count in the five quintiles (x < b1, ..., x >= b4); deliberately simple."""
    edges = np.concatenate([np.full((1,) + B.shape[1:], -np.inf), B, np.full((1,) + B.shape[1:], np.inf)])
    p = np.stack([((X >= edges[k]) & (X < edges[k + 1])).mean(axis=0) for k in range(5)])
    return p


def _corr(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    a, b, w = a[m], b[m], w[m]
    a = a - np.average(a, weights=w)
    b = b - np.average(b, weights=w)
    return float(np.sum(w * a * b) / np.sqrt(np.sum(w * a * a) * np.sum(w * b * b)))


def _tilt(p: np.ndarray) -> np.ndarray:
    """Expected quintile minus the middle one: -2 (surely lowest) .. +2 (surely highest)."""
    return np.tensordot(np.arange(-2, 3), p, axes=1)


def crosscheck(cfg: Config, init: dt.date, files_dir: Path | None = None, log=print) -> tuple[bool, str]:
    from AI_WQ_package import check_fc_submission as chk

    files_dir = files_dir or cfg.output_dir / ymd(init) / "email"
    W = area_weights()
    lsm = get_lsm(cfg) > 0.5
    lines = [f"# Cross-check of the {init:%d %B %Y} forecast ({cfg.teamname} / {cfg.modelname})", "",
             f"Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC by `python run.py crosscheck`.", ""]
    ok = True

    def check(cond: bool, text: str):
        nonlocal ok
        ok &= bool(cond)
        lines.append(f"| {'PASS' if cond else '**FAIL**'} | {text} |")

    # ---- dates
    lines += ["## Dates", "", "| Result | Check |", "|---|---|"]
    check(init.weekday() == 3, f"initialisation {init:%a %d %b %Y} is a Thursday")
    for w in WINDOWS:
        m = window_monday(init, w)
        d1 = (m - init).days + 1
        check(m.weekday() == 0 and d1 == (19 if w == 1 else 26),
              f"window {w}: {m:%a %d %b} to {m + dt.timedelta(days=6):%a %d %b} = days {d1}-{d1 + 6}")

    # ---- files
    lines += ["", "## Files", "", "| Result | Check |", "|---|---|"]
    for var in VARIABLES:
        for w in WINDOWS:
            name = f"{var}_{ymd(init)}_p{w}_{cfg.teamname}_{cfg.modelname}.nc"
            path = files_dir / name
            if not path.exists():
                check(False, f"`{name}` exists")
                continue
            with xr.open_dataset(path) as ds:
                da = ds[list(ds.data_vars)[0]].load()
            v = da.transpose("quintile", "latitude", "longitude").values
            s = v.sum(axis=0)
            fmt_ok = (da.sizes == {"quintile": 5, "latitude": 121, "longitude": 240}
                      and np.allclose(da.latitude, LAT) and np.allclose(da.longitude, LON)
                      and np.isfinite(v).all() and v.min() >= 0 and v.max() <= 1 and np.allclose(s, 1, atol=1e-6))
            same = np.allclose(v, load_forecast(cfg, init, var, w), atol=1e-6)
            try:
                chk.check_data_characteristics(chk.check_quintile_range(da), var, ymd(init), str(w))
                pkg = True
            except Exception as e:  # noqa: BLE001
                pkg = False
                log(f"package check failed for {name}: {e}")
            check(fmt_ok and same and pkg,
                  f"`{name}`: 5 x 121 x 240, 90N->90S, 0->358.5E, sums to 1 (range {s.min():.6f}-{s.max():.6f}), "
                  f"no NaN, identical to the saved forecast, AI-WQ-package checks pass")

    # ---- physics
    lines += ["", "## Does the forecast make sense?", "",
              "Raw = the 101 ECMWF members counted in the official ERA5 quintiles with no correction. "
              "Tilt = expected quintile minus the middle one (-2 to +2); correlations are area-weighted "
              "(tas and pr over land, as on the leaderboard).", "",
              "| Variable | Window | ENS mean - ERA5 median | Raw tilt vs final tilt (corr.) | "
              "Mean P(lowest) raw / final | Mean P(highest) raw / final | Final vs last observed week (corr.) |",
              "|---|---|---|---|---|---|---|"]
    for var in VARIABLES:
        last = [m for m in available_weeks(cfg, var) if m < init]
        O_last = read_obs(obs_file(cfg, var, last[-1]), var) if last else None
        B_last = read_clim(clim_file(cfg, var, last[-1]), var) if last else None
        for w in WINDOWS:
            m = window_monday(init, w)
            B = read_clim(clim_file(cfg, var, m), var)
            X = load_members(cfg, init, var, w)
            final = load_forecast(cfg, init, var, w)
            raw = _raw_counts(X, B)
            mask = lsm if var in ("tas", "pr") else np.ones_like(lsm)
            Wm = W * mask
            scale = 100.0 if var == "mslp" else 1.0
            bias = np.average((np.nanmean(X, axis=0) - 0.5 * (B[1] + B[2])) / scale, weights=Wm)
            spread = np.average((B[3] - B[0]) / scale, weights=Wm)
            c_raw = _corr(_tilt(raw), _tilt(final), Wm)
            if O_last is not None:
                cat = np.select([O_last < B_last[0], O_last < B_last[1], O_last < B_last[2], O_last < B_last[3]],
                                [-2, -1, 0, 1], 2).astype(float)
                c_obs = _corr(_tilt(final), cat, Wm)
            else:
                c_obs = np.nan
            pr_raw = [np.average(raw[k], weights=Wm) for k in (0, 4)]
            pr_fin = [np.average(final[k], weights=Wm) for k in (0, 4)]
            lines.append(f"| {NAMES[var]} | {w} | {bias:+.2f} {UNITS[var]} (inner quintile range {spread:.2f}) | "
                         f"{c_raw:+.2f} | {pr_raw[0]:.2f} / {pr_fin[0]:.2f} | {pr_raw[1]:.2f} / {pr_fin[1]:.2f} | "
                         f"{c_obs:+.2f} |")
            ok &= c_raw > 0.3 and abs(bias) < spread
    lines += ["", "Expected: ENS-minus-ERA5 differences small next to the inner quintile range (right units "
              "and grid); positive raw-vs-final correlation (calibration corrects and tempers the raw signal "
              "but does not reverse it); final mean P(lowest) and P(highest) close to how often recent "
              "observed weeks fell in those quintiles (table below); positive persistence correlations.", ""]
    lines += ["### How often recent observed weeks fell in the outer quintiles", "",
              "Area-weighted share of the last 26 published ERA5 weeks (tas and pr over land). "
              "A 20-year climatology gives 0.20 each; the blend's prior uses these frequencies, which is "
              "why the final forecast can lean further than the raw ensemble (e.g. warmer, for the "
              "warming trend).", "",
              "| Variable | Weeks | Observed P(lowest) | Observed P(highest) |", "|---|---|---|---|"]
    for var in VARIABLES:
        ws = [m for m in available_weeks(cfg, var) if m < init][-26:]
        mask = lsm if var in ("tas", "pr") else np.ones_like(lsm)
        lo = hi = 0.0
        for m in ws:
            O, B = read_obs(obs_file(cfg, var, m), var), read_clim(clim_file(cfg, var, m), var)
            lo += np.average(O < B[0], weights=W * mask) / len(ws)
            hi += np.average(O >= B[3], weights=W * mask) / len(ws)
        if ws:
            lines.append(f"| {NAMES[var]} | {ws[0]:%d %b %Y} to {ws[-1]:%d %b %Y} | {lo:.2f} | {hi:.2f} |")
    lines += ["",
              f"**Overall: {'all checks passed' if ok else 'SOME CHECKS FAILED - look before sending'}**"]
    text = "\n".join(lines) + "\n"
    out = cfg.output_dir / ymd(init) / "crosscheck.md"
    out.write_text(text, encoding="utf-8")
    log(f"Cross-check {'passed' if ok else 'FAILED'}: {out}")
    return ok, text
