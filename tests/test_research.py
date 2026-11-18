from datetime import date

import pandas as pd
import pytest

from trade_lab.backtest import BacktestCosts
from trade_lab.config import StrategyConfig
from trade_lab.filters import StrategyFilters
from trade_lab.instruments import AssetClass, InstrumentSpec
from trade_lab.research import (
    ResearchVariant,
    make_walk_forward_windows,
    run_walk_forward_research,
)


def instrument(symbol):
    return InstrumentSpec(
        symbol=symbol, asset_class=AssetClass.ETF, quote_currency="USD",
        tick_size=0.01, tick_value=0.01, tick_value_currency="USD",
        quantity_unit="share", min_quantity=1, quantity_step=1, max_quantity=100_000,
    )


def bars_for_sessions(sessions=12):
    parts = []
    for day in pd.date_range("2026-01-05", periods=sessions, freq="B"):
        index = pd.date_range(
            day.strftime("%Y-%m-%d") + " 15:00", periods=4, freq="5min", tz="UTC"
        )
        parts.append(pd.DataFrame({
            "Open": [100.0, 100.0, 100.5, 101.0],
            "High": [101.0, 101.0, 102.0, 103.0],
            "Low": [99.0, 99.0, 100.0, 100.5],
            "Close": [100.0, 100.5, 101.0, 102.0],
            "Volume": [1000.0] * 4,
        }, index=index))
    return pd.concat(parts)


def test_walk_forward_windows_are_ordered_and_non_overlapping():
    dates = [date(2026, 1, day) for day in range(1, 13)]
    windows = make_walk_forward_windows(dates, 4, 2, 2, step_days=2)
    assert len(windows) == 3
    assert windows[0].train_end < windows[0].validation_start
    assert windows[0].validation_end < windows[0].test_start
    assert windows[0].test_end < windows[1].test_start


def test_walk_forward_requires_enough_sessions():
    with pytest.raises(ValueError, match="insufficient"):
        run_walk_forward_research(
            {"ETF": bars_for_sessions(5)}, {"ETF": instrument("ETF")},
            {"ETF": BacktestCosts(spread_points=0.02)},
            [ResearchVariant("baseline", StrategyConfig(atr_period=1))],
            train_days=3, validation_days=2, test_days=2,
            data_sources={"ETF": "fixture: synthetic OHLCV 5m"},
        )


def test_research_requires_explicit_symbol_economics_and_costs():
    with pytest.raises(ValueError, match="explicit instrument"):
        run_walk_forward_research(
            {"ETF": bars_for_sessions()}, {}, {},
            [ResearchVariant("baseline", StrategyConfig(atr_period=1))],
            train_days=4, validation_days=2, test_days=2,
            data_sources={},
        )


def test_research_emits_candidates_and_separate_selected_test_rows():
    result = run_walk_forward_research(
        {"ETF": bars_for_sessions()}, {"ETF": instrument("ETF")},
        {"ETF": BacktestCosts(spread_points=0.02, slippage_points=0.01)},
        [
            ResearchVariant("baseline", StrategyConfig(atr_period=1)),
            ResearchVariant("filtered", StrategyConfig(
                atr_period=1, filters=StrategyFilters(min_atr_pct=0.1)
            )),
        ],
        train_days=4, validation_days=2, test_days=2, step_days=2,
        data_sources={"ETF": "fixture: synthetic OHLCV 5m"},
    )
    assert set(result["role"]) == {"candidate", "selected_test"}
    selected = result.loc[result["role"] == "selected_test"]
    assert len(selected) == 3
    assert set(selected["selected_on"]) == {"validation_expectancy_r"}
    assert selected["test_closed"].notna().all()


def test_reclaim_outcomes_measure_forward_excursion_in_r():
    from trade_lab.research import measure_reclaim_outcomes

    index = pd.date_range("2026-11-18 15:00", periods=4, freq="5min", tz="UTC")
    prepared = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 101.2, 101.4],
            "High": [101.2, 102.0, 102.5, 102.0],
            "Low": [99.9, 100.8, 101.0, 101.1],
            "Close": [101.0, 101.5, 102.0, 101.8],
            "Volume": [1000.0] * 4,
            "VWAP": [100.0, 101.0, 101.5, 101.5],
            "ATR": [1.0] * 4,
            "ATR_PCT": [1.0] * 4,
            "VWAP_SLOPE_ATR": [0.0] * 4,
        },
        index=index,
    )
    outcomes = measure_reclaim_outcomes(prepared, StrategyConfig(atr_stop_mult=1.0), (2,))
    assert len(outcomes) == 2  # candidates at bars 0 and 1 have a complete 2-bar horizon
    first = outcomes.iloc[0]
    assert first["direction"] == "LONG"
    assert first["mfe_r"] == pytest.approx(1.5)
    assert first["mae_r"] == pytest.approx(0.2)
    assert first["follow_through_r"] == pytest.approx(1.0)
    assert first["pullback_depth_atr"] == pytest.approx(0.1)
    assert first["reclaim_close_distance_atr"] == pytest.approx(1.0)
    assert first["reclaim_candle_range_atr"] == pytest.approx(1.3)


def test_reclaim_outcomes_reject_invalid_horizons():
    from trade_lab.research import measure_reclaim_outcomes

    with pytest.raises(ValueError, match="positive integers"):
        measure_reclaim_outcomes(pd.DataFrame(), StrategyConfig(), (0,))

def test_multi_instrument_research_uses_each_symbols_costs_and_records_provenance():
    result = run_walk_forward_research(
        {"ETF_A": bars_for_sessions(), "ETF_B": bars_for_sessions()},
        {"ETF_A": instrument("ETF_A"), "ETF_B": instrument("ETF_B")},
        {
            "ETF_A": BacktestCosts(spread_points=0.02),
            "ETF_B": BacktestCosts(spread_points=0.25, slippage_points=0.05),
        },
        [ResearchVariant("baseline", StrategyConfig(atr_period=1))],
        train_days=4, validation_days=2, test_days=2,
        data_sources={"ETF_A": "vendor-a 5m", "ETF_B": "vendor-b 5m"},
    )
    selected = result.loc[result["role"] == "selected_test"]
    assert set(selected["symbol"]) == {"ETF_A", "ETF_B"}
    assert dict(zip(selected["symbol"], selected["spread_points"], strict=True)) == {
        "ETF_A": 0.02, "ETF_B": 0.25
    }
    assert selected["config_hash"].str.len().eq(64).all()
    assert selected["data_bars"].eq(len(bars_for_sessions())).all()
    assert selected["instrument_quantity_unit"].eq("share").all()
    assert set(selected["data_source"]) == {"vendor-a 5m", "vendor-b 5m"}
    assert selected.groupby("window")["test_start"].nunique().eq(1).all()



def test_final_holdout_is_reserved_after_walk_forward_development():
    result = run_walk_forward_research(
        {"ETF": bars_for_sessions()},
        {"ETF": instrument("ETF")},
        {"ETF": BacktestCosts(spread_points=0.02)},
        [
            ResearchVariant("baseline", StrategyConfig(atr_period=1)),
            ResearchVariant(
                "filtered",
                StrategyConfig(atr_period=1, filters=StrategyFilters(min_atr_pct=0.1)),
            ),
        ],
        train_days=4,
        validation_days=2,
        test_days=2,
        final_holdout_days=2,
        data_sources={"ETF": "fixture: synthetic OHLCV 5m"},
    )
    holdout = result.loc[result["role"] == "final_holdout"]
    rolling = result.loc[result["role"] == "selected_test"]
    assert len(holdout) == 1
    assert holdout.iloc[0]["holdout_start"] > rolling["test_end"].max()
    assert holdout.iloc[0]["selected_on"] == "aggregate_validation_expectancy_r"
    assert pd.notna(holdout.iloc[0]["holdout_closed"])


def test_final_holdout_must_leave_development_sessions():
    with pytest.raises(ValueError, match="leave at least one development"):
        run_walk_forward_research(
            {"ETF": bars_for_sessions(5)},
            {"ETF": instrument("ETF")},
            {"ETF": BacktestCosts()},
            [ResearchVariant("baseline", StrategyConfig(atr_period=1))],
            train_days=2,
            validation_days=1,
            test_days=1,
            final_holdout_days=5,
            data_sources={"ETF": "fixture: synthetic OHLCV 5m"},
        )

def test_research_requires_explicit_data_provenance():
    with pytest.raises(ValueError, match="explicit data source"):
        run_walk_forward_research(
            {"ETF": bars_for_sessions()},
            {"ETF": instrument("ETF")},
            {"ETF": BacktestCosts()},
            [ResearchVariant("baseline", StrategyConfig(atr_period=1))],
            train_days=4,
            validation_days=2,
            test_days=2,
            data_sources={},
        )
