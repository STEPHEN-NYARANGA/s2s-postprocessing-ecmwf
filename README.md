# s2s-postprocessing-ecmwf

Statistical post-processing of the ECMWF extended-range ensemble for sub-seasonal forecasts
of weekly 2 m temperature, mean sea level pressure and precipitation (days 19-25 and 26-32).

This is the code behind **SeasonBlend**, the entry of team **Utabiri** (Stephen Nyaranga,
AIMS-RIC) in the [ECMWF AI Weather Quest](https://aiweatherquest.ecmwf.int/). Every week it
takes the Thursday 00 UTC ECMWF IFS ensemble, corrects it against ERA5 and submits global
quintile probabilities on the 1.5 degree competition grid. It runs on a laptop; no GPU is
needed.

## Method

For each variable, forecast window and grid point:

1. **Weekly aggregates.** Daily means of the 101-member ECMWF IFS ENS for lead days 19-25 and
   26-32 are averaged (tas, mslp) or summed (pr) and placed on the competition grid.
2. **Seasonal bias correction.** The bias (tas, mslp) or ratio (pr) is the weighted mean error
   of past forecasts against ERA5, with Gaussian weights in day of year (45 days) and spatial
   smoothing. The correction is scaled by a factor lambda.
3. **Spread scaling.** Member anomalies about the ensemble mean are multiplied by s to correct
   under-dispersion.
4. **Quintile probabilities.** Members are counted in the ERA5 20-year quintiles using the
   competition's tie rules (zero-rain boundaries) and smoothed in space.
5. **Blend.** p = a p_ens + c p_prior + (1 - a - c) 0.2, where p_prior is the seasonally weighted
   frequency with which recent ERA5 weeks fell in each quintile; it carries the warming trend
   relative to the 20-year climatology. The ranked probability score is quadratic in (a, c), so
   the weights are solved exactly in three latitude bands (north of 30N, tropics, south of 30S).

lambda, s and the smoothing width are chosen by a leave-one-out grid search over all verified
forecasts. Forecasts within 21 days of the target week are excluded, and the prior only uses
weeks that ended at least 30 days earlier. The score is the period-aggregated, area-weighted
RPSS with the leaderboard masks (land only for tas and pr, arid points skipped for pr); it
reproduces `AI_WQ_package.forecast_evaluation.work_out_RPSS` to six decimals. In operational
mode only ERA5 weeks that ended before the Thursday initialisation are used, as the rules
require.

## Weekly schedule

| Day (UTC) | What |
|---|---|
| Thursday 00:00 | Initialisation (Day 1) |
| Saturday ~00:00 | ECMWF run published on dynamical.org (48 h licence delay) |
| Saturday or Sunday | `python run.py weekly` |
| Sunday 23:59 | Submission window closes |

## Setup

Python 3.11 or newer and about 3 GB of free disk space.

```bash
git clone https://github.com/STEPHEN-NYARANGA/s2s-postprocessing-ecmwf.git
cd s2s-postprocessing-ecmwf
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install "sites-toolkit>=20261005.1" -i https://get.ecmwf.int/repository/pypi-all/simple
```

Set the team and model names in `config.toml`. The AI Weather Quest submission password is read
from the environment variable `AIWQ_PASSWORD` and is never stored in the repository:

```powershell
$env:AIWQ_PASSWORD = "..."     # Windows PowerShell
```
```bash
export AIWQ_PASSWORD="..."     # macOS / Linux
```

## Usage

```bash
python run.py status --remote   # what is cached; is this week's ECMWF run online?
python run.py fetch-ens         # ECMWF runs since 1 Jan 2026 (newest first, resumable, no password)
python run.py fetch-obs         # ERA5 weeks, quintile boundaries, land-sea mask (password)
python run.py fit               # leave-one-out fit + outputs/backtest/backtest_report.md
python run.py weekly            # fetch, refit, forecast, check and submit this week's forecast
python run.py crosscheck        # independent checks of this week's files -> crosscheck.md
python run.py results           # copy this week's results into results/ for Git
python run.py indices           # MJO (RMM), Nino 3.4 and IOD values known at each initialisation
python run.py --experiment NAME fit     # fit a research variant ([experiments.NAME] in config.toml)
python run.py compare control NAME      # paired block-bootstrap comparison -> results/experiments/
```

**Research experiments.** A variant of the method is a section `[experiments.NAME]` in
`config.toml` whose settings override `[method]`. Its fit, backtest and forecasts go to their own
files (`data/params_NAME.json`, `outputs/experiments/NAME/`), and it cannot submit under
SeasonBlend's name. `control` is SeasonBlend unchanged, the reference for comparisons. Every fit
now also reports a **fully cross-validated** score: the settings and blend weights are chosen
without the scored week as well, so methods with more fitted weights are not favoured. `compare`
resamples blocks of consecutive weeks (default 4), paired between models, because neighbouring
initialisations verify on overlapping weeks. The research plan is in
[docs/research-plan.md](docs/research-plan.md).

Useful options: `weekly --no-submit` stops after the official checks; `submit --dry-run` runs
the checks only; `weekly --wait-hours 12` keeps polling until the ECMWF run appears;
`fetch-ens --stride 2` takes every second Thursday for a lighter archive.

If the organisers ask for a forecast by email (for example during an ECBox outage),
`python run.py export --init YYYY-MM-DD` writes the six files to `outputs/YYYYMMDD/email/` in the
format they request (`tas_YYYYMMDD_p1_<team>_<model>.nc`, built with `AI_WQ_create_empty_dataarray`
and checked with the package).

dynamical.org stores all 46 days of a run together, so each run is read whole (roughly 0.4 to
0.7 GB per run, an estimate) even though only days 19-32 are kept (about 25 MB per run on disk).

Each forecast is saved in `outputs/YYYYMMDD/` with a quick-look map of upper minus lower
quintile probability on latitude/longitude axes. `weekly` also runs `crosscheck` (independent checks
of the six files: format, dates, units and whether the probabilities agree with the raw ensemble and
recent observations; the upload stops if they fail) and `results`, which copies the files, maps,
checks and backtest into [`results/`](results/README.md), the folder kept in Git for reviewers.

## Repository layout

```
run.py              entry point (python run.py --help)
config.toml         team/model names and method settings
aiwq/ens.py         dynamical.org download and weekly aggregation
aiwq/obs.py         ERA5 weeks, quintile boundaries, land-sea mask (AI-WQ-package)
aiwq/cds.py         the same files built from Copernicus ERA5 (fallback, --obs-source cds)
aiwq/calib.py       quintile counting, bias correction, prior, RPS algebra
aiwq/fit.py         leave-one-out fit and backtest report
aiwq/forecast.py    weekly probabilities
aiwq/submit.py      checks and upload through AI-WQ-package; email export
aiwq/crosscheck.py  independent sanity checks of a week's files (crosscheck.md)
aiwq/results.py     copies each week's results into results/ and writes its index
aiwq/stats.py       paired moving-block bootstrap comparison of fitted models
aiwq/indices.py     MJO, Nino 3.4 and IOD indices with publication lags
results/            submitted forecasts, maps, checks and backtest (tracked in Git)
aiwq/plots.py       quick-look maps and weekly RPSS plot
tests/              offline end-to-end test on synthetic data
docs/github-setup.md  pushing changes to GitHub with a personal access token
docs/research-plan.md weekly routine and research plan for new models
```

To push changes from your own computer with a GitHub personal access token, follow
[docs/github-setup.md](docs/github-setup.md). The weekly routine and the research plan for new
models are in [docs/research-plan.md](docs/research-plan.md).

## Tests

```bash
python tests/test_end_to_end.py
```

The test builds a synthetic world (a fake dynamical.org dataset and a fake ECBox server) and runs
the real AI-WQ-package functions against it. It checks that quintile counting and RPSS agree with
the official package, that days 19-25 and 26-32 are selected exactly, that calibration beats the
raw ensemble on data with known skill, and that the six submission files pass the package checks.

## Fallback: ERA5 from Copernicus when ECBox is unavailable

Submitting always needs ECBox. Training data does not: `--obs-source cds` (or `[obs] source = "cds"`
in `config.toml`) builds the weekly observations, 20-year quintile boundaries and land-sea mask from
ERA5 daily statistics on the [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/)
(`aiwq/cds.py`). It follows the method of `AI_WQ_package.compute_20yr_quintile_climatology`
(7-day means or totals; quintiles of 20 years x offsets of -4, -2, 0, 2 and 4 days).

```bash
pip install cdsapi              # plus a free CDS account and its API key in ~/.cdsapirc
python run.py --obs-source cds fetch-obs   # ~800 monthly requests; hours, resumable
python run.py --obs-source cds fit
python run.py --obs-source cds forecast
```

The stand-in files go to `data/obs_cds/` and the fit to `data/params_cds.json`, so they never mix
with the official files. They are close to, but not identical with, the leaderboard's ERA5T truth
and boundaries, so switch back to the official files (the default) as soon as ECBox works.

## Troubleshooting

- **"not on dynamical.org yet"**: the Thursday run normally appears on Saturday around 00 UTC.
- **"403 ... Not a Branca token" from ECBox**: `AIWQ_PASSWORD` holds an old password. Since the
  move from FTP to ECBox (13 August 2026) it must be the ECBox password from the organisers'
  technical update email, a long string of letters and digits. On Windows the pipeline also reads
  a user variable saved with `[Environment]::SetEnvironmentVariable(..., "User")`.
- **"nothing could be downloaded" in fetch-obs**: check `AIWQ_PASSWORD` and the sites-toolkit
  install.
- **"is not recognised as a registered AI Weather Quest teamname"**: the names in `config.toml`
  must match the registration exactly.
- **A variable reported MISSING by `status --remote`**: dynamical.org renamed it; edit
  `ENS_NAMES` in `aiwq/ens.py`.

## Data and credits

- ECMWF IFS ENS sub-seasonal-range forecast data processed by dynamical.org from the ECMWF Data
  Store, CC BY 4.0 ([dataset](https://dynamical.org/catalog/ecmwf-ifs-ens-forecast-46-day-daily-1-5-degree/)).
- ERA5 weekly observations, 20-year quintile boundaries and land-sea mask from the AI Weather
  Quest through [AI-WQ-package](https://ecmwf-ai-weather-quest.readthedocs.io/).
- Climate indices (research models): real-time RMM MJO index and weekly Indian Ocean Dipole index
  from the Australian Bureau of Meteorology; weekly Nino 3.4 SST anomaly from NOAA CPC.
- Fallback only: ERA5 daily statistics and land-sea mask from the Copernicus Climate Change
  Service Climate Data Store (Hersbach et al. 2020, doi:10.1038/s41586-020-0262-z), used under
  the Copernicus licence.

## License

MIT. See [LICENSE](LICENSE).
