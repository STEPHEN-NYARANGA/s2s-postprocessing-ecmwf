"""R1 analysis: blend-weight schemes evaluated with cross-validation on row-level RPS terms.

Inputs come from aiwq/research.py (data/research/rows_<var>_p<w>.npz): for every setting
combination c (lambda, spread, smoothing), verified week i and latitude row r, the six
sufficient statistics of RPS(a, c) = a^2 S11 + 2ac S12 + c^2 S22 - 2a R1 - 2c R2 + YY of the
blend p = a p_ens + c p_prior + (1 - a - c) 0.2 (area-weighted, leaderboard masks).

A *weighting scheme* writes the weights of row r as a(r) = sum_k B[r, k] alpha_k and
c(r) = sum_k B[r, k] gamma_k, where B >= 0 and every row of B sums to 1 (a partition of
unity). Then a(r), c(r) are convex combinations of node values, so the constraints
a >= 0, c >= 0, a + c <= 1 hold everywhere as soon as they hold at the nodes, and the RPS
is a quadratic in (alpha, gamma) with a small, exactly solvable problem.

* SeasonBlend (R1-A): B = indicator of three latitude bands (90-30N, 30N-30S, 30-90S).
  Solved with calib.solve_blend, exactly as the operational fit.
* Continuous latitude weights (R1-B): B = normalised Gaussian kernels in latitude.

Cross-validation (`cv_scores`) repeats, for every verified week i, the whole selection with
week i and the weeks within `exclude_days` of it removed: the setting combination and the
scheme's weights are chosen on the remaining weeks, then week i is scored.

Optional `classes` (for example MJO active / inactive at initialisation) give each class its
own weights (R1-D); a class with fewer than `min_class` training weeks uses the pooled
weights instead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from . import calib
from .grid import LAT

# --------------------------------------------------------------------------- schemes ----


def band_basis(bands=((90.0, 30.0), (30.0, -30.0), (-30.0, -90.0))) -> np.ndarray:
    from .grid import band_index

    idx = band_index([list(b) for b in bands])
    B = np.zeros((LAT.size, len(bands)))
    B[np.arange(LAT.size), idx] = 1.0
    return B


def gaussian_basis(nodes_deg=(90, 60, 30, 0, -30, -60, -90), width_deg=15.0) -> np.ndarray:
    nodes = np.asarray(nodes_deg, float)
    K = np.exp(-0.5 * ((LAT[:, None] - nodes[None]) / width_deg) ** 2)
    return K / K.sum(axis=1, keepdims=True)


@dataclass
class Scheme:
    name: str
    B: np.ndarray            # (rows, K) partition of unity

    @property
    def is_indicator(self) -> bool:
        return bool(np.all((self.B == 0) | (self.B == 1)))


# --------------------------------------------------------------------------- solver -----


def _quadratic(T: np.ndarray, B: np.ndarray):
    """T (rows, 6) -> H (2K, 2K), g (2K,), const such that RPS = th'H th - 2 g'th + const."""
    S11, S12, S22, R1, R2, YY = (T[:, k] for k in range(6))
    H11 = B.T @ (S11[:, None] * B)
    H12 = B.T @ (S12[:, None] * B)
    H22 = B.T @ (S22[:, None] * B)
    H = np.block([[H11, H12], [H12, H22]])
    g = np.concatenate([B.T @ R1, B.T @ R2])
    return H, g, float(YY.sum())


def solve_scheme(T: np.ndarray, scheme: Scheme) -> tuple[np.ndarray, np.ndarray]:
    """Node weights (alpha, gamma) minimising the summed RPS of row statistics T (rows, 6)."""
    B = scheme.B
    K = B.shape[1]
    if scheme.is_indicator:
        Tb = B.T @ T  # band sums, identical to SeasonBlend's band statistics
        ab = [calib.solve_blend(Tb[k]) for k in range(K)]
        return np.array([x[0] for x in ab]), np.array([x[1] for x in ab])
    H, g, _ = _quadratic(T, B)
    scale = max(np.abs(H).max(), 1e-300)
    Hs, gs = H / scale, g / scale
    fun = lambda th: float(th @ Hs @ th - 2 * gs @ th)  # noqa: E731
    jac = lambda th: 2 * (Hs @ th) - 2 * gs  # noqa: E731
    A = np.zeros((K, 2 * K))
    A[np.arange(K), np.arange(K)] = -1.0
    A[np.arange(K), K + np.arange(K)] = -1.0
    cons = [{"type": "ineq", "fun": lambda th: 1.0 + A @ th, "jac": lambda th: A}]
    best = None
    for start in (np.r_[np.full(K, 0.5), np.full(K, 0.25)], np.r_[np.ones(K), np.zeros(K)]):
        r = minimize(fun, start, jac=jac, bounds=[(0, 1)] * (2 * K), constraints=cons, method="SLSQP",
                     options={"ftol": 1e-12, "maxiter": 500})
        if best is None or r.fun < best.fun:
            best = r
    th = np.clip(best.x, 0, 1)
    al, ga = th[:K], th[K:]
    over = al + ga > 1
    ga[over] = 1 - al[over]
    return al, ga


def rps_rows(T: np.ndarray, a_rows: np.ndarray, c_rows: np.ndarray) -> float:
    S11, S12, S22, R1, R2, YY = (T[:, k] for k in range(6))
    return float(np.sum(a_rows ** 2 * S11 + 2 * a_rows * c_rows * S12 + c_rows ** 2 * S22
                        - 2 * a_rows * R1 - 2 * c_rows * R2 + YY))


def row_weights(scheme: Scheme, al, ga):
    return scheme.B @ al, scheme.B @ ga


# --------------------------------------------------------------------------- CV ---------


@dataclass
class CVResult:
    rps: np.ndarray        # (N,) RPS of each held-out week
    clim: np.ndarray       # (N,) RPS of climatology for that week
    combo: np.ndarray      # (N,) setting combination chosen in each fold
    a_rows: np.ndarray     # (N, rows) weights used for each held-out week
    c_rows: np.ndarray

    @property
    def rpss_ratio(self) -> float:
        """1 - sum RPS / sum RPS_clim (the aggregation used by fit.py)."""
        return float(1 - self.rps.sum() / self.clim.sum())

    @property
    def rpss_weekly(self) -> np.ndarray:
        return 1 - self.rps / self.clim

    @property
    def rpss_leaderboard(self) -> float:
        """Mean of weekly RPSS: the period-aggregated leaderboard convention."""
        return float(self.rpss_weekly.mean())


def _fit_fold(Tc: np.ndarray, scheme: Scheme):
    """Tc (combos, rows, 6) summed over training weeks -> best combo and its weights."""
    best = None
    for k in range(Tc.shape[0]):
        al, ga = solve_scheme(Tc[k], scheme)
        a, c = row_weights(scheme, al, ga)
        clim = Tc[k, :, 5].sum()
        sc = 1 - rps_rows(Tc[k], a, c) / clim if clim > 0 else -np.inf
        if best is None or sc > best[0]:
            best = (sc, k, a, c)
    return best[1], best[2], best[3]


def cv_scores(terms: np.ndarray, mon_ord: np.ndarray, exclude_days: int, scheme: Scheme,
              classes: np.ndarray | None = None, min_class: int = 6, combos: list[int] | None = None,
              past_only: bool = False, min_train: int = 10) -> CVResult:
    """terms (L, S, P, N, rows, 6). Returns out-of-sample scores of every week.

    combos: restrict the setting search (default: all). past_only: train only on weeks
    whose target Monday is at least exclude_days before week i's (a forward, operational-
    style split); weeks with fewer than min_train training weeks are not scored (NaN).
    """
    nL, nS, nP, N, R, _ = terms.shape
    flat = terms.reshape(nL * nS * nP, N, R, 6)
    if combos is not None:
        flat = flat[combos]
    rps = np.full(N, np.nan)
    clim = np.array([flat[0, i, :, 5].sum() for i in range(N)])
    chosen = np.full(N, -1)
    A = np.full((N, R), np.nan)
    C = np.full((N, R), np.nan)
    for i in range(N):
        d = mon_ord - mon_ord[i]
        keep = (d <= -exclude_days) if past_only else (np.abs(d) >= exclude_days)
        if keep.sum() < (min_train if past_only else 1):
            continue
        k, a, c = _fit_fold(flat[:, keep].sum(axis=1), scheme)
        if classes is not None:
            same = keep & (classes == classes[i])
            if same.sum() >= min_class:
                al, ga = solve_scheme(flat[k, same].sum(axis=0), scheme)
                a, c = row_weights(scheme, al, ga)
        rps[i] = rps_rows(flat[k, i], a, c)
        chosen[i], A[i], C[i] = k, a, c
    return CVResult(rps, clim, chosen, A, C)


def cv_scores_band_settings(terms: np.ndarray, mon_ord: np.ndarray, exclude_days: int, B: np.ndarray,
                            past_only: bool = False, min_train: int = 10) -> CVResult:
    """Cross-validation in which every band (indicator basis B) chooses its own setting
    combination (lambda, spread, smoothing) as well as its own blend weights.

    SeasonBlend chooses one combination per variable and window for the whole globe; here the
    choice is made per band inside each fold. With a single band this is cv_scores with that
    band. Returns the combination chosen for the first band in `combo` and the row weights.
    """
    assert np.all((B == 0) | (B == 1)) and np.allclose(B.sum(1), 1), "B must be an indicator basis"
    nL, nS, nP, N, R, _ = terms.shape
    flat = terms.reshape(nL * nS * nP, N, R, 6)
    Tb = np.einsum("cnrt,rk->cnkt", flat, B)  # (combos, N, bands, 6)
    K = B.shape[1]
    rps = np.full(N, np.nan)
    clim = np.array([flat[0, i, :, 5].sum() for i in range(N)])
    chosen = np.full(N, -1)
    A = np.full((N, R), np.nan)
    C = np.full((N, R), np.nan)
    for i in range(N):
        d = mon_ord - mon_ord[i]
        keep = (d <= -exclude_days) if past_only else (np.abs(d) >= exclude_days)
        if keep.sum() < (min_train if past_only else 1):
            continue
        tr = Tb[:, keep].sum(axis=1)  # (combos, bands, 6)
        total = 0.0
        a_b, c_b = np.zeros(K), np.zeros(K)
        for k in range(K):
            best = None
            for c in range(tr.shape[0]):
                a, g = calib.solve_blend(tr[c, k])
                S11, S12, S22, R1, R2, YY = tr[c, k]
                sc = a * a * S11 + 2 * a * g * S12 + g * g * S22 - 2 * a * R1 - 2 * g * R2  # YY is the same for every c
                if best is None or sc < best[0]:
                    best = (sc, c, a, g)
            _, c, a_b[k], c_b[k] = best
            S11, S12, S22, R1, R2, YY = Tb[c, i, k]
            total += a_b[k] ** 2 * S11 + 2 * a_b[k] * c_b[k] * S12 + c_b[k] ** 2 * S22 - 2 * a_b[k] * R1 - 2 * c_b[k] * R2 + YY
            if k == 0:
                chosen[i] = c
        rps[i] = total
        A[i], C[i] = B @ a_b, B @ c_b
    return CVResult(rps, clim, chosen, A, C)


def in_sample(terms: np.ndarray, scheme: Scheme, combo: int):
    """Weights fitted on all weeks for one setting combination, and the RPSS (ratio form)."""
    nL, nS, nP, N, R, _ = terms.shape
    flat = terms.reshape(nL * nS * nP, N, R, 6)[combo]
    al, ga = solve_scheme(flat.sum(axis=0), scheme)
    a, c = row_weights(scheme, al, ga)
    tot = flat.sum(axis=0)
    return al, ga, a, c, float(1 - rps_rows(tot, a, c) / tot[:, 5].sum())


# --------------------------------------------------------------------------- bootstrap --


def block_bootstrap_delta(rps_a: np.ndarray, rps_b: np.ndarray, clim: np.ndarray, block: int,
                          n_boot: int = 4000, seed: int = 0, convention: str = "leaderboard") -> dict:
    """Paired moving-block bootstrap of the score difference B - A over weeks (axis -1).

    Arrays may be (pairs, N) to average several variable/window pairs on the same dates
    (NaN where a pair has no score). convention 'leaderboard' = mean of weekly RPSS;
    'ratio' = 1 - sum RPS / sum RPS_clim.
    """
    from .stats import block_resample

    ra, rb, cl = (np.atleast_2d(x) for x in (rps_a, rps_b, clim))
    N = ra.shape[1]
    rng = np.random.default_rng(seed)

    def score(r, counts):
        if convention == "ratio":
            num = np.nansum(r * counts, axis=1)
            den = np.nansum(np.where(np.isfinite(r), cl, np.nan) * counts, axis=1)
            return (1 - num / den).mean()
        w = (1 - r / cl)
        ok = np.isfinite(w)
        return (np.nansum(w * counts, axis=1) / np.sum(ok * counts, axis=1)).mean()

    ones = np.ones(N)
    est = score(rb, ones) - score(ra, ones)
    samples = np.empty(n_boot)
    for b in range(n_boot):
        counts = np.bincount(block_resample(N, block, rng), minlength=N).astype(float)
        samples[b] = score(rb, counts) - score(ra, counts)
    lo, hi = np.percentile(samples, [5, 95])
    return {"est": float(est), "lo90": float(lo), "hi90": float(hi), "p_better": float((samples > 0).mean()),
            "block": block}
