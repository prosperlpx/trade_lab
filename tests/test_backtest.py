import pandas as pd
import pytest

from trade_lab.backtest import performance_summary, run_backtest
from trade_lab.config import StrategyConfig


def sample_bars(exit_bar):
    index = pd.date_range("2026-11-18 15:00", periods=3, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0, 100.5, exit_bar[0]],
            "High": [101.0, 102.0, exit_bar[1]],
            "Low": [99.0, 100.0, exit_bar[2]],
            "Close": [100.0, 101.0, exit_bar[3]],
            "Volume": [1000.0, 1000.0, 1000.0],
        },
        index=index,
    )


def config():
    return StrategyConfig(atr_period=1, account_size=10_000, risk_pct=0.01)


def test_backtest_uses_shared_signal_and_enters_at_signal_close():
    trades = run_backtest(sample_bars((101.0, 106.0, 100.0, 105.0)), config())
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["Direction"] == "LONG"
    assert trade["Entry_Time"] == "2026-11-18T15:05:00+00:00"
    assert trade["Entry"] == pytest.approx(101.0)
    assert trade["Status"] == "CLOSED"
    assert trade["Exit_Reason"] == "TARGET"


def test_stop_wins_when_stop_and_target_are_both_touched():
    trades = run_backtest(sample_bars((101.0, 106.0, 90.0, 100.0)), config())
    trade = trades.iloc[0]
    assert trade["Status"] == "CLOSED"
    assert trade["Exit_Reason"] == "STOP"


def test_stop_gap_fills_at_worse_open_price():
    trades = run_backtest(sample_bars((90.0, 100.0, 89.0, 95.0)), config())
    trade = trades.iloc[0]
    assert trade["Exit_Reason"] == "STOP"
    assert trade["Exit"] == pytest.approx(90.0)


def test_open_trade_is_marked_not_counted_as_realized():
    trades = run_backtest(sample_bars((101.0, 102.0, 100.0, 101.5)), config())
    trade = trades.iloc[0]
    assert trade["Status"] == "OPEN"
    assert trade["Realized_PnL_$"] == 0
    assert trade["Unrealized_PnL_$"] != 0
    summary = performance_summary(trades)
    assert summary["closed"] == 0
    assert summary["open"] == 1
    assert summary["realized_pnl"] == 0


def test_recent_start_date_does_not_truncate_indicator_warmup():
    bars = sample_bars((101.0, 106.0, 100.0, 105.0))
    trades = run_backtest(bars, config(), start_date=pd.Timestamp("2026-11-18").date())
    assert len(trades) == 1


def test_backtest_rejects_naive_or_unsorted_timestamps():
    bars = sample_bars((101.0, 106.0, 100.0, 105.0))
    naive = bars.copy()
    naive.index = naive.index.tz_localize(None)
    with pytest.raises(ValueError):
        run_backtest(naive, config())
    unsorted = bars.iloc[::-1]
    with pytest.raises(ValueError):
        run_backtest(unsorted, config())


def test_backtest_requires_open_for_gap_aware_execution():
    bars = sample_bars((101.0, 106.0, 100.0, 105.0)).drop(columns=["Open"])
    with pytest.raises(ValueError, match="Open"):
        run_backtest(bars, config())


def test_realized_drawdown_includes_initial_capital_baseline():
    trades = pd.DataFrame(
        {"Status": ["CLOSED", "CLOSED"], "Realized_PnL_$": [-25.0, 10.0]}
    )
    assert performance_summary(trades)["max_drawdown"] == pytest.approx(-25.0)
