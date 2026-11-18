import pandas as pd
import pytest

from trade_lab.backtest import BacktestCosts, performance_summary, run_backtest
from trade_lab.config import StrategyConfig
from trade_lab.instruments import AssetClass, InstrumentSpec


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


def append_bar(bars, values):
    timestamp = bars.index[-1] + pd.Timedelta(minutes=5)
    row = pd.DataFrame(
        [values], columns=["Open", "High", "Low", "Close", "Volume"],
        index=pd.DatetimeIndex([timestamp]),
    )
    return pd.concat([bars, row])


def test_backtest_enters_at_next_bar_open_after_signal_is_confirmed():
    trades = run_backtest(sample_bars((101.2, 106.0, 100.0, 105.0)), config())
    trade = trades.iloc[0]
    assert trade["Direction"] == "LONG"
    assert trade["Signal_Time"] == "2026-11-18T15:05:00+00:00"
    assert trade["Entry_Time"] == "2026-11-18T15:10:00+00:00"
    assert trade["Signal_Entry"] == pytest.approx(101.0)
    assert trade["Entry_Reference"] == pytest.approx(101.2)
    assert trade["Entry"] == pytest.approx(101.2)
    assert trade["Status"] == "CLOSED"
    assert trade["Exit_Reason"] == "TARGET"


def test_intrabar_stop_target_collision_resolves_to_stop():
    trades = run_backtest(sample_bars((101.0, 106.0, 90.0, 100.0)), config())
    assert trades.iloc[0]["Exit_Reason"] == "STOP"


def test_stop_gap_after_entry_fills_at_worse_open():
    bars = sample_bars((101.0, 101.5, 100.0, 101.0))
    bars = append_bar(bars, [98.0, 99.0, 97.0, 98.5, 1000.0])
    trades = run_backtest(bars, config())
    trade = trades.iloc[0]
    assert trade["Status"] == "CLOSED"
    assert trade["Exit_Reason"] == "STOP_GAP"
    assert trade["Exit"] == pytest.approx(98.0)


def test_entry_gap_through_stop_rejects_trade_instead_of_filling():
    trades = run_backtest(sample_bars((98.0, 100.0, 97.0, 99.0)), config())
    trade = trades.iloc[0]
    assert trade["Status"] == "NOT_EXECUTED"
    assert trade["Exit_Reason"] == "ENTRY_GAP_THROUGH_STOP"
    assert trade["Units"] == 0


def test_entry_gap_through_target_rejects_chasing():
    trades = run_backtest(sample_bars((105.0, 106.0, 104.5, 105.5)), config())
    trade = trades.iloc[0]
    assert trade["Status"] == "NOT_EXECUTED"
    assert trade["Exit_Reason"] == "ENTRY_GAP_THROUGH_TARGET"


def test_target_gap_after_entry_fills_at_open_or_better():
    bars = sample_bars((101.0, 101.5, 100.0, 101.0))
    bars = append_bar(bars, [106.0, 107.0, 105.5, 106.5, 1000.0])
    trades = run_backtest(bars, config())
    trade = trades.iloc[0]
    assert trade["Exit_Reason"] == "TARGET_GAP"
    assert trade["Exit"] == pytest.approx(106.0)


def test_no_next_in_session_bar_is_recorded_as_not_executed():
    bars = sample_bars((101.0, 101.5, 100.0, 101.0)).iloc[:2]
    trades = run_backtest(bars, config())
    assert trades.iloc[0]["Status"] == "NOT_EXECUTED"
    assert trades.iloc[0]["Exit_Reason"] == "NO_NEXT_IN_SESSION_BAR"


def test_open_trade_is_marked_not_counted_as_realized():
    trades = run_backtest(sample_bars((101.0, 102.0, 100.0, 101.5)), config())
    trade = trades.iloc[0]
    assert trade["Status"] == "OPEN"
    assert trade["Realized_PnL_$"] == 0
    assert trade["Unrealized_PnL_$"] != 0
    summary = performance_summary(trades)
    assert summary["closed"] == 0 and summary["open"] == 1
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
    with pytest.raises(ValueError):
        run_backtest(bars.iloc[::-1], config())


def test_backtest_requires_open_for_gap_aware_execution():
    bars = sample_bars((101.0, 106.0, 100.0, 105.0)).drop(columns=["Open"])
    with pytest.raises(ValueError, match="Open"):
        run_backtest(bars, config())


def test_realized_drawdown_includes_initial_capital_baseline():
    trades = pd.DataFrame({"Status": ["CLOSED", "CLOSED"], "Realized_PnL_$": [-25.0, 10.0]})
    assert performance_summary(trades)["max_drawdown"] == pytest.approx(-25.0)


def test_execution_costs_reduce_net_pnl_and_adjust_position_size():
    bars = sample_bars((101.0, 106.0, 100.0, 105.0))
    frictionless = run_backtest(bars, config())
    realistic = run_backtest(
        bars, config(),
        costs=BacktestCosts(spread_points=0.2, slippage_points=0.1, commission_per_unit=0.01),
    )
    assert realistic.iloc[0]["Units"] < frictionless.iloc[0]["Units"]
    assert realistic.iloc[0]["Execution_Costs_$"] > 0
    assert realistic.iloc[0]["Realized_PnL_$"] < frictionless.iloc[0]["Realized_PnL_$"]


def test_spread_and_slippage_are_applied_adversely_on_both_fills():
    bars = sample_bars((101.0, 106.0, 100.0, 105.0))
    trade = run_backtest(
        bars, config(), costs=BacktestCosts(spread_points=0.2, slippage_points=0.1)
    ).iloc[0]
    assert trade["Entry_Fill"] == pytest.approx(trade["Entry_Reference"] + 0.2)
    assert trade["Exit_Fill"] == pytest.approx(trade["Exit"] - 0.2)
    assert trade["Execution_Costs_$"] == pytest.approx(round(0.4 * trade["Units"], 2))


def test_signal_quality_and_executable_performance_are_reported_separately():
    trades = run_backtest(
        sample_bars((101.2, 106.0, 100.0, 105.0)),
        config(),
        costs=BacktestCosts(spread_points=0.2, slippage_points=0.1),
    )
    summary = performance_summary(trades)
    assert "Signal_R_Multiple" in trades
    assert summary["signal_expectancy_r"] == pytest.approx(trades.iloc[0]["Signal_R_Multiple"])
    assert summary["expectancy_r"] == pytest.approx(trades.iloc[0]["R_Multiple"])
    assert summary["expectancy_r"] != summary["signal_expectancy_r"]


def test_not_executed_signals_are_excluded_from_trade_expectancy():
    trades = run_backtest(sample_bars((98.0, 100.0, 97.0, 99.0)), config())
    summary = performance_summary(trades)
    assert summary["signals"] == 1
    assert summary["trades"] == 0
    assert summary["not_executed"] == 1
    assert summary["expectancy_r"] == 0


def test_backtest_costs_reject_invalid_values():
    with pytest.raises(ValueError):
        BacktestCosts(spread_points=-0.1)
    with pytest.raises(ValueError):
        BacktestCosts(slippage_points=float("nan"))


def test_performance_summary_reports_expectancy_and_costs():
    trades = run_backtest(
        sample_bars((101.0, 106.0, 100.0, 105.0)), config(),
        costs=BacktestCosts(spread_points=0.2),
    )
    summary = performance_summary(trades)
    assert summary["average_r"] == pytest.approx(summary["expectancy_r"])
    assert summary["execution_costs"] > 0


@pytest.mark.parametrize(
    ("spec", "unit"),
    [
        (
            InstrumentSpec(
                symbol="AAPL", asset_class=AssetClass.EQUITY, quote_currency="USD",
                tick_size=0.01, tick_value=0.01, tick_value_currency="USD",
                quantity_unit="share", min_quantity=1, quantity_step=1, max_quantity=100_000,
            ),
            "share",
        ),
        (
            InstrumentSpec(
                symbol="US100", asset_class=AssetClass.INDEX_CFD, quote_currency="USD",
                tick_size=0.1, tick_value=1.0, tick_value_currency="USD",
                quantity_unit="lot", min_quantity=0.01, quantity_step=0.01, max_quantity=100,
            ),
            "lot",
        ),
    ],
)
def test_backtest_uses_instrument_specific_tick_economics(spec, unit):
    trades = run_backtest(
        sample_bars((101.0, 106.0, 100.0, 105.0)),
        config(),
        costs=BacktestCosts(
            spread_points=0.2, slippage_points=0.1, commission_per_unit=0.01
        ),
        instrument=spec,
    )
    trade = trades.iloc[0]
    assert trade["Symbol"] == spec.symbol
    assert trade["Quantity_Unit"] == unit
    assert trade["Units"] > 0
    assert trade["Risk_Budget_$"] <= config().risk_dollars
    assert trade["Execution_Costs_$"] > 0


def test_instrument_backtest_requires_valid_account_currency_conversion():
    spec = InstrumentSpec(
        symbol="AAPL", asset_class=AssetClass.EQUITY, quote_currency="USD",
        tick_size=0.01, tick_value=0.01, tick_value_currency="USD",
        quantity_unit="share", min_quantity=1, quantity_step=1, max_quantity=100_000,
    )
    with pytest.raises(ValueError):
        run_backtest(
            sample_bars((101.0, 106.0, 100.0, 105.0)),
            config(), instrument=spec, value_to_account_rate=0,
        )


def test_backtest_accepts_separate_strategy_and_account_risk_configs():
    from trade_lab.config import AccountRiskConfig, StrategyParameters

    trades = run_backtest(
        sample_bars((101.0, 106.0, 100.0, 105.0)),
        StrategyParameters(atr_period=1),
        instrument=InstrumentSpec(
            symbol="AAPL", asset_class=AssetClass.EQUITY, quote_currency="USD",
            tick_size=0.01, tick_value=0.01, tick_value_currency="USD",
            quantity_unit="share", min_quantity=1, quantity_step=1,
            max_quantity=100_000,
        ),
        risk=AccountRiskConfig(account_size=5_000, risk_pct=0.01),
    )
    assert 0 < trades.iloc[0]["Risk_Budget_$"] <= 50.0


def test_short_stop_gap_fills_at_worse_open():
    index = pd.date_range("2026-11-18 15:00", periods=4, freq="5min", tz="UTC")
    bars = pd.DataFrame(
        {
            "Open": [100.0, 99.5, 99.0, 103.0],
            "High": [101.0, 100.0, 100.0, 104.0],
            "Low": [99.0, 98.0, 98.0, 102.0],
            "Close": [100.0, 99.0, 99.5, 103.5],
            "Volume": [1000.0] * 4,
        },
        index=index,
    )
    trade = run_backtest(bars, config()).iloc[0]
    assert trade["Direction"] == "SHORT"
    assert trade["Exit_Reason"] == "STOP_GAP"
    assert trade["Exit"] == pytest.approx(103.0)
