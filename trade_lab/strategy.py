"""The VWAP pullback rule, defined once and used by live and backtest code."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from .config import StrategyParameters
from .indicators import atr, session_vwap
from .sessions import NY, in_window, window_mask

LONG = 1
SHORT = -1


@dataclass(frozen=True)
class Signal:
    """A trade setup detected on a closed bar."""

    time: pd.Timestamp
    direction: int
    entry: float
    stop: float
    target: float
    risk_distance: float

    @property
    def side(self) -> str:
        return "LONG" if self.direction == LONG else "SHORT"


def prepare(df: pd.DataFrame, cfg: StrategyParameters) -> pd.DataFrame:
    """Return a copy of ``df`` with VWAP and ATR columns added."""
    out = df.sort_index().copy()
    out["VWAP"] = session_vwap(out)
    out["ATR"] = atr(out, cfg.atr_period)
    lookback = cfg.filters.vwap_slope_lookback
    out["VWAP_SLOPE_ATR"] = out["VWAP"].diff(lookback) / out["ATR"]
    out["ATR_PCT"] = out["ATR"] / out["Close"].abs() * 100.0
    return out


def signal_for_bar(
    ts: pd.Timestamp, bar: pd.Series, cfg: StrategyParameters
) -> Signal | None:
    """Evaluate one closed bar that already has VWAP and ATR values.

    Long: the bar closes above VWAP after its low touched (or came within the
    tolerance of) VWAP. Short is the mirror image. Entry is the bar close.
    """
    vwap = bar["VWAP"]
    bar_atr = bar["ATR"]
    if pd.isna(vwap) or pd.isna(bar_atr) or bar_atr <= 0:
        return None

    close = float(bar["Close"])
    low = float(bar["Low"])
    high = float(bar["High"])
    filters = cfg.filters
    atr_pct = bar.get("ATR_PCT", np.nan)
    slope = bar.get("VWAP_SLOPE_ATR", np.nan)
    if filters.min_atr_pct is not None and (pd.isna(atr_pct) or atr_pct < filters.min_atr_pct):
        return None
    if filters.max_atr_pct is not None and (pd.isna(atr_pct) or atr_pct > filters.max_atr_pct):
        return None
    risk = cfg.atr_stop_mult * float(bar_atr)

    if close > vwap and low <= vwap * (1 + cfg.vwap_tolerance):
        if (
            filters.max_pullback_atr is not None
            and max(0.0, float(vwap) - low) / float(bar_atr)
            > filters.max_pullback_atr
        ):
            return None
        if (
            filters.min_directional_vwap_slope_atr is not None
            and (
                pd.isna(slope)
                or float(slope) < filters.min_directional_vwap_slope_atr
            )
        ):
            return None
        return Signal(
            time=ts,
            direction=LONG,
            entry=close,
            stop=close - risk,
            target=close + risk * cfg.reward_risk,
            risk_distance=risk,
        )
    if close < vwap and high >= vwap * (1 - cfg.vwap_tolerance):
        if (
            filters.max_pullback_atr is not None
            and max(0.0, high - float(vwap)) / float(bar_atr)
            > filters.max_pullback_atr
        ):
            return None
        if (
            filters.min_directional_vwap_slope_atr is not None
            and (
                pd.isna(slope)
                or -float(slope) < filters.min_directional_vwap_slope_atr
            )
        ):
            return None
        return Signal(
            time=ts,
            direction=SHORT,
            entry=close,
            stop=close + risk,
            target=close - risk * cfg.reward_risk,
            risk_distance=risk,
        )
    return None


def first_signal(prepared: pd.DataFrame, cfg: StrategyParameters, day: date) -> Signal | None:
    """First setup of a New York trading day, scanning in-window bars in order.

    The strategy takes at most one trade per day, so the first qualifying bar
    defines that day's trade. Live and backtest both use this function, which
    keeps them identical by construction.
    """
    if prepared.empty:
        return None
    ny_days = np.asarray(prepared.index.tz_convert(NY).date)
    mask = (ny_days == day) & window_mask(prepared.index, cfg)
    for ts, row in prepared.loc[mask].iterrows():
        sig = signal_for_bar(ts, row, cfg)
        if sig is not None:
            return sig
    return None


def latest_signal(prepared: pd.DataFrame, cfg: StrategyParameters) -> Signal | None:
    """Signal for the newest bar of a prepared frame, only inside the window."""
    if prepared.empty:
        return None
    ts = prepared.index[-1]
    if not in_window(ts, cfg):
        return None
    return signal_for_bar(ts, prepared.iloc[-1], cfg)
