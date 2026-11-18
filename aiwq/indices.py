"""Climate indices known at each Thursday initialisation: MJO, El Nino (Nino 3.4) and the
Indian Ocean Dipole.

Sources (public text files, cached in data/indices/):
  MJO   Bureau of Meteorology real-time RMM index (Wheeler and Hendon 2004), daily
        https://www.bom.gov.au/clim_data/IDCKGEM000/rmm.74toRealtime.txt
  Nino  NOAA CPC weekly OISST Nino 3.4 anomaly, weeks centred on Wednesdays
        https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for
  IOD   Bureau of Meteorology weekly Dipole Mode Index (Monday-Sunday weeks)
        https://www.bom.gov.au/clim_data/IDCK000072/iod_1.txt

A forecast may only use what was published before its initialisation, so each index has a
publication lag, and `state_at(init)` takes the last value dated at least that many days
before the Thursday:
  RMM 2 days (the Bureau posts each day's value one to two days later),
  Nino 3.4 8 days (CPC posts the week centred on Wednesday on the following Monday),
  IOD 4 days (the Bureau posts the week ending on Sunday during the next few days).
"""

from __future__ import annotations

import csv
import datetime as dt
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import Config

SOURCES = {
    "rmm": "https://www.bom.gov.au/clim_data/IDCKGEM000/rmm.74toRealtime.txt",
    "nino34": "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for",
    "iod": "https://www.bom.gov.au/clim_data/IDCK000072/iod_1.txt",
}
LAG_DAYS = {"rmm": 2, "nino34": 8, "iod": 4}
USER_AGENT = "Mozilla/5.0 (compatible; aiwq-seasonblend research script)"
MAX_AGE_DAYS = {"rmm": 10, "nino34": 21, "iod": 21}  # older than this at init -> treated as missing


def _path(cfg: Config, name: str) -> Path:
    return cfg.indices_dir / Path(SOURCES[name]).name


def fetch(cfg: Config, log=print) -> dict[str, bool]:
    """Download the three files. Failures keep the cached copy and are reported, never raised."""
    import os

    cfg.indices_dir.mkdir(parents=True, exist_ok=True)
    ok = {}
    if os.environ.get("AIWQ_OFFLINE"):  # tests
        return {name: False for name in SOURCES}
    for name, url in SOURCES.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if len(data) < 1000 or b"<html" in data[:2000].lower():
                raise ValueError("unexpected content")
            tmp = _path(cfg, name).with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(_path(cfg, name))
            ok[name] = True
        except Exception as e:  # noqa: BLE001
            ok[name] = False
            log(f"  index {name}: download failed ({e}); {'using the cached copy' if _path(cfg, name).exists() else 'no copy'}")
    return ok


# ------------------------------------------------------------------ parsers ------------

def read_rmm(cfg: Config) -> dict[dt.date, tuple[float, float, int, float]]:
    out = {}
    for line in _path(cfg, "rmm").read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 7 or not parts[0].isdigit():
            continue
        try:
            d = dt.date(int(parts[0]), int(parts[1]), int(parts[2]))
            r1, r2, ph, amp = float(parts[3]), float(parts[4]), int(float(parts[5])), float(parts[6])
        except ValueError:
            continue
        if abs(r1) > 100 or abs(amp) > 100 or not 1 <= ph <= 8:
            continue  # missing value (1E36 or 999)
        out[d] = (r1, r2, ph, amp)
    return out


def read_nino34(cfg: Config) -> dict[dt.date, float]:
    """CPC file: week, then SST and SSTA for Nino1+2, 3, 3.4, 4. Numbers can touch
    ("24.8-0.1"), so they are found with a pattern rather than split on spaces."""
    import re

    out = {}
    for line in _path(cfg, "nino34").read_text(errors="replace").splitlines():
        try:
            d = dt.datetime.strptime(line[:10].strip(), "%d%b%Y").date()
        except ValueError:
            continue
        vals = re.findall(r"-?\d+\.\d+", line[10:])
        if len(vals) == 8:
            out[d] = float(vals[5])  # Nino 3.4 SSTA
    return out


def read_iod(cfg: Config) -> dict[dt.date, float]:
    """Rows 'YYYYMMDD,YYYYMMDD,value' (week start, week end, DMI); keyed by week end."""
    out = {}
    with _path(cfg, "iod").open(newline="", errors="replace") as f:
        for row in csv.reader(f):
            try:
                out[dt.datetime.strptime(row[1].strip(), "%Y%m%d").date()] = float(row[2])
            except (ValueError, IndexError):
                continue
    return out


# ------------------------------------------------------------------ state at init ------

@dataclass
class State:
    init: dt.date
    rmm1: float | None = None
    rmm2: float | None = None
    mjo_phase: int | None = None      # 1-8
    mjo_amp: float | None = None
    rmm_date: dt.date | None = None
    nino34: float | None = None       # K, weekly SST anomaly
    nino34_date: dt.date | None = None
    iod: float | None = None          # K, weekly Dipole Mode Index
    iod_date: dt.date | None = None

    @property
    def mjo_active(self) -> bool | None:
        return None if self.mjo_amp is None else self.mjo_amp >= 1.0

    @property
    def enso(self) -> str | None:
        if self.nino34 is None:
            return None
        return "El Nino" if self.nino34 >= 0.5 else "La Nina" if self.nino34 <= -0.5 else "neutral"

    def as_row(self) -> dict:
        f = lambda x, n=2: "" if x is None else (x.isoformat() if isinstance(x, dt.date) else round(x, n) if isinstance(x, float) else x)  # noqa: E731
        return {"init": self.init.isoformat(), "rmm1": f(self.rmm1), "rmm2": f(self.rmm2), "mjo_phase": f(self.mjo_phase),
                "mjo_amp": f(self.mjo_amp), "mjo_active": "" if self.mjo_active is None else int(self.mjo_active),
                "rmm_date": f(self.rmm_date), "nino34": f(self.nino34), "enso": self.enso or "",
                "nino34_week": f(self.nino34_date), "iod": f(self.iod), "iod_week_end": f(self.iod_date)}


def _last_before(series: dict, cutoff: dt.date, max_age: int):
    ds = [d for d in series if d <= cutoff]
    if not ds:
        return None, None
    d = max(ds)
    return (d, series[d]) if (cutoff - d).days <= max_age else (None, None)


class Indices:
    def __init__(self, cfg: Config):
        self.rmm = read_rmm(cfg) if _path(cfg, "rmm").exists() else {}
        self.nino = read_nino34(cfg) if _path(cfg, "nino34").exists() else {}
        self.iod = read_iod(cfg) if _path(cfg, "iod").exists() else {}

    def state_at(self, init: dt.date) -> State:
        s = State(init)
        d, v = _last_before(self.rmm, init - dt.timedelta(days=LAG_DAYS["rmm"]), MAX_AGE_DAYS["rmm"])
        if d:
            s.rmm1, s.rmm2, s.mjo_phase, s.mjo_amp = v
            s.rmm_date = d
        d, v = _last_before(self.nino, init - dt.timedelta(days=LAG_DAYS["nino34"]), MAX_AGE_DAYS["nino34"])
        if d:
            s.nino34, s.nino34_date = v, d
        d, v = _last_before(self.iod, init - dt.timedelta(days=LAG_DAYS["iod"]), MAX_AGE_DAYS["iod"])
        if d:
            s.iod, s.iod_date = v, d
        return s


def write_table(cfg: Config, inits, path: Path | None = None) -> Path:
    idx = Indices(cfg)
    path = path or cfg.indices_dir / "state_at_init.csv"
    rows = [idx.state_at(d).as_row() for d in inits]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path
