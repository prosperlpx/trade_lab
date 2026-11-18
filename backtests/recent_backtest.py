"""Recent-period backtest using the shared live strategy implementation."""

from datetime import date

from backtests._common import DATA_FILE, execute
from trade_lab.backtest import load_csv, run_backtest
from trade_lab.config import StrategyConfig

START_DATE = date.fromisoformat("2026-10-28")


def load_and_prepare_data():
    """Load normalized UTC bars; retain full history for ATR warm-up."""
    return load_csv(DATA_FILE)


def run_recent_backtest(df):
    """Run the shared strategy from START_DATE after full-frame indicator preparation."""
    return run_backtest(df, StrategyConfig.from_env(), start_date=START_DATE)


if __name__ == "__main__":
    execute(start_date=START_DATE, output_name="recent_backtest_results_shared.csv")
