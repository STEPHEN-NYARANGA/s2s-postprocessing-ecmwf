"""Copy each week's results into results/ (tracked in Git) and rebuild results/README.md.

results/
  README.md                 index: method in one paragraph, backtest scores, one row per week
  backtest/                 leave-one-out report, scores table and weekly RPSS plot
  YYYYMMDD/
    quicklook_YYYYMMDD.png  maps of P(upper quintile) - P(lower quintile)
    forecast_summary.json   settings used for each variable and window
    crosscheck.md           independent checks of the files (python run.py crosscheck)
    submission/             the six NetCDF files exactly as submitted
    submission_log.json     ECBox upload results, when uploaded with python run.py submit
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import shutil
from pathlib import Path

from .config import Config
from .dates import window_monday, ymd

def _copy(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def publish(cfg: Config, init: dt.date, log=print) -> Path:
    out = cfg.results_dir
    week = cfg.output_dir / ymd(init)
    dst = out / ymd(init)
    for name in ("backtest_report.md", "backtest_scores.csv", "backtest_weekly_rpss.png"):
        _copy(cfg.output_dir / "backtest" / name, out / "backtest" / name)
    for name in (f"quicklook_{ymd(init)}.png", "forecast_summary.json", "crosscheck.md", "submission_log.json"):
        _copy(week / name, dst / name)
    n = sum(_copy(p, dst / "submission" / p.name) for p in sorted((week / "email").glob("*.nc")))
    log(f"results/{ymd(init)}: {n} submission files, maps, summary and cross-check copied")
    write_index(cfg)
    return dst


def _status(week: Path) -> str:
    log_path = week / "submission_log.json"
    if log_path.exists():
        last = json.loads(log_path.read_text())[-1]["results"]
        ok = sum(v == "submitted" for v in last.values())
        return f"uploaded to ECBox ({ok}/{len(last)} files)"
    note = week / "STATUS.txt"
    if note.exists():
        return note.read_text(encoding="utf-8").strip()
    return "files prepared"


def _crosscheck(week: Path) -> str:
    p = week / "crosscheck.md"
    if not p.exists():
        return "-"
    return "passed" if "all checks passed" in p.read_text(encoding="utf-8") else "**FAILED**"


def write_index(cfg: Config) -> Path:
    out = cfg.results_dir
    lines = [
        "# SeasonBlend results",
        "",
        f"Forecasts of team **{cfg.teamname}**, model **{cfg.modelname}**, in the "
        "[ECMWF AI Weather Quest](https://aiweatherquest.ecmwf.int/). Each week the Thursday 00 UTC "
        "ECMWF IFS ensemble (101 members) is bias-corrected against ERA5, counted in the official "
        "20-year ERA5 quintiles and blended with the recent observed quintile frequencies; the "
        "weights are fitted by leave-one-out on all verified 2026 forecasts (see the "
        "[main README](../README.md#method)). This folder is updated by `python run.py results`.",
        "",
    ]
    scores = out / "backtest" / "backtest_scores.csv"
    if scores.exists():
        rows = list(csv.DictReader(scores.open()))
        lines += ["## Backtest (leave-one-out RPSS; 0 = 20-year climatology, higher is better)", "",
                  "\"Cross-validated\" also chooses the settings and blend weights without the scored week, "
                  "so it is the honest estimate of future skill.", "",
                  "| Variable | Window | Training runs | Raw ECMWF | SeasonBlend | SeasonBlend, cross-validated |",
                  "|---|---|---|---|---|---|"]
        for r in rows:
            cv = r.get("final_cv")
            cv = f"{float(cv):+.3f}" if cv not in (None, "", "nan") else "next refit"
            lines.append(f"| {r['variable']} | days {'19-25' if r['window'] == '1' else '26-32'} | {r['n_train']} | "
                         f"{float(r['raw_ensemble']):+.3f} | **{float(r['final']):+.3f}** | {cv} |")
        lines += ["", "Full report: [backtest/backtest_report.md](backtest/backtest_report.md); weekly scores: "
                  "[backtest/backtest_weekly_rpss.png](backtest/backtest_weekly_rpss.png).", ""]
    exp = out / "experiments"
    if exp.is_dir() and any(exp.glob("*.md")):
        lines += ["## Research experiments", "",
                  "Candidate methods compared with SeasonBlend by `python run.py compare` (paired block bootstrap; "
                  "plan in [docs/research-plan.md](../docs/research-plan.md)):", ""]
        lines += [f"- [{p.stem.replace('_', ' ')}](experiments/{p.name})" for p in sorted(exp.glob("*.md"))]
        lines.append("")
    lines += ["## Weekly forecasts", "",
              "| Initialisation | Days 19-25 | Days 26-32 | Status | Cross-check | Maps | Files |",
              "|---|---|---|---|---|---|---|"]
    for d in sorted((p for p in out.iterdir() if p.is_dir() and p.name.isdigit()), reverse=True):
        init = dt.datetime.strptime(d.name, "%Y%m%d").date()
        w1, w2 = window_monday(init, 1), window_monday(init, 2)
        span = lambda m: f"{m:%d %b}-{m + dt.timedelta(days=6):%d %b}"  # noqa: E731
        week = cfg.output_dir / d.name
        lines.append(f"| {init:%a %d %b %Y} | {span(w1)} | {span(w2)} | {_status(week)} | "
                     f"[{_crosscheck(week)}]({d.name}/crosscheck.md) | "
                     f"[map]({d.name}/quicklook_{d.name}.png) | [6 NetCDF]({d.name}/submission/) |")
    lines += ["", "Each file holds the probabilities of the five ERA5 quintiles (dimensions quintile x "
              "latitude x longitude, 1.5 degree grid) for one variable and window, named "
              "`{var}_{YYYYMMDD}_p{window}_{team}_{model}.nc`.", ""]
    path = out / "README.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
