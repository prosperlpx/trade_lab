"""Historical execution simulation built on the live strategy and indicators."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from .config import AccountRiskConfig, StrategyConfig, StrategyParameters
from .data import normalize_bars
from .instruments import InstrumentSpec
from .sessions import NY, in_window
from .sizing import quantity_for_instrument_risk
from .strategy import LONG, first_signal, prepare


@dataclass(frozen=True)
class BacktestCosts:
    """Static spread and slippage per fill; commission per unit per side."""

    spread_points: float = 0.0
    slippage_points: float = 0.0
    commission_per_unit: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("spread_points", self.spread_points),
            ("slippage_points", self.slippage_points),
            ("commission_per_unit", self.commission_per_unit),
        ):
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")

    @property
    def total_risk_cost_per_unit(self) -> float:
        """Round-trip spread, slippage, and commission in price-point units."""
        return (
            self.spread_points
            + 2.0 * self.slippage_points
            + 2.0 * self.commission_per_unit
        )


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load the repository's Datetime + OHLCV CSV format as normalized UTC bars."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Market data file not found: {source}")
    raw = pd.read_csv(source)
    if "Datetime" not in raw.columns:
        raise ValueError("CSV must contain a Datetime column")
    raw["Datetime"] = pd.to_datetime(raw["Datetime"], utc=True, errors="raise")
    return normalize_bars(raw.set_index("Datetime"))


def _exit_for_bar(
    direction: int, row: pd.Series, stop: float, target: float
) -> tuple[float, str] | None:
    """Resolve bracket fills from OHLC; stop wins collisions and gaps fill at open."""
    open_price = float(row["Open"])
    high = float(row["High"])
    low = float(row["Low"])
    if direction == LONG:
        if open_price <= stop:
            return open_price, "STOP_GAP"
        if open_price >= target:
            return open_price, "TARGET_GAP"
        stop_hit, target_hit = low <= stop, high >= target
        if stop_hit:
            return stop, "STOP"
        if target_hit:
            return target, "TARGET"
    else:
        if open_price >= stop:
            return open_price, "STOP_GAP"
        if open_price <= target:
            return open_price, "TARGET_GAP"
        stop_hit, target_hit = high >= stop, low <= target
        if stop_hit:
            return stop, "STOP"
        if target_hit:
            return target, "TARGET"
    return None


def _entry_rejection(direction: int, price: float, stop: float, target: float) -> str | None:
    """Do not chase a setup if the next bar opens beyond its original bracket."""
    if direction == LONG:
        if price <= stop:
            return "ENTRY_GAP_THROUGH_STOP"
        if price >= target:
            return "ENTRY_GAP_THROUGH_TARGET"
    else:
        if price >= stop:
            return "ENTRY_GAP_THROUGH_STOP"
        if price <= target:
            return "ENTRY_GAP_THROUGH_TARGET"
    return None


def run_backtest(
    bars: pd.DataFrame,
    cfg: StrategyParameters | None = None,
    start_date: date | None = None,
    costs: BacktestCosts | None = None,
    instrument: InstrumentSpec | None = None,
    value_to_account_rate: float = 1.0,
    risk: AccountRiskConfig | None = None,
) -> pd.DataFrame:
    """Simulate one first-signal trade per NY date using next-bar-open execution.

    A signal is known only after its candle closes. The earliest executable
    observation in this OHLC model is therefore the next in-window bar's open.
    Bracket levels remain anchored to the signal close. A next-bar open beyond
    either bracket rejects the setup rather than assuming a chase fill.

    OHLC bars cannot reveal whether stop or target traded first inside a candle;
    stop wins any intrabar collision. Stop gaps fill at the worse open. Static
    spread is paid half on each side, slippage is adverse on each fill, and
    commission is charged per unit per side. These are explicit assumptions,
    not a broker fill guarantee.
    """
    config = cfg or StrategyParameters()
    risk_config = risk or (
        AccountRiskConfig(config.account_size, config.risk_pct, config.max_daily_loss_pct)
        if isinstance(config, StrategyConfig)
        else AccountRiskConfig()
    )
    execution = costs or BacktestCosts()
    if bars.empty:
        return pd.DataFrame()
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("backtest bars require a timezone-aware DatetimeIndex")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("backtest bars must be sorted with unique timestamps")
    missing = {"Open", "High", "Low", "Close", "Volume"} - set(bars.columns)
    if missing:
        raise ValueError(f"backtest bars missing required columns: {sorted(missing)}")
    if bars[["Open", "High", "Low", "Close"]].isna().any().any():
        raise ValueError("backtest OHLC values cannot be missing")

    prepared = prepare(bars, config)
    ny_dates = prepared.index.tz_convert(NY).date
    trades: list[dict[str, object]] = []
    fill_cost = execution.spread_points / 2.0 + execution.slippage_points
    if instrument is not None and not isinstance(instrument, InstrumentSpec):
        raise TypeError("instrument must be an InstrumentSpec")

    for day in sorted(set(ny_dates)):
        if start_date is not None and day < start_date:
            continue
        signal = first_signal(prepared, config, day)
        if signal is None:
            continue

        signal_position = prepared.index.get_loc(signal.time)
        entry_position = signal_position + 1
        base = {
            "Date": day.isoformat(),
            "Symbol": instrument.symbol if instrument is not None else "",
            "Quantity_Unit": instrument.quantity_unit if instrument is not None else "unit",
            "Signal_Time": signal.time.isoformat(),
            "Signal_Entry": signal.entry,
            "Direction": signal.side,
            "Stop": signal.stop,
            "Target": signal.target,
        }
        if (
            entry_position >= len(prepared)
            or ny_dates[entry_position] != day
            or not in_window(prepared.index[entry_position], config)
        ):
            trades.append({
                **base, "Entry_Time": "", "Entry": "", "Entry_Reference": "",
                "Entry_Fill": "", "Exit_Time": "", "Exit": "", "Exit_Fill": "",
                "Units": 0.0, "Risk_Budget_$": 0.0, "Status": "NOT_EXECUTED",
                "Exit_Reason": "NO_NEXT_IN_SESSION_BAR", "Gross_PnL_$": 0.0,
                "Execution_Costs_$": 0.0, "Realized_PnL_$": 0.0,
                "Unrealized_PnL_$": 0.0, "R_Multiple": 0.0,
                "Signal_R_Multiple": 0.0, "Mark_Price": signal.entry,
            })
            continue

        entry_time = prepared.index[entry_position]
        entry_reference = float(prepared.iloc[entry_position]["Open"])
        rejection = _entry_rejection(
            signal.direction, entry_reference, signal.stop, signal.target
        )
        if rejection is not None:
            trades.append({
                **base, "Entry_Time": entry_time.isoformat(),
                "Entry": entry_reference, "Entry_Reference": entry_reference,
                "Entry_Fill": "", "Exit_Time": "", "Exit": "", "Exit_Fill": "",
                "Units": 0.0, "Risk_Budget_$": 0.0, "Status": "NOT_EXECUTED",
                "Exit_Reason": rejection, "Gross_PnL_$": 0.0,
                "Execution_Costs_$": 0.0, "Realized_PnL_$": 0.0,
                "Unrealized_PnL_$": 0.0, "R_Multiple": 0.0,
                "Signal_R_Multiple": 0.0, "Mark_Price": entry_reference,
            })
            continue

        stop_distance = abs(entry_reference - signal.stop)
        if instrument is None:
            risk_per_unit = stop_distance + execution.total_risk_cost_per_unit
            units = risk_config.risk_dollars / risk_per_unit
        else:
            if (
                isinstance(value_to_account_rate, bool)
                or not math.isfinite(value_to_account_rate)
                or value_to_account_rate <= 0
            ):
                raise ValueError("value_to_account_rate must be a positive finite number")
            point_value = (
                instrument.tick_value / instrument.tick_size * value_to_account_rate
            )
            commission_points = 2.0 * execution.commission_per_unit / point_value
            effective_stop_distance = (
                stop_distance + execution.spread_points
                + 2.0 * execution.slippage_points + commission_points
            )
            units = quantity_for_instrument_risk(
                risk_config.risk_dollars, effective_stop_distance,
                instrument, value_to_account_rate,
            )
            if units <= 0:
                continue
            risk_per_unit = point_value * (
                stop_distance + execution.spread_points
                + 2.0 * execution.slippage_points
            ) + 2.0 * execution.commission_per_unit

        entry_fill = entry_reference + signal.direction * fill_cost
        exit_reference: float | None = None
        exit_fill: float | None = None
        exit_time: pd.Timestamp | None = None
        exit_reason = "OPEN_AT_SESSION_END"
        status = "OPEN"
        last_mark = entry_reference

        last_position = entry_position
        for pos in range(entry_position, len(prepared)):
            if ny_dates[pos] != day or not in_window(prepared.index[pos], config):
                break
            last_position = pos
            row = prepared.iloc[pos]
            last_mark = float(row["Close"])
            outcome = _exit_for_bar(signal.direction, row, signal.stop, signal.target)
            if outcome is None:
                continue
            exit_reference, exit_reason = outcome
            exit_fill = exit_reference - signal.direction * fill_cost
            exit_time = prepared.index[pos]
            status = "CLOSED"
            break

        if status == "OPEN":
            last_mark = float(prepared.iloc[last_position]["Close"])
            exit_time = prepared.index[last_position]
            exit_reference = last_mark
            exit_fill = exit_reference - signal.direction * fill_cost

        account_value_per_point = (
            instrument.tick_value / instrument.tick_size * value_to_account_rate
            if instrument is not None else 1.0
        )
        gross_pnl = (
            (exit_reference - entry_reference) * signal.direction
            * account_value_per_point * units
        )
        net_pnl = (
            (exit_fill - entry_fill) * signal.direction
            * account_value_per_point * units
            - 2.0 * execution.commission_per_unit * units
        )
        modeled_costs = gross_pnl - net_pnl
        risk_budget = units * risk_per_unit
        r_multiple = net_pnl / risk_budget if risk_budget else 0.0
        signal_r = (
            (exit_reference - signal.entry) * signal.direction / signal.risk_distance
        )
        realized = net_pnl if status == "CLOSED" else 0.0
        unrealized = net_pnl if status == "OPEN" else 0.0
        trades.append({
            **base,
            "Entry_Time": entry_time.isoformat(),
            "Entry": entry_reference,
            "Entry_Reference": entry_reference,
            "Entry_Fill": entry_fill,
            "Exit_Time": exit_time.isoformat() if exit_time is not None else "",
            "Exit": exit_reference if status == "CLOSED" else "",
            "Exit_Fill": exit_fill,
            "Units": units,
            "Risk_Budget_$": round(risk_budget, 2),
            "Status": status,
            "Exit_Reason": exit_reason,
            "Gross_PnL_$": round(gross_pnl, 2),
            "Execution_Costs_$": round(modeled_costs, 2),
            "Realized_PnL_$": round(realized, 2),
            "Unrealized_PnL_$": round(unrealized, 2),
            "R_Multiple": round(r_multiple, 4),
            "Signal_R_Multiple": round(signal_r, 4),
            "Mark_Price": float(exit_reference),
        })
    return pd.DataFrame(trades)


def performance_summary(trades: pd.DataFrame) -> dict[str, float | int]:
    """Summarize executable outcomes separately from signal-close reference outcomes."""
    if trades.empty:
        return {
            "trades": 0, "signals": 0, "closed": 0, "open": 0, "not_executed": 0,
            "win_rate_pct": 0.0, "realized_pnl": 0.0, "max_drawdown": 0.0,
            "profit_factor": 0.0, "average_r": 0.0, "expectancy_r": 0.0,
            "signal_expectancy_r": 0.0, "execution_costs": 0.0,
        }
    closed = trades.loc[trades["Status"] == "CLOSED"].copy()
    pnl = closed["Realized_PnL_$"].astype(float)
    cumulative = pnl.cumsum()
    peak = cumulative.cummax().clip(lower=0)
    drawdown = cumulative - peak
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = abs(float(pnl[pnl < 0].sum()))
    profit_factor = gross_profit / gross_loss if gross_loss else (
        float("inf") if gross_profit else 0.0
    )
    r_values = (
        closed["R_Multiple"].astype(float)
        if "R_Multiple" in closed else pd.Series(dtype=float)
    )
    signal_r = (
        closed["Signal_R_Multiple"].astype(float)
        if "Signal_R_Multiple" in closed else pd.Series(dtype=float)
    )
    costs_total = (
        float(trades["Execution_Costs_$"].astype(float).sum())
        if "Execution_Costs_$" in trades else 0.0
    )
    average_r = float(r_values.mean()) if len(r_values) else 0.0
    return {
        "trades": int((trades["Status"] != "NOT_EXECUTED").sum()),
        "signals": int(len(trades)),
        "closed": int(len(closed)),
        "open": int((trades["Status"] == "OPEN").sum()),
        "not_executed": int((trades["Status"] == "NOT_EXECUTED").sum()),
        "win_rate_pct": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "realized_pnl": float(pnl.sum()) if len(pnl) else 0.0,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "profit_factor": profit_factor,
        "average_r": average_r,
        "expectancy_r": average_r,
        "signal_expectancy_r": float(signal_r.mean()) if len(signal_r) else 0.0,
        "execution_costs": costs_total,
    }
