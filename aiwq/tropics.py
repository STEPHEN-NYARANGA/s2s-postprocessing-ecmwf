"""MJO phase and tropical-storm-day forecasts (the Quest's two extra variables), a separate model.

Both are statistical, built only from the official AIWQ training data on ECBox and the Bureau of
Meteorology real-time RMM index, and scored exactly as in AI_WQ_package.forecast_evaluation.

Tropical storms (TS), tercile probabilities of weekly storm days per basin
    The official tercile bounds come from 100 historical weeks (20 years x 5 day offsets). Storm-day
    counts are integers with many zero weeks, so bounds often tie (lower = 0, or lower = upper) and the
    categories are far from equally likely: "< 0" can never happen. The evaluation reference is a flat
    1/3 forecast. Our forecast is the frequency of each category in that same 100-week sample,
    computed with the evaluation's own category rule; it beats the flat reference whenever the
    categories are unequal. Optional: weight the sample years by ENSO similarity (off unless the
    hindcast shows a gain).

MJO, phase probabilities (inactive + 8 phases) at days 8, 15, 22 and 29
    Kernel analogues: past days whose (RMM1, RMM2) state is close to the latest observed state and
    whose calendar day is within a seasonal window; the forecast is the weighted frequency of the
    phase observed the same number of days later (inactive when amplitude < 1, as in the evaluation).
    Leaves out the target year and its neighbours in hindcasts. The evaluation reference is the
    official 20-year climatology, so any skill here is genuine.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import glob
import io
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .config import Config
from .dates import ymd

BASINS = ("ATL", "NWP", "SWIO", "SEIO")
MJO_LAGS = (7, 14, 21, 28)          # valid times: days 8, 15, 22, 29 (only 22 and 29 are scored)
TS_START = {1: 18, 2: 25}           # target week starts this many days after initialisation (a Monday)
OFFSETS = (-4, -2, 0, 2, 4)         # official climatology day offsets
YEARS = range(-20, 0)               # official climatology: the 20 previous years


@dataclass
class TropicsSettings:
    modelname: str = ""
    mjo_bandwidth: float = 0.75     # kernel width in RMM units
    mjo_season_days: int = 45       # +/- calendar window for analogues
    mjo_weight: float = 1.0         # weight of the analogue forecast vs climatology
    ts_enso_weighting: bool = False


def data_dir(cfg: Config) -> Path:
    return cfg.data_dir / "mjo_ts"


def fetch_training(cfg: Config, last_year: int | None = None, log=print) -> None:
    """Download the official TS (weekly storm days) and MJO (daily RMM) training files from ECBox."""
    from AI_WQ_package import retrieve_training_data as rt

    out = data_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    last_year = last_year or dt.date.today().year
    for var, years, stem in (("TS", range(1980, last_year), "TS_sevenday_WEEKLYTSDAYS"),
                             ("MJO", range(1979, last_year + 1), "MJO_DAILY")):
        for y in years:
            fn = out / f"{stem}_{y}.nc"
            if fn.exists() and not (var == "MJO" and y == last_year):
                continue
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    rt.retrieve_annual_training_data(y, var, cfg.password, local_destination=str(out))
                log(f"  {fn.name}")
            except Exception as e:  # noqa: BLE001 - the newest year may not exist yet
                log(f"  {fn.name}: not available ({type(e).__name__})")


# ----------------------------------------------------------------------------- tropical storms
def load_ts(cfg: Config) -> pd.DataFrame:
    """Storm days in [t, t + 7) for each basin, indexed by day t."""
    parts = []
    for f in sorted(glob.glob(str(data_dir(cfg) / "TS_sevenday_WEEKLYTSDAYS_*.nc"))):
        da = xr.open_dataset(f)["__xarray_dataarray_variable__"].load()
        dim = "basin" if "basin" in da.dims else "domain"
        da = da.rename({dim: "basin"})
        if [str(b) for b in da.basin.values] != list(BASINS):
            raise ValueError(f"{f}: unexpected basin order {da.basin.values}")
        parts.append(da.to_pandas())
    ts = pd.concat(parts)
    ts.index = pd.to_datetime(ts.index).normalize()
    return ts[~ts.index.duplicated()].sort_index()


def ts_sample(ts: pd.DataFrame, target: dt.date) -> tuple[np.ndarray, np.ndarray]:
    """The official 100-week sample (rows) for a target week, and the year of each row."""
    rows, years = [], []
    for yd in YEARS:
        for dd in OFFSETS:
            t = pd.Timestamp(target) + pd.DateOffset(years=yd) + pd.Timedelta(days=dd)
            if t in ts.index:
                rows.append(ts.loc[t].values)
                years.append(t.year)
    return np.array(rows, dtype=float), np.array(years)


def ts_bounds(sample: np.ndarray) -> np.ndarray:
    """Lower and upper tercile bounds per basin, exactly as TS_processing (numpy percentile)."""
    return np.percentile(sample, [100 / 3, 200 / 3], axis=0)


def ts_category(x: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """One-hot categories (3, ...) with forecast_evaluation.conditional_obs_probs' rule. When the two
    bounds are equal the official code masks the week (NaN): it is not scored."""
    x, lo, hi = np.broadcast_arrays(np.asarray(x, float), np.asarray(lo, float), np.asarray(hi, float))
    c0 = x < lo
    c1 = (lo <= x) & (x < hi) & (lo != hi)
    c2 = x >= hi
    out = np.stack([c0, c1, c2]).astype(float)
    out[:, lo == hi] = np.nan
    return out


def official_ts_bounds(cfg: Config, target: dt.date) -> np.ndarray:
    """The official tercile bounds (2, 4) for a target week, from ECBox. They carry floating-point
    noise from numpy's percentile (e.g. 2.000000000000014 or 0.9999999999999858) that decides the
    category of an integer count equal to the bound, so real-time forecasts use these exact values."""
    from AI_WQ_package import retrieve_evaluation_data as red

    out = data_dir(cfg)
    with contextlib.redirect_stdout(io.StringIO()):
        da = red.retrieve_20yr_quantile_clim(ymd(target), "TS", cfg.password, local_destination=str(out))
    da = da.transpose("tercile", ...)
    if [str(b) for b in da["basin"].values] != list(BASINS):
        raise ValueError(f"unexpected basin order in the official TS climatology: {da['basin'].values}")
    return da.values.astype(float)


def ts_forecast(ts: pd.DataFrame, target: dt.date, enso_weights: np.ndarray | None = None,
                bounds: np.ndarray | None = None) -> np.ndarray:
    """(3, 4) tercile probabilities: frequency of each category in the official sample. A basin whose
    bounds tie is not scored; it gets 1/3 each so that the file still passes the sum check.
    `bounds` (2, 4): the official bounds; by default recomputed from the sample."""
    s, yrs = ts_sample(ts, target)
    lo, hi = ts_bounds(s) if bounds is None else bounds
    cats = ts_category(s.T, lo[:, None], hi[:, None])  # (3, 4 basins, n weeks)
    w = np.ones(len(s)) if enso_weights is None else enso_weights
    p = (np.nan_to_num(cats) * w).sum(axis=2) / w.sum()
    p[:, lo == hi] = 1 / 3
    return p


# ----------------------------------------------------------------------------- MJO
def load_mjo(cfg: Config) -> pd.DataFrame:
    parts = [xr.open_dataset(f).load().to_dataframe() for f in
             sorted(glob.glob(str(data_dir(cfg) / "MJO_DAILY_*.nc")))]
    m = pd.concat(parts)
    m.index = pd.to_datetime(m.index).normalize()
    m = m[~m.index.duplicated()].sort_index()
    m["cat"] = np.where(m["amplitude"] < 1.0, 0, m["phase"]).astype(int)
    return m


def mjo_category(rmm1: float, rmm2: float) -> int:
    """Inactive (0) or Wheeler-Hendon phase 1-8 from the RMM components."""
    if np.hypot(rmm1, rmm2) < 1.0:
        return 0
    ang = np.degrees(np.arctan2(rmm2, rmm1)) % 360  # phase 1 starts at 180 degrees
    return int(((ang - 180) % 360) // 45) + 1


def mjo_clim(m: pd.DataFrame, valid: dt.date) -> np.ndarray:
    c = []
    for yd in YEARS:
        for dd in OFFSETS:
            t = pd.Timestamp(valid) + pd.DateOffset(years=yd) + pd.Timedelta(days=dd)
            if t in m.index:
                c.append(m["cat"][t])
    return np.bincount(c, minlength=9) / len(c)


def mjo_analogue(m: pd.DataFrame, state: tuple[float, float], state_date: dt.date, lead: int,
                 st: TropicsSettings, exclude_years=()) -> np.ndarray:
    """Weighted frequency of the phase `lead` days after past states near `state` in the same season."""
    X = m[["RMM1", "RMM2"]].to_numpy()
    doy = m.index.dayofyear.to_numpy()
    yrs = m.index.year.to_numpy()
    sdoy = pd.Timestamp(state_date).dayofyear
    dd = np.abs(((doy - sdoy + 182) % 365) - 182)
    n = len(m)
    ok = (dd <= st.mjo_season_days) & (np.arange(n) + lead < n) & np.isfinite(X).all(axis=1)
    ok &= m.index.to_numpy() + np.timedelta64(lead, "D") <= np.datetime64(pd.Timestamp(state_date))  # no future data
    for y in exclude_years:
        ok &= yrs != y
    j = np.where(ok)[0]
    # outcome day must exist exactly `lead` days later
    out_idx = m.index.get_indexer(m.index[j] + pd.Timedelta(days=lead))
    keep = out_idx >= 0
    j, out_idx = j[keep], out_idx[keep]
    w = np.exp(-np.sum((X[j] - np.asarray(state)) ** 2, axis=1) / (2 * st.mjo_bandwidth ** 2))
    p = np.bincount(m["cat"].to_numpy()[out_idx], weights=w, minlength=9)
    return p / p.sum()


def mjo_forecast(m: pd.DataFrame, init: dt.date, state: tuple[float, float], state_date: dt.date,
                 st: TropicsSettings, exclude_years=()) -> np.ndarray:
    """(9, 4) probabilities for the valid times init + 7, 14, 21, 28 days."""
    cols = []
    for lag in MJO_LAGS:
        valid = init + dt.timedelta(days=lag)
        lead = (valid - state_date).days
        a = mjo_analogue(m, state, state_date, lead, st, exclude_years)
        c = mjo_clim(m, valid)
        cols.append(st.mjo_weight * a + (1 - st.mjo_weight) * c)
    return np.stack(cols, axis=1)


# ----------------------------------------------------------------------------- scores
def rps(f: np.ndarray, o: np.ndarray) -> float:
    return float(np.sum((np.cumsum(f) - np.cumsum(o)) ** 2))


def brier(f: np.ndarray, o: np.ndarray) -> float:
    return float(np.mean((f - o) ** 2))


def djf_inits(year: int) -> list[dt.date]:
    """The 13 Thursdays of a DJF competition period starting in November of `year`."""
    d = dt.date(year, 11, 12)
    d += dt.timedelta(days=(3 - d.weekday()) % 7)
    return [d + dt.timedelta(weeks=k) for k in range(13)]


def hindcast_ts(ts: pd.DataFrame, years=range(2001, 2026)) -> pd.DataFrame:
    rows = []
    for Y in years:
        for init in djf_inits(Y):
            for p, off in TS_START.items():
                tgt = init + dt.timedelta(days=off)
                if pd.Timestamp(tgt) not in ts.index:
                    continue
                f = ts_forecast(ts, tgt)
                s, _ = ts_sample(ts, tgt)
                lo, hi = ts_bounds(s)
                o = ts_category(ts.loc[pd.Timestamp(tgt)].to_numpy(float), lo, hi)
                for j, b in enumerate(BASINS):
                    if np.isnan(o[:, j]).any():
                        continue  # tied bounds: not scored by the Quest
                    rows.append(dict(year=Y, init=init, period=p, basin=b, rps=rps(f[:, j], o[:, j]),
                                     rps_ref=rps(np.full(3, 1 / 3), o[:, j])))
    return pd.DataFrame(rows)


def hindcast_mjo(m: pd.DataFrame, bom: pd.DataFrame | None, st: TropicsSettings,
                 years=range(2001, 2026), state_lag: int = 2) -> pd.DataFrame:
    """Leave-three-years-out MJO hindcast for DJF inits; the state is taken `state_lag` days before init
    from `bom` (real-time BoM RMM) when given, else from the official series."""
    src = bom if bom is not None else m
    rows = []
    for Y in years:
        for init in djf_inits(Y):
            sd = init - dt.timedelta(days=state_lag)
            if pd.Timestamp(sd) not in src.index:
                continue
            state = tuple(src.loc[pd.Timestamp(sd), ["RMM1", "RMM2"]].astype(float))
            excl = {Y - 1, Y, Y + 1, Y + 2}
            f = mjo_forecast(m, init, state, sd, st, exclude_years=excl)
            for k, lag in enumerate(MJO_LAGS):
                v = pd.Timestamp(init + dt.timedelta(days=lag))
                if v not in m.index:
                    continue
                o = np.zeros(9); o[m["cat"][v]] = 1
                rows.append(dict(year=Y, init=init, lag=lag, bs=brier(f[:, k], o),
                                 bs_ref=brier(mjo_clim(m, v.date()), o)))
    return pd.DataFrame(rows)


def read_bom_rmm(cfg: Config) -> pd.DataFrame:
    from .indices import read_rmm

    r = read_rmm(cfg)
    df = pd.DataFrame([(d, v[0], v[1]) for d, v in r.items()], columns=["date", "RMM1", "RMM2"]).set_index("date")
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


# ----------------------------------------------------------------------------- real-time forecast and files
def make_forecast(cfg: Config, init: dt.date, st: TropicsSettings, log=print) -> dict:
    """Probabilities for one initialisation; uses only data dated on or before init."""
    ts = load_ts(cfg)
    m = load_mjo(cfg)
    m = m[m.index <= pd.Timestamp(init)]
    # The rules allow any data timestamped on or before Thursday 00 UTC, whenever it is published, so
    # the BoM value for the day before init (posted a day or two later) is allowed.
    bom = read_bom_rmm(cfg)
    bom = bom[bom.index < pd.Timestamp(init)]
    if bom.empty or (pd.Timestamp(init) - bom.index[-1]).days > 7:
        raise RuntimeError(f"No BoM RMM value in the week before {init}; run 'python run.py indices' first.")
    sdate = bom.index[-1].date()
    state = (float(bom["RMM1"].iloc[-1]), float(bom["RMM2"].iloc[-1]))
    out = {"init": init.isoformat(), "mjo_state": {"rmm1": state[0], "rmm2": state[1], "date": sdate.isoformat(),
                                                   "category": mjo_category(*state)}}
    out["MJO"] = mjo_forecast(m, init, state, sdate, st)
    for p, off in TS_START.items():
        tgt = init + dt.timedelta(days=off)
        b = official_ts_bounds(cfg, tgt)
        s_, _ = ts_sample(ts, tgt)
        mine = ts_bounds(s_)
        if not np.allclose(b, mine, atol=1e-6):
            log(f"  NOTE: official TS bounds for {tgt} {b.tolist()} differ from the recomputed {mine.tolist()}")
        out[f"TS_p{p}"] = ts_forecast(ts, tgt, bounds=b)
        out[f"TS_p{p}_bounds"] = b
        out[f"TS_p{p}_target"] = tgt.isoformat()
    log(f"MJO state {state[0]:+.2f}, {state[1]:+.2f} on {sdate} (category {out['mjo_state']['category']})")
    return out


def files_for(fc: dict) -> list[tuple[str, str, np.ndarray]]:
    """(variable, period, array) for each file. MJO is sent as p1 and p2 (the period is redundant for MJO
    but required in the file name; both carry the same four valid times)."""
    return [("TS", "1", fc["TS_p1"]), ("TS", "2", fc["TS_p2"]), ("MJO", "1", fc["MJO"]), ("MJO", "2", fc["MJO"])]


def write_files(cfg: Config, init: dt.date, fc: dict, modelname: str, log=print) -> list[Path]:
    from AI_WQ_package import check_fc_submission as chk
    from AI_WQ_package import forecast_submission as fs

    outdir = cfg.output_dir / ymd(init) / "tropics"
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for var, p, arr in files_for(fc):
        da = fs.AI_WQ_create_empty_dataarray(var, ymd(init), p, cfg.teamname, modelname, cfg.password)
        da.values = arr
        if var == "TS":
            chk.check_tercile_range(da)
        chk.check_data_characteristics(da, var, ymd(init), p)
        path = outdir / f"{var}_{ymd(init)}_p{p}_{cfg.teamname}_{modelname}.nc"
        da.to_netcdf(path)
        paths.append(path)
        log(f"  {path.name}: written and passes the package checks")
    meta = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in fc.items()}
    (outdir / "tropics_forecast.json").write_text(json.dumps(meta, indent=1))
    return paths


def submit(cfg: Config, init: dt.date, fc: dict, modelname: str, log=print) -> dict:
    from AI_WQ_package import forecast_submission as fs

    workdir = cfg.output_dir / ymd(init) / "_submission_tmp_tropics"
    workdir.mkdir(parents=True, exist_ok=True)
    res = {}
    with contextlib.chdir(workdir):
        for var, p, arr in files_for(fc):
            key = f"{var}_p{p}"
            try:
                da = fs.AI_WQ_create_empty_dataarray(var, ymd(init), p, cfg.teamname, modelname, cfg.password)
                da.values = arr
                fs.AI_WQ_forecast_submission(da, var, ymd(init), p, cfg.teamname, modelname, cfg.password)
                fs.AI_WQ_check_submission(var, ymd(init), p, cfg.teamname, modelname, cfg.password)
                res[key] = "submitted"
                log(f"  {key}: submitted and confirmed on ECBox")
            except Exception as e:  # noqa: BLE001
                res[key] = f"FAILED: {e}"
                log(f"  {key}: FAILED: {e}")
    return res
