import numpy as np
import pandas as pd
import pytest
from conftest import make_bars

from trade_lab.indicators import atr, session_vwap, true_range


def test_vwap_hand_computed():
    # Typical prices 9, 11, 10 with volumes 100, 200, 100
    df = make_bars(
        "2026-11-18 15:00",
        [(10, 8, 9, 100), (12, 10, 11, 200), (11, 9, 10, 100)],
    )
    vwap = session_vwap(df)
    assert vwap.iloc[0] == pytest.approx(9.0)
    assert vwap.iloc[1] == pytest.approx((900 + 2200) / 300)
    assert vwap.iloc[2] == pytest.approx((900 + 2200 + 1000) / 400)


def test_vwap_resets_each_ny_session():
    day1 = make_bars("2026-11-17 15:00", [(10, 8, 9, 100)])
    day2 = make_bars("2026-11-18 15:00", [(52, 48, 50, 100)])
    vwap = session_vwap(pd.concat([day1, day2]))
    assert vwap.iloc[1] == pytest.approx(50.0)


def test_vwap_zero_volume_is_nan_not_fabricated():
    df = make_bars("2026-11-18 15:00", [(10, 8, 9, 0), (12, 10, 11, 100)])
    vwap = session_vwap(df)
    assert np.isnan(vwap.iloc[0])
    assert vwap.iloc[1] == pytest.approx(11.0)


def test_true_range_ignores_overnight_gap():
    day1 = make_bars("2026-11-17 15:00", [(91, 89, 90, 100)])
    day2 = make_bars("2026-11-18 15:00", [(101, 100.5, 100.8, 100)])
    tr = true_range(pd.concat([day1, day2]))
    # A gap-aware calculation would report about 11 on the second day.
    assert tr.iloc[1] == pytest.approx(0.5)


def test_true_range_uses_previous_close_within_session():
    df = make_bars("2026-11-18 15:00", [(10, 9, 9.5, 100), (13, 12, 12.5, 100)])
    tr = true_range(df)
    assert tr.iloc[1] == pytest.approx(3.5)  # |13 - 9.5|


def test_atr_rolling_window_can_include_prior_day_true_ranges():
    day1 = make_bars("2026-11-17 19:50", [(20, 10, 15, 100)])
    day2 = make_bars("2026-11-18 15:00", [(102, 100, 101, 100)])
    result = atr(pd.concat([day1, day2]), period=2)
    # Day two true range ignores the overnight gap (2), but ATR averages
    # it with the previous day's true range (10).
    assert result.iloc[1] == pytest.approx(6.0)


def test_atr_needs_full_period_then_is_exact():
    df = make_bars("2026-11-18 15:00", [(101, 99, 100, 100)] * 5)
    result = atr(df, period=3)
    assert result.iloc[:2].isna().all()
    assert result.iloc[2:].tolist() == pytest.approx([2.0, 2.0, 2.0])


def test_missing_columns_rejected():
    df = make_bars("2026-11-18 15:00", [(10, 8, 9, 100)]).drop(columns=["Volume"])
    with pytest.raises(ValueError):
        session_vwap(df)


def test_naive_index_rejected():
    df = make_bars("2026-11-18 15:00", [(10, 8, 9, 100)])
    df.index = df.index.tz_localize(None)
    with pytest.raises(ValueError):
        session_vwap(df)
