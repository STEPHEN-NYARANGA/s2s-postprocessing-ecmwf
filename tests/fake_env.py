"""A synthetic world for offline testing.

* A fake `dynamical_catalog` whose dataset mimics the dynamical.org ECMWF 46-day product
  (lat -90..90, lon -180..178.5, degC / Pa / kg m-2 s-1, daily means, 21 members).
* A fake `sites` (ECBox) module so the *real* AI_WQ_package functions run unchanged; its
  downloads are synthetic ERA5 weeks / quintile boundaries / land-sea mask, and uploads are
  recorded.

Truth for week starting Monday M, in standard units z:
    obs z = 0.7 a(M) + 0.71 e(M) (+0.3 warm trend for tas)
    member z_m = 0.7 a(M) + 0.3 noise_m       (under-dispersed)  + a fixed model bias
so a calibrated forecast has real skill and the raw ensemble does not.
"""

from __future__ import annotations

import datetime as dt
import functools
import io
import os
import sys
import tempfile
import types

import numpy as np
import pandas as pd
import xarray as xr
from scipy.ndimage import gaussian_filter
from scipy.stats import norm

from aiwq.grid import LAT, LON

NY, NX = LAT.size, LON.size
N_MEMBERS = 21
LAT2, LON2 = np.meshgrid(LAT, LON, indexing="ij")
VAR_ID = {"tas": 1, "mslp": 2, "pr": 3}


def smooth_noise(seed: int, sigma: float = 4.0) -> np.ndarray:
    f = np.random.default_rng(seed).standard_normal((NY, NX))
    f = gaussian_filter(f, sigma, mode=("nearest", "wrap"))
    return f / f.std()


BASE = {
    "tas": 300.0 - 45.0 * np.sin(np.deg2rad(LAT2)) ** 2,
    "mslp": 101300.0 + 800.0 * np.cos(np.deg2rad(2 * LAT2)),
}
SIG = {"tas": 2.0, "mslp": 600.0}
BIAS = {"tas": 1.5 * smooth_noise(11), "mslp": 300.0 * smooth_noise(12), "pr": 1.3}
BASE_PR = 20.0 + 40.0 * np.exp(-(LAT2 / 15.0) ** 2)
DESERT = (LAT2 >= 15) & (LAT2 <= 30) & (LON2 <= 45)
BASE_PR[DESERT] = 0.0
SHIFT = np.zeros((NY, NX))
band = (np.abs(LAT2) <= 10) & (LON2 >= 90) & (LON2 <= 180)
SHIFT[band] = ((LON2[band] - 90.0) / 90.0) * 0.95  # creates tied lower boundaries
LSM = ((smooth_noise(99, 8) > 0.3) | DESERT | band).astype(np.float64)


def pr_fun(z):
    return np.maximum(BASE_PR * (np.exp(0.5 * z) - SHIFT), 0.0)


def anom(var: str, monday: dt.date) -> np.ndarray:
    return smooth_noise(VAR_ID[var] * 1_000_000 + monday.toordinal(), 5.0)


def unpred(var: str, monday: dt.date) -> np.ndarray:
    return smooth_noise(VAR_ID[var] * 2_000_000 + monday.toordinal(), 5.0)


def obs_week(var: str, monday: dt.date) -> np.ndarray:
    z = 0.7 * anom(var, monday) + 0.71 * unpred(var, monday)
    if var == "tas":
        return BASE["tas"] + SIG["tas"] * (z + 0.3)
    if var == "mslp":
        return BASE["mslp"] + SIG["mslp"] * z
    return pr_fun(z)


def bounds(var: str) -> np.ndarray:
    z = norm.ppf([0.2, 0.4, 0.6, 0.8])[:, None, None]
    if var == "pr":
        return pr_fun(z)
    return BASE[var][None] + SIG[var] * z


@functools.lru_cache(maxsize=24)
def ens_week(var: str, init_ord: int, mon_ord: int) -> np.ndarray:
    """(M, ny, nx) weekly value per member on the competition grid, obs units."""
    monday = dt.date.fromordinal(mon_ord)
    rng = np.random.default_rng(init_ord * 10 + VAR_ID[var])
    z = 0.7 * anom(var, monday)[None] + 0.3 * rng.standard_normal((N_MEMBERS, NY, NX))
    if var == "pr":
        return BIAS["pr"] * pr_fun(z)
    return BASE[var][None] + BIAS[var][None] + SIG[var] * z


# ------------------------------------------------------------- fake dynamical dataset -----

FAKE_LAT = LAT[::-1]
FAKE_LON = np.arange(-180.0, 180.0, 1.5)
_LON_IDX = np.round((FAKE_LON % 360.0) / 1.5).astype(int)
NAMES = {"tas": "average_temperature_2m", "mslp": "pressure_reduced_to_mean_sea_level", "pr": "precipitation_surface"}


def _daily(var: str, init: dt.date, lead_days: int) -> np.ndarray:
    if lead_days == 0:
        return np.full((N_MEMBERS, NY, NX), np.nan, np.float32)
    d = init + dt.timedelta(days=lead_days - 1)          # calendar day covered by this lead
    monday = d - dt.timedelta(days=d.weekday())
    k = d.weekday()
    weekly = ens_week(var, init.toordinal(), monday.toordinal())
    if var == "pr":
        daily = weekly / 7.0 * (1.0 + 0.3 * np.sin(2 * np.pi * k / 7))  # sums to weekly
        daily = daily / 86400.0
    else:
        daily = weekly + (1.0 if var == "tas" else 100.0) * np.sin(2 * np.pi * k / 7)  # averages to weekly
        if var == "tas":
            daily = daily - 273.15
    return daily[:, ::-1, :][:, :, _LON_IDX].astype(np.float32)


def make_fake_dataset(inits: list[dt.date]) -> xr.Dataset:
    import dask.array as dsa

    leads = np.arange(0, 47)
    data_vars = {}
    for var, name in NAMES.items():
        def block(block_info=None, var=var):
            i, l = block_info[None]["chunk-location"][:2]
            return _daily(var, inits[i], int(leads[l]))[None, None]

        arr = dsa.map_blocks(block, chunks=((1,) * len(inits), (1,) * len(leads), (N_MEMBERS,), (NY,), (NX,)),
                             dtype=np.float32)
        units = {"tas": "degree_Celsius", "mslp": "Pa", "pr": "kg m-2 s-1"}[var]
        data_vars[name] = (("init_time", "lead_time", "ensemble_member", "latitude", "longitude"), arr, {"units": units})
    ds = xr.Dataset(
        data_vars,
        coords=dict(init_time=pd.to_datetime(inits), lead_time=pd.to_timedelta(leads, unit="D"),
                    ensemble_member=np.arange(N_MEMBERS), latitude=FAKE_LAT, longitude=FAKE_LON),
    )
    # Like the real dataset: extra coordinates and dict-valued attributes, which netCDF cannot store
    ds = ds.assign_coords(
        valid_time=ds["init_time"] + ds["lead_time"],
        expected_forecast_length=("init_time", np.full(len(inits), np.timedelta64(46 * 86400, "s"))),
    )
    for c in ds.coords:
        ds[c].attrs["statistics_approximate"] = {"min": "0 days 00:00:00", "max": "46 days 00:00:00"}
    return ds


def install_fake_dynamical(inits: list[dt.date]):
    mod = types.ModuleType("dynamical_catalog")
    ds = make_fake_dataset(inits)
    mod.open = lambda dataset_id, chunks=None, **kw: ds
    sys.modules["dynamical_catalog"] = mod


# ------------------------------------------------------------- fake ECBox -----------------

UPLOADS: dict[str, bytes] = {}
PASSWORD = "test-password"


def _nc_bytes(obj) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "x.nc")
        obj.to_netcdf(p)
        return open(p, "rb").read()


def _serve(remote_path: str) -> bytes:
    name = os.path.basename(remote_path)
    if name == "land_sea_mask_1pt5DEG.nc":
        da = xr.DataArray(LSM[None], dims=("time", "latitude", "longitude"),
                          coords=dict(time=[np.datetime64("2000-01-01")], latitude=LAT, longitude=LON), name="lsm")
        return _nc_bytes(da)
    if name == "AI_WQ_unique_IDs.csv":
        if remote_path in UPLOADS:
            return UPLOADS[remote_path]
        raise RuntimeError("404 not found")
    parts = name[:-3].split("_")
    var, date = parts[0], dt.datetime.strptime(parts[-1], "%Y%m%d").date()
    if "20yrCLIM" in name:
        # boundaries with 'lat'/'lon' names and a 'quantile' dim, as the package renames them
        da = xr.DataArray(bounds(var), dims=("quantile", "lat", "lon"),
                          coords=dict(quantile=[0.2, 0.4, 0.6, 0.8], lat=LAT, lon=LON), name=var)
        return _nc_bytes(da)
    if "_obs_" in name:
        if date + dt.timedelta(days=12) > dt.date(2026, 11, 14):
            raise RuntimeError("404 not found")
        t = np.datetime64(date)
        ds = xr.Dataset({var: (("time", "latitude", "longitude"), obs_week(var, date)[None]),
                         "time_bnds": (("time", "bnds"), np.array([[t, t + np.timedelta64(7, "D")]]))},
                        coords=dict(time=[t], latitude=LAT, longitude=LON))
        return _nc_bytes(ds)
    raise RuntimeError(f"404 not found: {remote_path}")


class _CM:
    def download(self, remote_path):
        return _serve(remote_path)

    def upload(self, local_path, remote_path=None, upload_zero_byte_files=False):
        key = (remote_path.rstrip("/") + "/" if remote_path else "") + os.path.basename(str(local_path))
        UPLOADS[key.lstrip("/")] = open(local_path, "rb").read()
        return {"ok": True}

    def list(self, remote_path, file_type=None, continuation_token=None):
        rp = remote_path.strip("/")
        files = [{"path": k} for k in UPLOADS if k.startswith(rp + "/")]
        if file_type is not None:
            files = [{"path": k.split("/")[1]} for k in UPLOADS if k.startswith("forecast_submissions/")]
        return {"files": files}


class _Site:
    @classmethod
    def from_space_and_name(cls, space, name):
        return cls()

    def get_content_manager(self, authenticator):
        if authenticator.token != PASSWORD:
            raise RuntimeError("401 unauthorised")
        return _CM()


class _Auth:
    def __init__(self, token):
        self.token = token

    @classmethod
    def from_token(cls, token):
        return cls(token)


def install_fake_sites():
    sites = types.ModuleType("sites"); sdk = types.ModuleType("sites.sdk")
    ss = types.ModuleType("sites.sdk.sites"); utils = types.ModuleType("sites.sdk.sites.utils")
    ss.Site, ss.Authenticator = _Site, _Auth
    utils.FileType = types.SimpleNamespace(DIR="dir", FILE="file")
    sys.modules.update({"sites": sites, "sites.sdk": sdk, "sites.sdk.sites": ss, "sites.sdk.sites.utils": utils})
    from AI_WQ_package import check_fc_submission as chk
    chk.check_registered_teamname = lambda t: print(f"(fake) {t} registered")
    chk.check_registered_modelname = lambda m: print(f"(fake) {m} registered")
    chk.check_forecast_data_window = lambda d: print("(fake) inside window")
