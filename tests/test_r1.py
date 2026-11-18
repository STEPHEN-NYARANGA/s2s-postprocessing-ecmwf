"""Unit tests of the R1 analysis code (aiwq/r1.py).  Run:  python tests/test_r1.py

Synthetic probability fields are only used to check the algebra and the solver; no result in
results/ comes from synthetic data.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from aiwq import calib, r1  # noqa: E402
from aiwq.fit import cross_validated_rps  # noqa: E402
from aiwq.grid import LAT, area_weights  # noqa: E402

PASSED = []


def check(name, cond, detail=""):
    if not cond:
        raise AssertionError(f"FAILED: {name} {detail}")
    PASSED.append(name)
    print(f"  ok  {name} {detail}")


def synthetic_terms(n_combo=3, N=14, seed=0):
    """Row-level terms from random but valid probability fields on a coarse longitude grid."""
    rng = np.random.default_rng(seed)
    nx = 24
    W = area_weights()[:, :nx]
    rows = np.arange(LAT.size)
    T = np.zeros((n_combo, 1, 1, N, LAT.size, 6))
    for i in range(N):
        signal = rng.normal(size=(LAT.size, nx))
        cat = np.clip(np.round(signal + rng.normal(scale=0.8, size=signal.shape) + 2), 0, 4).astype(int)
        oh = np.zeros((5, LAT.size, nx))
        np.put_along_axis(oh, cat[None], 1.0, axis=0)
        prior = rng.dirichlet(np.ones(5) * 8, size=(LAT.size, nx)).transpose(2, 0, 1)
        for k in range(n_combo):
            logits = -0.5 * (np.arange(5)[:, None, None] - (signal + 2)[None]) ** 2 * (0.3 + 0.3 * k)
            p = np.exp(logits)
            p /= p.sum(axis=0, keepdims=True)
            T[k, 0, 0, i] = calib.rps_terms(p, prior, oh, W, rows, LAT.size)
    return T


def test_band_scheme_matches_operational():
    print("\n[r1-1] three-band scheme reproduces SeasonBlend's algebra")
    T = synthetic_terms()
    bands = r1.Scheme("bands", r1.band_basis())
    mon = np.arange(T.shape[3]) * 7
    res = r1.cv_scores(T, mon, 21, bands)
    # the same terms summed into bands, scored by the operational cross-validation
    Tb = np.einsum("lspnrt,rk->lspnkt", T, bands.B)
    op = np.array(cross_validated_rps(Tb, mon, 21))
    check("cross-validated RPS identical to fit.cross_validated_rps", np.allclose(res.rps, op, rtol=1e-12, atol=1e-12),
          f"(max diff {np.max(np.abs(res.rps - op)):.2e})")
    check("leaderboard convention is the mean of weekly RPSS",
          abs(res.rpss_leaderboard - np.mean(1 - res.rps / res.clim)) < 1e-15)


def test_smooth_solver():
    print("\n[r1-2] continuous latitude weights")
    T = synthetic_terms(n_combo=1, N=10, seed=3)[0, 0, 0].sum(axis=0)
    B = r1.gaussian_basis()
    check("Gaussian basis is a partition of unity", np.allclose(B.sum(1), 1) and (B >= 0).all())
    sch = r1.Scheme("smooth", B)
    al, ga = r1.solve_scheme(T, sch)
    a, c = r1.row_weights(sch, al, ga)
    check("weights feasible at every latitude", (a >= -1e-12).all() and (c >= -1e-12).all() and (a + c <= 1 + 1e-9).all())
    best = r1.rps_rows(T, a, c)
    rng = np.random.default_rng(1)
    worse = 0
    for _ in range(300):
        x = rng.dirichlet(np.ones(3), size=B.shape[1])  # random feasible node weights
        aa, cc = r1.row_weights(sch, x[:, 0], x[:, 1])
        worse += r1.rps_rows(T, aa, cc) >= best - 1e-9 * abs(best)
    check("solver optimum beats 300 random feasible weightings", worse == 300)
    # a one-node 'smooth' basis must give the same optimum as the exact band solver
    one = r1.Scheme("one", np.ones((LAT.size, 1)) * 0.999999 + 1e-6)
    al1, ga1 = r1.solve_scheme(T, one)
    ref = calib.solve_blend(T.sum(axis=0))
    check("QP solver agrees with the exact solver on a single region", abs(al1[0] - ref[0]) < 1e-4 and abs(ga1[0] - ref[1]) < 1e-4,
          f"(QP {al1[0]:.5f},{ga1[0]:.5f} vs exact {ref[0]:.5f},{ref[1]:.5f})")


def test_folds_and_bootstrap():
    print("\n[r1-3] folds and bootstrap")
    T = synthetic_terms(n_combo=2, N=16, seed=5)
    mon = np.arange(16) * 7
    sch = r1.Scheme("bands", r1.band_basis())
    fwd = r1.cv_scores(T, mon, 21, sch, past_only=True, min_train=5)
    first = np.where(np.isfinite(fwd.rps))[0][0]
    check("forward split scores only weeks with enough past training weeks", first == 7,
          f"(first scored week {first})")
    classes = (np.arange(16) % 2).astype(int)
    cls = r1.cv_scores(T, mon, 21, sch, classes=classes, min_class=3)
    check("class-conditioned weights produce finite scores", np.isfinite(cls.rps).all())
    res = r1.cv_scores(T, mon, 21, sch)
    d = r1.block_bootstrap_delta(res.rps, res.rps, res.clim, block=4, n_boot=200)
    check("bootstrap of identical forecasts gives zero difference", d["est"] == 0 and d["lo90"] == 0 and d["hi90"] == 0)
    d2 = r1.block_bootstrap_delta(res.rps, res.rps * 0.99, res.clim, block=4, n_boot=200)
    check("a uniformly better forecast is better in every bootstrap sample", d2["p_better"] == 1.0 and d2["lo90"] > 0)


def test_band_settings():
    print("\n[r1-4] per-band choice of settings")
    T = synthetic_terms(n_combo=3, N=14, seed=7)
    mon = np.arange(14) * 7
    one = np.ones((LAT.size, 1))
    a = r1.cv_scores(T, mon, 21, r1.Scheme("one", one))
    b = r1.cv_scores_band_settings(T, mon, 21, one)
    check("with one band it equals the pooled cross-validation", np.allclose(a.rps, b.rps, rtol=1e-10) and (a.combo == b.combo).all())
    B3 = r1.band_basis()
    single = r1.cv_scores(T, mon, 21, r1.Scheme("bands", B3), combos=[1])
    per = r1.cv_scores_band_settings(T[[1]] if T.shape[0] > 1 else T, mon, 21, B3)
    check("with one setting combination it equals the band scheme", np.allclose(single.rps, per.rps, rtol=1e-10))


if __name__ == "__main__":
    test_band_scheme_matches_operational()
    test_smooth_solver()
    test_folds_and_bootstrap()
    test_band_settings()
    print(f"\nALL {len(PASSED)} R1 CHECKS PASSED")
