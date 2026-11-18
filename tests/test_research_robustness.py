import pandas as pd

from trade_lab.backtest import BacktestCosts
from trade_lab.config import StrategyConfig
from trade_lab.instruments import AssetClass, InstrumentSpec
from trade_lab.research import ResearchVariant, run_walk_forward_research


def _bars_for_sessions(sessions=12):
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


def _instrument():
    return InstrumentSpec(
        symbol="ETF", asset_class=AssetClass.ETF, quote_currency="USD",
        tick_size=0.01, tick_value=0.01, tick_value_currency="USD",
        quantity_unit="share", min_quantity=1, quantity_step=1, max_quantity=100_000,
    )


def test_walk_forward_reports_uncertainty_sensitivity_and_cost_stress():
    report = run_walk_forward_research(
        {"ETF": _bars_for_sessions()},
        {"ETF": _instrument()},
        {"ETF": BacktestCosts(spread_points=0.02, slippage_points=0.01)},
        [
            ResearchVariant("baseline", StrategyConfig(atr_period=1), "atr-neighborhood"),
            ResearchVariant("alternate", StrategyConfig(atr_period=2), "atr-neighborhood"),
        ],
        train_days=4,
        validation_days=2,
        test_days=2,
        step_days=2,
        data_sources={"ETF": "synthetic fixture, 5m"},
        bootstrap_samples=200,
        bootstrap_block_length=2,
        cost_stress_multipliers=(1.0, 2.0),
    )
    candidates = report.loc[report["role"] == "candidate"]
    selected = report.loc[report["role"] == "selected_test"]
    assert candidates["validation_sample_trades"].notna().all()
    assert candidates["sensitivity_group"].eq("atr-neighborhood").all()
    assert candidates["sensitivity_variant_count"].eq(2).all()
    assert selected["decision"].eq("REJECT").all()
    assert "test_cost_2x_adjusted_ci_low" in selected.columns
    assert "COST_STRESS_FAILURE" in ";".join(selected["rejection_reasons"].astype(str))
