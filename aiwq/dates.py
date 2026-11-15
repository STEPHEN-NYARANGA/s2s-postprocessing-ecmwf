"""Date helpers for the weekly AI Weather Quest cycle.

Day 1 is the Thursday initialisation (00 UTC). Window 1 covers days 19-25 (Monday to
Sunday, starting init + 18 days); window 2 covers days 26-32 (starting init + 25 days).
"""

from __future__ import annotations

import datetime as dt
import os

WINDOW_OFFSET_DAYS = {1: 18, 2: 25}


def utc_today() -> dt.date:
    fake = os.environ.get("AIWQ_FAKE_TODAY")  # used by the tests only
    if fake:
        return parse_date(fake)
    return dt.datetime.now(dt.timezone.utc).date()


def parse_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Cannot read date {value!r}; use YYYY-MM-DD or YYYYMMDD.")


def ymd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def is_thursday(d: dt.date) -> bool:
    return d.weekday() == 3


def latest_thursday(today: dt.date | None = None) -> dt.date:
    today = today or utc_today()
    return today - dt.timedelta(days=(today.weekday() - 3) % 7)


def thursdays(start: dt.date, end: dt.date) -> list[dt.date]:
    first = start + dt.timedelta(days=(3 - start.weekday()) % 7)
    out, d = [], first
    while d <= end:
        out.append(d)
        d += dt.timedelta(days=7)
    return out


def mondays(start: dt.date, end: dt.date) -> list[dt.date]:
    first = start + dt.timedelta(days=(0 - start.weekday()) % 7)
    out, d = [], first
    while d <= end:
        out.append(d)
        d += dt.timedelta(days=7)
    return out


def window_monday(init: dt.date, window: int) -> dt.date:
    return init + dt.timedelta(days=WINDOW_OFFSET_DAYS[int(window)])


def obs_ready(monday: dt.date, latency_days: int, today: dt.date | None = None) -> bool:
    """True when the ERA5T week starting on `monday` should be published."""
    today = today or utc_today()
    return monday + dt.timedelta(days=6 + latency_days) <= today


def day_of_year(d: dt.date) -> int:
    return d.timetuple().tm_yday


def submission_deadline(init: dt.date) -> dt.datetime:
    return dt.datetime.combine(init + dt.timedelta(days=3), dt.time(23, 59, 59))
