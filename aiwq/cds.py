"""ERA5 from the Copernicus Climate Data Store (CDS): a stand-in for the AI Weather Quest files on
ECBox (weekly observations, 20-year quintile boundaries, land-sea mask).

Use it when ECBox is not reachable: set  [obs] source = "cds"  in config.toml. Files are written
to data/obs_cds/ with the official names and layout, so the rest of the pipeline is unchanged and
the official files in data/obs/ take over again with  source = "ecbox".

Needs a free CDS account and its API key in ~/.cdsapirc (https://cds.climate.copernicus.eu/how-to-api).

Method, following AI_WQ_package.compute_20yr_quintile_climatology:
* daily means of ERA5 (six-hourly for tas and mslp, hourly for pr, regridded to 1.5 deg by the CDS);
* weekly values are 7-day means (tas, mslp) or totals (pr) starting on the given day;
* boundaries for day D are the 0.2/0.4/0.6/0.8 quantiles of the 100 weekly values that start on
  D + offset - n years, for offsets -4, -2, 0, 2, 4 days and n = 1..20.
The result is close to, but not guaranteed identical with, the official files (regridding and
precipitation accumulation conventions may differ slightly).
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .config import Config
from .dates import ymd
from .grid import LAT, LON, to_grid

CDS_VAR = {"tas": "2m_temperature", "mslp": "mean_sea_level_pressure", "pr": "total_precipitation"}
FREQ = {"tas": "6_hourly", "mslp": "6_hourly", "pr": "1_hourly"}
OFFSETS = (-4, -2, 0, 2, 4)
QUANTILES = (0.2, 0.4, 0.6, 0.8)
LATENCY_DAYS = 6  # ERA5T reaches the CDS about five days behind real time


def daily_path(cfg: Config, var: str, year: int) -> Path:
    return cfg.data_dir / "cds" / f"{var}_daily_{year}.nc"


def _unpack(download: str) -> str:
    """The CDS may return a zip with one netCDF inside."""
    if zipfile.is_zipfile(download):
        d = tempfile.mkdtemp()
        with zipfile.ZipFile(download) as z:
            z.extractall(d)
        ncs = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".nc")]
        if len(ncs) != 1:
            raise RuntimeError(f"Expected one netCDF in the CDS zip, found {ncs}")
        return ncs[0]
    return download


def _to_daily(var: str, path: str) -> xr.DataArray:
    with xr.open_dataset(path) as ds:
        name = [v for v in ds.data_vars if ds[v].ndim == 3][0]
        da = ds[name].load()
    tname = "valid_time" if "valid_time" in da.dims else "time"
    da = da.rename({tname: "time"})
    da["time"] = pd.to_datetime(da["time"].values).normalize()
    da = to_grid(da).transpose("time", "latitude", "longitude")
    if var == "pr":  # daily mean of hourly accumulations (m) -> daily total in mm
        da = da * 24.0 * 1000.0
    return da.astype(np.float32)


def download_year(cfg: Config, var: str, year: int, log=print) -> Path:
    """Daily ERA5 for one variable and year (up to the latest published day for the current year)."""
    path = daily_path(cfg, var, year)
    last_day = dt.date.today() - dt.timedelta(days=LATENCY_DAYS)
    complete = year < last_day.year
    if path.exists():
        with xr.open_dataset(path) as ds:
            have = pd.Timestamp(ds["time"].values[-1]).date()
        if complete or have >= last_day:
            return path
    import cdsapi

    months = range(1, 13 if complete else last_day.month + 1)
    tmpdir = tempfile.mkdtemp()
    t0 = time.time()
    try:
        client = cdsapi.Client(quiet=True)
        parts = []
        for m in months:  # one month per request: a whole year exceeds the CDS cost limit
            request = {
                "product_type": "reanalysis",
                "variable": [CDS_VAR[var]],
                "year": str(year),
                "month": [f"{m:02d}"],
                "day": [f"{d:02d}" for d in range(1, 32)],
                "daily_statistic": "daily_mean",
                "time_zone": "utc+00:00",
                "frequency": FREQ[var],
                "grid": [1.5, 1.5],
            }
            target = os.path.join(tmpdir, f"download_{m:02d}")
            client.retrieve("derived-era5-single-levels-daily-statistics", request, target)
            parts.append(_to_daily(var, _unpack(target)))
        daily = xr.concat(parts, dim="time").sortby("time")
        if not complete:
            daily = daily.sel(time=slice(None, str(last_day)))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        daily.to_dataset(name=var).to_netcdf(tmp, encoding={var: {"zlib": True, "complevel": 4}})
        tmp.replace(path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    log(f"  CDS {var} {year}: {daily.sizes['time']} days in {time.time() - t0:.0f} s")
    return path


def ensure_daily(cfg: Config, variables, first_year: int, log=print, workers: int = 6) -> None:
    """Download every missing (variable, year) from first_year to the current year, in parallel."""
    years = range(first_year, dt.date.today().year + 1)
    jobs = [(v, y) for v in variables for y in years]
    log(f"CDS: checking {len(jobs)} variable-years ({first_year}-{years[-1]}) ...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_year, cfg, v, y, log): (v, y) for v, y in jobs}
        for f in as_completed(futures):
            v, y = futures[f]
            try:
                f.result()
            except Exception as e:  # keep going; a rerun retries the missing years
                log(f"  CDS {v} {y} FAILED: {type(e).__name__}: {str(e)[:300]}")


# ---------------------------------------------------------------- building files ----------

_DAILY_CACHE: dict[str, xr.DataArray] = {}


def daily_series(cfg: Config, var: str) -> xr.DataArray:
    if var not in _DAILY_CACHE:
        files = sorted((cfg.data_dir / "cds").glob(f"{var}_daily_*.nc"))
        if not files:
            raise FileNotFoundError(f"No CDS daily files for {var}; run fetch-obs with [obs] source = 'cds'")
        parts = []
        for p in files:
            with xr.open_dataset(p) as ds:
                parts.append(ds[var].load())
        da = xr.concat(parts, dim="time").sortby("time")
        _DAILY_CACHE[var] = da
    return _DAILY_CACHE[var]


def _weekly(daily: xr.DataArray, start: pd.Timestamp, var: str) -> np.ndarray | None:
    sel = daily.sel(time=slice(start, start + pd.Timedelta(days=6)))
    if sel.sizes["time"] != 7:
        return None
    return (sel.sum("time") if var == "pr" else sel.mean("time")).values


def _write(da: xr.DataArray, path: Path, attrs: dict) -> None:
    da.attrs.update(attrs)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    da.to_netcdf(tmp)
    tmp.replace(path)


def build_obs(cfg: Config, var: str, monday: dt.date, path: Path) -> bool:
    w = _weekly(daily_series(cfg, var), pd.Timestamp(monday), var)
    if w is None:
        return False
    da = xr.DataArray(w, dims=("latitude", "longitude"), coords=dict(latitude=LAT, longitude=LON), name=var)
    _write(da, path, {"source": "ERA5 daily statistics from the Copernicus CDS (stand-in for ECBox)",
                      "units": {"tas": "K", "mslp": "Pa", "pr": "mm/week"}[var]})
    return True


def build_clim(cfg: Config, var: str, date: dt.date, path: Path) -> bool:
    daily = daily_series(cfg, var)
    d0 = pd.Timestamp(date)
    samples = []
    for n in range(1, 21):
        for off in OFFSETS:
            w = _weekly(daily, d0 - pd.DateOffset(years=n) + pd.Timedelta(days=off), var)
            if w is None:
                return False
            samples.append(w)
    q = np.quantile(np.stack(samples), QUANTILES, axis=0).astype(np.float32)  # linear, like xarray
    da = xr.DataArray(q, dims=("quantile", "latitude", "longitude"),
                      coords=dict(quantile=list(QUANTILES), latitude=LAT, longitude=LON), name=var)
    _write(da, path, {"source": "20-year ERA5 quintiles from CDS daily statistics (stand-in for ECBox)"})
    return True


def build_lsm(cfg: Config, path: Path) -> None:
    import cdsapi

    tmpdir = tempfile.mkdtemp()
    try:
        target = os.path.join(tmpdir, "lsm")
        cdsapi.Client(quiet=True).retrieve("reanalysis-era5-single-levels", {
            "product_type": ["reanalysis"], "variable": ["land_sea_mask"],
            "year": ["2020"], "month": ["01"], "day": ["01"], "time": ["00:00"],
            "grid": [1.5, 1.5], "data_format": "netcdf"}, target)
        with xr.open_dataset(_unpack(target)) as ds:
            da = ds[list(ds.data_vars)[0]].load().squeeze(drop=True)
        da = to_grid(da)
        da = xr.DataArray(da.values.astype(np.float32), dims=("latitude", "longitude"),
                          coords=dict(latitude=LAT, longitude=LON), name="lsm")
        _write(da, path, {"source": "ERA5 land-sea mask from the Copernicus CDS"})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
