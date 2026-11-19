"""Research data for R2: earlier ECMWF runs aligned to each Thursday's target weeks (lagged ensemble).

The competition allows "any data with a timestamp strictly prior or equal to Thursday 00 UTC"
(aiweatherquest.ecmwf.int/submitting-forecasts), and dynamical.org holds a 00 UTC ENS run for
every day since 2026-01-01. A run started `lag` days before Thursday reaches the same target weeks
(days 19-25 and 26-32 after Thursday) at lead days 19+lag..32+lag.

Files go to data/research/ens_lag/<thursday>_lag<L>_<var>.nc, in the same layout and packing as
the operational cache (window, member, latitude, longitude). They are never read by the
operational pipeline, whose cache is data/ens/.

    python -m aiwq.research_lag --lags 1 3
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .config import VARIABLES, Config, load_config
from .dates import ymd
from .ens import ENS_NAMES, LEAD_DAYS, _ENCODING, cached_inits, open_remote, remote_inits, weekly_from_daily


def lag_dir(cfg: Config) -> Path:
    d = cfg.data_dir / "research" / "ens_lag"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lag_path(cfg: Config, thursday: dt.date, lag: int, var: str) -> Path:
    return lag_dir(cfg) / f"{ymd(thursday)}_lag{lag}_{var}.nc"


def download_lagged(ds, cfg: Config, thursday: dt.date, lag: int, var: str) -> Path:
    run = thursday - dt.timedelta(days=lag)
    leads = pd.to_timedelta([d + lag for d in LEAD_DAYS[1] + LEAD_DAYS[2]], unit="D")
    da = ds[ENS_NAMES[var]].sel(init_time=pd.Timestamp(run)).sel(lead_time=leads).load()
    if bool(da.isnull().all()):
        raise RuntimeError(f"{var} for run {run} is entirely missing on dynamical.org")
    # relabel so that lead 19 means "day 19 after the Thursday"; the weekly aggregation is then shared
    da = da.assign_coords(lead_time=da["lead_time"] - pd.Timedelta(days=lag))
    weekly = weekly_from_daily(var, da)
    weekly.attrs = {"units": {"tas": "K", "mslp": "Pa", "pr": "mm/week"}[var],
                    "source": f"ECMWF IFS ENS via dynamical.org ({cfg.dataset_id})",
                    "run": run.isoformat(), "aligned_to_thursday": thursday.isoformat(), "lag_days": lag}
    path = lag_path(cfg, thursday, lag, var)
    tmp = path.with_suffix(".tmp")
    enc = dict(_ENCODING[var], zlib=True, complevel=4,
               chunksizes=(1, weekly.sizes["member"], weekly.sizes["latitude"], weekly.sizes["longitude"]))
    weekly.to_dataset(name=var).to_netcdf(tmp, encoding={var: enc})
    tmp.replace(path)
    return path


def load_lagged(cfg: Config, thursday: dt.date, lag: int, var: str, window: int) -> np.ndarray | None:
    import xarray as xr
    p = lag_path(cfg, thursday, lag, var)
    if not p.exists():
        return None
    with xr.open_dataset(p) as ds:
        return ds[var].sel(window=int(window)).values.astype(np.float32)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--lags", nargs="+", type=int, default=[1, 3])
    ap.add_argument("--vars", nargs="+", default=list(VARIABLES))
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    log = lambda m: print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}Z] {m}", flush=True)  # noqa: E731
    ds = open_remote(cfg)
    avail = remote_inits(ds)
    thursdays = sorted(cached_inits(cfg), reverse=True)  # newest first
    for lag in args.lags:
        for k, th in enumerate(thursdays, 1):
            run = th - dt.timedelta(days=lag)
            if run not in avail:
                log(f"lag {lag}: {th} -> run {run} not in the archive, skipped")
                continue
            t0 = time.time()
            for var in args.vars:
                if lag_path(cfg, th, lag, var).exists():
                    continue
                for attempt in range(3):
                    try:
                        download_lagged(ds, cfg, th, lag, var)
                        break
                    except Exception as e:  # network hiccups
                        if attempt == 2:
                            raise
                        log(f"  retry {var} {th} lag {lag}: {e}")
                        time.sleep(10 * (attempt + 1))
            log(f"lag {lag}: [{k}/{len(thursdays)}] {th} (run {run}) done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
