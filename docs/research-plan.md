# Research plan, DJF 2026 period (November 2026 to February 2027)

The plan for running SeasonBlend every week and, alongside it, building new models that are
both novel and more skilful. Written 18 November 2026; updated as experiments finish.
Results of each experiment go into [`results/`](../results/README.md).

## Goals, in order

1. **Never miss a week.** SeasonBlend runs unchanged for all 13 weeks of DJF 2026.
2. **Beat SeasonBlend with something new**, measured with the same leave-one-out backtest.
3. **Be strongest where we have an edge:** Africa (Africa leaderboards from mid-December
   2026; mentor at ICPAC) and the new MJO and tropical-storm variables.
4. **Make it citable:** a method, weekly checks and Africa verification that can become a
   paper or thesis chapter.

## Rules that shape the plan

What we know from the competition pages:

- A model is ranked for a period only if it submits **every week of the 13-week period with the
  same model**. Only minimal changes are allowed within a period.
- A team is ranked by its best model. The website says up to 5 models per team; the package
  documentation says 3.
- Headline score: mean RPSS over tas, mslp and pr, for both windows. tas and pr count over land
  only, and pr also skips arid points.
- MJO (9 phases, Brier skill score) and tropical-storm days (terciles; in DJF only the SW and
  SE Indian Ocean basins) have their own leaderboards from DJF 2026.
- The next period, MAM 2027, starts with the 11 February 2027 initialisation.

What follows from them:

- **SeasonBlend stays frozen until 4 February 2027.** Only bug fixes, and only if they are needed.
- A new model started now **cannot be period-ranked in DJF**, because it missed week 1. It still
  gets a weekly score. So we develop now, run the best candidate live from mid-December as a
  real out-of-sample test, and **launch it as a ranked entry on 11 February 2027 (MAM)**.

Points to check on the competition website before launching a second model (no need to ask
the organisers): the number of models per team (the website says 5, the package documentation
3), whether MJO and tropical-storm files can be added mid-period, and the data-use rules for
other forecast systems and climate indices.

## Weekly routine

| When (UTC) | Task | Command or output |
|---|---|---|
| Thu | Initialisation. Read the forum. | - |
| Sat morning | ECMWF run on dynamical.org (about 00 UTC) | `python run.py status --remote` |
| Sat | Build, cross-check, look at the map | `python run.py weekly --no-submit`, then read `outputs/YYYYMMDD/crosscheck.md` |
| Sat / Sun midday | Submit; results go to GitHub | `python run.py weekly`, then `git add results && git commit && git push` |
| Sun 23:59 | **Deadline**: Sunday evening is the backup, never the plan | - |
| Mon to Wed | One research experiment (tracks below) | backtest table in `results/experiments/` |
| Wed | Short note to Nishadh: what was tried, the score, the next step | WhatsApp or email with the GitHub link |

If dynamical.org is late, run `python run.py weekly --wait-hours 12`. If ECBox fails, use
`python run.py export` and email the files (as in week 1).

### DJF 2026 calendar

| Week | Initialisation | Run appears | Deadline (23:59 UTC) | Note |
|---|---|---|---|---|
| 1 | Thu 12 Nov | Sat 14 Nov | Sun 15 Nov | emailed late, by agreement |
| 2 | Thu 19 Nov | Sat 21 Nov | Sun 22 Nov | |
| 3 | Thu 26 Nov | Sat 28 Nov | Sun 29 Nov | |
| 4 | Thu 03 Dec | Sat 05 Dec | Sun 06 Dec | |
| 5 | Thu 10 Dec | Sat 12 Dec | Sun 13 Dec | Africa leaderboards begin about now |
| 6 | Thu 17 Dec | Sat 19 Dec | Sun 20 Dec | |
| 7 | Thu 24 Dec | Sat 26 Dec | Sun 27 Dec | holidays: submit on the Saturday |
| 8 | Thu 31 Dec | Sat 02 Jan | Sun 03 Jan | holidays: submit on the Saturday |
| 9 | Thu 07 Jan | Sat 09 Jan | Sun 10 Jan | |
| 10 | Thu 14 Jan | Sat 16 Jan | Sun 17 Jan | |
| 11 | Thu 21 Jan | Sat 23 Jan | Sun 24 Jan | |
| 12 | Thu 28 Jan | Sat 30 Jan | Sun 31 Jan | freeze the MAM model(s) |
| 13 | Thu 04 Feb | Sat 06 Feb | Sun 07 Feb | last DJF week; MAM starts 11 Feb |

## How an idea becomes a model

Every idea is scored the same way, so the comparisons are fair:

- the same leave-one-out backtest, leaderboard masks and RPSS as SeasonBlend (`aiwq/fit.py`);
- the gain over SeasonBlend for each variable and window, with a **bootstrap over weeks**
  (resampling whole weeks) to show whether the gain is larger than chance;
- for Africa ideas, also the score over the Africa domain.

**Promotion rule:** a candidate replaces nothing and goes live only if it beats SeasonBlend on
the mean RPSS, with the bootstrap interval above zero, and does not lose clearly on any single
variable. Ideas that fail are still written up in `results/experiments/`; a clear negative
result is useful to the mentor and to a paper.

## Research tracks

### R0. Foundations (week 2, before anything else)

- **Experiment harness:** a model name in the config (`modelname`, a separate `params` file and
  output folder) so that variants never overwrite SeasonBlend's files.
- **Bootstrap significance** of score differences, added to the backtest report.
- **Climate indices** saved weekly, with the value known at each initialisation:
  - MJO RMM phase and amplitude (Bureau of Meteorology RMM series; to confirm it is still
    updated);
  - Niño 3.4 (NOAA CPC weekly);
  - Indian Ocean Dipole (DMI).
  Only values published before the Thursday initialisation are used, as the rules require.

**Done when:** `python run.py --experiment <name> fit` and `python run.py compare control <name>`
score a variant against SeasonBlend with intervals, and the indices are cached.

**Status: done 18 November 2026.** The `control` experiment reproduces SeasonBlend exactly.
SeasonBlend's fully cross-validated mean RPSS is +0.114 (90% interval +0.073 to +0.155), against
-0.028 for the raw ensemble. Details: [results/experiments/R0_findings.md](../results/experiments/R0_findings.md).

### R1. Weights that depend on the weather situation (main novel idea)

**Why:** forecasts of weeks 3 and 4 are more skilful in known "windows of opportunity", above
all when the MJO is strong, because its tropical heating sets up predictable patterns
elsewhere. SeasonBlend uses the same blend weights every week. Static calibration, as in the
MicroEnsemble PBC method, does not use this.

**Method:**

- Let the ensemble weight `a` and the prior weight `c` depend on the state at initialisation.
- Start with MJO amplitude, as two classes (active, amplitude ≥ 1, or inactive) or as a linear
  term.
- The RPS stays quadratic in (a, c) within each class, so the exact solver in `fit.py` still
  applies.
- Phase groups (for example 2-3, 4-5, 6-7, 8-1) only if the data support them.

**ENSO-aware prior (added after R0).** 2026 went from weak La Niña (Niño 3.4 -0.7 K in
January) to a very strong El Niño (+3.2 K in November), with a positive IOD (+0.8 K). The
seasonal prior for this winter leans on the two previous, La Niña-like winters. The test:
weight each past ERA5 week by its similarity in Niño 3.4 (and IOD) as well as in season. The
ENSO swing during 2026 gives the backtest contrast to learn from. See
[results/experiments/R0_findings.md](../results/experiments/R0_findings.md).

**Caution:** with about 42 runs, every extra parameter risks overfitting. Keep at most two
MJO classes and one ENSO similarity width until more training data exists (R3), and judge every
variant with the cross-validated score.

**Done when:** the backtest shows whether the MJO classes improve RPSS, and where on the map.

### R2. Africa-focused weights and smooth maps

**Why:** the three latitude bands leave visible seams at ±30° and treat Africa like the rest of
its band. The Africa leaderboards will judge exactly this region.

**Method:**

- Replace the bands with weights that vary smoothly with latitude (for example a few basis
  functions), which removes the seams.
- Add an Africa-focused version: regional weights for East Africa, Southern Africa and the
  Sahel, and an evaluation over the Africa domain.
- In DJF the rainy season is in southern Africa and the short rains are ending in East Africa,
  so report pr skill by region.
- Ask Nishadh which ICPAC regions and verification habits matter.

**Done when:** the backtest gives a score over the Africa domain, and the maps show no seams.

### R3. More training data (biggest long-term gain)

**Why:** about 42 runs from 2026 limit every method we try. The MicroEnsemble PBC method trains
on 20 years of ECMWF reforecasts. Reforecasts would let us estimate seasonal bias properly, use
ENSO and IOD states, and apply quantile mapping reliably.

**Tasks:**

- Find a free, timely source of ECMWF extended-range reforecasts, and their format and
  resolution. Check the MicroEnsemble repository ([mouatadid/pbc](https://github.com/mouatadid/pbc)),
  ECMWF open data and dynamical.org.
- Write `aiwq/refc.py` to build the same weekly aggregates.
- Refit SeasonBlend and the R1 and R2 variants with reforecast years.

**Done when:** we know whether reforecasts are obtainable in time. If they are, the backtest is
rerun with them.

### R4. Benchmarks the mentor suggested: xclim quantile mapping and PBC

**Why:** a fair comparison against well-known methods shows what is new in ours.

**Method:**

- **Empirical quantile mapping** of each member with xclim, or with `xsdba`, the package newer
  xclim versions point to. Then count members in the quintiles as usual.
- **A PBC-style debias plus persistence** benchmark, following the published open code.
- Both go through the same backtest.

**Expectation:** with 42 runs quantile mapping may be noisy. It becomes stronger with R3.

**Done when:** both appear as rows in the backtest table beside SeasonBlend.

### R5. MJO and tropical-storm forecasts (new leaderboards)

**Why:** fewer teams compete on them, and SW Indian Ocean cyclones (Madagascar, Mozambique)
matter for Africa.

**Method:**

- **MJO:** phase probabilities from the ECMWF ensemble, calibrated against observed RMM.
  - First check which fields dynamical.org offers: an RMM index needs OLR and zonal wind at 850
    and 200 hPa.
  - Fallback: a calibrated mix of persistence of the observed phase and climatology.
- **Tropical-storm days:** tercile probabilities for the SWIO and SEIO basins, starting from
  IBTrACS climatology (with an ENSO and MJO adjustment), then adding ensemble storm counts if
  data allow.
- Start submitting once the website's rules confirm that adding them is allowed. Weekly scores
  are visible even if the period ranking is not possible in DJF.

**Done when:** valid MJO and tropical-storm files pass the package checks and have a backtest
against climatology.

### R6. A second forecast system (only if the rules allow)

Combining ECMWF with another ensemble, such as NOAA GEFS, usually beats either alone. This
needs the website's data-use rules to allow it, and the run must be published well before the Sunday
deadline. Low priority until R1 to R3 are done.

## Timeline

| Week of | Research | Live |
|---|---|---|
| 19 Nov | R0 harness, bootstrap, indices (done 18 Nov) | SeasonBlend week 2 |
| 26 Nov | R1 MJO-conditioned weights; R4 quantile mapping baseline | SeasonBlend |
| 03 Dec | R2 smooth and Africa weights; R3 reforecast scouting | SeasonBlend |
| 10 Dec | Choose the best candidate; register it as model 2 | SeasonBlend; model 2 starts live (weekly scores only) |
| 17 Dec | R5 MJO probabilities | both |
| 24 Dec to 3 Jan | Light weeks: run and submit only | both, submitted on Saturdays |
| 07 Jan | R3 refit with reforecasts if available; R5 tropical storms | both |
| 14 to 28 Jan | Consolidate; write up methods and Africa verification | both |
| 04 Feb | **Freeze** the MAM 2027 line-up and documentation | last DJF week |
| 11 Feb | MAM 2027: best models enter as ranked, 13-week entries | - |

## Reporting to the mentor

Each Wednesday, a short note containing:

1. What was tried.
2. The backtest score against SeasonBlend, including Africa.
3. A map or figure.
4. The next step.

All results live in [`results/`](../results/README.md):
- weekly forecasts in `results/YYYYMMDD/`;
- experiments in `results/experiments/<name>/`.

## Risks

| Risk | Guard |
|---|---|
| Missing a deadline while doing research | Submit on Saturday; the weekly run is independent of the experiments |
| Overfitting with 42 runs | Leave-one-out, at most two classes, bootstrap, promotion rule |
| Changing SeasonBlend by accident | Experiment harness with a separate model name and files |
| dynamical.org or ECBox outage | `--wait-hours`, email export, and the CDS fallback for training data |
| Using data not available at initialisation | Indices and ERA5 cut off before the Thursday initialisation |
