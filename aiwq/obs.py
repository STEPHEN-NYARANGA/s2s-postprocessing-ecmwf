"""ERA5 weekly observations, 20-year quintile boundaries and the land-sea mask.

Everything comes from the official AI-WQ-package (ECBox, needs the submission password),
so the truth and the quintile boundaries are exactly those used for the leaderboards.
Files are cached under data/obs/ and reused.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import numpy as np
import xarray as xr

from .config import VARIABLES, Config
from .dates import mondays, obs_ready, utc_today, ymd
from .grid import to_grid

_RETRY_HOURS = 12.0
LAST_ERROR: list[str] = [""]


def _kind(var: str) -> str:
    return "WEEKLYSUM" if var == "pr" else "WEEKLYMEAN"


def obs_file(cfg: Config, var: str, monday: dt.date) -> Path:
    return cfg.obs_dir / var / f"{var}_obs_{_kind(var)}_{ymd(monday)}.nc"


def clim_file(cfg: Config, var: str, date: dt.date) -> Path:
    return cfg.obs_dir / var / f"{var}_20yrCLIM_{_kind(var)}_quintiles_{ymd(date)}.nc"


def lsm_file(cfg: Config) -> Path:
    return cfg.obs_dir / "land_sea_mask_1pt5DEG.nc"


# ---------------------------------------------------------------- reading ---------------

def _read_field(path: Path) -> tuple[xr.DataArray, list]:
    with xr.open_dataset(path) as ds:
        def has_ll(v):
            dims = set(ds[v].dims)
            return bool(dims & {"latitude", "lat"}) and bool(dims & {"longitude", "lon"})

        names = [v for v in ds.data_vars if "bnds" not in v and "bounds" not in v and has_ll(v)]
        if not names:
            raise ValueError(f"No gridded variable in {path.name}")
        da = ds[names[0]].load()
    da = da.squeeze(drop=True)
    da = to_grid(da)
    extra = [d for d in da.dims if d not in ("latitude", "longitude")]
    for d in extra[:]:
        if da.sizes[d] == 1:
            da = da.isel({d: 0}, drop=True)
            extra.remove(d)
    return da, extra


def _harmonise(var: str, arr: np.ndarray) -> np.ndarray:
    """ERA5 files should already be K, Pa and mm per week; guard against other units."""
    if var == "tas" and np.nanmean(arr) < 150.0:
        return arr + 273.15
    if var == "mslp" and np.nanmean(arr) < 2000.0:
        return arr * 100.0
    if var == "pr" and np.nanmax(arr) < 5.0:  # metres per week
        return arr * 1000.0
    return arr


def read_obs(path: Path, var: str) -> np.ndarray:
    da, extra = _read_field(path)
    if extra:
        raise ValueError(f"Unexpected dimensions {extra} in {path.name}")
    return _harmonise(var, da.transpose("latitude", "longitude").values.astype(np.float32))


def read_clim(path: Path, var: str) -> np.ndarray:
    da, extra = _read_field(path)
    if len(extra) != 1:
        raise ValueError(f"Expected one quantile dimension in {path.name}, found {extra}")
    q = extra[0]
    da = da.transpose(q, "latitude", "longitude")
    if da.sizes[q] == 5:  # drop a 1.0 (maximum) level if present
        qv = np.asarray(da[q].values, dtype=float) if q in da.coords else np.arange(1, 6) / 5
        keep = np.where(qv < 0.99)[0] if (qv > 0.99).any() else np.arange(4)
        da = da.isel({q: keep})
    if da.sizes[q] != 4:
        raise ValueError(f"Expected 4 quintile boundaries in {path.name}, found {da.sizes[q]}")
    vals = da.values.astype(np.float32)
    vals = np.sort(vals, axis=0)  # boundaries must be non-decreasing
    return _harmonise(var, vals)


# ---------------------------------------------------------------- downloading -----------

class _Missing:
    """Remembers failed downloads so a weekly run does not hammer ECBox for files that are
    not yet published."""

    def __init__(self, cfg: Config):
        self.path = cfg.obs_dir / "missing.json"
        try:
            self.data = json.loads(self.path.read_text())
        except Exception:
            self.data = {}

    def recent(self, key: str) -> bool:
        t = self.data.get(key)
        return t is not None and (time.time() - t) < _RETRY_HOURS * 3600

    def mark(self, key: str):
        self.data[key] = time.time()
        self.path.write_text(json.dumps(self.data))

    def clear(self, key: str):
        if self.data.pop(key, None) is not None:
            self.path.write_text(json.dumps(self.data))


def _download(cfg: Config, func_name: str, args: tuple, target: Path, missing: _Missing | None) -> bool:
    if cfg.obs_source == "cds":  # build the same file from Copernicus ERA5 instead of ECBox
        from . import cds

        var, date = args[1], dt.datetime.strptime(args[0], "%Y%m%d").date()
        builder = cds.build_obs if func_name == "retrieve_weekly_obs" else cds.build_clim
        try:
            return builder(cfg, var, date, target)
        except Exception as e:
            LAST_ERROR[0] = f"{type(e).__name__}: {e}"
            return False
    key = target.name
    if missing is not None and missing.recent(key):
        return False
    from AI_WQ_package import retrieve_evaluation_data as red

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        getattr(red, func_name)(*args, cfg.password, local_destination=str(target.parent))
    except SystemExit:
        raise
    except Exception as e:  # the file may still be fine (the package also opens it); check below
        LAST_ERROR[0] = f"{type(e).__name__}: {e}" + (f" (cause: {e.__cause__})" if e.__cause__ else "")
    ok = target.exists() and target.stat().st_size > 0
    if ok:
        try:
            _read_field(target)
        except Exception:
            ok = False
    if not ok:
        if target.exists():
            target.unlink()
        if missing is not None:
            missing.mark(key)
        return False
    if missing is not None:
        missing.clear(key)
    return True


def get_obs(cfg: Config, monday: dt.date, var: str, download: bool = True, missing=None):
    path = obs_file(cfg, var, monday)
    if not path.exists():
        if not download or not obs_ready(monday, cfg.obs_latency_days):
            return None
        if not _download(cfg, "retrieve_weekly_obs", (ymd(monday), var), path, missing or _Missing(cfg)):
            return None
    return read_obs(path, var)


def get_clim(cfg: Config, date: dt.date, var: str, download: bool = True, missing=None):
    path = clim_file(cfg, var, date)
    if not path.exists():
        if not download:
            return None
        if not _download(cfg, "retrieve_20yr_quantile_clim", (ymd(date), var), path, missing or _Missing(cfg)):
            return None
    return read_clim(path, var)


def get_lsm(cfg: Config) -> np.ndarray:
    path = lsm_file(cfg)
    if not path.exists() and cfg.obs_source == "cds":
        from . import cds

        cds.build_lsm(cfg, path)
    elif not path.exists():
        from AI_WQ_package import retrieve_evaluation_data as red

        red.retrieve_land_sea_mask(cfg.password, local_destination=str(path.parent))
    da, extra = _read_field(path)
    if extra:
        raise ValueError(f"Unexpected dimensions {extra} in land-sea mask")
    lsm = da.transpose("latitude", "longitude").values.astype(np.float32)
    if np.nanmax(lsm) > 1.5:  # percent
        lsm = lsm / 100.0
    return lsm


def backfill(cfg: Config, variables=VARIABLES, start: dt.date | None = None, log=print) -> dict:
    """Download weekly obs + quintile boundaries for every published Monday."""
    from .dates import parse_date

    start = start or parse_date(cfg.obs_first_monday)
    today = utc_today()
    weeks = [m for m in mondays(start, today) if obs_ready(m, cfg.obs_latency_days, today)]
    missing = _Missing(cfg)
    if cfg.obs_source == "cds":  # daily ERA5 for the 20 years before the first week, then build files
        from . import cds

        cds.ensure_daily(cfg, variables, first_year=start.year - 20, log=log)
    get_lsm(cfg)
    stats = {}
    for var in variables:
        todo = [m for m in weeks if not (obs_file(cfg, var, m).exists() and clim_file(cfg, var, m).exists())]
        log(f"{var}: {len(weeks)} published weeks since {start}, {len(todo)} to download")
        n_ok = 0
        t0 = time.time()
        for k, m in enumerate(todo, 1):
            o = get_obs(cfg, m, var, missing=missing)
            c = get_clim(cfg, m, var, missing=missing)
            n_ok += (o is not None) and (c is not None)
            if k % 10 == 0 or k == len(todo):
                log(f"  {var}: {k}/{len(todo)} weeks ({time.time() - t0:.0f} s)")
        if todo and n_ok == 0:
            log(f"  WARNING: nothing could be downloaded for {var}. Last error: {LAST_ERROR[0]}")
            log("  Check the AIWQ_PASSWORD value and that sites-toolkit is installed (README step 2).")
        stats[var] = {"weeks": len(weeks), "downloaded": n_ok, "requested": len(todo)}
    return stats


def available_weeks(cfg: Config, var: str) -> list[dt.date]:
    """Mondays for which both the observation and the boundaries are cached."""
    out = []
    for p in (cfg.obs_dir / var).glob(f"{var}_obs_*.nc"):
        d = dt.datetime.strptime(p.stem.split("_")[-1], "%Y%m%d").date()
        if clim_file(cfg, var, d).exists():
            out.append(d)
    return sorted(out)
