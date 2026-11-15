"""ECMWF IFS ENS extended-range forecasts from dynamical.org, reduced to weekly aggregates.

Source dataset: "ecmwf-ifs-ens-forecast-46-day-daily-1-5-degree" (CC BY 4.0, ECMWF data
processed by dynamical.org). 101 members, 00 UTC runs, daily values that average the
previous 24 h, published about 48 h after initialisation (Saturday for a Thursday run).

lead_time = N days holds the mean over hours (N-1)*24 to N*24, i.e. calendar day N with
day 1 = the Thursday of initialisation. Window 1 (days 19-25) therefore uses lead_time
19..25 days and window 2 (days 26-32) uses 26..32 days.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .config import VARIABLES, Config
from .dates import ymd
from .grid import to_grid

ENS_NAMES = {
    "tas": "average_temperature_2m",
    "mslp": "pressure_reduced_to_mean_sea_level",
    "pr": "precipitation_surface",
}
LEAD_DAYS = {1: list(range(19, 26)), 2: list(range(26, 33))}

# int16 packing keeps the cache small (precision: 0.005 K, 0.5 Pa, 0.05 mm per week)
_ENCODING = {
    "tas": dict(dtype="int16", scale_factor=0.005, add_offset=260.0, _FillValue=np.int16(-32768)),
    "mslp": dict(dtype="int16", scale_factor=0.5, add_offset=100000.0, _FillValue=np.int16(-32768)),
    "pr": dict(dtype="uint16", scale_factor=0.05, add_offset=0.0, _FillValue=np.uint16(65535)),
}
_LIMITS = {"tas": (100.0, 420.0), "mslp": (84000.0, 116000.0), "pr": (0.0, 3270.0)}


def ens_path(cfg: Config, init: dt.date, var: str) -> Path:
    return cfg.ens_dir / f"{ymd(init)}_{var}.nc"


def is_cached(cfg: Config, init: dt.date, variables=VARIABLES) -> bool:
    return all(ens_path(cfg, init, v).exists() for v in variables)


def cached_inits(cfg: Config, variables=VARIABLES) -> list[dt.date]:
    dates = set()
    for p in cfg.ens_dir.glob("*_tas.nc"):
        try:
            d = dt.datetime.strptime(p.name[:8], "%Y%m%d").date()
        except ValueError:
            continue
        if is_cached(cfg, d, variables):
            dates.add(d)
    return sorted(dates)


def open_remote(cfg: Config) -> xr.Dataset:
    import dynamical_catalog

    return dynamical_catalog.open(cfg.dataset_id, chunks=None)


def remote_inits(ds: xr.Dataset) -> set[dt.date]:
    t = pd.to_datetime(ds["init_time"].values)
    return {x.date() for x in t if x.hour == 0}


def _to_obs_units(var: str, da: xr.DataArray) -> xr.DataArray:
    """Convert to the units of the ERA5 weekly files (K, Pa, mm). Decided from the values,
    which is robust to unit-label spellings: global means are ~278 K / ~5 degC, ~1e5 Pa /
    ~1e3 hPa, and ~3e-5 kg m-2 s-1 / ~2.7 mm per day."""
    mean = float(da.mean(skipna=True))
    if var == "tas":
        return da + 273.15 if mean < 150.0 else da
    if var == "mslp":
        return da * 100.0 if mean < 2000.0 else da
    if var == "pr":  # daily-mean rate -> mm per day
        return da * 86400.0 if mean < 0.01 else da
    raise ValueError(var)


def weekly_from_daily(var: str, daily: xr.DataArray) -> xr.DataArray:
    """daily: (lead_time, member, lat, lon) with the 14 leads 19..32 days -> (window, member, lat, lon)."""
    daily = _to_obs_units(var, daily)
    weeks = []
    for w, leads in LEAD_DAYS.items():
        sel = daily.sel(lead_time=pd.to_timedelta(leads, unit="D"))
        weeks.append(sel.sum("lead_time", skipna=False) if var == "pr" else sel.mean("lead_time", skipna=False))
    out = xr.concat(weeks, dim=pd.Index([1, 2], name="window"))
    if "ensemble_member" in out.dims:
        out = out.rename({"ensemble_member": "member"})
    out = to_grid(out).transpose("window", "member", "latitude", "longitude")
    lo, hi = _LIMITS[var]
    out = out.clip(lo, hi).astype(np.float32)
    # Keep only the four dimension coordinates. dynamical.org adds extra coordinates (init_time,
    # expected_forecast_length, ...) and dict-valued attributes such as 'statistics_approximate'
    # that cannot be written to netCDF.
    return xr.DataArray(np.asarray(out.values), dims=out.dims,
                        coords={d: np.asarray(out[d].values) for d in out.dims})


def download_init(ds: xr.Dataset, cfg: Config, init: dt.date, var: str) -> Path:
    leads = pd.to_timedelta(LEAD_DAYS[1] + LEAD_DAYS[2], unit="D")
    da = ds[ENS_NAMES[var]].sel(init_time=pd.Timestamp(init)).sel(lead_time=leads)
    da = da.load()
    if bool(da.isnull().all()):
        raise RuntimeError(f"{var} for {init} is entirely missing on dynamical.org")
    weekly = weekly_from_daily(var, da)
    weekly.attrs = {"units": {"tas": "K", "mslp": "Pa", "pr": "mm/week"}[var],
                    "source": f"ECMWF IFS ENS via dynamical.org ({cfg.dataset_id})",
                    "init": init.isoformat()}
    path = ens_path(cfg, init, var)
    tmp = path.with_suffix(".tmp")
    enc = dict(_ENCODING[var], zlib=True, complevel=4,
               chunksizes=(1, weekly.sizes["member"], weekly.sizes["latitude"], weekly.sizes["longitude"]))
    weekly.to_dataset(name=var).to_netcdf(tmp, encoding={var: enc})
    tmp.replace(path)
    return path


def fetch(cfg: Config, inits: list[dt.date], variables=VARIABLES, log=print) -> dict:
    """Download every missing (init, variable); returns {'done': [...], 'unavailable': [...]}."""
    # newest first: if a long backfill is interrupted, the most useful (recent) runs are in
    todo = sorted((d for d in inits if not is_cached(cfg, d, variables)), reverse=True)
    result = {"done": [], "unavailable": []}
    if not todo:
        log(f"ENS cache already holds all {len(inits)} requested initialisations.")
        return result
    log(f"Opening {cfg.dataset_id} on dynamical.org ...")
    ds = open_remote(cfg)
    avail = remote_inits(ds)
    latest = max(avail) if avail else None
    log(f"Remote archive: {len(avail)} runs, latest {latest}. Need {len(todo)} Thursday runs.")
    for k, init in enumerate(todo, 1):
        if init not in avail:
            log(f"  [{k}/{len(todo)}] {init}: not on dynamical.org yet (runs appear about 48 h after 00 UTC).")
            result["unavailable"].append(init)
            continue
        t0 = time.time()
        for var in variables:
            if ens_path(cfg, init, var).exists():
                continue
            for attempt in range(3):
                try:
                    download_init(ds, cfg, init, var)
                    break
                except Exception as e:  # network hiccups are common on long backfills
                    if attempt == 2:
                        raise
                    log(f"    retrying {var} {init} after error: {e}")
                    time.sleep(10 * (attempt + 1))
        log(f"  [{k}/{len(todo)}] {init}: done in {time.time() - t0:.0f} s")
        result["done"].append(init)
    return result


def load_members(cfg: Config, init: dt.date, var: str, window: int) -> np.ndarray:
    with xr.open_dataset(ens_path(cfg, init, var)) as ds:
        return ds[var].sel(window=int(window)).values.astype(np.float32)


def load_mean(cfg: Config, init: dt.date, var: str, window: int) -> np.ndarray:
    return np.nanmean(load_members(cfg, init, var, window), axis=0)
