"""Market data access and normalisation."""

from __future__ import annotations

import time

import pandas as pd

OHLCV = ["Open", "High", "Low", "Close", "Volume"]


class DataError(RuntimeError):
    """Raised when market data cannot be fetched or is unusable."""


def normalize_bars(raw: pd.DataFrame) -> pd.DataFrame:
    """Return clean OHLCV bars indexed by UTC timestamps.

    Handles the MultiIndex columns some yfinance versions return, drops
    duplicate and incomplete rows, and refuses timezone-naive data because a
    guessed timezone would silently shift the trading window.
    """
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise DataError(f"vendor data missing columns: {missing}")
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
        raise DataError("vendor data has a timezone-naive index")

    df = df[OHLCV]
    df.index = df.index.tz_convert("UTC")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0)
    return df.astype(float)


def conversion_factor(base: pd.DataFrame, other: pd.DataFrame) -> float | None:
    """Ratio other/base at the newest timestamp present in both frames.

    Using one shared timestamp avoids mixing a fresh quote from one
    instrument with a stale quote from the other.
    """
    common = base.index.intersection(other.index)
    if common.empty:
        return None
    stamp = common[-1]
    base_close = float(base.at[stamp, "Close"])
    other_close = float(other.at[stamp, "Close"])
    if base_close <= 0 or other_close <= 0:
        return None
    return other_close / base_close


def fetch_bars(
    symbol: str,
    period: str = "5d",
    interval: str = "5m",
    attempts: int = 3,
) -> pd.DataFrame:
    """Download recent intraday bars from Yahoo Finance with simple retries."""
    import yfinance as yf  # imported lazily so the core package works without it

    reason = "unknown error"
    for attempt in range(attempts):
        try:
            raw = yf.Ticker(symbol).history(period=period, interval=interval)
        except Exception as exc:  # network and parsing libraries raise many types
            reason = type(exc).__name__
        else:
            if raw is not None and not raw.empty:
                return normalize_bars(raw)
            reason = "empty response"
        if attempt < attempts - 1:
            time.sleep(2 * (attempt + 1))
    raise DataError(f"{symbol}: {reason}")
