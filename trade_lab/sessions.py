"""Time handling: New York session window, bar-closure and freshness checks."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .config import StrategyConfig

NY = ZoneInfo("America/New_York")


def to_ny(ts: pd.Timestamp | str) -> pd.Timestamp:
    """Convert a timezone-aware timestamp to New York time."""
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return stamp.tz_convert(NY)


def ny_date(ts: pd.Timestamp | str) -> date:
    """Calendar date of a timestamp in New York."""
    return to_ny(ts).date()


def in_window(ts: pd.Timestamp | str, cfg: StrategyConfig) -> bool:
    """True when the timestamp falls inside the configured NY trading window."""
    local = to_ny(ts).time()
    return cfg.session_start <= local < cfg.session_end


def window_mask(index: pd.DatetimeIndex, cfg: StrategyConfig) -> np.ndarray:
    """Vectorised version of in_window for a tz-aware index."""
    if index.tz is None:
        raise ValueError("index must be timezone-aware")
    local = index.tz_convert(NY)
    minutes = np.asarray(local.hour) * 60 + np.asarray(local.minute)
    start = cfg.session_start.hour * 60 + cfg.session_start.minute
    end = cfg.session_end.hour * 60 + cfg.session_end.minute
    return (minutes >= start) & (minutes < end)


def drop_open_bar(
    df: pd.DataFrame, now: pd.Timestamp | str, bar_minutes: int = 5
) -> pd.DataFrame:
    """Remove bars that have not finished yet.

    Data vendors return the in-progress candle. Acting on it makes signals
    repaint, so only bars whose end time is at or before ``now`` are kept.
    """
    stamp = pd.Timestamp(now)
    if stamp.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    bar_end = df.index + pd.Timedelta(minutes=bar_minutes)
    return df.loc[bar_end <= stamp]


def is_fresh(
    df: pd.DataFrame,
    now: pd.Timestamp | str,
    bar_minutes: int = 5,
    max_lag_minutes: int = 15,
) -> bool:
    """True when the newest closed bar is recent enough to act on.

    This doubles as a holiday and outage guard: on a market holiday or when
    the vendor stalls, the last bar is old, so the bot stays silent.
    """
    if df.empty:
        return False
    stamp = pd.Timestamp(now)
    last_end = df.index[-1] + pd.Timedelta(minutes=bar_minutes)
    return stamp - last_end <= pd.Timedelta(minutes=max_lag_minutes)
