# R0 findings: how good is SeasonBlend really, and what state is the climate in?

18 November 2026. The groundwork for research step R0 in [docs/research-plan.md](../../docs/research-plan.md).

## 1. The experiment harness reproduces SeasonBlend exactly

`python run.py --experiment control fit` refits SeasonBlend's settings into separate files
(`data/params_control.json`, `outputs/experiments/control/`). On the 42 verified ECMWF runs
(1 January to 15 October 2026) the chosen settings, weights and scores are identical to the
operational fit for all six variable and window pairs. Every later idea is compared with `control`.

## 2. SeasonBlend's skill is real, not a product of fitting

The original backtest left each week out of the bias correction and prior, but chose the
settings and blend weights with all weeks. The new **fully cross-validated** score also refits
those without the scored week (and its neighbours within 21 days).

The intervals come from a paired moving-block bootstrap: 4000 samples, in blocks of 4
consecutive weeks.

| Variable | Window | In-sample RPSS | Cross-validated RPSS | 90% interval | Raw ECMWF |
|---|---|---|---|---|---|
| tas | days 19-25 | +0.115 | +0.111 | +0.068 to +0.154 | -0.162 |
| tas | days 26-32 | +0.096 | +0.091 | +0.047 to +0.134 | -0.189 |
| mslp | days 19-25 | +0.196 | +0.186 | +0.115 to +0.254 | +0.083 |
| mslp | days 26-32 | +0.154 | +0.145 | +0.069 to +0.217 | +0.050 |
| pr | days 19-25 | +0.083 | +0.082 | +0.068 to +0.096 | +0.031 |
| pr | days 26-32 | +0.073 | +0.071 | +0.057 to +0.085 | +0.017 |
| **Mean** | | **+0.120** | **+0.114** | **+0.073 to +0.155** | **-0.028** |

- Fitting the settings and weights in-sample adds only about 0.005 RPSS. The method is not
  overfitted.
- SeasonBlend beats climatology for every pair, with the whole 90% interval above zero.
- It beats the raw ECMWF ensemble by **+0.143** (90% interval +0.133 to +0.153), and in
  every bootstrap sample.
- The raw ensemble is worse than climatology for temperature, because it misses the warm shift
  of recent years relative to the 20-year climatology. Correcting that shift is the largest
  single gain.

Caveat: these are global scores on 42 runs from one year, and the intervals reflect sampling
of those weeks only.

## 3. The climate state: an exceptional El Niño, and an active MJO

`python run.py indices` saves the index values known at each initialisation
(`data/indices/state_at_init.csv`). Each value is taken only after its publication lag.

| Index | January 2026 | Now (19 November 2026 initialisation) |
|---|---|---|
| Niño 3.4 SST anomaly (NOAA CPC, weekly) | -0.7 K (weak La Niña) | **+3.2 K** (very strong El Niño) |
| Indian Ocean Dipole (BoM, weekly) | +0.1 K | **+0.8 K** (positive IOD) |
| MJO (BoM RMM) | phase 5, amplitude 0.95 | phase 3, amplitude 1.8 (active) |

Of the 47 initialisations from January to November 2026, the MJO was active (amplitude ≥ 1) at
34 and El Niño conditions held at 31.

## 4. Why this matters for the next step (R1)

SeasonBlend's prior is the seasonally weighted frequency of recent ERA5 weeks. For a December
to February target it leans mostly on the last two northern winters, 2024/25 and 2025/26, which
were La Niña-like. This winter has a very strong El Niño with a positive IOD, whose patterns are
often opposite. In East Africa, for example, a positive IOD and El Niño usually bring a wet
end to the short rains, and southern Africa tends to be dry in DJF.

So the prior may currently carry the wrong teleconnection signal into the tropics, where its
weight is about 0.3 to 0.4 for tas and pr. R1 will test, in the backtest:

1. **An ENSO-aware prior:** past weeks weighted by similarity of Niño 3.4 (and the IOD) as
   well as by season.
2. **MJO-dependent blend weights:** more weight on ECMWF when the MJO is active at
   initialisation.

Both are judged with the cross-validated score and the paired bootstrap against `control`.
