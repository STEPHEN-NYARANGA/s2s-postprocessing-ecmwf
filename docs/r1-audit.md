# R1 groundwork: audit, data availability and novelty

Written 18 November 2026 on branch `research/r1`. Section 1 audits what was done before R1.
Section 2 records the competition rules as read on the website. Section 3 covers whether
historical reforecasts can be obtained, and section 4 sets the proposed direction against
published work. The R1 experiments themselves are in
[notebooks/R1_calibration_experiments.ipynb](../notebooks/R1_calibration_experiments.ipynb), and
their results are in [results/experiments/R1/](../results/experiments/R1/README.md).

## 1. Audit of R0 and the operational model

### Verified

| Item | Evidence |
|---|---|
| Week-1 (12 Nov) files | Six files, 5 × 121 × 240, sums to 1, package checks pass ([crosscheck.md](../results/20261112/crosscheck.md)); emailed 18 Nov |
| Backtest numbers | The reported +0.131 and +0.108 are the in-sample RPSS averaged over the three variables for days 19-25 and 26-32: (0.115 + 0.196 + 0.083) / 3 and (0.096 + 0.154 + 0.073) / 3 |
| Fully cross-validated mean | +0.114 (ratio convention). The 42 / 41 verified runs have initialisations from 1 Jan to 15 Oct 2026 |
| Control reproduces SeasonBlend | Checked twice: `params_control.json` equals `params.json` (R0), and the independent row-level code in `aiwq/r1.py` reproduces the weights, in-sample scores and every weekly cross-validated RPS to within 1e-11 (notebook, section 2) |
| Operational code | `research/r1` adds files only. `fit.py`, `forecast.py`, `submit.py` and `params.json` are not changed by R1 work |

### What the cross-validation does and does not refit

`final_cv` (fit.py) refits **the setting combination (lambda, spread, smoothing) and the blend
weights** without the scored week and the weeks within 21 days of it. Before that, the **bias
correction and the prior** for the scored week were already estimated without it.

These remaining issues are not corrected:

1. **Second-order leakage.** The statistics of a *training* week j inside the fold for week i
   were built with a bias correction that used week i's observation. The bias field is a
   seasonally weighted mean over about 40 weeks, so a single week contributes at most a few
   percent. The effect on fold selection should be small, but it is not zero and has not been
   measured. Removing it needs a fully nested loop, about 40 times the cost of a 33-minute fit.
2. **Not chronological.** Leave-one-out trains on later weeks as well. The notebook adds a
   forward split (weights fitted on earlier weeks only) as a sensitivity check. The bias and
   prior inside the statistics are still leave-one-out.
3. **Researcher degrees of freedom.** The setting grid, the 45-day seasonal window, the 21-day
   exclusion and the three bands were chosen while developing on the same 2026 data. That
   optimism cannot be measured without independent years.
4. **One year only.** All verified targets lie between 19 January and early November 2026. No
   cross-year or cross-ENSO validation is possible.
5. **Prior cut-off.** The backtest prior uses ERA5 weeks that ended at least 23 days before the
   target Monday. For days 26-32 the latest week used ends 4 days before the initialisation,
   which is allowed. For days 19-25 the backtest is stricter than operations.

### Scoring convention: a mismatch with the leaderboard

The Evaluation System page says that period-aggregated scores are "calculated from mean skill
scores across all evaluated weeks", that is, the **mean of weekly RPSS**. The fit and the R0
report use 1 − ΣRPS / ΣRPS_clim, which weights weeks by their climatological RPS. Both are now
reported. The leaderboard convention gives slightly lower numbers: for tas days 19-25, +0.108
against +0.111. The settings are still selected with the ratio form in both the operational fit
and R1, so that comparisons are like for like.

### Uncertainty estimates

- The bootstrap resamples whole weeks. Spatial dependence is therefore kept exactly; it is not
  ignored.
- Temporal dependence is handled with moving blocks of 4 weeks. With about 42 weeks that is
  only about 10 independent blocks, so the percentile intervals are approximate and may be
  somewhat too narrow.
- R1 reports block lengths 1, 2, 4 and 8.
- The intervals describe week-to-week sampling within 2026, not uncertainty about other years.

### The 39 tests, inspected

**Covered:**

- Quintile counting and RPSS equal the official package functions on tied-boundary and desert
  cases.
- Days 19-25 and 26-32 are picked exactly.
- The submission files pass the package's own checks.
- The upload path works against a fake ECBox.
- The experiment harness is isolated and reproduces the operational fit.
- The bootstrap behaves correctly on identical inputs.

**Weak or not covered:**

- "Final beats raw" uses synthetic data with built-in skill, so it is a plumbing test, not
  evidence of skill.
- The "cross-validated ≤ in-sample" check passes with equality on synthetic data.
- Nothing tests the publication lags of the indices, the leaderboard averaging convention or
  leakage.
- `tests/test_r1.py` adds 10 checks for the R1 algebra. Among them, the three-band scheme must
  reproduce `fit.cross_validated_rps` exactly.

### Climate indices

- The rules allow "any data with a timestamp strictly prior or equal to Thursday 00 UTC ...
  regardless of when the data becomes available". The publication lags in `aiwq/indices.py`
  (RMM 2 days, Niño 3.4 8 days, IOD 4 days) are therefore stricter than required. That is safe,
  but could be relaxed to timestamps of 1 day or less before the initialisation.
- **Revisions:**
  - The BoM RMM file states that values up to 2013 had ENSO and the 120-day mean removed,
    whereas later values have only the 120-day mean removed. A training set that spans 2013
    mixes two definitions.
  - CPC weekly OISST anomalies are recomputed when the base period or OISST version changes.
  - Values read today for past dates are therefore retrospective, not necessarily what was
    available in real time. For 2026 the difference is small. For reforecast years it must be
    stated.

### Environment incident (resolved)

Installing `xsdba` into the operational venv downgraded scipy from 1.18.1 to 1.17.1, because
xsdba requires scipy < 1.18. The research packages now live in a separate `.venv-research`,
and the operational `.venv` was restored to scipy 1.18.1 (see the commit for this stage).

## 2. Competition rules (website, read 18 November 2026)

- **Models:** up to five AI/ML models per team, each with up to ten forecasted variables (five
  variables × two lead times).
- **Data:** models may use "any observational or forecast datasets". Initial data may have any
  timestamp up to Thursday 00 UTC.
- **Changes:** only minimal model changes during a period; refinement between periods.
- **Period ranking:** to appear on the period-aggregated leaderboards, a model must submit
  every week of a full 13-week period with the same model. Historical leaderboards include a
  model for a variable and window only if it submitted every week up to the chosen week. A new
  model started in DJF week 2 or later is therefore scored weekly but not period-ranked for
  DJF.
- **MJO and tropical storms:**
  - MJO: phase probabilities for days 22 and 29, scored with the Brier skill score.
  - Tropical storms: tercile storm-day probabilities, scored only in basins active in the
    period (DJF: SW and SE Indian Ocean).
  - The website gives no separate entry requirement for them.
- **Timetable:** DJF 2026 covers initialisations from 12 Nov 2026 to 4 Feb 2027, and MAM 2027
  starts on 11 Feb. The 19 Nov initialisation closes on Sun 22 Nov 23:59 UTC.
- **Africa leaderboards:** not on the website. ECMWF's email of 16 Nov announced them for
  mid-December (ArcX initiative); details are to be confirmed when published.

## 3. Historical reforecasts: what exists and how to get it

R1 shows that 42 runs from one year cannot identify ENSO-conditioned calibration. Reforecasts
are what can. The candidates are:

| Source | Coverage | Members | Grid | Variables | Access | Fit for purpose |
|---|---|---|---|---|---|---|
| **ECMWF Data Store, S2S reforecasts** (`s2s-reforecasts`, DOI 10.21957/1bf331b9) | ECMWF on-the-fly: 20 past years for every Monday and Thursday model-version date; hindcast years listed from 1981 to 2025 | 11 (10 + control), per ECMWF's S2S configuration page | 1.5° global | 2 m temperature (daily mean), MSLP (instantaneous), total precipitation (accumulated), up to 46 days | Free ECMWF account, plus accepting the **S2S licence** in the Data Store; API requests | **Best match:** same model family, Thursday dates, the competition grid, and 20 winters with several El Niño and La Niña events |
| IRI Data Library mirror of S2S ECMWF (used by MicroEnsemble's PBC code) | as above | as above | 1.5° | as above | Free IRI account (sign-in required, checked 18 Nov) and licence acceptance | Equivalent; a backup route |
| ECMWF MARS hindcast streams (enfh / eefh) | 20 years | 11 | native | all | Real-time service agreement (licensed) | Not available to us free of charge |
| Lower-resolution extended-range reforecasts 1959-2023 (CY47R3) | 65 years, initialised on the 1st, 8th, 15th and 22nd of each month | 11 | lower resolution | to check | Dataset page on ecmwf.int; terms to check | Very long ENSO record, but not Thursday-based and from an older cycle; for regime studies, not operations |

**Verification for reforecast years.** ECBox only offers ERA5 weekly files from 2024. Earlier
years need ERA5 from the Copernicus Climate Data Store, built by `aiwq/cds.py` with the same
weekly aggregation and quintile method. It is close to, but not identical with, the
leaderboard's ERA5T. A CDS key exists on this computer, and 30 of 69 variable-years are cached.

**Proposed acquisition (needs your approval).** Accepting a licence is your decision, so
nothing has been downloaded. The steps:

1. You sign in to the ECMWF Data Store and accept the S2S licence.
2. A pilot download covers the 13 DJF model-version Thursdays (Nov to Feb). Each holds 20
   years × 11 members, with only the steps for days 19-32: tp at 432, 600 and 768 h; daily
   2 m temperature; MSLP every 6 h. That gives 20 winters covering El Niño (e.g. 2009/10,
   2015/16, 2023/24) and La Niña (e.g. 2010/11, 2020-22).
3. Build the weekly aggregates on the competition grid, with ERA5 verification from CDS.
4. Validate leaving one **year** out, so that a whole winter is never in its own training set.

Synthetic data will not be used as a substitute.

## 4. Novelty: what is already established

These references were checked against Crossref on 18 November 2026.

| Theme | Established | Implication for us |
|---|---|---|
| Regime-dependent post-processing | Allen, Ferro & Kwasniok (2019, QJRMS, doi:10.1002/qj.3638) condition EMOS parameters on weather regimes; Mariotti et al. (2020, BAMS, doi:10.1175/BAMS-D-18-0326.1) review windows of opportunity; Johnson et al. (2014, WAF, doi:10.1175/WAF-D-13-00102.1) build week 3-4 forecasts from ENSO and MJO states | Conditioning calibration on a climate regime is **not new**. Any novelty must lie in the specific setting (global quintile probabilities at weeks 3-4, a climatological-prior blend, Africa with the IOD) and in leakage-free multi-year evidence |
| Spatially varying calibration | Scheuerer & Büermann (2013, JRSS-C, doi:10.1111/rssc.12040) let post-processing parameters vary in space | Smooth latitude weights (R1-B) are an engineering refinement, not a scientific contribution |
| Reforecast calibration of ECMWF | Hagedorn et al. (2012, QJRMS, doi:10.1002/qj.1895); Monhart et al. (2018, JGR, doi:10.1029/2017JD027923); Manrique-Suñén et al. (2020, MWR, doi:10.1175/MWR-D-20-0067.1) on how verification choices change S2S skill | Our one-year training is far below standard practice. Reforecasts are needed before claims are made |
| ML post-processing at subseasonal range | Guan et al. (2026, Nature, doi:10.1038/s41586-026-11126-x; PBC, open code); Horat & Lerch (2024, MWR, doi:10.1175/MWR-D-23-0150.1); Vigaud et al. (2017, MWR, doi:10.1175/MWR-D-17-0092.1) on extended logistic regression | PBC already blends debiased ECMWF with persistence, trained on reforecasts. SeasonBlend's observed-frequency prior is a related but different idea, and has to be compared with PBC directly |
| Quantile mapping | Cannon et al. (2015, J. Climate, doi:10.1175/JCLI-D-14-00754.1); xclim/xsdba implementations | A standard baseline, evaluated in R1 |
| Africa | de Andrade et al. (2021, WAF, doi:10.1175/WAF-D-20-0054.1) on S2S precipitation skill and its sources in Africa; MacLeod et al. (2021, JHM, doi:10.1175/JHM-D-20-0211.1) on East African heavy rainfall | Africa-focused evaluation exists. A contribution would be a calibration method whose gains are shown and explained (IOD, ENSO, MJO) for these regions |
| Statistics | Wilks (1997, J. Climate) on resampling autocorrelated fields; Weigel et al. (2007, MWR, doi:10.1175/MWR3280.1) on the discrete RPSS | Block bootstrap, and debiasing for small ensembles |
| Data | Vitart et al. (2017, BAMS, doi:10.1175/BAMS-D-16-0017.1), the S2S database; Wheeler & Hendon (2004, MWR), RMM; Hersbach et al. (2020, QJRMS, doi:10.1002/qj.3803), ERA5 | - |

**Candidate contribution, stated carefully:** a calibration of S2S quintile probabilities in
which the climatological reference itself, not just the ensemble correction, depends on the
ocean state (ENSO, IOD). It would be estimated from a long reanalysis and multi-year
reforecasts, judged with leaderboard-consistent, leakage-free validation, and evaluated for
African regions.

**Falsification:** it is not novel or not useful if, under leave-one-year-out validation on
reforecasts, it does not beat a fixed-weight SeasonBlend and a reforecast-trained PBC-style
benchmark beyond the bootstrap interval, or if its gains cannot be traced to known
teleconnections.
