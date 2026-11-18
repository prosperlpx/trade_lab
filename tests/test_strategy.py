import pandas as pd
import pytest
from conftest import make_bars

from trade_lab.config import StrategyConfig
from trade_lab.filters import StrategyFilters
from trade_lab.strategy import LONG, SHORT, latest_signal, prepare, signal_for_bar

CFG = StrategyConfig()
TS = pd.Timestamp("2026-11-18 16:00", tz="UTC")


def bar(close, low, high, vwap, atr_value):
    return pd.Series(
        {"Close": close, "Low": low, "High": high, "VWAP": vwap, "ATR": atr_value}
    )


def test_long_signal_levels():
    sig = signal_for_bar(TS, bar(100.5, 99.9, 100.7, 100.0, 0.4), CFG)
    assert sig is not None and sig.direction == LONG
    assert sig.entry == pytest.approx(100.5)
    assert sig.risk_distance == pytest.approx(0.6)
    assert sig.stop == pytest.approx(99.9)
    assert sig.target == pytest.approx(100.5 + 0.6 * 1.3)


def test_short_signal_levels():
    sig = signal_for_bar(TS, bar(99.5, 99.3, 100.1, 100.0, 0.4), CFG)
    assert sig is not None and sig.direction == SHORT
    assert sig.stop == pytest.approx(99.5 + 0.6)
    assert sig.target == pytest.approx(99.5 - 0.6 * 1.3)
    assert sig.side == "SHORT"


def test_pullback_rule_is_one_sided_and_allows_price_to_cross_vwap():
    # The implemented inequalities do not cap how far the candle can cross VWAP.
    long_sig = signal_for_bar(TS, bar(100.5, 90.0, 101.0, 100.0, 0.4), CFG)
    short_sig = signal_for_bar(TS, bar(99.5, 99.0, 110.0, 100.0, 0.4), CFG)
    assert long_sig is not None and long_sig.direction == LONG
    assert short_sig is not None and short_sig.direction == SHORT


def test_no_signal_when_bar_never_touched_vwap():
    assert signal_for_bar(TS, bar(101.0, 100.5, 101.2, 100.0, 0.4), CFG) is None
    assert signal_for_bar(TS, bar(99.0, 98.8, 99.5, 100.0, 0.4), CFG) is None


def test_touch_tolerance_boundary():
    # Low exactly at vwap * 1.001 still counts as a touch
    assert signal_for_bar(TS, bar(100.5, 100.1, 100.7, 100.0, 0.4), CFG) is not None
    assert signal_for_bar(TS, bar(100.5, 100.11, 100.7, 100.0, 0.4), CFG) is None


def test_missing_indicators_give_no_signal():
    assert signal_for_bar(TS, bar(100.5, 99.9, 100.7, float("nan"), 0.4), CFG) is None
    assert signal_for_bar(TS, bar(100.5, 99.9, 100.7, 100.0, float("nan")), CFG) is None
    assert signal_for_bar(TS, bar(100.5, 99.9, 100.7, 100.0, 0.0), CFG) is None


def _flat_then_pullback(start: str) -> pd.DataFrame:
    rows = [(100.5, 99.5, 100.0, 1000)] * 5 + [(101.0, 99.9, 100.4, 1000)]
    return make_bars(start, rows)


def test_latest_signal_inside_window():
    cfg = StrategyConfig(atr_period=3)
    prepared = prepare(_flat_then_pullback("2026-11-18 15:30"), cfg)
    sig = latest_signal(prepared, cfg)
    assert sig is not None and sig.direction == LONG
    assert sig.risk_distance == pytest.approx(1.5 * prepared["ATR"].iloc[-1])


def test_latest_signal_outside_window_is_none():
    cfg = StrategyConfig(atr_period=3)
    prepared = prepare(_flat_then_pullback("2026-11-18 13:00"), cfg)
    assert latest_signal(prepared, cfg) is None


def test_latest_signal_on_empty_frame():
    cfg = StrategyConfig(atr_period=3)
    prepared = prepare(_flat_then_pullback("2026-11-18 15:30"), cfg).iloc[0:0]
    assert latest_signal(prepared, cfg) is None


def test_optional_filters_disabled_by_default():
    cfg = StrategyConfig(atr_period=3)
    prepared = prepare(_flat_then_pullback("2026-11-18 15:30"), cfg)
    assert latest_signal(prepared, cfg) is not None

def test_max_pullback_depth_filter_rejects_deep_reclaim():
    cfg = StrategyConfig(filters=StrategyFilters(max_pullback_atr=0.1))
    assert signal_for_bar(TS, bar(100.5, 99.0, 100.7, 100.0, 0.4), cfg) is None

def test_directional_vwap_slope_filter_requires_aligned_slope():
    cfg = StrategyConfig(filters=StrategyFilters(min_directional_vwap_slope_atr=0.2))
    aligned = bar(100.5, 99.9, 100.7, 100.0, 0.4)
    aligned["VWAP_SLOPE_ATR"] = 0.3
    opposed = aligned.copy()
    opposed["VWAP_SLOPE_ATR"] = -0.3
    assert signal_for_bar(TS, aligned, cfg) is not None
    assert signal_for_bar(TS, opposed, cfg) is None

def test_volatility_filter_rejects_out_of_range_atr_pct():
    cfg = StrategyConfig(filters=StrategyFilters(min_atr_pct=0.5, max_atr_pct=1.0))
    candidate = bar(100.5, 99.9, 100.7, 100.0, 0.4)
    candidate["ATR_PCT"] = 0.7
    assert signal_for_bar(TS, candidate, cfg) is not None
    candidate["ATR_PCT"] = 0.2
    assert signal_for_bar(TS, candidate, cfg) is None

def test_strategy_filter_validation():
    with pytest.raises(ValueError, match="min_atr_pct"):
        StrategyFilters(min_atr_pct=2.0, max_atr_pct=1.0)
    with pytest.raises(ValueError, match="positive integer"):
        StrategyFilters(vwap_slope_lookback=0)