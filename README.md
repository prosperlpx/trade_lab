# Trade Lab

A Python market-monitoring and Telegram alerting system for a VWAP pullback strategy. Live monitoring and maintained historical backtests share one strategy implementation. Trade Lab does not yet place broker orders or reconcile live positions.

## Current capabilities

- New York timezone-aware session handling and completed-bar filtering.
- Shared VWAP, true-range, ATR, and first-signal logic for live monitoring and historical backtests.
- Configurable spread, slippage, and commission simulation with risk-adjusted sizing.
- Trade ledger with gross/net P&L, execution costs, risk budget, and R-multiple metrics.
- Chronological multi-instrument research with per-symbol economics, costs, provenance, and holdout evaluation.
- Telegram alerting with validated, checkpointed state persistence.
- Pytest, Ruff, and documentation verification in GitHub Actions.

## Architecture direction

Instrument economics and broker execution are separate interfaces. The current foundation supports equity, ETF, index CFD, FX, futures, crypto, and other asset-class identifiers; each tradable instrument supplies its own tick economics and quantity constraints. Broker integrations implement a shared asynchronous adapter contract rather than being embedded in strategy logic.

Execution modes are explicit: disabled, paper, demo, and live. Broker submission is blocked in disabled/paper modes, demo mode rejects live accounts, and live mode is disabled unless separately enabled. These are foundations only; concrete broker adapters and automated order execution are not implemented.

## Important limitations

- Zero-cost backtests remain the default in the legacy Python API for backwards compatibility; the research CLI requires explicit cost assumptions.
- QQQ/NQ reference conversion is not a validated Exness US100 execution price.
- Historical input snapshots are not versioned; Yahoo Finance coverage and quality vary.
- No broker adapter or live order execution is implemented yet.
- A backtest is not evidence of profitability.

## Quick start

Requires Python 3.10 or newer.

~~~bash
git clone https://github.com/Emiloart/trade_lab.git
cd trade_lab
python -m venv .venv
~~~

Activate the environment:

~~~bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
~~~

Install:

~~~bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
~~~

## Run the monitor

~~~bash
python -m trade_lab.live --dry-run
~~~

## Run multi-instrument research

Prepare a JSON configuration with verified instrument specifications, explicit
cost assumptions, account-currency conversion rates, and CSV data provenance.
Then run:

~~~bash
python -m trade_lab.research_cli --config research.json --output reports/walk-forward.csv
~~~

See [Research methodology](docs/research.md) and the
[research CLI configuration guide](docs/research_cli.md) for details. See
[Backtesting](docs/backtesting.md) for execution-cost assumptions.

## Tests and lint

~~~bash
python -m pytest -q
ruff check .
python scripts/verify_docs.py
~~~

## Attribution

Maintained by **Emiloart**.
