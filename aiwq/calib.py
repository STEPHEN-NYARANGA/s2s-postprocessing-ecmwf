"""Core calibration maths (pure numpy, no I/O).

Forecast for one variable, window and grid point:

    X'_m  = bias-corrected member m        (additive for tas/mslp, multiplicative for pr,
                                            correction shrunk by lambda)
    X''_m = mean(X') + s * (X'_m - mean(X'))   (spread scaling s)
    p_ens = fraction of members in each quintile (official tie rules), smoothed in space
    p     = a * p_ens + c * p_prior + (1 - a - c) * 0.2

p_prior is the seasonally weighted frequency with which recent ERA5 weeks fell in each
quintile of the 20-year climatology (it carries the warming trend). The ranked probability
score is quadratic in (a, c), so the blend weights have a closed-form least-squares
solution per latitude band.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

CUM_CLIM = np.array([0.2, 0.4, 0.6, 0.8], dtype=np.float64)[:, None, None]


# ------------------------------------------------------------ quintile counting ---------

def categorize(X: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Members X (M, ny, nx) and boundaries B (4, ny, nx) -> probabilities (5, ny, nx).

    Same rules as AI_WQ_package.forecast_evaluation.conditional_obs_probs:
    bin 1: x < b1; bins 2-4: b_lo <= x < b_hi (empty when b_lo == b_hi); bin 5: x >= b4.
    Missing members are ignored; points without valid data get 0.2 everywhere.
    """
    b0, b1, b2, b3 = B[0], B[1], B[2], B[3]
    valid = np.isfinite(X)
    n = valid.sum(axis=0)
    p = np.empty((5,) + B.shape[1:], dtype=np.float64)
    p[0] = (X < b0).sum(axis=0)
    p[1] = ((X >= b0) & (X < b1)).sum(axis=0) * (b0 != b1)
    p[2] = ((X >= b1) & (X < b2)).sum(axis=0) * (b1 != b2)
    p[3] = ((X >= b2) & (X < b3)).sum(axis=0) * (b2 != b3)
    p[4] = (X >= b3).sum(axis=0)
    p /= np.maximum(n, 1)[None]
    bad = (n == 0) | ~np.isfinite(B).all(axis=0)
    p[:, bad] = 0.2
    return p


def obs_onehot(O: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Observed category as one-hot (5, ny, nx); NaN where the official scoring skips the
    point (missing obs, or all boundaries equal, e.g. 0 mm everywhere in deserts)."""
    oh = categorize(O[None], B)
    invalid = ~np.isfinite(O) | ~np.isfinite(B).all(axis=0) | (np.nanmin(B, axis=0) == np.nanmax(B, axis=0))
    oh[:, invalid] = np.nan
    return oh


# ------------------------------------------------------------ smoothing -----------------

def smooth2d(a: np.ndarray, sigma: float) -> np.ndarray:
    """NaN-aware Gaussian smoothing on the lat-lon grid (wraps in longitude)."""
    if sigma <= 0:
        return a
    m = np.isfinite(a)
    num = gaussian_filter(np.where(m, a, 0.0), sigma, mode=("nearest", "wrap"))
    den = gaussian_filter(m.astype(np.float64), sigma, mode=("nearest", "wrap"))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[den < 1e-6] = np.nan
    return out


def smooth_probs(p: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return p
    out = np.stack([smooth2d(p[k], sigma) for k in range(p.shape[0])])
    out[:, ~np.isfinite(out).all(axis=0)] = 0.2
    return out / out.sum(axis=0, keepdims=True)


# ------------------------------------------------------------ seasonal weighting --------

def season_weights(target_doy: float, doys, sigma: float, floor: float) -> np.ndarray:
    d = np.abs(np.asarray(doys, dtype=float) - float(target_doy))
    d = np.minimum(d, 365.25 - d)
    return floor + (1.0 - floor) * np.exp(-0.5 * (d / sigma) ** 2)


def weighted_mean(stack: np.ndarray, w: np.ndarray) -> np.ndarray:
    """stack (N, ...) with NaNs, weights (N,) -> weighted mean over N."""
    m = np.isfinite(stack)
    w = np.asarray(w, dtype=np.float64).reshape((-1,) + (1,) * (stack.ndim - 1))
    num = (np.where(m, stack, 0.0) * w).sum(axis=0)
    den = (m * w).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


# ------------------------------------------------------------ bias correction -----------

def correction_field(var: str, fc_means: np.ndarray, obs: np.ndarray, w: np.ndarray, sigma: float) -> np.ndarray:
    """Additive bias (tas, mslp) or multiplicative ratio (pr) from training pairs.

    fc_means, obs: (N, ny, nx); w: (N,) seasonal weights.
    """
    if var == "pr":
        f = smooth2d(weighted_mean(fc_means, w), sigma)
        o = smooth2d(weighted_mean(obs, w), sigma)
        eps = 1.0  # mm per week
        r = (o + eps) / (f + eps)
        r = np.clip(np.nan_to_num(r, nan=1.0), 0.2, 5.0)
        return r
    bias = smooth2d(weighted_mean(fc_means - obs, w), sigma)
    return np.nan_to_num(bias, nan=0.0)


def apply_correction(var: str, X: np.ndarray, corr: np.ndarray, lam: float) -> np.ndarray:
    if lam == 0:
        return X
    if var == "pr":
        return X * (corr ** lam)[None].astype(X.dtype)
    return X - (lam * corr)[None].astype(X.dtype)


def scale_spread(var: str, X: np.ndarray, s: float, mean: np.ndarray | None = None) -> np.ndarray:
    if s == 1.0:
        return X
    mu = np.nanmean(X, axis=0) if mean is None else mean
    Y = mu[None] + s * (X - mu[None])
    if var == "pr":
        np.maximum(Y, 0.0, out=Y)
    return Y


def ensemble_probs(var, X, B, corr, lam, s, sigma_p) -> np.ndarray:
    Xc = apply_correction(var, X, corr, lam)
    Xc = scale_spread(var, Xc, s)
    return smooth_probs(categorize(Xc, B), sigma_p)


# ------------------------------------------------------------ prior ---------------------

def prior_probs(onehots: np.ndarray, w: np.ndarray, sigma: float) -> np.ndarray:
    """onehots (K, 5, ny, nx) with NaN for unscored points; w (K,) -> (5, ny, nx)."""
    if onehots.shape[0] == 0 or np.sum(w) <= 0:
        return np.full((5,) + onehots.shape[2:], 0.2)
    p = weighted_mean(onehots, w)
    p = np.stack([smooth2d(p[k], sigma) for k in range(5)])
    p[:, ~np.isfinite(p).all(axis=0)] = 0.2
    p = np.clip(p, 0.0, None)
    return p / p.sum(axis=0, keepdims=True)


# ------------------------------------------------------------ RPS bookkeeping -----------

TERMS = ("S11", "S12", "S22", "R1", "R2", "YY")


def rps_terms(p_ens: np.ndarray, p_prior: np.ndarray, onehot: np.ndarray, W: np.ndarray,
              band_idx: np.ndarray, nbands: int) -> np.ndarray:
    """Sufficient statistics (nbands, 6) for RPS(a, c) of p = a*p_ens + c*p_prior + (1-a-c)*clim.

    W is the area weight times the variable's land mask (ny, nx).
    """
    valid = np.isfinite(onehot[0]) & (W > 0)
    Wv = np.where(valid, W, 0.0)
    D1 = np.cumsum(p_ens, axis=0)[:4] - CUM_CLIM
    D2 = np.cumsum(p_prior, axis=0)[:4] - CUM_CLIM
    Y = np.cumsum(np.nan_to_num(onehot), axis=0)[:4] - CUM_CLIM
    fields = ((D1 * D1).sum(0), (D1 * D2).sum(0), (D2 * D2).sum(0),
              (D1 * Y).sum(0), (D2 * Y).sum(0), (Y * Y).sum(0))
    out = np.zeros((nbands, 6))
    for t, f in enumerate(fields):
        rows = (f * Wv).sum(axis=1)
        out[:, t] = np.bincount(band_idx, weights=rows, minlength=nbands)
    return out


def rps_of(terms: np.ndarray, a: float, c: float) -> float:
    S11, S12, S22, R1, R2, YY = terms
    return a * a * S11 + 2 * a * c * S12 + c * c * S22 - 2 * a * R1 - 2 * c * R2 + YY


def solve_blend(terms: np.ndarray) -> tuple[float, float]:
    """Minimise RPS(a, c) subject to a >= 0, c >= 0, a + c <= 1."""
    S11, S12, S22, R1, R2, YY = terms
    if YY <= 0:
        return 1.0, 0.0
    cands = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    det = S11 * S22 - S12 * S12
    if det > 1e-12 * max(S11 * S22, 1e-300):
        cands.append(((R1 * S22 - R2 * S12) / det, (R2 * S11 - R1 * S12) / det))
    if S11 > 0:
        cands.append((R1 / S11, 0.0))
    if S22 > 0:
        cands.append((0.0, R2 / S22))
    den = S11 - 2 * S12 + S22
    if den > 0:
        t = (R1 - R2 - S12 + S22) / den
        cands.append((t, 1.0 - t))
    feas = [(a, c) for a, c in cands if a >= -1e-9 and c >= -1e-9 and a + c <= 1 + 1e-9]
    a, c = min(feas, key=lambda ac: rps_of(terms, *ac))
    return float(np.clip(a, 0, 1)), float(np.clip(c, 0, 1 - np.clip(a, 0, 1)))


def blend(p_ens: np.ndarray, p_prior: np.ndarray, a_band, c_band, band_idx: np.ndarray) -> np.ndarray:
    a = np.asarray(a_band)[band_idx][None, :, None]
    c = np.asarray(c_band)[band_idx][None, :, None]
    return a * p_ens + c * p_prior + (1.0 - a - c) * 0.2


def finalize(p: np.ndarray) -> np.ndarray:
    """No NaNs, inside [0, 1], sums exactly 1 along the quintile axis."""
    p = np.array(p, dtype=np.float64)
    p[:, ~np.isfinite(p).all(axis=0)] = 0.2
    p = np.clip(p, 0.0, 1.0)
    s = p.sum(axis=0, keepdims=True)
    p = np.where(s > 0, p / np.where(s > 0, s, 1.0), 0.2)
    return p


def rpss_from_terms(terms_total: np.ndarray, a_band, c_band) -> float:
    rps = sum(rps_of(terms_total[b], a_band[b], c_band[b]) for b in range(terms_total.shape[0]))
    clim = terms_total[:, 5].sum()
    return float(1.0 - rps / clim) if clim > 0 else float("nan")
