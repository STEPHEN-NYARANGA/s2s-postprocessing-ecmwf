# SeasonBlend results

Forecasts of team **UtabiriBora**, model **SeasonBlend**, in the [ECMWF AI Weather Quest](https://aiweatherquest.ecmwf.int/). Each week the Thursday 00 UTC ECMWF IFS ensemble (101 members) is bias-corrected against ERA5, counted in the official 20-year ERA5 quintiles and blended with the recent observed quintile frequencies; the weights are fitted by leave-one-out on all verified 2026 forecasts (see the [main README](../README.md#method)). This folder is updated by `python run.py results`.

## Backtest (leave-one-out RPSS; 0 = 20-year climatology, higher is better)

"Cross-validated" also chooses the settings and blend weights without the scored week, so it is the honest estimate of future skill.

| Variable | Window | Training runs | Raw ECMWF | SeasonBlend | SeasonBlend, cross-validated |
|---|---|---|---|---|---|
| tas | days 19-25 | 43 | -0.160 | **+0.115** | +0.111 |
| mslp | days 19-25 | 43 | +0.086 | **+0.202** | +0.194 |
| pr | days 19-25 | 43 | +0.032 | **+0.083** | +0.082 |
| tas | days 26-32 | 42 | -0.186 | **+0.097** | +0.092 |
| mslp | days 26-32 | 42 | +0.053 | **+0.160** | +0.146 |
| pr | days 26-32 | 42 | +0.018 | **+0.072** | +0.071 |

Full report: [backtest/backtest_report.md](backtest/backtest_report.md); weekly scores: [backtest/backtest_weekly_rpss.png](backtest/backtest_weekly_rpss.png).

## Research experiments

Candidate methods compared with SeasonBlend by `python run.py compare` (paired block bootstrap; plan in [docs/research-plan.md](../docs/research-plan.md)):

- [R0 findings](experiments/R0_findings.md)

## Weekly forecasts

| Initialisation | Days 19-25 | Days 26-32 | Status | Cross-check | Maps | Files |
|---|---|---|---|---|---|---|
| Thu 19 Nov 2026 | 07 Dec-13 Dec | 14 Dec-20 Dec | uploaded to ECBox (6/6 files) | [passed](20261119/crosscheck.md) | [map](20261119/quicklook_20261119.png) | [6 NetCDF](20261119/submission/) |
| Thu 12 Nov 2026 | 30 Nov-06 Dec | 07 Dec-13 Dec | emailed to ECMWF (J. Talib) on 18 Nov 2026, late submission agreed by ECMWF | [passed](20261112/crosscheck.md) | [map](20261112/quicklook_20261112.png) | [6 NetCDF](20261112/submission/) |

Each file holds the probabilities of the five ERA5 quintiles (dimensions quintile x latitude x longitude, 1.5 degree grid) for one variable and window, named `{var}_{YYYYMMDD}_p{window}_{team}_{model}.nc`.
