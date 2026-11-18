"""Is one method really better than another? Paired block bootstrap of backtest scores.

Every fitted model (SeasonBlend or an experiment) stores, for each variable, window and
verified week, the RPS of its cross-validated forecast and the RPS of climatology
(params[var][window]["weekly"]). The period score is RPSS = 1 - sum(RPS) / sum(RPS_clim),
the same aggregation as the leaderboards.

To judge a difference between two models:

* weeks are resampled **together for both models** (paired), so the shared week-to-week
  luck cancels;
* weeks are resampled in **blocks of consecutive weeks** (moving-block bootstrap, default
  4 weeks), because neighbouring initialisations verify on overlapping weeks and their
  errors are correlated; resampling single weeks would make the interval too narrow;
* the same resampled dates are used for all six variable/window pairs, so the
  variable-averaged score keeps the correlation between them.

The settings were chosen on these same weeks, which is why the comparison uses the fully
cross-validated RPS (rps_final_cv) when it exists.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

from .config import VARIABLES, WINDOWS, Config


def load_model(cfg: Config, name: str) -> dict:
    """'operational' (data/params.json) or the name of an experiment."""
    stem = "params" if name == "operational" else f"params_{name}"
    path = cfg.data_dir / (f"{stem}_cds.json" if cfg.obs_source == "cds" else f"{stem}.json")
    if not path.exists():
        hint = "python run.py fit" if name == "operational" else f"python run.py --experiment {name} fit"
        raise SystemExit(f"No fitted parameters for {name} ({path.name}). Run:  {hint}")
    return json.loads(path.read_text())


def _weekly(params: dict, var: str, w: int, key: str) -> dict[str, tuple[float, float]]:
    p = params.get(var, {}).get(str(w))
    if not p or "rps_clim" not in p.get("weekly", {}):
        return {}
    wk = p["weekly"]
    rps = wk.get(key) or wk["rps_final"]
    return {d: (r, c) for d, r, c in zip(wk["inits"], rps, wk["rps_clim"])}


def block_resample(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """Indices 0..n-1 resampled in circular blocks of `block` consecutive weeks."""
    block = max(1, min(block, n))
    starts = rng.integers(0, n, size=int(np.ceil(n / block)))
    idx = (starts[:, None] + np.arange(block)[None]) % n
    return idx.ravel()[:n]


def compare(cfg: Config, names: list[str], reference: str | None = None, key: str = "rps_final_cv",
            n_boot: int | None = None, block: int | None = None, seed: int = 0) -> dict:
    """Scores of each model on the weeks all of them share, and bootstrap intervals of the
    difference from `reference` (default: the first name)."""
    n_boot = n_boot or cfg.bootstrap_samples
    block = block or cfg.bootstrap_block_weeks
    reference = reference or names[0]
    models = {n: load_model(cfg, n) for n in names}
    pairs = [(v, w) for v in VARIABLES for w in WINDOWS]
    weekly = {(n, v, w): _weekly(models[n], v, w, key) for n in names for v, w in pairs}
    common = {(v, w): sorted(set.intersection(*(set(weekly[(n, v, w)]) for n in names))) for v, w in pairs}
    dates = sorted(set().union(*common.values()))
    if not dates:
        raise SystemExit("The models share no verified weeks with stored weekly scores. Refit them with this version.")
    pos = {d: i for i, d in enumerate(dates)}

    # arrays (model, pair, date) of RPS and RPS_clim; NaN where a pair has no score that week
    R = np.full((len(names), len(pairs), len(dates)), np.nan)
    C = np.full((len(pairs), len(dates)), np.nan)
    for j, (v, w) in enumerate(pairs):
        for d in common[(v, w)]:
            for m, n in enumerate(names):
                R[m, j, pos[d]], C[j, pos[d]] = weekly[(n, v, w)][d]

    def scores(counts: np.ndarray) -> np.ndarray:
        """counts (dates,) = how often each date is drawn -> RPSS (model, pair)."""
        num = np.nansum(R * counts, axis=2)
        den = np.nansum(C * counts, axis=1)
        return 1.0 - num / den[None]

    full = scores(np.ones(len(dates)))
    rng = np.random.default_rng(seed)
    boot = np.empty((n_boot,) + full.shape)
    for b in range(n_boot):
        counts = np.bincount(block_resample(len(dates), block, rng), minlength=len(dates)).astype(float)
        boot[b] = scores(counts)
    ref = names.index(reference)
    out = {"names": names, "reference": reference, "key": key, "block_weeks": block, "n_boot": n_boot,
           "dates": [dates[0], dates[-1]], "n_dates": len(dates),
           "pairs": [f"{v}_p{w}" for v, w in pairs],
           "n_weeks": {f"{v}_p{w}": len(common[(v, w)]) for v, w in pairs}, "rows": []}
    for m, n in enumerate(names):
        mean_full, mean_boot = full[m].mean(), boot[:, m].mean(axis=1)
        row = {"name": n, "rpss": {p: float(x) for p, x in zip(out["pairs"], full[m])}, "mean": float(mean_full)}
        if m != ref:
            d_full = full[m] - full[ref]
            d_boot = boot[:, m] - boot[:, ref]
            dm_boot = mean_boot - boot[:, ref].mean(axis=1)
            row["delta"] = {p: _summary(d_full[j], d_boot[:, j]) for j, p in enumerate(out["pairs"])}
            row["delta_mean"] = _summary(float(d_full.mean()), dm_boot)
        out["rows"].append(row)
    return out


def _summary(est: float, samples: np.ndarray) -> dict:
    lo, hi = np.percentile(samples, [5, 95])
    return {"est": float(est), "lo90": float(lo), "hi90": float(hi), "p_better": float((samples > 0).mean())}


def write_comparison(cfg: Config, res: dict, path: Path) -> Path:
    names, ref = res["names"], res["reference"]
    lines = [f"# Comparison: {', '.join(names)}", "",
             f"Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC by `python run.py compare`. "
             f"{res['n_dates']} initialisations from {res['dates'][0]} to {res['dates'][1]}; "
             f"score: {'fully cross-validated' if res['key'] == 'rps_final_cv' else res['key']} RPSS "
             "(0 = 20-year climatology), aggregated like the leaderboards.", "",
             "## Scores", "", "| Model | " + " | ".join(res["pairs"]) + " | Mean |",
             "|---|" + "---|" * (len(res["pairs"]) + 1)]
    for r in res["rows"]:
        lines.append(f"| {r['name']} | " + " | ".join(f"{r['rpss'][p]:+.3f}" for p in res["pairs"]) +
                     f" | **{r['mean']:+.3f}** |")
    lines += ["", f"## Difference from {ref}", "",
              f"Estimate [90% interval], and how often the model beats {ref} in {res['n_boot']} paired "
              f"moving-block bootstrap samples (blocks of {res['block_weeks']} weeks).", "",
              "| Model | " + " | ".join(res["pairs"]) + " | Mean |", "|---|" + "---|" * (len(res["pairs"]) + 1)]
    for r in res["rows"]:
        if "delta" not in r:
            continue
        cell = lambda d: f"{d['est']:+.3f} [{d['lo90']:+.3f}, {d['hi90']:+.3f}] {100 * d['p_better']:.0f}%"  # noqa: E731
        lines.append(f"| {r['name']} | " + " | ".join(cell(r["delta"][p]) for p in res["pairs"]) +
                     f" | **{cell(r['delta_mean'])}** |")
    lines += ["", "Promotion rule (docs/research-plan.md): the mean difference must be positive with the 90% "
              "interval above zero, and no variable may get clearly worse.", ""]
    for r in res["rows"]:
        if "delta_mean" in r:
            d = r["delta_mean"]
            verdict = ("passes" if d["lo90"] > 0 and all(x["hi90"] > 0 for x in r["delta"].values())
                       else "does not pass")
            lines.append(f"- **{r['name']}** {verdict} (mean {d['est']:+.3f}, 90% interval {d['lo90']:+.3f} to "
                         f"{d['hi90']:+.3f}).")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
