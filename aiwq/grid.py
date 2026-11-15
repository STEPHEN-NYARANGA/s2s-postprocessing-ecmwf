"""The competition grid: 1.5 degree, latitude 90 to -90, longitude 0 to 358.5."""

from __future__ import annotations

import numpy as np
import xarray as xr

LAT = np.round(np.arange(90.0, -90.1, -1.5), 6)  # 121 points, north to south
LON = np.round(np.arange(0.0, 360.0, 1.5), 6)    # 240 points, 0 to 358.5
SHAPE = (LAT.size, LON.size)

_LAT_NAMES = ("latitude", "lat", "latitudes", "lat_deg", "y")
_LON_NAMES = ("longitude", "lon", "longitudes", "lon_deg", "x")


def _find(da: xr.DataArray, names) -> str:
    for n in names:
        if n in da.dims or n in da.coords:
            return n
    raise ValueError(f"No coordinate among {names} in {list(da.dims)}")


def to_grid(da: xr.DataArray) -> xr.DataArray:
    """Rename lat/lon, convert longitudes to 0-360 and order the grid like the submission."""
    lat, lon = _find(da, _LAT_NAMES), _find(da, _LON_NAMES)
    da = da.rename({lat: "latitude", lon: "longitude"}) if (lat, lon) != ("latitude", "longitude") else da
    da = da.assign_coords(longitude=np.round(da["longitude"].values % 360.0, 6))
    da = da.sortby("longitude").sortby("latitude", ascending=False)
    if da.sizes["latitude"] != LAT.size or da.sizes["longitude"] != LON.size:
        raise ValueError(f"Expected a 121 x 240 grid, got {da.sizes['latitude']} x {da.sizes['longitude']}")
    if not (np.allclose(da["latitude"].values, LAT, atol=1e-3) and np.allclose(da["longitude"].values, LON, atol=1e-3)):
        raise ValueError("Grid points do not match the 1.5 degree competition grid")
    return da.assign_coords(latitude=LAT, longitude=LON)


def area_weights() -> np.ndarray:
    return np.repeat(np.cos(np.deg2rad(LAT))[:, None], LON.size, axis=1).astype(np.float64)


def band_index(bands) -> np.ndarray:
    """Index of the latitude band (from config blend_bands) for each of the 121 latitudes."""
    idx = np.full(LAT.size, -1, dtype=int)
    for k, (hi, lo) in enumerate(bands):
        sel = (LAT <= hi + 1e-6) & (LAT > lo + 1e-6) if k < len(bands) - 1 else (LAT <= hi + 1e-6) & (LAT >= lo - 1e-6)
        idx[sel & (idx < 0)] = k
    if (idx < 0).any():
        raise ValueError("blend_bands must cover 90 to -90")
    return idx


def prob_dataarray(p: np.ndarray, name: str = "probability") -> xr.DataArray:
    return xr.DataArray(
        p.astype(np.float64),
        dims=("quintile", "latitude", "longitude"),
        coords=dict(quintile=np.arange(1, 6) / 5.0, latitude=LAT, longitude=LON),
        name=name,
    )
