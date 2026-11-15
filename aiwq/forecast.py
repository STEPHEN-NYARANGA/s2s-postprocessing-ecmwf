"""Build the submission probabilities for one Thursday initialisation."""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import xarray as xr

from . import calib
from .config import VARIABLES, WINDOWS, Config
from .dates import day_of_year, window_monday, ymd
from .ens import is_cached, load_mean, load_members
from .fit import prior_data, prior_for, training_data
from .grid import band_index, prob_dataarray
from .obs import get_clim


def forecast_path(cfg: Config, init: dt.date, var: str, window: int):
    return cfg.output_dir / ymd(init) / f"{var}_p{window}.nc"


def forecast_one(cfg: Config, init: dt.date, var: str, window: int, p: dict, pweeks, ponehots) -> tuple[np.ndarray, dict]:
    M = window_monday(init, window)
    X = load_members(cfg, init, var, window)
    B = get_clim(cfg, M, var)
    if B is None:
        raise RuntimeError(f"Could not get the quintile boundaries for {var} week {M} (check password/ECBox).")
    # training pairs: only weeks that ended before this initialisation (competition rule)
    tr = training_data(cfg, var, window, before=init)
    if len(tr.inits) >= 2:
        means = np.stack([load_mean(cfg, d, var, window) for d in tr.inits])
        w = calib.season_weights(day_of_year(M), tr.doys, cfg.season_sigma_days, cfg.season_floor)
        corr = calib.correction_field(var, means, tr.obs, w, cfg.bias_smooth_sigma)
    else:
        corr = np.ones(B.shape[1:]) if var == "pr" else np.zeros(B.shape[1:])
    prior = prior_for(cfg, M, pweeks, ponehots, cutoff=init)
    pe = calib.ensemble_probs(var, X, B, corr, p["lam"], p["s"], p["sigma_p"])
    bidx = band_index(p["bands"])
    prob = calib.blend(pe, prior, p["a"], p["c"], bidx)
    prob[:, np.nanmin(B, axis=0) == np.nanmax(B, axis=0)] = 0.2  # unscored (e.g. 0 mm in all quintiles)
    prob = calib.finalize(prob)
    info = {"init": init.isoformat(), "window": window, "window_start": M.isoformat(),
            "members": int(np.isfinite(X).all(axis=(1, 2)).sum()), "n_train": len(tr.inits),
            "lam": p["lam"], "s": p["s"], "sigma_p": p["sigma_p"], "a": p["a"], "c": p["c"]}
    return prob, info


def make_forecast(cfg: Config, init: dt.date, params: dict, variables=VARIABLES, windows=WINDOWS, log=print) -> dict:
    if not is_cached(cfg, init, variables):
        raise SystemExit(f"The ECMWF run for {init} is not downloaded yet. Run:  python run.py fetch-ens --init {init}")
    outdir = cfg.output_dir / ymd(init)
    outdir.mkdir(parents=True, exist_ok=True)
    summary = {}
    probs = {}
    for var in variables:
        pweeks, ponehots = prior_data(cfg, var)
        for w in windows:
            p = params.get(var, {}).get(str(w))
            if p is None:
                log(f"  {var} window {w}: no fitted parameters, skipped.")
                continue
            prob, info = forecast_one(cfg, init, var, w, p, pweeks, ponehots)
            da = prob_dataarray(prob, name=f"{var}_quintile_probability")
            da.attrs.update({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in info.items()})
            da.attrs.update({"teamname": cfg.teamname, "modelname": cfg.modelname})
            da.to_netcdf(forecast_path(cfg, init, var, w))
            probs[(var, w)] = prob
            summary[f"{var}_p{w}"] = info
            top = prob[4].mean(); bot = prob[0].mean()
            log(f"  {var} window {w}: saved (mean P(top quintile) {top:.2f}, P(bottom) {bot:.2f}, "
                f"{info['n_train']} training runs)")
        del ponehots
    (outdir / "forecast_summary.json").write_text(json.dumps(summary, indent=1))
    try:
        from .plots import quicklook
        quicklook(cfg, init, probs, outdir / f"quicklook_{ymd(init)}.png")
    except Exception as e:
        log(f"(quick-look plot skipped: {e})")
    return summary


def load_forecast(cfg: Config, init: dt.date, var: str, window: int) -> np.ndarray:
    path = forecast_path(cfg, init, var, window)
    if not path.exists():
        raise SystemExit(f"No saved forecast {path.name} for {init}. Run:  python run.py forecast --init {init}")
    with xr.open_dataarray(path) as da:
        return da.transpose("quintile", "latitude", "longitude").values.astype(np.float64)
