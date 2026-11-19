# R2: Where can SeasonBlend still gain leaderboard points, and does an ENSO/IOD prior help?

Branch `research/r2`, 19 November 2026. This is competition research only. The operational SeasonBlend
model, its parameters (`data/params.json`), its pipeline and its submitted files are unchanged.

- **Notebook (executed, all outputs stored):**
  [notebooks/R2_ENSO_IOD_Competition_Experiment.ipynb](../../../notebooks/R2_ENSO_IOD_Competition_Experiment.ipynb)
- **Code:**
  - [aiwq/r2.py](../../../aiwq/r2.py): ERA5 pilot, priors and scores
  - [aiwq/research_lag.py](../../../aiwq/research_lag.py): earlier ECMWF runs aligned to Thursday weeks
  - [tests/test_r2.py](../../../tests/test_r2.py)

## Short answer

| Question | Answer |
|---|---|
| Is SeasonBlend safe for the 19 Nov submission? | Yes. Nothing operational changed. The pipeline checked healthy on 18 Nov 22:22 UTC. The run lands on dynamical.org about Sat 21 Nov 00 UTC, and the deadline is **Sun 22 Nov 23:59 UTC** (end of day 4, confirmed on the competition site). |
| Did ENSO conditioning help? | **Yes, for 2 m temperature.** ERA5 2005-2025, leave one ENSO year out: +0.015 RPSS over SeasonBlend's existing prior (90 % +0.007 to +0.024; 18 of 22 years better). |
| Did it help SeasonBlend in 2026? | tas +0.0048 RPSS with refitted weights (90 % +0.0024 to +0.0071) and +0.0041 with weights fixed (+0.0003 to +0.0080). That is **+0.0016 on the headline** (mean of 6 pairs). |
| IOD? | No gain, alone or combined with ENSO. |
| Lagged ensemble (Wed/Mon runs)? | **Worse:** −0.0009 headline (Wed) and −0.0025 (Wed + Mon; 90 % −0.0040 to −0.0010). |
| Promote anything into SeasonBlend? | **No.** SeasonBlend stays frozen for DJF. The ENSO prior is a candidate for a second model. |

## Rules that shaped the work (read 19 Nov 2026)

- **Models:** up to 5 per team.
- **Changes within a period:** "only minimal model changes during each competitive period".
- **Period ranking:** needs every week of the 13-week period with the same model.
- **Inputs:** "any data with a timestamp strictly prior or equal to Thursday 00 UTC". Climate indices
  and Monday-Wednesday ECMWF runs are therefore allowed; Friday/Saturday runs are not.
- **Headline score:** mean RPSS of tas, mslp and pr. tas and pr are scored on land, pr without arid
  points, and mslp everywhere; all are area weighted.
- **Period aggregation:** the evaluation page describes both pooled RPS and mean weekly skill, so
  both conventions are reported.
- **Africa (ArcX) leaderboard:** not published yet.
- **MJO and tropical storms:** their own leaderboards.

## 1. Where SeasonBlend loses points (2026, cross-validated)

| Weakness | Headline points | Comment |
|---|---:|---|
| Weight noise (in-sample minus CV) | 0.0042 | Mostly optimism: the learning curve is flat (0.1122 with 10 training weeks, 0.1142 with 36) |
| Calibration headroom (RPS reliability term) | ≤ 0.0032 | In-sample upper bound |
| Coldest-quintile over-forecast | 0.0009 | First cumulative threshold |
| South of 30°S, SeasonBlend vs raw | ≈ 0.001 | tas gains, mslp and pr lose about 0.001 each |
| Equatorial East Africa | ≤ 0.0004 | Tiny share of the global score |
| Northern extratropics | (largest) | RPSS 0.045 on 36 % of the climatological RPS |
| Days 26-32 vs 19-25 | — | 0.100 against 0.123 in every variable: predictability, not a bias |

This corrects R1's reading: SeasonBlend is **not** short of training weeks for its blend weights.
More of the same data buys about 0.001. New *information* is what can help.

## 2. ENSO/IOD pilot (ERA5 2 m temperature, 2005-2025)

**Set-up.**
- **Cases:** 2190 Thursday cases (both windows) on 9839 scored land points, over 21 ENSO-year folds.
- **Inputs:** Niño 3.4 (CPC weekly, 8-day lag) and DMI (BoM weekly, 4-day lag; from Aug 2008).
- **Model:** a Gaussian-shift prior from a leave-one-year-out regression with trend; κ is chosen
  nested.

**Nested results, RPSS against climatology:**

| Prior | RPSS | Δ vs baseline [90 %] |
|---|---:|---|
| Existing prior (`recent`) | −0.0124 | baseline |
| recent × ENSO | +0.0022 | **+0.0146 [+0.0066, +0.0239]**, 18/22 years |
| ENSO alone (vs climatology) | +0.0107 | +0.0107 [+0.0028, +0.0193] |
| recent × IOD (DMI period) | −0.0124 | +0.0023 [+0.0004, +0.0043] |
| recent × ENSO+IOD (DMI period) | −0.0005 | +0.0143 (no better than ENSO alone on the same cases: +0.0145) |

**Where the gain comes from:**
- **Regions:** tropics +0.034, Africa +0.021, East Africa +0.030, Southern Africa +0.039; the
  extratropics show no change.
- **ENSO strength:** +0.048 when |Niño 3.4| ≥ 1 K.
- **Seasons:** every season gains, most in DJF and MAM.
- **Reliability component** (×10⁻³): recent 1.43 → recent × ENSO 1.19.

## 3. Integration into SeasonBlend (2026 temperature)

The slopes are fitted on ERA5 weeks ending by 31 Dec 2025, and κ comes from the pilot. The variant
is scored with the official ERA5 weekly files and quintiles.

| Variant | Mode | Δ tas RPSS [90 %] | Headline Δ |
|---|---|---|---:|
| prior × ENSO | fixed weights | +0.0041 [+0.0003, +0.0080] | +0.0014 |
| prior × ENSO | refitted weights | +0.0048 [+0.0024, +0.0071] | +0.0016 |
| prior × IOD | refitted | −0.0002 | −0.0001 |
| prior × ENSO+IOD | refitted | +0.0045 | +0.0015 |

**When the gain appears.** The weekly gains start after July 2026, once Niño 3.4 passed about
1.5 K (`fig3`). In the pilot, too, El Niño years carry the gain: 2009, 2015 and 2023 gain +0.05 to
+0.09, while La Niña years gain little (`fig2`). The coming DJF weeks start at Niño 3.4 ≈ +3 K.

**2026 reliability is mixed** (`R2_integration_reliability.csv`, ×10⁻³, fixed weights):

| Window | Model | Coldest quintile | Warmest quintile | Mean |
|---|---|---:|---:|---:|
| days 19-25 | SeasonBlend | 1.36 | 0.79 | 0.56 |
| days 19-25 | prior × ENSO | 1.18 | 1.19 | 0.62 |
| days 26-32 | SeasonBlend | 1.46 | 0.80 | 0.57 |
| days 26-32 | prior × ENSO | 1.29 | 1.29 | 0.64 |

The coldest-quintile over-forecast eases, but the warmest quintile becomes over-forecast, so the
RPSS gain comes from resolution, not calibration. A damped κ for the warm tail should be checked
before any live use.

## 4. Lagged ensemble (2026, all variables)

Wednesday (lag 1) and Monday (lag 3) runs were downloaded for every Thursday, bias-corrected
separately and pooled with equal weight per run. The comparison uses the same 40-41 weeks.
- **Thursday + Wednesday:** −0.0009 headline (90 % −0.0019 to +0.0002).
- **Thursday + Wednesday + Monday:** −0.0025 (−0.0040 to −0.0010). The loss is largest for mslp at
  days 19-25 (−0.0088).

The older runs dilute the newest one. **Dropped.**

## Decision and next steps

1. **SeasonBlend runs unchanged for the rest of DJF 2026.** Every week, check, cross-check and
   submit only after approval.
2. **Precipitation pilot next.** ERA5 precipitation 2004-2026 is downloading into `data/cds/`.
   The notebook picks it up automatically and repeats Sections 4-5 for pr. SeasonBlend relies on its
   pr prior in the tropics (c ≈ 0.37-0.41), so this is where the next gain is most likely.
3. **If pr confirms**, build SeasonBlend-ENSO (SeasonBlend with the ENSO-tilted prior) as a
   **second model**.
   - **Now:** run it as a weekly shadow forecast; register and submit it only with approval.
   - **Ranking:** it cannot be period-ranked in DJF because it missed weeks 1-2. The earliest ranked
     entry is **MAM 2027 (11 Feb 2027 initialisation)**, if its live weekly scores agree with this
     backtest.
4. **Later:** check whether an independent forecast system available before Thursday 00 UTC is
   worth testing for the northern extratropics, where most of the score is.

## Limitations

- The pilot's quintile boundaries come from all other years of 2004-2025, not the official trailing
  20 years.
- The ENSO prior was tested inside SeasonBlend on a single year (2026), which has a strong ENSO
  trend.
- Pressure is excluded, because SeasonBlend gives its pressure prior almost no weight.
- The learning curve covers the blend weights and settings, not the bias correction's sample size.

## Files

| File | Content |
|---|---|
| `R2_weakness_points.csv`, `R2_region_points.csv`, `R2_learning_curve.csv` | Section 1 |
| `R2_pilot_folds.csv`, `R2_pilot_kappa.csv`, `R2_pilot_nested.csv`, `R2_pilot_breakdown.csv`, `R2_pilot_reliability.csv` | Section 2 |
| `R2_integration_scores.csv`, `R2_integration_bootstrap.csv`, `R2_integration_reliability.csv` | Section 3 |
| `R2_lagged_scores.csv`, `R2_lagged_bootstrap.csv` | Section 4 |
| `R2_decision.json`, `provenance.json` | Decision record, data and software versions |
| `figures/fig1_learning_curve.png`, `fig2_enso_pilot_tas.png`, `fig3_integration_weekly.png` | Figures |

**Reproduce:** run `python -m aiwq.research_lag` (`.venv`), then run the notebook top to bottom with
`.venv-research`. It takes about 25 minutes. The lagged-run cache is 1.7 GB in
`data/research/ens_lag/` (not in Git).
