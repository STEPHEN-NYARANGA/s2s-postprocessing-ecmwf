"""Research data collection for R1 (not used by the operational SeasonBlend pipeline).

`collect` repeats exactly the leave-one-out loop of fit.fit_one, with two differences that
make later experiments cheap and comparable:

1. The RPS sufficient statistics are kept for every latitude row (121) instead of the three
   blend bands. Summing rows inside a band reproduces SeasonBlend's statistics exactly, and
   any latitude-dependent weighting (smooth weights, other bands) can be fitted from them
   without touching the ensemble data again.
2. For SeasonBlend's selected settings (lambda, spread, smoothing from the control fit), the
   per-week fields p_ens, p_prior and the observed category are saved, so scores can be
   computed for any region (Africa) and reliability diagrams drawn.

Output: data/research/rows_<var>_p<window>.npz. Nothing in data/params*.json or outputs/ is
changed.

    python -m aiwq.research [--vars tas mslp pr] [--windows 1 2]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import numpy as np

from . import calib
from .config import VARIABLES, WINDOWS, Config, load_config
from .ens import load_members
from .fit import PRIOR_GAP_DAYS, prior_data, prior_for, score_weights, training_data
from .obs import get_lsm

NROW = 121


def research_dir(cfg: Config) -> Path:
    d = cfg.data_dir / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d


def rows_path(cfg: Config, var: str, window: int) -> Path:
    return research_dir(cfg) / f"rows_{var}_p{window}.npz"


def collect(cfg: Config, var: str, window: int, control: dict, lsm: np.ndarray, pweeks, ponehots,
            log=print) -> Path:
    tr = training_data(cfg, var, window, download=False)
    N = len(tr.inits)
    t0 = time.time()
    X_all = [load_members(cfg, d, var, window) for d in tr.inits]
    means = np.stack([np.nanmean(X, axis=0) for X in X_all])
    doys = tr.doys
    mon_ord = np.array([m.toordinal() for m in tr.mondays])
    rows = np.arange(NROW)
    W = score_weights(var, lsm)
    L, S, P = cfg.lambdas, cfg.spreads, cfg.prob_smooth_sigmas
    cl = (L.index(control["lam"]), S.index(control["s"]), P.index(control["sigma_p"]))
    terms = np.zeros((len(L), len(S), len(P), N, NROW, 6))
    shp = (N, 5) + lsm.shape
    p_ens = np.zeros(shp, np.float32)
    p_prior = np.zeros(shp, np.float32)
    onehot = np.zeros(shp, np.float32)
    for i in range(N):
        keep = np.abs(mon_ord - mon_ord[i]) >= cfg.exclude_days
        w_i = calib.season_weights(doys[i], doys, cfg.season_sigma_days, cfg.season_floor) * keep
        corr = calib.correction_field(var, means, tr.obs, w_i, cfg.bias_smooth_sigma)
        prior = prior_for(cfg, tr.mondays[i], pweeks, ponehots, tr.mondays[i] - dt.timedelta(days=PRIOR_GAP_DAYS - 7))
        oh = calib.obs_onehot(tr.obs[i], tr.bounds[i])
        p_prior[i], onehot[i] = prior, oh
        for li, lam in enumerate(L):
            Xl = calib.apply_correction(var, X_all[i], corr, lam)
            mu = np.nanmean(Xl, axis=0)
            for si, s in enumerate(S):
                p = calib.categorize(calib.scale_spread(var, Xl, s, mean=mu), tr.bounds[i])
                for pi, sp in enumerate(P):
                    ps = calib.smooth_probs(p, sp)
                    terms[li, si, pi, i] = calib.rps_terms(ps, prior, oh, W, rows, NROW)
                    if (li, si, pi) == cl:
                        p_ens[i] = ps
        if (i + 1) % 10 == 0 or i + 1 == N:
            log(f"    {var} window {window}: {i + 1}/{N} runs ({time.time() - t0:.0f} s)")
    path = rows_path(cfg, var, window)
    np.savez_compressed(
        path, terms=terms, inits=np.array([d.isoformat() for d in tr.inits]),
        mondays=np.array([m.isoformat() for m in tr.mondays]), mon_ord=mon_ord, doys=doys,
        lambdas=np.array(L), spreads=np.array(S), sigmas=np.array(P), control_combo=np.array(cl),
        p_ens=p_ens, p_prior=p_prior, onehot=onehot, score_weight=W,
        exclude_days=cfg.exclude_days)
    log(f"  {var} window {window}: saved {path.name} ({N} runs, {time.time() - t0:.0f} s)")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--vars", nargs="+", default=list(VARIABLES))
    ap.add_argument("--windows", nargs="+", type=int, default=list(WINDOWS))
    args = ap.parse_args(argv)
    cfg = load_config(args.config, experiment="control")
    params = json.loads(cfg.params_path.read_text())
    lsm = get_lsm(cfg)
    log = lambda m: print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}Z] {m}", flush=True)  # noqa: E731
    for var in args.vars:
        pweeks, ponehots = prior_data(cfg, var)
        for w in args.windows:
            collect(cfg, var, w, params[var][str(w)], lsm, pweeks, ponehots, log=log)
        del ponehots


if __name__ == "__main__":
    main()
