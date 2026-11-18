"""Quantile-mapping reference experiment (R1, mentor's recommendation) with xsdba.

For every verified week i (same weeks as SeasonBlend's backtest), an empirical quantile
mapping (xsdba.EmpiricalQuantileMapping) is trained on the other weeks (weeks within
exclude_days of i left out, as in SeasonBlend's leave-one-out) and applied to the 101
members of week i, which are then counted in the official ERA5 quintiles.

Seasonality. Training covers all seasons of 2026 (about 40 weeks), so values are first
expressed relative to the 20-year ERA5 climatology of their own target week:
  tas, mslp: anomaly x - m, mapped additively (kind "+");
  pr:        ratio (x + 1) / (m + 1), mapped multiplicatively (kind "*"),
where m is the climatological median, taken as the mean of the 40% and 60% boundaries.
The mapped values are transformed back with the target week's m.

The training sample per grid point is about 38 observed weeks against 38 x 25 member
values (25 of the 101 exchangeable members per training week, drawn at random, to keep memory
manageable on a laptop); the target week keeps all 101 members. nquantiles is set to 15 so that each quantile is estimated from more than two
observations. To measure the sensitivity to training length, each fold is repeated with a
random subset of 20 and of 10 training weeks.

Output: data/research/qm_<var>_p<w>.npz with weekly RPS (full, n20, n10), the raw-ensemble
RPS, climatology RPS and the QM probabilities of each week.

    python -m aiwq.research_qm [--vars ...] [--windows ...]
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
import warnings

import numpy as np
import pandas as pd
import xarray as xr

from . import calib
from .config import VARIABLES, WINDOWS, load_config
from .ens import load_members
from .fit import score_weights, training_data
from .obs import get_lsm
from .research import research_dir

NQ = 15
TRAIN_MEMBERS = 25
ONE_ROW = np.zeros(121, dtype=int)


def _da(values: np.ndarray, start: str = "2000-01-01") -> xr.DataArray:
    """(T, ny, nx) -> DataArray with a daily 'time' axis (xsdba needs a time coordinate)."""
    t = pd.date_range(start, periods=values.shape[0], freq="D")
    return xr.DataArray(values.astype(np.float32), dims=("time", "lat", "lon"), coords={"time": t},
                        attrs={"units": "1"})


def _to_space(var, x, m):
    return x - m if var != "pr" else (x + 1.0) / (m + 1.0)


def _from_space(var, y, m):
    return y + m if var != "pr" else np.maximum(y * (m + 1.0) - 1.0, 0.0)


def qm_fold(var: str, train_X: np.ndarray, train_O: np.ndarray, target_X: np.ndarray) -> np.ndarray:
    """train_X (Ntr, m, ny, nx) and train_O (Ntr, ny, nx) in anomaly space; target_X (M, ny, nx).

    xsdba trains on matching time axes, so each member value is paired with its verifying
    observation (each observed week repeated m times). Equal replication leaves the empirical
    quantiles of the observations unchanged.
    """
    import xsdba

    kind = "*" if var == "pr" else "+"
    m = train_X.shape[1]
    ref = _da(np.repeat(train_O, m, axis=0))
    hist = _da(train_X.reshape(-1, *train_X.shape[2:]))
    sim = _da(target_X, "2003-01-01")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eqm = xsdba.EmpiricalQuantileMapping.train(ref, hist, nquantiles=NQ, group="time", kind=kind)
        out = eqm.adjust(sim, extrapolation="constant", interp="linear")
    return out.transpose("time", "lat", "lon").values


def rps_of_probs(p, oh, W):
    t = calib.rps_terms(p, np.full_like(p, 0.2), oh, W, ONE_ROW, 1)[0]
    return float(t[0] - 2 * t[3] + t[5]), float(t[5])


def run(cfg, var: str, window: int, lsm, log=print, seed: int = 0):
    tr = training_data(cfg, var, window, download=False)
    N = len(tr.inits)
    W = score_weights(var, lsm)
    mon = np.array([m.toordinal() for m in tr.mondays])
    mid = 0.5 * (tr.bounds[:, 1] + tr.bounds[:, 2])  # (N, ny, nx)
    rng = np.random.default_rng(seed)
    A = []
    for i, d in enumerate(tr.inits):  # anomaly space, float32; raw values are recovered with _from_space
        A.append(_to_space(var, load_members(cfg, d, var, window), mid[i][None]).astype(np.float32))
    A = np.stack(A)  # (N, M, ny, nx)
    M = A.shape[1]
    Oa = _to_space(var, tr.obs, mid)
    msub = np.sort(rng.choice(M, min(TRAIN_MEMBERS, M), replace=False))
    out = {k: np.full(N, np.nan) for k in ("rps_qm", "rps_qm_n20", "rps_qm_n10", "rps_raw", "rps_clim")}
    p_qm_all = np.zeros((N, 5) + lsm.shape, np.float32)
    p_raw_all = np.zeros((N, 5) + lsm.shape, np.float32)
    t0 = time.time()
    for i in range(N):
        oh = calib.obs_onehot(tr.obs[i], tr.bounds[i])
        raw = _from_space(var, A[i].astype(np.float64), mid[i][None])
        p_raw_all[i] = calib.categorize(raw, tr.bounds[i])
        out["rps_raw"][i], out["rps_clim"][i] = rps_of_probs(p_raw_all[i].astype(np.float64), oh, W)
        keep = np.where(np.abs(mon - mon[i]) >= cfg.exclude_days)[0]
        for key, n in (("rps_qm", None), ("rps_qm_n20", 20), ("rps_qm_n10", 10)):
            sel = keep if n is None or n >= keep.size else np.sort(rng.choice(keep, n, replace=False))
            Y = qm_fold(var, A[sel][:, msub], Oa[sel], A[i])
            p = calib.categorize(_from_space(var, Y, mid[i][None]), tr.bounds[i])
            out[key][i] = rps_of_probs(p, oh, W)[0]
            if n is None:
                p_qm_all[i] = p
        if (i + 1) % 5 == 0 or i + 1 == N:
            log(f"    {var} window {window}: {i + 1}/{N} weeks ({time.time() - t0:.0f} s)")
    path = research_dir(cfg) / f"qm_{var}_p{window}.npz"
    np.savez_compressed(path, inits=np.array([d.isoformat() for d in tr.inits]), mon_ord=mon, members=M,
                        train_members=msub,
                        nquantiles=NQ, p_qm=p_qm_all, p_raw=p_raw_all, **out)
    rs = {k: 1 - np.nansum(out[k]) / np.nansum(out["rps_clim"]) for k in ("rps_qm", "rps_qm_n20", "rps_qm_n10", "rps_raw")}
    log(f"  {var} window {window}: RPSS raw {rs['rps_raw']:+.3f}, QM {rs['rps_qm']:+.3f} "
        f"(20 weeks {rs['rps_qm_n20']:+.3f}, 10 weeks {rs['rps_qm_n10']:+.3f}); saved {path.name}")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--vars", nargs="+", default=list(VARIABLES))
    ap.add_argument("--windows", nargs="+", type=int, default=list(WINDOWS))
    args = ap.parse_args(argv)
    cfg = load_config(args.config, experiment="control")
    lsm = get_lsm(cfg)
    log = lambda m: print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}Z] {m}", flush=True)  # noqa: E731
    for var in args.vars:
        for w in args.windows:
            run(cfg, var, w, lsm, log=log)


if __name__ == "__main__":
    main()
