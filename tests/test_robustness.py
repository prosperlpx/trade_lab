import pandas as pd
import pytest

from trade_lab.backtest import BacktestCosts
from trade_lab.robustness import (
    block_bootstrap_summary,
    cost_scenarios,
    rejection_reasons,
)


def _trades(values):
    return pd.DataFrame({
        "Date": [f"2026-01-{day:02d}" for day in range(1, len(values) + 1)],
        "Status": ["CLOSED"] * len(values),
        "R_Multiple": values,
    })


def test_block_bootstrap_is_deterministic_and_reports_trade_and_day_counts():
    trades = _trades([0.5, 0.3, -0.1, 0.4, 0.2, 0.1, -0.2, 0.6])
    first = block_bootstrap_summary(
        trades, bootstrap_samples=500, block_length=2, seed=7
    )
    second = block_bootstrap_summary(
        trades, bootstrap_samples=500, block_length=2, seed=7
    )
    assert first == second
    assert first["sample_trades"] == 8
    assert first["sample_days"] == 8
    assert first["expectancy_ci_low"] <= first["expectancy_ci_high"]


def test_bonferroni_family_size_widens_adjusted_expectancy_interval():
    trades = _trades([0.5, 0.3, -0.1, 0.4, 0.2, 0.1, -0.2, 0.6])
    ordinary = block_bootstrap_summary(
        trades, bootstrap_samples=500, block_length=2, family_size=1
    )
    adjusted = block_bootstrap_summary(
        trades, bootstrap_samples=500, block_length=2, family_size=10
    )
    assert adjusted["adjusted_expectancy_ci_low"] <= ordinary["expectancy_ci_low"]
    assert adjusted["adjusted_expectancy_ci_high"] >= ordinary["expectancy_ci_high"]


def test_single_day_sample_does_not_claim_a_confidence_interval():
    summary = block_bootstrap_summary(
        _trades([0.5]), bootstrap_samples=500, block_length=1
    )
    assert summary["sample_trades"] == 1
    assert pd.isna(summary["adjusted_expectancy_ci_low"])


def test_rejection_reasons_enforce_sample_size_and_adjusted_lower_bound():
    summary = {
        "sample_trades": 8,
        "adjusted_expectancy_ci_low": -0.02,
    }
    assert rejection_reasons(summary, minimum_trades=10) == [
        "INSUFFICIENT_TRADES",
        "NON_POSITIVE_ADJUSTED_EXPECTANCY_LOWER_BOUND",
    ]


def test_cost_scenarios_scale_all_execution_cost_components():
    scenarios = cost_scenarios(
        BacktestCosts(spread_points=0.02, slippage_points=0.01, commission_per_unit=0.03),
        (1.0, 2.0, 3.0),
    )
    assert [item[0] for item in scenarios] == [1.0, 2.0, 3.0]
    assert scenarios[1][1] == BacktestCosts(
        spread_points=0.04, slippage_points=0.02, commission_per_unit=0.06
    )


@pytest.mark.parametrize("multipliers", [(2.0,), (1.0, 1.0), (0.5, 1.0)])
def test_cost_scenarios_require_unique_multipliers_at_or_above_one(multipliers):
    with pytest.raises(ValueError):
        cost_scenarios(BacktestCosts(), multipliers)
