# Backtest of SeasonBlend (leave-one-out), fitted 2026-11-28T05:16:15+00:00

Period-aggregated RPSS against the 20-year ERA5 climatology (0 = climatology). "Fully cross-validated" also fits the settings and blend weights without the scored week; it is the fair number for comparing methods.

**Window 1 (days 19-25)**

| Forecast | tas | mslp | pr | Variable-averaged |
|---|---|---|---|---|
| Raw ECMWF ensemble | -0.157 | +0.090 | +0.033 | -0.011 |
| Bias-corrected ensemble | +0.019 | +0.200 | +0.060 | +0.093 |
| Calibrated ensemble (no blend) | +0.093 | +0.207 | +0.074 | +0.124 |
| Observed-frequency prior only | +0.039 | -0.030 | +0.020 | +0.010 |
| SeasonBlend (final) | +0.118 | +0.208 | +0.083 | +0.136 |
| SeasonBlend, fully cross-validated | +0.114 | +0.201 | +0.082 | +0.132 |

**Window 2 (days 26-32)**

| Forecast | tas | mslp | pr | Variable-averaged |
|---|---|---|---|---|
| Raw ECMWF ensemble | -0.183 | +0.059 | +0.019 | -0.035 |
| Bias-corrected ensemble | -0.011 | +0.153 | +0.046 | +0.063 |
| Calibrated ensemble (no blend) | +0.065 | +0.161 | +0.061 | +0.096 |
| Observed-frequency prior only | +0.042 | -0.029 | +0.021 | +0.011 |
| SeasonBlend (final) | +0.100 | +0.166 | +0.073 | +0.113 |
| SeasonBlend, fully cross-validated | +0.095 | +0.152 | +0.071 | +0.106 |

**Settings**

| Variable | Window | Runs | lambda | spread | smoothing | a (N, Tropics, S) | c (N, Tropics, S) |
|---|---|---|---|---|---|---|---|
| tas | 1 | 44 (2026-01-01 to 2026-10-29) | 1.0 | 1.0 | 1.0 | 0.48, 0.67, 0.70 | 0.38, 0.33, 0.00 |
| tas | 2 | 43 (2026-01-01 to 2026-10-22) | 1.0 | 1.0 | 1.0 | 0.37, 0.59, 0.60 | 0.48, 0.39, 0.02 |
| mslp | 1 | 44 (2026-01-01 to 2026-10-29) | 1.0 | 1.0 | 2.0 | 0.85, 1.00, 0.87 | 0.00, 0.00, 0.00 |
| mslp | 2 | 43 (2026-01-01 to 2026-10-22) | 0.75 | 1.0 | 1.0 | 0.71, 0.87, 0.76 | 0.00, 0.13, 0.00 |
| pr | 1 | 44 (2026-01-01 to 2026-10-29) | 1.0 | 1.0 | 0.0 | 0.57, 0.63, 0.72 | 0.17, 0.37, 0.09 |
| pr | 2 | 43 (2026-01-01 to 2026-10-22) | 1.0 | 1.0 | 0.0 | 0.50, 0.59, 0.66 | 0.23, 0.41, 0.07 |
