# Backtest of SeasonBlend (leave-one-out), fitted 2026-11-21T04:54:53+00:00

Period-aggregated RPSS against the 20-year ERA5 climatology (0 = climatology). "Fully cross-validated" also fits the settings and blend weights without the scored week; it is the fair number for comparing methods.

**Window 1 (days 19-25)**

| Forecast | tas | mslp | pr | Variable-averaged |
|---|---|---|---|---|
| Raw ECMWF ensemble | -0.160 | +0.085 | +0.032 | -0.014 |
| Bias-corrected ensemble | +0.014 | +0.194 | +0.060 | +0.089 |
| Calibrated ensemble (no blend) | +0.088 | +0.200 | +0.074 | +0.121 |
| Observed-frequency prior only | +0.036 | -0.032 | +0.020 | +0.008 |
| SeasonBlend (final) | +0.115 | +0.202 | +0.083 | +0.133 |
| SeasonBlend, fully cross-validated | +0.111 | +0.194 | +0.082 | +0.129 |

**Window 2 (days 26-32)**

| Forecast | tas | mslp | pr | Variable-averaged |
|---|---|---|---|---|
| Raw ECMWF ensemble | -0.186 | +0.053 | +0.018 | -0.038 |
| Bias-corrected ensemble | -0.015 | +0.145 | +0.045 | +0.058 |
| Calibrated ensemble (no blend) | +0.061 | +0.155 | +0.060 | +0.092 |
| Observed-frequency prior only | +0.039 | -0.031 | +0.021 | +0.009 |
| SeasonBlend (final) | +0.097 | +0.160 | +0.072 | +0.110 |
| SeasonBlend, fully cross-validated | +0.092 | +0.146 | +0.071 | +0.103 |

**Settings**

| Variable | Window | Runs | lambda | spread | smoothing | a (N, Tropics, S) | c (N, Tropics, S) |
|---|---|---|---|---|---|---|---|
| tas | 1 | 43 (2026-01-01 to 2026-10-22) | 1.0 | 1.0 | 1.0 | 0.46, 0.68, 0.68 | 0.38, 0.32, 0.00 |
| tas | 2 | 42 (2026-01-01 to 2026-10-15) | 1.0 | 1.0 | 1.0 | 0.35, 0.60, 0.57 | 0.48, 0.38, 0.00 |
| mslp | 1 | 43 (2026-01-01 to 2026-10-22) | 1.0 | 1.0 | 2.0 | 0.85, 0.99, 0.86 | 0.00, 0.01, 0.00 |
| mslp | 2 | 42 (2026-01-01 to 2026-10-15) | 0.75 | 1.0 | 1.0 | 0.70, 0.87, 0.75 | 0.00, 0.13, 0.00 |
| pr | 1 | 43 (2026-01-01 to 2026-10-22) | 1.0 | 1.0 | 0.0 | 0.56, 0.63, 0.71 | 0.19, 0.37, 0.07 |
| pr | 2 | 42 (2026-01-01 to 2026-10-15) | 1.0 | 1.0 | 0.0 | 0.49, 0.59, 0.65 | 0.25, 0.41, 0.06 |
