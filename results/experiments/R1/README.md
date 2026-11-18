# R1: does a more flexible calibration beat SeasonBlend?

Branch `research/r1`, 18 November 2026. Research only: the operational SeasonBlend model, its
parameters, its submission pipeline and its forecast files are unchanged.

- **Notebook (executed, all outputs stored):**
  [notebooks/R1_calibration_experiments.ipynb](../../../notebooks/R1_calibration_experiments.ipynb)
- **Audit, rules, reforecast availability and literature review (with DOIs):**
  [docs/r1-audit.md](../../../docs/r1-audit.md)

## Short answer

**No.** SeasonBlend's three-band blend is already the best form that one year of ECMWF runs
can support. Every extra degree of freedom lost skill out of sample:
- continuous latitude weights;
- more bands;
- MJO-conditioned weights;
- per-band settings;
- a standard quantile mapping.

What limits the skill is the **estimation noise** of the calibration parameters, not their
form. The next step must therefore add *information* (more years), not *parameters*.

## Data and method

| | |
|---|---|
| Forecasts | ECMWF ENS, 101 members (dynamical.org), 42 Thursday runs from 1 Jan to 15 Oct 2026, days 19-25 and 26-32 |
| Verification | ERA5 weekly means and the official 20-year quintile boundaries (ECBox), leaderboard land and arid masks |
| Scoring | RPSS against climatology (0.2 per quintile), area weighted; leaderboard convention = mean of weekly RPSS |
| Validation | Leave-one-out with ±21 days excluded, refitting **everything** (settings and weights) in every fold; plus a forward, past-only split |
| Uncertainty | Paired moving-block bootstrap over weeks (whole global fields, so spatial dependence is kept), blocks of 1, 2, 4 and 8 weeks, 4000 samples |
| Leakage control | Climate indices (RMM, Niño 3.4, IOD) taken only with timestamps at or before each initialisation, using conservative publication lags (`data/indices/state_at_init.csv`) |

To compare many weighting schemes exactly, `aiwq/research.py` stores the six sufficient
statistics of the RPS for every setting, week and latitude row (121 rows). The RPS is
quadratic in the blend weights, so any scheme is a small quadratic program
(`aiwq/r1.py`, tested in `tests/test_r1.py`).

## Results

### SeasonBlend and the benchmarks (cross-validated)

| Variable / window | Raw ECMWF | Quantile mapping (xsdba) | **SeasonBlend** |
|---|---|---|---|
| tas, days 19-25 | -0.166 | +0.038 | **+0.108** |
| tas, days 26-32 | -0.193 | +0.005 | **+0.088** |
| mslp, days 19-25 | +0.077 | +0.170 | **+0.181** |
| mslp, days 26-32 | +0.045 | +0.126 | **+0.140** |
| pr, days 19-25 | +0.031 | +0.031 | **+0.082** |
| pr, days 26-32 | +0.017 | +0.016 | **+0.071** |
| **Mean** | -0.032 | +0.064 | **+0.112** |

- **Quantile mapping minus SeasonBlend:** -0.047, 90% interval [-0.059, -0.035].
- Quantile mapping degrades with less training data:

  | Training weeks | QM mean RPSS |
  |---|---|
  | all | +0.064 |
  | 20 | +0.039 |
  | 10 | -0.006 |

  It needs multi-year training data to be competitive (`R1_quantile_mapping.csv`).

**Reliability**, outer quintiles, both windows pooled. The reliability component, ×10⁻³
(lower is better):

| | Raw ECMWF | Quantile mapping | **SeasonBlend** |
|---|---|---|---|
| Reliability component (×10⁻³) | 21.4 | 7.5 | **0.57** |

Raw and quantile-mapped forecasts are strongly over-confident, while SeasonBlend is close to
the diagonal (fig3). One systematic error remains: **the lowest temperature quintile is
over-forecast**. In the warm, El Niño year 2026, cold weeks happened less often than
forecast.

### Regions, including Africa (ratio RPSS within region, mean over the six pairs)

| Region | Raw ECMWF | Quantile mapping | **SeasonBlend** | R1-B |
|---|---|---|---|---|
| Global | -0.028 | +0.068 | **+0.115** | +0.114 |
| Tropics 30°S-30°N | -0.060 | +0.145 | **+0.188** | +0.187 |
| N extratropics | -0.016 | -0.015 | **+0.045** | +0.044 |
| S extratropics | +0.032 | +0.020 | **+0.047** | +0.045 |
| **Africa** | -0.079 | +0.096 | **+0.152** | +0.151 |
| Equatorial East Africa | -0.134 | +0.088 | **+0.132** | +0.131 |
| Southern Africa | +0.011 | +0.022 | **+0.078** | +0.077 |

Over Africa SeasonBlend beats quantile mapping by 0.056 [0.036, 0.076]. In equatorial East
Africa (a small region) the interval for quantile mapping includes zero. Equatorial East
African rainfall is the weakest African score (SeasonBlend +0.029 and +0.025 for the two windows), which is where better
information on the ocean state (IOD, ENSO) should matter most.

### The R1 variants (difference from SeasonBlend, mean of the six pairs)

| Variant | Difference [90% interval, 4-week blocks] | Verdict |
|---|---|---|
| R1-B continuous latitude weights, 7 Gaussian nodes (primary) | -0.0009 [-0.0016, -0.0003] | **worse** at every block length (P(better) ≤ 0.006); forward split -0.0003 |
| 6 bands of 30° | -0.0009 [-0.0014, -0.0003] | worse |
| Smooth, 13 nodes | -0.0012 [-0.0022, -0.0004] | worse |
| R1-D MJO active/inactive weights | -0.0011 [-0.0027, +0.0002] | no gain |
| R1-E (post-hoc) own settings per band, 3 bands | +0.0001 [-0.0006, +0.0009] | no gain |
| R1-E (post-hoc) own settings per band, 6 bands | -0.0021 [-0.0032, -0.0011] | worse |
| R1-C ENSO-conditioned weights | - | **not identifiable from 2026** (see below) |

The only pair where R1-B gains is mslp days 26-32: +0.0010, with an interval above zero. That
is one pair out of six, consistent with chance after the comparison is made six times.

**Why ENSO cannot be tested on 2026 alone.** Niño 3.4 rose almost monotonically, from -0.7 K
in January to +3.2 K in November. ENSO state is therefore collinear with season and time in
the 42 runs. Any "ENSO effect" fitted on them could not be told apart from a seasonal or trend
effect (fig1).

**Why the variants fail (section 8b, exploratory).**
- South of 30°S the fitted blend beats the raw ensemble in-sample. Under cross-validation it
  loses to the raw ensemble for mslp and pr (mslp days 19-25: 0.084 cross-validated, 0.090 for
  raw counts).
- The ensemble weight there varies from 0.74 to 0.94 between folds.
- About 38 training weeks give weights that are noisier than the gains they deliver. Every
  added parameter makes this worse.

## Decision checklist (Phase 11)

| Question | Answer |
|---|---|
| Does the research code reproduce SeasonBlend exactly? | Yes: weekly RPS differences of 0, weight differences of 0 |
| Is the cross-validation free of leakage? | Settings and weights are refitted in every fold, with ±21 days excluded. Remaining issues, documented in `docs/r1-audit.md`: (a) the bias and prior fields of training weeks were built with all data (second order); (b) leave-one-out is not chronological, so a forward split was added and agrees |
| Was any post-initialisation data used? | No. Indices are taken at the initialisation, with publication lags |
| Was any synthetic data used in the results? | No. Synthetic fields appear only in the unit tests of the algebra |
| Does any variant beat SeasonBlend beyond the bootstrap interval, for all block lengths? | **No** |
| Promote a variant to a registered model? | **No.** SeasonBlend stays the DJF model, unchanged |
| Negative results reported? | Yes, all of them, in the table above and in the notebook |
| Tests | `tests/test_r1.py` 12/12; `tests/test_end_to_end.py` 39/39 (operational pipeline) |

## Publication pathway (Phase 9)

R1 on its own is **not** a paper: regime-dependent and spatially varying calibration are
established ideas (Allen et al. 2019; Scheuerer & Büermann 2013), and here the outcome is
negative on one year of data. It does provide:

1. a validated, exactly reproducible evaluation harness that is consistent with the
   leaderboard;
2. the evidence that the bottleneck is estimation noise;
3. an Africa-focused verification baseline.

A paper becomes realistic if the ENSO/IOD-conditioned prior (below) passes its falsification
test on multi-year data. Candidate venues: *Weather and Forecasting* or *QJRMS* for the
method; *Meteorological Applications* or the ECMWF/ICPAC report series for the African
verification.

## Next experiment (recommended): an ocean-state conditioned climatological prior

**Hypothesis.** SeasonBlend's prior, the frequency of each quintile in past ERA5 weeks of the
same season, does not know the ocean state. In a strong El Niño with a positive IOD, the
quintile frequencies of the coming weeks shift (warm and wet over equatorial East Africa in
OND/DJF, for example). A prior that weights each past year by its similarity in Niño 3.4 and
the IOD should be sharper and still reliable. The over-forecast cold quintile in 2026 is one
symptom of exactly this.

**Why it avoids the R1 failure mode.** The prior is estimated from **ERA5 alone**. That gives
45 years × 52 weeks instead of 42 runs, with only one or two new parameters (the width of the
similarity kernel in Niño 3.4 and the IOD).

**Design.**

1. Build weekly ERA5 aggregates for 1981-2025 on the competition grid (`aiwq/cds.py`; the CDS
   key exists and 30 of 69 variable-years are already cached). This is a public reanalysis
   download, with no new licence.
2. Conditioned prior: for target week *t*, weight year *y* by
   exp(-(N34_y - N34_t)² / 2h²) × exp(-(IOD_y - IOD_t)² / 2k²). Use the index values at the
   initialisation, from the observed series, with publication lags.
3. Validate **leaving one year out**, so that a whole year is never in its own training set:
   - first as a stand-alone forecast (conditioned prior vs plain seasonal prior, 45 years);
   - then inside SeasonBlend's blend on the 42 runs of 2026.
4. Falsification: the conditioned prior is rejected if its gain over the seasonal prior is
   not above the bootstrap interval, or if the gains cannot be traced to known teleconnections
   (maps by region, with East Africa in OND/DJF as the primary test).

**Later, with your approval:** after you accept the S2S licence, the ECMWF S2S reforecasts
(20 years × 11 members, Data Store) allow a reforecast-trained PBC-style benchmark and a
multi-year refit of the ensemble part.

## Draft weekly update for the mentor (not sent)

> Dear Nishadh,
>
> This week I finished R1: can a more flexible calibration beat SeasonBlend? Using the 42 ECMWF
> runs of 2026 and a fully cross-validated, block-bootstrap evaluation, the answer is no.
>
> - Smooth latitude weights, MJO-conditioned weights, per-band settings and an xsdba empirical
>   quantile mapping all scored lower than SeasonBlend out of sample.
> - The quantile mapping you suggested reaches RPSS +0.064, against +0.112 for SeasonBlend, and
>   drops to -0.006 with 10 training weeks.
> - SeasonBlend is also by far the most reliable of the candidates.
> - Over Africa it scores +0.152 (equatorial East Africa +0.132).
>
> The main lesson is that with one year of runs, the limit is estimation noise, not the form
> of the calibration. ENSO conditioning cannot be tested on 2026 alone, because Niño 3.4 rose
> steadily all year.
>
> Next, I plan to condition the climatological prior on ENSO and the IOD using 45 years of
> ERA5, validated leaving one year out, with equatorial East Africa as the primary test region.
>
> Results and notebook: https://github.com/STEPHEN-NYARANGA/s2s-postprocessing-ecmwf/tree/research/r1/results/experiments/R1
>
> SeasonBlend continues unchanged for the weekly DJF submissions.

## Files

| File | Content |
|---|---|
| `R1A_reproduction.csv` | Row-level code vs the operational fit |
| `R1B_cv_scores.csv`, `R1B_bootstrap_mean_delta.csv`, `R1B_bootstrap_per_pair.csv`, `R1B_forward_validation.csv` | R1-B schemes |
| `R1_region_scores.csv`, `R1_region_bootstrap.csv` | Regions, including Africa |
| `R1_reliability.csv` | Reliability diagrams (fig3) |
| `R1D_mjo_two_class.csv` | MJO-conditioned weights |
| `R1E_band_settings_bootstrap.csv`, `R1E_southern_band_diagnostic.csv` | Post-hoc diagnostic |
| `R1_quantile_mapping.csv` | xsdba quantile mapping, with training-size sensitivity |
| `R1_decision.json`, `R1_folds.csv` | Decision record; every fold's training set and choices |
| `provenance.json` | Git commit, runs, package versions |
| `figures/` | fig1 indices, fig2 weight profiles, fig3 reliability, fig4 maps (PNG and PDF) |

**Reproduce:** the steps below use `.venv-research`, which holds xsdba and is kept separate
from the operational `.venv`.

1. Build the row-level statistics: `python -m aiwq.research` (about 15 min).
2. Run the quantile-mapping experiment: `python -m aiwq.research_qm` (about 2.5 h on a
   laptop).
3. Execute the notebook with `AIWQ_ROOT` set to the repository root (about 35 min).
