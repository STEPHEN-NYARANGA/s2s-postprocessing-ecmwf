# Backtest (leave-one-out), fitted 2026-11-16T10:04:10+00:00

Period-aggregated RPSS against the 20-year ERA5 climatology (0 = climatology).

**Window 1 (days 19-25)**

| Forecast | tas | mslp | pr | Variable-averaged |
|---|---|---|---|---|
| Raw ECMWF ensemble | -0.162 | +0.083 | +0.031 | -0.016 |
| Bias-corrected ensemble | +0.014 | +0.188 | +0.060 | +0.087 |
| Calibrated ensemble (no blend) | +0.088 | +0.195 | +0.074 | +0.119 |
| Observed-frequency prior only | +0.033 | -0.036 | +0.019 | +0.006 |
| SeasonBlend (final) | +0.115 | +0.196 | +0.083 | +0.131 |

**Window 2 (days 26-32)**

| Forecast | tas | mslp | pr | Variable-averaged |
|---|---|---|---|---|
| Raw ECMWF ensemble | -0.189 | +0.050 | +0.017 | -0.041 |
| Bias-corrected ensemble | -0.016 | +0.138 | +0.045 | +0.055 |
| Calibrated ensemble (no blend) | +0.060 | +0.149 | +0.060 | +0.090 |
| Observed-frequency prior only | +0.036 | -0.035 | +0.020 | +0.007 |
| SeasonBlend (final) | +0.096 | +0.154 | +0.073 | +0.108 |

**Settings**

| Variable | Window | Runs | lambda | spread | smoothing | a (N, Tropics, S) | c (N, Tropics, S) |
|---|---|---|---|---|---|---|---|
| tas | 1 | 42 (2026-01-01 to 2026-10-15) | 1.0 | 1.0 | 1.0 | 0.46, 0.68, 0.70 | 0.37, 0.32, 0.00 |
| tas | 2 | 41 (2026-01-01 to 2026-10-08) | 1.0 | 1.0 | 1.0 | 0.34, 0.60, 0.60 | 0.47, 0.37, 0.00 |
| mslp | 1 | 42 (2026-01-01 to 2026-10-15) | 1.0 | 1.0 | 2.0 | 0.85, 0.98, 0.85 | 0.00, 0.02, 0.00 |
| mslp | 2 | 41 (2026-01-01 to 2026-10-08) | 0.75 | 1.0 | 1.0 | 0.69, 0.86, 0.74 | 0.00, 0.13, 0.00 |
| pr | 1 | 42 (2026-01-01 to 2026-10-15) | 1.0 | 1.0 | 0.0 | 0.56, 0.63, 0.70 | 0.16, 0.37, 0.06 |
| pr | 2 | 41 (2026-01-01 to 2026-10-08) | 1.0 | 1.0 | 0.0 | 0.49, 0.59, 0.65 | 0.23, 0.41, 0.05 |
