"""Historical execution simulation built on the live strategy and indicators."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .config import StrategyConfig
from .data import normalize_bars
from .sessions import NY, in_window
from .sizing import units_for_risk
from .strategy import LONG, first_signal, prepare


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
    """Resolve OHLC stop/target touches conservatively; stop wins collisions."""
    open_price = float(row["Open"])
    high = float(row["High"])
    low = float(row["Low"])
    if direction == LONG:
        if low <= stop:
            return min(open_price, stop), "STOP"
        if high >= target:
            return target, "TARGET"
    else:
        if high >= stop:
            return max(open_price, stop), "STOP"
        if low <= target:
            return target, "TARGET"
    return None


def run_backtest(
    bars: pd.DataFrame,
    cfg: StrategyConfig | None = None,
    start_date: date | None = None,
) -> pd.DataFrame:
    """Simulate one first-signal trade per NY date using the shared live rule.

    Signals enter at the signal bar close. Exit checks begin on the next bar,
    within the configured session. Unclosed positions are marked to market at
    the final in-window close and reported as OPEN, not counted as realized P&L.
    """
    config = cfg or StrategyConfig()
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

    for day in sorted(set(ny_dates)):
        if start_date is not None and day < start_date:
            continue
        signal = first_signal(prepared, config, day)
        if signal is None:
            continue

        entry_position = prepared.index.get_loc(signal.time)
        day_positions = [
            pos
            for pos, bar_day in enumerate(ny_dates)
            if bar_day == day and pos > entry_position and in_window(prepared.index[pos], config)
        ]
        units = units_for_risk(config.risk_dollars, signal.risk_distance)
        exit_price: float | None = None
        exit_time: pd.Timestamp | None = None
        exit_reason = "OPEN_AT_SESSION_END"
        status = "OPEN"
        last_mark: float | None = None

        for pos in day_positions:
            row = prepared.iloc[pos]
            last_mark = float(row["Close"])
            outcome = _exit_for_bar(signal.direction, row, signal.stop, signal.target)
            if outcome is None:
                continue
            exit_price, exit_reason = outcome
            exit_time = prepared.index[pos]
            status = "CLOSED"
            break

        if status == "OPEN" and day_positions:
            last_pos = day_positions[-1]
            last_mark = float(prepared.iloc[last_pos]["Close"])
            exit_time = prepared.index[last_pos]

        if status == "CLOSED" and exit_price is not None:
            points = (exit_price - signal.entry) * signal.direction
            realized = points * units
            unrealized = 0.0
            mark_price = exit_price
        else:
            realized = 0.0
            mark_price = last_mark if last_mark is not None else signal.entry
            unrealized = (mark_price - signal.entry) * signal.direction * units

        trades.append(
            {
                "Date": day.isoformat(),
                "Entry_Time": signal.time.isoformat(),
                "Exit_Time": exit_time.isoformat() if exit_time is not None else "",
                "Direction": signal.side,
                "Entry": signal.entry,
                "Stop": signal.stop,
                "Target": signal.target,
                "Exit": exit_price if exit_price is not None else "",
                "Units": units,
                "Status": status,
                "Exit_Reason": exit_reason,
                "Realized_PnL_$": round(realized, 2),
                "Unrealized_PnL_$": round(unrealized, 2),
                "Mark_Price": mark_price,
            }
        )

    return pd.DataFrame(trades)


def performance_summary(trades: pd.DataFrame) -> dict[str, float | int]:
    """Summarize closed trades only; open marks are deliberately excluded."""
    if trades.empty:
        return {
            "trades": 0,
            "closed": 0,
            "open": 0,
            "win_rate_pct": 0.0,
            "realized_pnl": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
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
    return {
        "trades": int(len(trades)),
        "closed": int(len(closed)),
        "open": int((trades["Status"] == "OPEN").sum()),
        "win_rate_pct": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "realized_pnl": float(pnl.sum()) if len(pnl) else 0.0,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "profit_factor": profit_factor,
    }
