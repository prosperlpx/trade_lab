"""Full-history backtest using the shared live strategy implementation."""

from backtests._common import DATA_FILE, execute
from trade_lab.backtest import load_csv, run_backtest
from trade_lab.config import StrategyConfig


def load_and_prepare_data():
    """Load normalized UTC bars; indicators are prepared by the shared engine."""
    return load_csv(DATA_FILE)


def run_vwap_backtest(df):
    """Run the shared strategy and historical execution simulation."""
    return run_backtest(df, StrategyConfig.from_env())


if __name__ == "__main__":
    execute(output_name="backtest_results_shared.csv")
