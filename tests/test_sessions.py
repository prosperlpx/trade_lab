import pandas as pd
import pytest
from conftest import make_bars

from trade_lab.config import StrategyConfig
from trade_lab.sessions import drop_open_bar, in_window, is_fresh, ny_date, window_mask

CFG = StrategyConfig()


def test_window_in_winter_est():
    # 15:00 UTC is 10:00 EST in November
    assert in_window("2026-11-18 15:00:00+00:00", CFG)
    assert in_window("2026-11-18 19:55:00+00:00", CFG)
    assert not in_window("2026-11-18 14:55:00+00:00", CFG)
    assert not in_window("2026-11-18 20:00:00+00:00", CFG)


def test_window_in_summer_edt():
    # 14:00 UTC is 10:00 EDT in July
    assert in_window("2026-07-15 14:00:00+00:00", CFG)
    assert in_window("2026-07-15 18:55:00+00:00", CFG)
    assert not in_window("2026-07-15 13:55:00+00:00", CFG)
    assert not in_window("2026-07-15 19:00:00+00:00", CFG)


def test_same_utc_time_flips_between_seasons():
    # A fixed UTC or WAT window would treat both identically.
    assert in_window("2026-07-15 14:30:00+00:00", CFG)
    assert not in_window("2026-11-18 14:30:00+00:00", CFG)


def test_window_follows_wall_clock_across_dst_change():
    # US clocks went back on 2026-11-01; the window should track NY wall time.
    before = pd.Timestamp("2026-10-30 10:00", tz="America/New_York")
    after = pd.Timestamp("2026-11-02 10:00", tz="America/New_York")
    assert in_window(before, CFG)
    assert in_window(after, CFG)


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        in_window(pd.Timestamp("2026-11-18 15:00"), CFG)


def test_window_mask_matches_scalar():
    df = make_bars("2026-11-18 13:00", [(1, 1, 1, 1)] * 96)
    mask = window_mask(df.index, CFG)
    expected = [in_window(ts, CFG) for ts in df.index]
    assert list(mask) == expected


def test_ny_date_uses_new_york_calendar():
    # 03:00 UTC on the 19th is still the evening of the 18th in New York
    assert str(ny_date("2026-11-19 03:00:00+00:00")) == "2026-11-18"


def test_drop_open_bar_removes_in_progress_candle():
    df = make_bars("2026-11-18 15:00", [(1, 1, 1, 1)] * 3)
    kept = drop_open_bar(df, "2026-11-18 15:07:00+00:00")
    assert len(kept) == 1
    assert kept.index[-1] == pd.Timestamp("2026-11-18 15:00", tz="UTC")


def test_drop_open_bar_keeps_bar_closing_exactly_now():
    df = make_bars("2026-11-18 15:00", [(1, 1, 1, 1)] * 2)
    kept = drop_open_bar(df, "2026-11-18 15:10:00+00:00")
    assert len(kept) == 2


def test_is_fresh_detects_stale_data():
    df = make_bars("2026-11-18 15:00", [(1, 1, 1, 1)] * 2)
    assert is_fresh(df, "2026-11-18 15:20:00+00:00")
    assert not is_fresh(df, "2026-11-18 18:00:00+00:00")
    assert not is_fresh(df.iloc[0:0], "2026-11-18 15:20:00+00:00")
