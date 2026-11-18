"""Shared command-line helpers for historical backtest entry points."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from trade_lab.backtest import load_csv, performance_summary, run_backtest
from trade_lab.config import StrategyConfig

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "us100_5m.csv"


def execute(start_date=None, output_name: str = "backtest_results.csv") -> pd.DataFrame:
    bars = load_csv(DATA_FILE)
    cfg = StrategyConfig.from_env()
    trades = run_backtest(bars, cfg, start_date=start_date)
    if trades.empty:
        print("No qualifying strategy signals were found.")
        return trades

    summary = performance_summary(trades)
    print("\nSHARED STRATEGY BACKTEST")
    print(f"Signals: {summary['trades']} | Closed: {summary['closed']} | Open: {summary['open']}")
    print(f"Win rate (closed): {summary['win_rate_pct']:.2f}%")
    print(f"Realized P&L (closed only): ${summary['realized_pnl']:.2f}")
    print(f"Maximum realized drawdown: ${summary['max_drawdown']:.2f}")
    print(f"Profit factor (closed only): {summary['profit_factor']:.2f}")
    output = DATA_FILE.parent / output_name
    trades.to_csv(output, index=False)
    print(f"Trade ledger written to {output}")
    return trades
