"""Session VWAP and gap-free ATR.

Both indicators reset or ignore overnight gaps by grouping on the New York
calendar date, so the first bar of a session is never distorted by the
previous day's close.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .sessions import NY

REQUIRED_COLUMNS = ("High", "Low", "Close", "Volume")


def _check(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
        raise ValueError("index must be a timezone-aware DatetimeIndex")


def session_key(index: pd.DatetimeIndex) -> np.ndarray:
    """New York calendar date of each bar, used to group sessions."""
    return np.asarray(index.tz_convert(NY).date)


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """Cumulative volume-weighted average price, reset each NY session.

    Bars with zero cumulative volume yield NaN instead of a fabricated value.
    """
    _check(df)
    key = session_key(df.index)
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_pv = (typical * df["Volume"]).groupby(key).cumsum()
    cum_vol = df["Volume"].groupby(key).cumsum()
    return (cum_pv / cum_vol.where(cum_vol > 0)).rename("VWAP")


def true_range(df: pd.DataFrame) -> pd.Series:
    """True range that ignores the overnight gap.

    The first bar of each session has no same-session previous close, so its
    range is simply High minus Low.
    """
    _check(df)
    key = session_key(df.index)
    prev_close = df["Close"].groupby(key).shift(1)
    parts = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return parts.max(axis=1).rename("TR")


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Simple moving average of the gap-free true range."""
    return true_range(df).rolling(period).mean().rename("ATR")
