# SeasonBlend results

Forecasts of team **NyarangaS2S**, model **SeasonBlend**, in the [ECMWF AI Weather Quest](https://aiweatherquest.ecmwf.int/). Each week the Thursday 00 UTC ECMWF IFS ensemble (101 members) is bias-corrected against ERA5, counted in the official 20-year ERA5 quintiles and blended with the recent observed quintile frequencies; the weights are fitted by leave-one-out on all verified 2026 forecasts (see the [main README](../README.md#method)). This folder is updated by `python run.py results`.

## Backtest (leave-one-out RPSS; 0 = 20-year climatology, higher is better)

| Variable | Window | Training runs | Raw ECMWF | SeasonBlend |
|---|---|---|---|---|
| tas | days 19-25 | 42 | -0.162 | **+0.115** |
| mslp | days 19-25 | 42 | +0.083 | **+0.196** |
| pr | days 19-25 | 42 | +0.031 | **+0.083** |
| tas | days 26-32 | 41 | -0.190 | **+0.096** |
| mslp | days 26-32 | 41 | +0.050 | **+0.154** |
| pr | days 26-32 | 41 | +0.017 | **+0.072** |

Full report: [backtest/backtest_report.md](backtest/backtest_report.md); weekly scores: [backtest/backtest_weekly_rpss.png](backtest/backtest_weekly_rpss.png).

## Weekly forecasts

| Initialisation | Days 19-25 | Days 26-32 | Status | Cross-check | Maps | Files |
|---|---|---|---|---|---|---|
| Thu 12 Nov 2026 | 30 Nov-06 Dec | 07 Dec-13 Dec | emailed to ECMWF (J. Talib) on 18 Nov 2026, late submission agreed by ECMWF | [passed](20261112/crosscheck.md) | [map](20261112/quicklook_20261112.png) | [6 NetCDF](20261112/submission/) |

Each file holds the probabilities of the five ERA5 quintiles (dimensions quintile x latitude x longitude, 1.5 degree grid) for one variable and window, named `{var}_{YYYYMMDD}_p{window}_{team}_{model}.nc`.
