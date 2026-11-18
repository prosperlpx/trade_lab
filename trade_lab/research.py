"""Chronological strategy research with instrument-specific execution assumptions.

Variants are ranked on validation intervals. Their selected configurations are
then evaluated on subsequent test intervals, which do not participate in selection.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

from .backtest import BacktestCosts, performance_summary, run_backtest
from .config import AccountRiskConfig, StrategyConfig, StrategyParameters
from .instruments import InstrumentSpec
from .sessions import NY, in_window
from .strategy import Signal, signal_for_bar


@dataclass(frozen=True)
class ResearchVariant:
    """Named strategy configuration included in a research universe."""
    name: str
    config: StrategyParameters

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("variant name cannot be empty")


@dataclass(frozen=True)
class WalkForwardWindow:
    """Chronological date ranges; boundaries are inclusive."""
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date


def make_walk_forward_windows(
    trading_dates: list[date],
    train_days: int,
    validation_days: int,
    test_days: int,
    step_days: int | None = None,
) -> list[WalkForwardWindow]:
    """Create expanding-history, rolling-forward windows over observed sessions."""
    sizes = (train_days, validation_days, test_days)
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in sizes):
        raise ValueError("train_days, validation_days and test_days must be positive integers")
    step = test_days if step_days is None else step_days
    if isinstance(step, bool) or not isinstance(step, int) or step < 1:
        raise ValueError("step_days must be a positive integer")
    dates = sorted(set(trading_dates))
    windows: list[WalkForwardWindow] = []
    first_test = train_days + validation_days
    for test_start in range(first_test, len(dates) - test_days + 1, step):
        windows.append(
            WalkForwardWindow(
                train_start=dates[0],
                train_end=dates[test_start - validation_days - 1],
                validation_start=dates[test_start - validation_days],
                validation_end=dates[test_start - 1],
                test_start=dates[test_start],
                test_end=dates[test_start + test_days - 1],
            )
        )
    return windows


def _summary_for_range(
    trades: pd.DataFrame, start: date, end: date
) -> dict[str, float | int]:
    if trades.empty:
        selected = trades
    else:
        selected = trades.loc[trades["Date"].map(date.fromisoformat).between(start, end)]
    return performance_summary(selected)


def _config_fingerprint(config: StrategyParameters) -> str:
    canonical = json.dumps(asdict(config), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _selection_key(summary: Mapping[str, float | int]) -> tuple[float, float, int]:
    expectancy = float(summary["expectancy_r"])
    profit_factor = float(summary["profit_factor"])
    if not math.isfinite(profit_factor):
        profit_factor = 1_000_000.0
    return expectancy, profit_factor, int(summary["closed"])


def run_walk_forward_research(
    datasets: Mapping[str, pd.DataFrame],
    instruments: Mapping[str, InstrumentSpec],
    costs: Mapping[str, BacktestCosts],
    variants: list[ResearchVariant],
    *,
    train_days: int,
    validation_days: int,
    test_days: int,
    step_days: int | None = None,
    value_to_account_rates: Mapping[str, float] | None = None,
    risk: AccountRiskConfig | None = None,
    data_sources: Mapping[str, str],
    final_holdout_days: int = 0,
) -> pd.DataFrame:
    """Evaluate symbols on shared calendar windows and explicit per-symbol costs.

    The intersection of observed New York sessions is used for every symbol,
    keeping cross-instrument train/validation/test date boundaries aligned.
    Each symbol/variant backtest is computed once and reused across windows.
    Validation expectancy selects the variant; test data never participates
    in selection. Full history is passed to preserve indicator warm-up.
    """
    if not datasets:
        raise ValueError("at least one dataset is required")
    if not variants:
        raise ValueError("at least one research variant is required")
    if len({variant.name for variant in variants}) != len(variants):
        raise ValueError("research variant names must be unique")
    if (
        isinstance(final_holdout_days, bool)
        or not isinstance(final_holdout_days, int)
        or final_holdout_days < 0
    ):
        raise ValueError("final_holdout_days must be a non-negative integer")

    rates = value_to_account_rates or {}
    sources = data_sources
    sessions_by_symbol: dict[str, set[date]] = {}
    for symbol, bars in datasets.items():
        if symbol not in instruments or symbol not in costs:
            raise ValueError(f"{symbol} requires explicit instrument economics and costs")
        if instruments[symbol].symbol != symbol:
            instrument_symbol = instruments[symbol].symbol
            raise ValueError(
                f"instrument key {symbol!r} does not match {instrument_symbol!r}"
            )
        if bars.empty or not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
            raise ValueError(f"{symbol} requires non-empty timezone-aware bars")
        if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
            raise ValueError(f"{symbol} bars must be sorted with unique timestamps")
        if symbol not in sources or not sources[symbol].strip():
            raise ValueError(f"{symbol} requires an explicit data source description")
        sessions_by_symbol[symbol] = set(bars.index.tz_convert(NY).date)

    common_sessions = sorted(set.intersection(*sessions_by_symbol.values()))
    if final_holdout_days >= len(common_sessions) and final_holdout_days:
        raise ValueError("final holdout must leave at least one development session")
    holdout_sessions = (
        common_sessions[-final_holdout_days:] if final_holdout_days else []
    )
    development_sessions = (
        common_sessions[:-final_holdout_days] if final_holdout_days else common_sessions
    )
    windows = make_walk_forward_windows(
        development_sessions, train_days, validation_days, test_days, step_days
    )
    if not windows:
        raise ValueError(
            f"only {len(common_sessions)} common New York sessions; "
            "insufficient for requested walk-forward windows"
        )

    validation_sessions = {
        session
        for window in windows
        for session in common_sessions
        if window.validation_start <= session <= window.validation_end
    }
    output: list[dict[str, object]] = []
    for symbol, bars in datasets.items():
        instrument = instruments[symbol]
        execution_costs = costs[symbol]
        trades_by_variant: dict[str, pd.DataFrame] = {}
        metadata_by_variant: dict[str, dict[str, object]] = {}

        for variant in variants:
            trades_by_variant[variant.name] = run_backtest(
                bars,
                variant.config,
                costs=execution_costs,
                instrument=instrument,
                value_to_account_rate=rates.get(symbol, 1.0),
                risk=risk,
            )
            variant_risk = risk or (
                AccountRiskConfig(
                    variant.config.account_size,
                    variant.config.risk_pct,
                    variant.config.max_daily_loss_pct,
                )
                if isinstance(variant.config, StrategyConfig)
                else AccountRiskConfig()
            )
            metadata_by_variant[variant.name] = {
                "config_hash": _config_fingerprint(variant.config),
                "data_source": sources[symbol],
                "data_hash": hashlib.sha256(
                    (
                        "|".join(map(str, bars.columns))
                        + pd.util.hash_pandas_object(bars, index=True).values.tobytes().hex()
                    ).encode("utf-8")
                ).hexdigest(),
                "data_start": bars.index[0].isoformat(),
                "data_end": bars.index[-1].isoformat(),
                "data_bars": len(bars),
                "instrument_tick_size": instrument.tick_size,
                "instrument_tick_value": instrument.tick_value,
                "instrument_tick_value_currency": instrument.tick_value_currency,
                "instrument_quantity_unit": instrument.quantity_unit,
                "instrument_min_quantity": instrument.min_quantity,
                "instrument_quantity_step": instrument.quantity_step,
                "instrument_max_quantity": instrument.max_quantity,
                "spread_points": execution_costs.spread_points,
                "slippage_points": execution_costs.slippage_points,
                "commission_per_unit": execution_costs.commission_per_unit,
                "value_to_account_rate": rates.get(symbol, 1.0),
                "account_size": variant_risk.account_size,
                "risk_pct": variant_risk.risk_pct,
                "max_daily_loss_pct": variant_risk.max_daily_loss_pct,
            }

        for window_number, window in enumerate(windows, start=1):
            evaluated = []
            for variant in variants:
                trades = trades_by_variant[variant.name]
                train = _summary_for_range(trades, window.train_start, window.train_end)
                validation = _summary_for_range(
                    trades, window.validation_start, window.validation_end
                )
                evaluated.append((variant, validation))
                output.append({
                    "symbol": symbol,
                    "window": window_number,
                    "variant": variant.name,
                    "role": "candidate",
                    **metadata_by_variant[variant.name],
                    "train_start": window.train_start.isoformat(),
                    "train_end": window.train_end.isoformat(),
                    "validation_start": window.validation_start.isoformat(),
                    "validation_end": window.validation_end.isoformat(),
                    "test_start": window.test_start.isoformat(),
                    "test_end": window.test_end.isoformat(),
                    **{f"train_{key}": value for key, value in train.items()},
                    **{f"validation_{key}": value for key, value in validation.items()},
                })

            selected_variant, _ = max(evaluated, key=lambda item: _selection_key(item[1]))
            test = _summary_for_range(
                trades_by_variant[selected_variant.name], window.test_start, window.test_end
            )
            output.append({
                "symbol": symbol,
                "window": window_number,
                "variant": selected_variant.name,
                "role": "selected_test",
                "selected_on": "validation_expectancy_r",
                **metadata_by_variant[selected_variant.name],
                "train_start": window.train_start.isoformat(),
                "train_end": window.train_end.isoformat(),
                "validation_start": window.validation_start.isoformat(),
                "validation_end": window.validation_end.isoformat(),
                "test_start": window.test_start.isoformat(),
                "test_end": window.test_end.isoformat(),
                **{f"test_{key}": value for key, value in test.items()},
            })

        if holdout_sessions:
            aggregate = []
            for variant in variants:
                trades = trades_by_variant[variant.name]
                validation_trades = (
                    trades.loc[
                        trades["Date"].map(date.fromisoformat).isin(validation_sessions)
                    ]
                    if not trades.empty
                    else trades
                )
                aggregate.append((variant, performance_summary(validation_trades)))
            final_variant, _ = max(aggregate, key=lambda item: _selection_key(item[1]))
            holdout = _summary_for_range(
                trades_by_variant[final_variant.name],
                holdout_sessions[0],
                holdout_sessions[-1],
            )
            output.append({
                "symbol": symbol,
                "window": "final",
                "variant": final_variant.name,
                "role": "final_holdout",
                "selected_on": "aggregate_validation_expectancy_r",
                **metadata_by_variant[final_variant.name],
                "validation_sessions_used": len(validation_sessions),
                "holdout_start": holdout_sessions[0].isoformat(),
                "holdout_end": holdout_sessions[-1].isoformat(),
                **{f"holdout_{key}": value for key, value in holdout.items()},
            })
    return pd.DataFrame(output)


def measure_reclaim_outcomes(
    prepared: pd.DataFrame,
    config: StrategyParameters,
    horizons_bars: tuple[int, ...] = (3, 6, 12),
) -> pd.DataFrame:
    """Measure forward excursion after every qualifying reclaim candidate.

    Outcomes are normalized by the signal's initial stop distance (R). Only
    complete horizons contained within the same New York session date are
    included. This is a descriptive label study, not a trade simulation.
    """
    if not horizons_bars or any(
        isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1
        for horizon in horizons_bars
    ):
        raise ValueError("horizons_bars must contain positive integers")
    if len(set(horizons_bars)) != len(horizons_bars):
        raise ValueError("horizons_bars must not contain duplicates")
    if not isinstance(prepared.index, pd.DatetimeIndex) or prepared.index.tz is None:
        raise ValueError("prepared bars require a timezone-aware DatetimeIndex")
    if prepared.index.has_duplicates or not prepared.index.is_monotonic_increasing:
        raise ValueError("prepared bars must be sorted with unique timestamps")

    ny_dates = prepared.index.tz_convert(NY).date
    rows: list[dict[str, object]] = []
    for position, (stamp, bar) in enumerate(prepared.iterrows()):
        if not in_window(stamp, config):
            continue
        signal: Signal | None = signal_for_bar(stamp, bar, config)
        if signal is None:
            continue
        for horizon in horizons_bars:
            end_position = position + horizon
            if end_position >= len(prepared):
                continue
            if ny_dates[end_position] != ny_dates[position]:
                continue
            future = prepared.iloc[position + 1 : end_position + 1]
            direction = signal.direction
            favorable = (
                future["High"].astype(float) - signal.entry
                if direction == 1
                else signal.entry - future["Low"].astype(float)
            )
            adverse = (
                signal.entry - future["Low"].astype(float)
                if direction == 1
                else future["High"].astype(float) - signal.entry
            )
            rows.append(
                {
                    "signal_time": stamp.isoformat(),
                    "direction": signal.side,
                    "entry": signal.entry,
                    "risk_distance": signal.risk_distance,
                    "horizon_bars": horizon,
                    "horizon_end_time": future.index[-1].isoformat(),
                    "pullback_depth_atr": (
                        max(0.0, float(bar["VWAP"]) - float(bar["Low"]))
                        if direction == 1
                        else max(0.0, float(bar["High"]) - float(bar["VWAP"]))
                    ) / float(bar["ATR"]),
                    "vwap_slope_atr": float(bar.get("VWAP_SLOPE_ATR", float("nan"))),
                    "atr_pct": float(bar.get("ATR_PCT", float("nan"))),
                    "reclaim_close_distance_atr": (
                        direction * (float(bar["Close"]) - float(bar["VWAP"]))
                        / float(bar["ATR"])
                    ),
                    "reclaim_candle_range_atr": (
                        float(bar["High"]) - float(bar["Low"])
                    ) / float(bar["ATR"]),
                    "follow_through_r": (
                        (float(future["Close"].iloc[-1]) - signal.entry)
                        * direction
                        / signal.risk_distance
                    ),
                    "mfe_r": max(0.0, float(favorable.max())) / signal.risk_distance,
                    "mae_r": max(0.0, float(adverse.max())) / signal.risk_distance,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "signal_time", "direction", "entry", "risk_distance", "horizon_bars",
            "horizon_end_time", "pullback_depth_atr", "vwap_slope_atr",
            "atr_pct", "reclaim_close_distance_atr", "reclaim_candle_range_atr",
            "follow_through_r", "mfe_r", "mae_r",
        ],
    )
