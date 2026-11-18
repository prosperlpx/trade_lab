"""Statistical diagnostics for strategy research.

Intervals use a moving-block bootstrap over New York trading dates. Blocks
preserve short-range serial dependence; they do not eliminate regime or
cross-instrument dependence. Family-wise intervals use Bonferroni adjustment.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd


def block_bootstrap_summary(
    trades: pd.DataFrame,
    *,
    confidence_level: float = 0.95,
    bootstrap_samples: int = 2000,
    block_length: int = 5,
    family_size: int = 1,
    seed: int = 1729,
) -> dict[str, float | int]:
    """Estimate expectancy and win-rate intervals by resampling date blocks."""
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0 and 1")
    if (
        isinstance(bootstrap_samples, bool)
        or not isinstance(bootstrap_samples, int)
        or bootstrap_samples < 200
    ):
        raise ValueError("bootstrap_samples must be an integer >= 200")
    if (
        isinstance(block_length, bool)
        or not isinstance(block_length, int)
        or block_length < 1
    ):
        raise ValueError("block_length must be a positive integer")
    if (
        isinstance(family_size, bool)
        or not isinstance(family_size, int)
        or family_size < 1
    ):
        raise ValueError("family_size must be a positive integer")

    closed = (
        trades.loc[trades["Status"] == "CLOSED"].copy()
        if not trades.empty else trades.copy()
    )
    if closed.empty:
        return {
            "sample_trades": 0,
            "sample_days": 0,
            "expectancy_ci_low": 0.0,
            "expectancy_ci_high": 0.0,
            "adjusted_expectancy_ci_low": 0.0,
            "adjusted_expectancy_ci_high": 0.0,
            "win_rate_ci_low": 0.0,
            "win_rate_ci_high": 0.0,
            "adjusted_confidence_level": 1.0 - (1.0 - confidence_level) / family_size,
        }

    closed["Date"] = closed["Date"].astype(str)
    closed["R_Multiple"] = closed["R_Multiple"].astype(float)
    closed["is_win"] = closed["R_Multiple"] > 0
    daily = (
        closed.groupby("Date", sort=True)
        .agg(r_sum=("R_Multiple", "sum"), wins=("is_win", "sum"), count=("is_win", "size"))
        .reset_index(drop=True)
    )
    day_count = len(daily)
    if day_count < 2:
        expectancy = float(closed["R_Multiple"].mean())
        win_rate = float(closed["is_win"].mean())
        return {
            "sample_trades": int(len(closed)),
            "sample_days": day_count,
            "expectancy_ci_low": float("nan"),
            "expectancy_ci_high": float("nan"),
            "adjusted_expectancy_ci_low": float("nan"),
            "adjusted_expectancy_ci_high": float("nan"),
            "win_rate_ci_low": float("nan"),
            "win_rate_ci_high": float("nan"),
            "adjusted_confidence_level": 1.0 - (1.0 - confidence_level) / family_size,
            "point_expectancy": expectancy,
            "point_win_rate_pct": win_rate * 100.0,
        }

    values = daily[["r_sum", "wins", "count"]].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    block = min(block_length, day_count)
    blocks_needed = math.ceil(day_count / block)
    expectancy_samples = np.empty(bootstrap_samples, dtype=float)
    win_samples = np.empty(bootstrap_samples, dtype=float)
    starts = np.arange(day_count)
    for sample in range(bootstrap_samples):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        indices = np.concatenate(
            [(np.arange(start, start + block) % day_count) for start in chosen]
        )[:day_count]
        sample_values = values[indices]
        trade_count = float(sample_values[:, 2].sum())
        expectancy_samples[sample] = (
            float(sample_values[:, 0].sum()) / trade_count if trade_count else 0.0
        )
        win_samples[sample] = (
            float(sample_values[:, 1].sum()) / trade_count if trade_count else 0.0
        )

    alpha = 1.0 - confidence_level
    adjusted_confidence = 1.0 - alpha / family_size
    low = alpha / 2.0
    high = 1.0 - low
    adjusted_tail = (1.0 - adjusted_confidence) / 2.0
    point_expectancy = float(closed["R_Multiple"].mean())
    point_win_rate = float(closed["is_win"].mean())
    return {
        "sample_trades": int(len(closed)),
        "sample_days": day_count,
        "point_expectancy": point_expectancy,
        "point_win_rate_pct": point_win_rate * 100.0,
        "expectancy_ci_low": float(np.quantile(expectancy_samples, low)),
        "expectancy_ci_high": float(np.quantile(expectancy_samples, high)),
        "adjusted_expectancy_ci_low": float(np.quantile(expectancy_samples, adjusted_tail)),
        "adjusted_expectancy_ci_high": float(np.quantile(expectancy_samples, 1.0 - adjusted_tail)),
        "win_rate_ci_low": float(np.quantile(win_samples, low) * 100.0),
        "win_rate_ci_high": float(np.quantile(win_samples, high) * 100.0),
        "adjusted_confidence_level": adjusted_confidence,
    }


def rejection_reasons(
    summary: dict[str, float | int],
    *,
    minimum_trades: int,
    require_positive_adjusted_lower_bound: bool = True,
) -> list[str]:
    """Return explicit, deterministic rejection reasons for an evaluation."""
    reasons: list[str] = []
    if int(summary.get("sample_trades", 0)) < minimum_trades:
        reasons.append("INSUFFICIENT_TRADES")
    lower = float(summary.get("adjusted_expectancy_ci_low", float("nan")))
    if require_positive_adjusted_lower_bound and (
        not math.isfinite(lower) or lower <= 0
    ):
        reasons.append("NON_POSITIVE_ADJUSTED_EXPECTANCY_LOWER_BOUND")
    return reasons


def cost_scenarios(
    base_costs: object, multipliers: Sequence[float]
) -> list[tuple[float, object]]:
    """Scale all modeled transaction-cost components by each stress multiplier."""
    from .backtest import BacktestCosts

    if not isinstance(base_costs, BacktestCosts):
        raise TypeError("base_costs must be BacktestCosts")
    if not multipliers or any(
        isinstance(value, bool) or not math.isfinite(value) or value < 1
        for value in multipliers
    ):
        raise ValueError("cost stress multipliers must be finite numbers >= 1")
    if len(set(multipliers)) != len(multipliers) or 1.0 not in multipliers:
        raise ValueError("cost stress multipliers must be unique and include 1.0")
    return [
        (
            float(multiplier),
            BacktestCosts(
                spread_points=base_costs.spread_points * multiplier,
                slippage_points=base_costs.slippage_points * multiplier,
                commission_per_unit=base_costs.commission_per_unit * multiplier,
            ),
        )
        for multiplier in multipliers
    ]
