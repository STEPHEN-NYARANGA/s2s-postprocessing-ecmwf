"""Leave-one-out fit of the calibration settings, plus a backtest report.

For each variable and window, every cached Thursday run with a verifying ERA5 week is
forecast again using bias corrections estimated from the *other* runs (runs within
`exclude_days` of the target week are left out, because consecutive weeks overlap), and a
prior built only from weeks that ended at least 30 days before the target week. The grid
search picks (lambda, spread, smoothing); blend weights are solved in closed form per
latitude band. Scores are period-aggregated RPSS, computed the same way as the
leaderboards (area weighted, land points only for tas and pr, deserts skipped for pr).

The bias correction and prior are always left out for the scored week, but the grid search
and the blend weights use all weeks, so the "final" score is slightly optimistic. The
cross-validated score ("final_cv") also chooses the settings and solves the blend weights
without the scored week (and the weeks within exclude_days of it). Use final_cv to compare
methods with different numbers of fitted weights; it is the honest estimate.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass

import numpy as np

from . import calib
from .config import VARIABLES, WINDOWS, Config
from .dates import day_of_year, utc_today, window_monday
from .ens import cached_inits, load_members
from .grid import LAT, area_weights, band_index
from .obs import available_weeks, get_clim, get_lsm, get_obs, read_clim, read_obs, clim_file, obs_file

PRIOR_GAP_DAYS = 30


@dataclass
class Training:
    inits: list
    mondays: list
    obs: np.ndarray      # (N, ny, nx)
    bounds: np.ndarray   # (N, 4, ny, nx)

    @property
    def doys(self):
        return np.array([day_of_year(m) for m in self.mondays])


def training_data(cfg: Config, var: str, window: int, before: dt.date | None = None,
                  download: bool = True) -> Training:
    """Cached ENS runs that have a verifying week. With `before`, only weeks that ended
    before that initialisation are used (forecast mode)."""
    inits, mons, O, B = [], [], [], []
    for init in cached_inits(cfg, (var,)):
        m = window_monday(init, window)
        if before is not None and (init >= before or m + dt.timedelta(days=7) > before):
            continue
        o = get_obs(cfg, m, var, download=download)
        if o is None:
            continue
        b = get_clim(cfg, m, var, download=download)
        if b is None:
            continue
        inits.append(init); mons.append(m); O.append(o); B.append(b)
    if not inits:
        return Training([], [], np.zeros((0,) + LAT.shape + (240,)), np.zeros((0, 4) + LAT.shape + (240,)))
    return Training(inits, mons, np.stack(O), np.stack(B))


def prior_data(cfg: Config, var: str):
    weeks = available_weeks(cfg, var)
    oh = np.stack([calib.obs_onehot(read_obs(obs_file(cfg, var, m), var),
                                    read_clim(clim_file(cfg, var, m), var)).astype(np.float32)
                   for m in weeks]) if weeks else np.zeros((0, 5) + LAT.shape + (240,), np.float32)
    return weeks, oh


def prior_for(cfg: Config, target_monday: dt.date, weeks, onehots, cutoff: dt.date) -> np.ndarray:
    sel = np.array([m + dt.timedelta(days=7) <= cutoff for m in weeks], dtype=bool)
    if not sel.any():
        return np.full((5,) + LAT.shape + (240,), 0.2)
    w = calib.season_weights(day_of_year(target_monday), [day_of_year(m) for m in np.array(weeks)[sel]],
                             cfg.season_sigma_days, 0.0)
    return calib.prior_probs(onehots[sel], w, cfg.prior_smooth_sigma)


def score_weights(var: str, lsm: np.ndarray) -> np.ndarray:
    W = area_weights()
    if var in ("tas", "pr"):
        W = W * (lsm >= 0.5)
    return W


def fit_one(cfg: Config, var: str, window: int, lsm: np.ndarray, pweeks, ponehots, log=print) -> dict | None:
    tr = training_data(cfg, var, window)
    N = len(tr.inits)
    if N < cfg.min_train:
        log(f"  {var} window {window}: only {N} verified runs (need {cfg.min_train}); skipping fit.")
        return None
    t0 = time.time()
    X_all = [load_members(cfg, d, var, window) for d in tr.inits]
    means = np.stack([np.nanmean(X, axis=0) for X in X_all])
    doys = tr.doys
    mon_ord = np.array([m.toordinal() for m in tr.mondays])
    bidx = band_index(cfg.blend_bands)
    nb = len(cfg.blend_bands)
    W = score_weights(var, lsm)
    L, S, P = cfg.lambdas, cfg.spreads, cfg.prob_smooth_sigmas
    terms = np.zeros((len(L), len(S), len(P), N, nb, 6))
    for i in range(N):
        keep = np.abs(mon_ord - mon_ord[i]) >= cfg.exclude_days
        w_i = calib.season_weights(doys[i], doys, cfg.season_sigma_days, cfg.season_floor) * keep
        corr = calib.correction_field(var, means, tr.obs, w_i, cfg.bias_smooth_sigma)
        prior = prior_for(cfg, tr.mondays[i], pweeks, ponehots, tr.mondays[i] - dt.timedelta(days=PRIOR_GAP_DAYS - 7))
        oh = calib.obs_onehot(tr.obs[i], tr.bounds[i])
        for li, lam in enumerate(L):
            Xl = calib.apply_correction(var, X_all[i], corr, lam)
            mu = np.nanmean(Xl, axis=0)
            for si, s in enumerate(S):
                p = calib.categorize(calib.scale_spread(var, Xl, s, mean=mu), tr.bounds[i])
                for pi, sp in enumerate(P):
                    terms[li, si, pi, i] = calib.rps_terms(calib.smooth_probs(p, sp), prior, oh, W, bidx, nb)
        if (i + 1) % 10 == 0 or i + 1 == N:
            log(f"    {var} window {window}: {i + 1}/{N} runs ({time.time() - t0:.0f} s)")

    tot = terms.sum(axis=3)  # (L, S, P, nb, 6)
    best = None
    for li in range(len(L)):
        for si in range(len(S)):
            for pi in range(len(P)):
                ab = [calib.solve_blend(tot[li, si, pi, b]) for b in range(nb)]
                a, c = [x[0] for x in ab], [x[1] for x in ab]
                score = calib.rpss_from_terms(tot[li, si, pi], a, c)
                if best is None or score > best[0]:
                    best = (score, li, si, pi, a, c)
    score, li, si, pi, a, c = best

    def cfg_score(lam, s, sp, aa, cc):
        return calib.rpss_from_terms(tot[L.index(lam), S.index(s), P.index(sp)], aa, cc)

    ones, zeros = [1.0] * nb, [0.0] * nb
    ens_only = max(calib.rpss_from_terms(tot[x, y, z], ones, zeros)
                   for x in range(len(L)) for y in range(len(S)) for z in range(len(P)))
    scores = {
        "raw_ensemble": cfg_score(0.0, 1.0, 0.0, ones, zeros),
        "bias_corrected": cfg_score(1.0, 1.0, 0.0, ones, zeros),
        "ensemble_calibrated": ens_only,
        "prior_only": cfg_score(0.0, 1.0, 0.0, zeros, ones),
        "final": score,
    }
    weekly_final = [calib.rpss_from_terms(terms[li, si, pi, i], a, c) for i in range(N)]
    raw_i = (L.index(0.0), S.index(1.0), P.index(0.0))
    weekly_raw = [calib.rpss_from_terms(terms[raw_i + (i,)], ones, zeros) for i in range(N)]

    def rps_sum(t, aa, cc):
        return float(sum(calib.rps_of(t[b], aa[b], cc[b]) for b in range(nb)))

    rps_final = [rps_sum(terms[li, si, pi, i], a, c) for i in range(N)]
    rps_raw = [rps_sum(terms[raw_i + (i,)], ones, zeros) for i in range(N)]
    rps_clim = [float(terms[0, 0, 0, i, :, 5].sum()) for i in range(N)]
    rps_cv = cross_validated_rps(terms, mon_ord, cfg.exclude_days)
    scores["final_cv"] = 1.0 - sum(rps_cv) / sum(rps_clim)
    log(f"  {var} window {window}: N={N}, lambda={L[li]}, spread={S[si]}, smooth={P[pi]}, "
        f"a={np.round(a, 2).tolist()}, c={np.round(c, 2).tolist()}, "
        f"RPSS raw {scores['raw_ensemble']:+.3f} -> final {score:+.3f} (cross-validated {scores['final_cv']:+.3f})")
    return {
        "lam": L[li], "s": S[si], "sigma_p": P[pi], "bands": cfg.blend_bands, "a": a, "c": c,
        "n_train": N, "train_first": tr.inits[0].isoformat(), "train_last": tr.inits[-1].isoformat(),
        "scores": scores,
        "weekly": {"inits": [d.isoformat() for d in tr.inits], "rpss_final": weekly_final, "rpss_raw": weekly_raw,
                   "rps_final": rps_final, "rps_final_cv": rps_cv, "rps_raw": rps_raw, "rps_clim": rps_clim},
    }


def cross_validated_rps(terms: np.ndarray, mon_ord: np.ndarray, exclude_days: int) -> list[float]:
    """RPS of each week with everything fitted without it.

    terms: (L, S, P, N, nb, 6) sufficient statistics. For week i the weeks within exclude_days
    are dropped, the settings (lambda, spread, smoothing) and the blend weights of each band
    are chosen on the rest, and week i is scored with them.
    """
    nL, nS, nP, N, nb, _ = terms.shape
    flat = terms.reshape(nL * nS * nP, N, nb, 6)
    out = []
    for i in range(N):
        keep = np.abs(mon_ord - mon_ord[i]) >= exclude_days
        tot = flat[:, keep].sum(axis=1)  # (combos, nb, 6)
        best = None
        for k in range(flat.shape[0]):
            ab = [calib.solve_blend(tot[k, b]) for b in range(nb)]
            aa, cc = [x[0] for x in ab], [x[1] for x in ab]
            sc = calib.rpss_from_terms(tot[k], aa, cc)
            if best is None or sc > best[0]:
                best = (sc, k, aa, cc)
        _, k, aa, cc = best
        out.append(float(sum(calib.rps_of(flat[k, i, b], aa[b], cc[b]) for b in range(nb))))
    return out


def fit_all(cfg: Config, variables=VARIABLES, windows=WINDOWS, log=print) -> dict:
    lsm = get_lsm(cfg)
    params = {"fitted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "fitted_on": utc_today().isoformat(), "teamname": cfg.teamname, "modelname": cfg.modelname,
              "experiment": cfg.experiment, "note": cfg.experiment_note}
    for var in variables:
        pweeks, ponehots = prior_data(cfg, var)
        log(f"{var}: prior uses {len(pweeks)} ERA5 weeks")
        params[var] = {}
        for w in windows:
            res = fit_one(cfg, var, w, lsm, pweeks, ponehots, log=log)
            if res is not None:
                params[var][str(w)] = res
        del ponehots
    cfg.params_path.write_text(json.dumps(params, indent=1))
    write_report(cfg, params)
    return params


def load_params(cfg: Config) -> dict:
    if not cfg.params_path.exists():
        raise SystemExit("No fitted parameters yet. Run:  python run.py fit")
    return json.loads(cfg.params_path.read_text())


def write_report(cfg: Config, params: dict):
    out = cfg.output_dir / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    rows = ["raw_ensemble", "bias_corrected", "ensemble_calibrated", "prior_only", "final", "final_cv"]
    labels = {"raw_ensemble": "Raw ECMWF ensemble", "bias_corrected": "Bias-corrected ensemble",
              "ensemble_calibrated": "Calibrated ensemble (no blend)", "prior_only": "Observed-frequency prior only",
              "final": f"{cfg.label} (final)", "final_cv": f"{cfg.label}, fully cross-validated"}
    title = f"experiment `{cfg.experiment}`" if cfg.experiment else cfg.modelname
    lines = [f"# Backtest of {title} (leave-one-out), fitted {params['fitted_at']}", ""]
    if cfg.experiment_note:
        lines += [cfg.experiment_note, ""]
    lines += ["Period-aggregated RPSS against the 20-year ERA5 climatology (0 = climatology). "
              "\"Fully cross-validated\" also fits the settings and blend weights without the scored week; "
              "it is the fair number for comparing methods.", ""]
    csv = ["variable,window,n_train,lambda,spread,smooth," + ",".join(rows)]
    for w in WINDOWS:
        lines += [f"**Window {w} (days {19 if w == 1 else 26}-{25 if w == 1 else 32})**", "",
                  "| Forecast | " + " | ".join(VARIABLES) + " | Variable-averaged |",
                  "|---|" + "---|" * (len(VARIABLES) + 1)]
        for r in rows:
            vals = [params.get(v, {}).get(str(w), {}).get("scores", {}).get(r) for v in VARIABLES]
            if all(x is None for x in vals):
                continue
            ok = [x for x in vals if x is not None]
            avg = np.mean(ok) if len(ok) == len(VARIABLES) else None
            cells = [f"{x:+.3f}" if x is not None else "n/a" for x in vals]
            lines.append(f"| {labels[r]} | " + " | ".join(cells) + f" | {avg:+.3f} |" if avg is not None
                         else f"| {labels[r]} | " + " | ".join(cells) + " | n/a |")
        lines.append("")
        for v in VARIABLES:
            p = params.get(v, {}).get(str(w))
            if p:
                csv.append(f"{v},{w},{p['n_train']},{p['lam']},{p['s']},{p['sigma_p']}," +
                           ",".join(f"{p['scores'].get(r, float('nan')):.4f}" for r in rows))
    lines += ["**Settings**", "", "| Variable | Window | Runs | lambda | spread | smoothing | a (N, Tropics, S) | c (N, Tropics, S) |",
              "|---|---|---|---|---|---|---|---|"]
    for v in VARIABLES:
        for w in WINDOWS:
            p = params.get(v, {}).get(str(w))
            if p:
                lines.append(f"| {v} | {w} | {p['n_train']} ({p['train_first']} to {p['train_last']}) | {p['lam']} | {p['s']} | "
                             f"{p['sigma_p']} | {', '.join(f'{x:.2f}' for x in p['a'])} | {', '.join(f'{x:.2f}' for x in p['c'])} |")
    (out / "backtest_report.md").write_text("\n".join(lines) + "\n")
    (out / "backtest_scores.csv").write_text("\n".join(csv) + "\n")
    try:
        from .plots import weekly_rpss_plot
        weekly_rpss_plot(params, out / "backtest_weekly_rpss.png")
    except Exception as e:  # plotting must never stop the pipeline
        print(f"(weekly RPSS plot skipped: {e})")
