# Cross-check of the 12 November 2026 forecast (NyarangaS2S / SeasonBlend)

Generated 2026-11-18 09:14 UTC by `python run.py crosscheck`.

## Dates

| Result | Check |
|---|---|
| PASS | initialisation Thu 12 Nov 2026 is a Thursday |
| PASS | window 1: Mon 30 Nov to Sun 06 Dec = days 19-25 |
| PASS | window 2: Mon 07 Dec to Sun 13 Dec = days 26-32 |

## Files

| Result | Check |
|---|---|
| PASS | `tas_20261112_p1_NyarangaS2S_SeasonBlend.nc`: 5 x 121 x 240, 90N->90S, 0->358.5E, sums to 1 (range 1.000000-1.000000), no NaN, identical to the saved forecast, AI-WQ-package checks pass |
| PASS | `tas_20261112_p2_NyarangaS2S_SeasonBlend.nc`: 5 x 121 x 240, 90N->90S, 0->358.5E, sums to 1 (range 1.000000-1.000000), no NaN, identical to the saved forecast, AI-WQ-package checks pass |
| PASS | `mslp_20261112_p1_NyarangaS2S_SeasonBlend.nc`: 5 x 121 x 240, 90N->90S, 0->358.5E, sums to 1 (range 1.000000-1.000000), no NaN, identical to the saved forecast, AI-WQ-package checks pass |
| PASS | `mslp_20261112_p2_NyarangaS2S_SeasonBlend.nc`: 5 x 121 x 240, 90N->90S, 0->358.5E, sums to 1 (range 1.000000-1.000000), no NaN, identical to the saved forecast, AI-WQ-package checks pass |
| PASS | `pr_20261112_p1_NyarangaS2S_SeasonBlend.nc`: 5 x 121 x 240, 90N->90S, 0->358.5E, sums to 1 (range 1.000000-1.000000), no NaN, identical to the saved forecast, AI-WQ-package checks pass |
| PASS | `pr_20261112_p2_NyarangaS2S_SeasonBlend.nc`: 5 x 121 x 240, 90N->90S, 0->358.5E, sums to 1 (range 1.000000-1.000000), no NaN, identical to the saved forecast, AI-WQ-package checks pass |

## Does the forecast make sense?

Raw = the 101 ECMWF members counted in the official ERA5 quintiles with no correction. Tilt = expected quintile minus the middle one (-2 to +2); correlations are area-weighted (tas and pr over land, as on the leaderboard).

| Variable | Window | ENS mean - ERA5 median | Raw tilt vs final tilt (corr.) | Mean P(lowest) raw / final | Mean P(highest) raw / final | Final vs last observed week (corr.) |
|---|---|---|---|---|---|---|
| 2 m temperature | 1 | +0.44 K (inner quintile range 4.74) | +0.55 | 0.20 / 0.14 | 0.27 / 0.34 | +0.44 |
| 2 m temperature | 2 | +0.46 K (inner quintile range 4.74) | +0.57 | 0.21 / 0.14 | 0.29 / 0.35 | +0.44 |
| Mean sea level pressure | 1 | +0.08 hPa (inner quintile range 6.83) | +0.85 | 0.25 / 0.21 | 0.32 / 0.35 | +0.64 |
| Mean sea level pressure | 2 | +0.14 hPa (inner quintile range 6.88) | +0.90 | 0.25 / 0.22 | 0.32 / 0.33 | +0.63 |
| Precipitation | 1 | +3.77 mm/week (inner quintile range 15.71) | +0.69 | 0.16 / 0.19 | 0.30 / 0.22 | +0.23 |
| Precipitation | 2 | +3.53 mm/week (inner quintile range 15.72) | +0.64 | 0.17 / 0.19 | 0.30 / 0.22 | +0.28 |

Expected: ENS-minus-ERA5 differences small next to the inner quintile range (right units and grid); positive raw-vs-final correlation (calibration corrects and tempers the raw signal but does not reverse it); final mean P(lowest) and P(highest) close to how often recent observed weeks fell in those quintiles (table below); positive persistence correlations.

### How often recent observed weeks fell in the outer quintiles

Area-weighted share of the last 26 published ERA5 weeks (tas and pr over land). A 20-year climatology gives 0.20 each; the blend's prior uses these frequencies, which is why the final forecast can lean further than the raw ensemble (e.g. warmer, for the warming trend).

| Variable | Weeks | Observed P(lowest) | Observed P(highest) |
|---|---|---|---|
| 2 m temperature | 11 May 2026 to 02 Nov 2026 | 0.12 | 0.33 |
| Mean sea level pressure | 11 May 2026 to 02 Nov 2026 | 0.22 | 0.30 |
| Precipitation | 11 May 2026 to 02 Nov 2026 | 0.21 | 0.24 |

**Overall: all checks passed**
