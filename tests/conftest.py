"""Shared test helpers."""

from __future__ import annotations

import pandas as pd


def make_bars(
    start: str,
    rows: list[tuple[float, float, float, float]],
    tz: str = "UTC",
    freq: str = "5min",
) -> pd.DataFrame:
    """Build a bar frame from (High, Low, Close, Volume) tuples."""
    index = pd.date_range(start=start, periods=len(rows), freq=freq, tz=tz)
    df = pd.DataFrame(rows, index=index, columns=["High", "Low", "Close", "Volume"])
    df["Open"] = df["Close"]
    return df
