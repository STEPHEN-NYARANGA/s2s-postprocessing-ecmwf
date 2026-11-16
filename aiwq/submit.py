"""Submission through the official AI-WQ-package (ECBox upload)."""

from __future__ import annotations

import contextlib
import datetime as dt
import json

import numpy as np

from .config import VARIABLES, WINDOWS, Config
from .dates import submission_deadline, ymd
from .forecast import load_forecast
from .grid import prob_dataarray


def dry_run(cfg: Config, init: dt.date, variables=VARIABLES, windows=WINDOWS, log=print) -> bool:
    """Run the package's own checks without uploading anything."""
    from AI_WQ_package import check_fc_submission as chk

    ok = True
    try:
        chk.check_filename_characteristics("tas", ymd(init), "1", cfg.teamname, cfg.modelname)
        log(f"Team {cfg.teamname} and model {cfg.modelname} are registered and active.")
    except Exception as e:
        ok = False
        log(f"REGISTRATION CHECK FAILED: {e}")
    try:
        chk.check_forecast_data_window(ymd(init))
        log(f"Inside the submission window (closes {submission_deadline(init):%a %d %b %Y %H:%M} UTC).")
    except Exception as e:
        ok = False
        log(f"TIME WINDOW: {e}")
    for var in variables:
        for w in windows:
            try:
                da = prob_dataarray(load_forecast(cfg, init, var, w))
                da = chk.check_and_flip_latitudes(da)
                da = chk.check_and_convert_longitudes(da)
                da = chk.check_quintile_range(da)
                chk.check_data_characteristics(da, var, ymd(init), str(w))
                log(f"  {var} window {w}: array passes the package checks")
            except Exception as e:
                ok = False
                log(f"  {var} window {w}: FAILED: {e}")
    return ok


def export_for_email(cfg: Config, init: dt.date, variables=VARIABLES, windows=WINDOWS, log=print) -> list:
    """Write the six files for an email submission, as the organisers ask when ECBox upload is not
    possible (forum.ecmwf.int/t/14808): the array comes from AI_WQ_create_empty_dataarray, is filled
    with the probabilities and saved as {var}_{YYYYMMDD}_p{w}_{team}_{model}.nc."""
    from AI_WQ_package import check_fc_submission as chk
    from AI_WQ_package import forecast_submission as fs

    password = cfg.password
    outdir = cfg.output_dir / ymd(init) / "email"
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for var in variables:
        for w in windows:
            prob = load_forecast(cfg, init, var, w)
            if not np.allclose(prob.sum(axis=0), 1.0) or not np.isfinite(prob).all():
                raise ValueError(f"{var} window {w}: probabilities do not sum to 1")
            da = fs.AI_WQ_create_empty_dataarray(var, ymd(init), str(w), cfg.teamname, cfg.modelname, password)
            da.values = prob
            chk.check_data_characteristics(chk.check_quintile_range(da), var, ymd(init), str(w))
            path = outdir / f"{var}_{ymd(init)}_p{w}_{cfg.teamname}_{cfg.modelname}.nc"
            da.to_netcdf(path)
            paths.append(path)
            log(f"  {path.name}: written and passes the package checks")
    return paths


def submit(cfg: Config, init: dt.date, variables=VARIABLES, windows=WINDOWS, log=print) -> dict:
    from AI_WQ_package import forecast_submission as fs

    password = cfg.password
    workdir = cfg.output_dir / ymd(init) / "_submission_tmp"
    workdir.mkdir(parents=True, exist_ok=True)
    results = {}
    with contextlib.chdir(workdir):  # the package writes the netCDF in the working directory
        for var in variables:
            for w in windows:
                key = f"{var}_p{w}"
                try:
                    prob = load_forecast(cfg, init, var, w)
                    if not np.allclose(prob.sum(axis=0), 1.0) or not np.isfinite(prob).all():
                        raise ValueError("probabilities do not sum to 1")
                    da = fs.AI_WQ_create_empty_dataarray(var, ymd(init), str(w), cfg.teamname, cfg.modelname, password)
                    da.values = prob
                    fs.AI_WQ_forecast_submission(da, var, ymd(init), str(w), cfg.teamname, cfg.modelname, password)
                    fs.AI_WQ_check_submission(var, ymd(init), str(w), cfg.teamname, cfg.modelname, password)
                    results[key] = "submitted"
                    log(f"  {key}: submitted and confirmed on ECBox")
                except SystemExit:
                    raise
                except Exception as e:
                    results[key] = f"FAILED: {e}"
                    log(f"  {key}: FAILED: {e}")
    log_path = cfg.output_dir / ymd(init) / "submission_log.json"
    history = json.loads(log_path.read_text()) if log_path.exists() else []
    history.append({"time_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "results": results})
    log_path.write_text(json.dumps(history, indent=1))
    return results
