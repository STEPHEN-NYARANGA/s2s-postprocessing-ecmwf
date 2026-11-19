"""R2: climate-state-conditioned climatological priors, tested on ERA5 history (research only).

Nothing here is used by the operational SeasonBlend pipeline.

Pilot design (2 m temperature, the only variable with a long daily ERA5 record in data/cds/):

* Weekly means: 7-day means of ERA5 daily 2 m temperature on the 1.5 degree grid, land points
  that the leaderboard scores (land fraction >= 0.5).
* Forecast cases: every Thursday initialisation from 2005 to 2025; window 1 verifies the 7 days
  starting on day 19 (Thursday + 18 = Monday), window 2 the 7 days starting on day 26.
* Quintile boundaries, as AI_WQ_package.compute_20yr_quintile_climatology does it (weekly values
  starting at D + {-4, -2, 0, 2, 4} days in other years), but from every other year of 2004-2025
  rather than the 20 years before (the record starts in 2004). The target's own year is never used.
* Folds: "ENSO years" running July to June, so one El Nino or La Nina winter is never split
  between training and test. Every statistic used for a held-out fold (regression slopes, trend,
  residual spread) is estimated from the other folds only.
* Climate indices known at initialisation (aiwq.indices: CPC weekly Nino 3.4 with an 8-day lag,
  BoM weekly Dipole Mode Index with a 4-day lag). The BoM weekly DMI starts in August 2008, so
  IOD comparisons use initialisations from 2008-09 onwards and are repeated for ENSO on the same
  subset.

Candidates (probabilities over the five quintiles):

* clim     - 0.2 everywhere (RPSS = 0 by definition).
* recent   - SeasonBlend's existing prior: the seasonally weighted (sigma 45 d) frequency of each
             quintile in Monday weeks of the past 3 years that ended at least 6 days before the
             initialisation, smoothed in space (sigma 1.5 grid points), as aiwq.fit.prior_for.
* g(state) - a Gaussian-shift prior: z = alpha + gamma * t + beta . x + noise is fitted per grid
             point and calendar date (seasonal weights, sigma 45 d) to standardised weekly
             anomalies, with x the index values at initialisation. The state part beta . x shifts a
             normal distribution with the residual spread; its probabilities in the standard
             normal quintiles give g. A shrinkage factor kappa multiplies beta.
* recent x g - SeasonBlend's prior tilted by the state: p ~ recent * g / 0.2, renormalised.
  This keeps the trend information of the existing prior and adds only the state signal.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd
import xarray as xr
from scipy.special import ndtr, ndtri

from . import calib
from .config import Config
from .cds import daily_path
from .dates import day_of_year
from .grid import LAT, area_weights
from .indices import Indices

OFFSETS = (-4, -2, 0, 2, 4)
ZQ = np.array([-0.8416212335729143, -0.2533471031357997, 0.2533471031357997, 0.8416212335729143])
LEADS = {1: 18, 2: 25}   # days from Thursday to the first day of each window


# ------------------------------------------------------------------ data ------------------

@dataclass
class Daily:
    days: pd.DatetimeIndex      # (T,)
    x: np.ndarray               # (T, P) float32 daily means on the selected points
    points: np.ndarray          # (P,) flat indices into the (121, 240) grid


def load_daily(cfg: Config, var: str, years, mask: np.ndarray) -> Daily:
    pts = np.flatnonzero(mask.ravel())
    days, xs = [], []
    for y in years:
        p = daily_path(cfg, var, y)
        with xr.open_dataset(p) as ds:
            da = ds[var]
            if float(da.latitude[0]) < float(da.latitude[-1]):
                da = da.isel(latitude=slice(None, None, -1))
            arr = da.values.reshape(da.sizes["time"], -1)[:, pts].astype(np.float32)
            days.append(pd.DatetimeIndex(da["time"].values).normalize())
            xs.append(arr)
    t = days[0].append(days[1:])
    x = np.concatenate(xs)
    full = pd.date_range(t[0], t[-1], freq="D")
    if len(full) != len(t) or not (full == t).all():
        raise ValueError(f"{var}: daily record has gaps")
    return Daily(t, x, pts)


def weekly_means(d: Daily) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """7-day means starting on every day (the last 6 days have no complete week)."""
    c = np.cumsum(np.vstack([np.zeros((1, d.x.shape[1]), np.float64), d.x.astype(np.float64)]), axis=0)
    wk = ((c[7:] - c[:-7]) / 7.0).astype(np.float32)
    return d.days[: wk.shape[0]], wk


class WeeklyClimate:
    """Leave-own-year-out climatology of weekly means (boundaries, mean and spread)."""

    def __init__(self, starts: pd.DatetimeIndex, wk: np.ndarray, years):
        self.pos = {t: i for i, t in enumerate(starts)}
        self.wk = wk
        self.years = list(years)

    def sample(self, start: pd.Timestamp, exclude_year: int) -> np.ndarray:
        idx = []
        for y in self.years:
            if y == exclude_year:
                continue
            try:
                base = start.replace(year=y)
            except ValueError:  # 29 February
                base = (start - pd.Timedelta(days=1)).replace(year=y)
            for off in OFFSETS:
                i = self.pos.get(base + pd.Timedelta(days=off))
                if i is not None:
                    idx.append(i)
        return self.wk[idx]

    def stats(self, start: pd.Timestamp):
        s = self.sample(start, start.year)
        b = np.quantile(s, [0.2, 0.4, 0.6, 0.8], axis=0).astype(np.float32)
        return b, s.mean(axis=0), s.std(axis=0) + 1e-6


def onehot(x: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Observed category (official tie rules) -> (5, P)."""
    k = (x[None] >= b).sum(axis=0)
    return (np.arange(5)[:, None] == k[None]).astype(np.uint8)


# ------------------------------------------------------------------ cases -----------------

@dataclass
class Cases:
    init: pd.DatetimeIndex     # (N,) Thursdays
    window: np.ndarray         # (N,)
    start: pd.DatetimeIndex    # (N,) first day of the verifying week
    fold: np.ndarray           # (N,) ENSO year (July-June), labelled by the July year
    oh: np.ndarray             # (N, 5, P) observed category
    z: np.ndarray              # (N, P) standardised anomaly (leave-own-year-out climatology)
    nino34: np.ndarray         # (N,)
    dmi: np.ndarray            # (N,)
    valid: np.ndarray | None = None   # (N, P) points the leaderboard scores (pr: not arid); None = all

    def weights(self, pw: np.ndarray) -> np.ndarray:
        """Point weights per case (N, P): area weight, zero where the point is not scored."""
        return np.broadcast_to(pw, self.z.shape) if self.valid is None else self.valid * pw[None]


def enso_year(d) -> int:
    return d.year if d.month >= 7 else d.year - 1


def normal_scores(x: np.ndarray, sample: np.ndarray) -> np.ndarray:
    """Rank of x within the climatological sample, mapped to a standard normal value (ties split)."""
    n = sample.shape[0]
    r = (sample < x[None]).sum(0) + 0.5 * (sample == x[None]).sum(0)
    return ndtri((r + 0.5) / (n + 1.0)).astype(np.float32)


def build_cases(cfg: Config, starts, wk, clim: WeeklyClimate, first: str, last: str, zmode: str = "std",
                arid_mask: bool = False) -> Cases:
    """zmode 'std': (x - mean) / sd of the climatological sample (temperature); 'rank': normal
    scores (precipitation, whose weekly totals are skewed). arid_mask: leave out points whose
    wettest-quintile boundary is 0, as the leaderboard does for precipitation."""
    idx = Indices(cfg)
    inits = pd.date_range(first, last, freq="W-THU")
    rows = []
    for init in inits:
        st = idx.state_at(init.date())
        for w, lead in LEADS.items():
            s = init + pd.Timedelta(days=lead)
            if s not in clim.pos:
                continue
            rows.append((init, w, s, st.nino34, st.iod))
    N, P = len(rows), wk.shape[1]
    oh = np.zeros((N, 5, P), np.uint8)
    z = np.zeros((N, P), np.float32)
    valid = np.ones((N, P), bool) if arid_mask else None
    cache = {}
    for n, (init, w, s, _, _) in enumerate(rows):
        if s not in cache:
            x = wk[clim.pos[s]]
            if zmode == "rank":
                smp = clim.sample(s, s.year)
                b = np.quantile(smp, [0.2, 0.4, 0.6, 0.8], axis=0).astype(np.float32)
                zz = normal_scores(x, smp)
            else:
                b, m, sd = clim.stats(s)
                zz = (x - m) / sd
            cache[s] = (onehot(x, b), zz, b[3] > 0)
        oh[n], z[n] = cache[s][0], cache[s][1]
        if valid is not None:
            valid[n] = cache[s][2]
    nan = lambda v: np.nan if v is None else v  # noqa: E731
    return Cases(pd.DatetimeIndex([r[0] for r in rows]), np.array([r[1] for r in rows]),
                 pd.DatetimeIndex([r[2] for r in rows]), np.array([enso_year(r[0]) for r in rows]),
                 oh, z, np.array([nan(r[3]) for r in rows], float), np.array([nan(r[4]) for r in rows], float), valid)


# ------------------------------------------------------------------ priors ----------------

def scatter(v: np.ndarray, points: np.ndarray, shape=(121, 240)) -> np.ndarray:
    g = np.full(int(np.prod(shape)), np.nan)
    g[points] = v
    return g.reshape(shape)


def smooth_points(v: np.ndarray, points: np.ndarray, sigma: float) -> np.ndarray:
    """NaN-aware Gaussian smoothing of a field given on `points` only (other points do not leak in)."""
    if sigma <= 0:
        return v
    if v.ndim == 1:
        return calib.smooth2d(scatter(v, points), sigma).ravel()[points]
    return np.stack([smooth_points(v[k], points, sigma) for k in range(v.shape[0])])


def recent_prior(cases: Cases, starts, wk, clim: WeeklyClimate, points, years_back: float = 3.0,
                 latency_days: int = 6, sigma_season: float = 45.0, sigma_space: float = 1.5) -> np.ndarray:
    """SeasonBlend's observed-frequency prior, from Monday weeks of the past `years_back` years."""
    mondays = starts[starts.dayofweek == 0]
    cat = {}
    for m in mondays:
        b, _, _ = clim.stats(m)
        cat[m] = onehot(wk[clim.pos[m]], b)
    mon = np.array(mondays)
    mon_doy = np.array([day_of_year(m.date()) for m in mondays])
    OH = np.stack([cat[m] for m in mondays]).astype(np.float32)   # (M, 5, P)
    out = np.empty(cases.oh.shape, np.float32)
    done = {}
    for n in range(len(cases.init)):
        key = (cases.init[n], cases.window[n])
        cutoff = cases.init[n] - pd.Timedelta(days=latency_days)
        lo = cases.init[n] - pd.Timedelta(days=int(365.25 * years_back))
        sel = (mon + np.timedelta64(7, "D") <= np.datetime64(cutoff)) & (mon >= np.datetime64(lo))
        if not sel.any():
            out[n] = 0.2
            continue
        w = calib.season_weights(day_of_year(cases.start[n].date()), mon_doy[sel], sigma_season, 0.0)
        p = np.tensordot(w / w.sum(), OH[sel], axes=(0, 0))
        p = smooth_points(p, points, sigma_space)
        p = np.clip(np.nan_to_num(p, nan=0.2), 0, None)
        out[n] = p / p.sum(axis=0, keepdims=True)
        done[key] = n
    return out


def gauss_probs(mu: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Probabilities of the standard-normal quintiles for N(mu, s^2); mu, s (..., P) -> (..., 5, P)."""
    zq = ZQ.astype(np.float32).reshape((1,) * (mu.ndim - 1) + (4, 1))
    c = ndtr((zq - mu[..., None, :].astype(np.float32)) / s[..., None, :].astype(np.float32))
    c = np.concatenate([np.zeros_like(c[..., :1, :]), c, np.ones_like(c[..., :1, :])], axis=-2)
    return np.diff(c, axis=-2)


def tilt(prior: np.ndarray, g: np.ndarray) -> np.ndarray:
    p = prior * (g / 0.2)
    return p / p.sum(axis=-2, keepdims=True)


@dataclass
class StateFit:
    mu: np.ndarray       # (N, P) state part of the predicted standardised anomaly (kappa = 1)
    s: np.ndarray        # (N, P) residual spread (fraction of the climatological standard deviation)
    beta: dict           # fold -> (k, ndoy, P) slopes for diagnostics (only for the requested folds)


def fit_state(cases: Cases, predictors: list[str], points, sigma_season: float = 45.0,
              sigma_space: float = 1.5, keep_beta_for=(), use=None, s_floor: float = 0.6) -> StateFit:
    """Leave-one-ENSO-year-out regression of z on [1, trend, predictors] with seasonal weights.

    For every held-out fold and every calendar date of its cases, the slopes are fitted on the
    other folds (cases in `use`, default all), smoothed in space, and the state part beta . x and
    the residual spread are returned for the held-out cases.
    """
    N, P = cases.z.shape
    use = np.ones(N, bool) if use is None else use
    X = np.column_stack([np.ones(N), (cases.init.year + cases.init.dayofyear / 365.25 - 2015.0) / 10.0]
                        + [getattr(cases, p) for p in predictors])
    ok = use & np.isfinite(X).all(axis=1)
    doy = np.array([day_of_year(d.date()) for d in cases.start])
    mu = np.full((N, P), np.nan, np.float32)
    s = np.full((N, P), np.nan, np.float32)
    betas = {}
    k = len(predictors)
    for f in np.unique(cases.fold[ok]):
        test = ok & (cases.fold == f)
        train = ok & (cases.fold != f)
        Xt, Zt = X[train], cases.z[train].astype(np.float64)
        Z2 = Zt ** 2
        dt_ = doy[train]
        udoy = np.unique(doy[test])
        bkeep = []
        for d in udoy:
            w = calib.season_weights(d, dt_, sigma_season, 0.0)
            XtW = Xt.T * w
            A = XtW @ Xt + 1e-6 * np.eye(Xt.shape[1])
            XWZ = XtW @ Zt
            coef = np.linalg.solve(A, XWZ)                            # (2 + k, P)
            wz2 = w @ Z2
            ssr = wz2 - np.sum(coef * XWZ, axis=0)                    # weighted residual sum of squares
            sst = wz2 - (w @ Zt) ** 2 / w.sum()
            r2 = 1.0 - ssr / np.maximum(sst, 1e-12)
            sd = np.sqrt(np.clip(1.0 - r2, s_floor ** 2, 1.0))
            beta = smooth_points(coef[2:], points, sigma_space) if k else np.zeros((0, P))
            sel = test & (doy == d)
            mu[sel] = X[sel, 2:] @ beta if k else 0.0
            s[sel] = sd
            if f in keep_beta_for:
                bkeep.append(beta)
        if f in keep_beta_for:
            betas[f] = (udoy, np.stack(bkeep))
    return StateFit(mu, s, betas)


def fit_predict(cases: Cases, predictors: list[str], points, train: np.ndarray, doys_new, X_new,
                sigma_season: float = 45.0, sigma_space: float = 1.5, s_floor: float = 0.6):
    """Fit on the cases in `train` and predict the state part and spread for new initialisations.

    doys_new (M,) day of year of each new verifying week; X_new (M, k) index values at its
    initialisation. Returns mu (M, P), s (M, P) and the slopes (M, k, P).
    """
    N, P = cases.z.shape
    X = np.column_stack([np.ones(N), (cases.init.year + cases.init.dayofyear / 365.25 - 2015.0) / 10.0]
                        + [getattr(cases, p) for p in predictors])
    ok = train & np.isfinite(X).all(axis=1)
    Xt, Zt = X[ok], cases.z[ok].astype(np.float64)
    Z2 = Zt ** 2
    doy = np.array([day_of_year(d.date()) for d in cases.start])[ok]
    M = len(doys_new)
    mu = np.zeros((M, P), np.float32); s = np.ones((M, P), np.float32)
    B = np.zeros((M, len(predictors), P), np.float32)
    for d in np.unique(doys_new):
        w = calib.season_weights(d, doy, sigma_season, 0.0)
        XtW = Xt.T * w
        XWZ = XtW @ Zt
        coef = np.linalg.solve(XtW @ Xt + 1e-6 * np.eye(Xt.shape[1]), XWZ)
        wz2 = w @ Z2
        r2 = 1.0 - (wz2 - np.sum(coef * XWZ, axis=0)) / np.maximum(wz2 - (w @ Zt) ** 2 / w.sum(), 1e-12)
        beta = smooth_points(coef[2:], points, sigma_space)
        sel = np.asarray(doys_new) == d
        mu[sel] = np.asarray(X_new)[sel] @ beta
        s[sel] = np.sqrt(np.clip(1.0 - r2, s_floor ** 2, 1.0))
        B[sel] = beta
    return mu, s, B


# ------------------------------------------------------------------ scores ----------------

def rps(p: np.ndarray, oh: np.ndarray) -> np.ndarray:
    """p, oh (..., 5, P) -> RPS per point (..., P)."""
    d = np.cumsum(p, axis=-2, dtype=np.float32)[..., :4, :] - np.cumsum(oh, axis=-2, dtype=np.float32)[..., :4, :]
    return (d * d).sum(axis=-2)


def point_weights(points: np.ndarray, base: np.ndarray | None = None) -> np.ndarray:
    W = area_weights() if base is None else base
    return W.ravel()[points]


def weekly_scores(p: np.ndarray, oh: np.ndarray, w: np.ndarray, mask: np.ndarray | None = None):
    """Area-weighted RPS of forecast and climatology for every case -> (rps, rps_clim)."""
    ww = w if mask is None else w * mask
    r = rps(p, oh) @ ww
    rc = rps(np.full(p.shape, 0.2, np.float32), oh) @ ww
    return r, rc


def reliability_component(p: np.ndarray, oh: np.ndarray, w: np.ndarray, nbins: int = 10) -> np.ndarray:
    """Share-weighted (forecast - observed)^2 per category, 10 probability bins -> (5,)."""
    out = np.zeros(5)
    for k in range(5):
        f = p[:, k].ravel()
        o = oh[:, k].ravel()
        ww = np.broadcast_to(w, p[:, k].shape).ravel()
        b = np.minimum((f * nbins).astype(int), nbins - 1)
        tot = np.bincount(b, ww, nbins)
        fm = np.bincount(b, ww * f, nbins) / np.maximum(tot, 1e-12)
        om = np.bincount(b, ww * o, nbins) / np.maximum(tot, 1e-12)
        out[k] = np.sum(tot / tot.sum() * (fm - om) ** 2)
    return out


# ------------------------------------------------------------------ R1 weaknesses ---------

def rps_reliability(p: np.ndarray, oh: np.ndarray, w: np.ndarray, nbins: int = 20) -> np.ndarray:
    """Reliability term of the RPS, per cumulative threshold (4,), from forecasts p (N, 5, ...) and
    observed categories oh (N, 5, ...) with point weights w (broadcastable to p[:, 0]).

    RPS = sum over thresholds of the Brier score of the cumulative probability, and each Brier
    score = reliability - resolution + uncertainty. Summed over thresholds and divided by the
    climatological RPS, the reliability term is the most a perfect recalibration of these
    probabilities (keeping their ranking) could add to the RPSS, measured in-sample.
    """
    F = np.cumsum(p, axis=1)[:, :4]
    O = np.cumsum(oh, axis=1)[:, :4]
    ww = np.broadcast_to(w, p[:, 0].shape).ravel()
    ok = np.isfinite(ww) & (ww > 0)
    out = np.zeros(4)
    for k in range(4):
        f = F[:, k].ravel()[ok]; o = O[:, k].ravel()[ok]; wk = ww[ok]
        good = np.isfinite(f) & np.isfinite(o)
        f, o, wk = f[good], o[good], wk[good]
        b = np.minimum((f * nbins).astype(int), nbins - 1)
        tot = np.bincount(b, wk, nbins)
        fm = np.bincount(b, wk * f, nbins) / np.maximum(tot, 1e-12)
        om = np.bincount(b, wk * o, nbins) / np.maximum(tot, 1e-12)
        out[k] = np.sum(tot * (fm - om) ** 2)
    return out


def cv_subsample(terms: np.ndarray, mon_ord: np.ndarray, exclude_days: int, scheme, n_train: int,
                 rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Leave-one-out like r1.cv_scores, but each fold trains on a random subset of n_train of the
    eligible weeks: the learning curve of SeasonBlend's fitted settings and weights."""
    from . import r1
    nL, nS, nP, N, R, _ = terms.shape
    flat = terms.reshape(nL * nS * nP, N, R, 6)
    rps = np.full(N, np.nan)
    clim = np.array([flat[0, i, :, 5].sum() for i in range(N)])
    for i in range(N):
        elig = np.flatnonzero(np.abs(mon_ord - mon_ord[i]) >= exclude_days)
        if len(elig) < n_train:
            continue
        keep = rng.choice(elig, n_train, replace=False)
        k, a, c = r1._fit_fold(flat[:, keep].sum(axis=1), scheme)
        rps[i] = r1.rps_rows(flat[k, i], a, c)
    return rps, clim


def year_bootstrap(rps_a: np.ndarray, rps_b: np.ndarray, clim: np.ndarray, groups: np.ndarray,
                   n_boot: int = 4000, seed: int = 0) -> dict:
    """Difference in RPSS (b minus a, ratio convention) with whole groups (ENSO years) resampled."""
    rng = np.random.default_rng(seed)
    g = np.unique(groups)
    idx = [np.flatnonzero(groups == x) for x in g]
    A = np.array([rps_a[i].sum() for i in idx]); B = np.array([rps_b[i].sum() for i in idx])
    C = np.array([clim[i].sum() for i in idx])
    d0 = (A.sum() - B.sum()) / C.sum()
    s = rng.integers(0, len(g), (n_boot, len(g)))
    d = (A[s].sum(1) - B[s].sum(1)) / C[s].sum(1)
    return {"delta": d0, "lo90": float(np.quantile(d, 0.05)), "hi90": float(np.quantile(d, 0.95)),
            "p_le_0": float(np.mean(d <= 0)), "n_groups": len(g),
            "groups_better": int(np.sum(A - B > 0))}
