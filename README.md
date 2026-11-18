# Trade Lab

Trade Lab is a Python research and market-monitoring platform for systematic trading strategies. It brings strategy evaluation, historical execution simulation, multi-instrument research, and live market alerts into one codebase.

The project is built around a VWAP pullback strategy. Its research and monitoring workflows share the same strategy logic, while instrument specifications and execution assumptions remain explicit inputs to the analysis.

## What it does

- **Market monitoring:** evaluates completed market bars with New York session awareness and sends Telegram alerts.
- **Historical backtesting:** evaluates strategy signals against historical price data using next-bar execution, modeled spread, slippage, commissions, and risk-based position sizing.
- **Multi-instrument research:** compares instruments using their own trading specifications, account-currency conversion, execution costs, and data provenance.
- **Walk-forward evaluation:** separates chronological training, validation, test, and optional holdout periods, with uncertainty intervals, multiple-testing controls, parameter-sensitivity analysis, and explicit acceptance criteria.
- **Cost stress testing:** evaluates selected configurations under higher spread, slippage, and commission assumptions.
- **Instrument calibration:** produces broker-specific sizing matrices from operator-attested contract specifications, currency conversion, quantity limits, and execution costs.
- **Reproducible research:** validates historical datasets and records configuration, data fingerprints, provenance, and experiment artifacts.
- **Engineering quality:** includes automated tests, linting, and documentation checks in GitHub Actions.

## System design

Trade Lab separates four concerns:

1. **Strategy logic** — shared calculations and signal generation for historical evaluation and market monitoring.
2. **Instrument specifications** — tick size, tick value, contract economics, and quantity constraints for each instrument.
3. **Execution simulation** — entry and exit assumptions, transaction costs, position sizing, and trade accounting.
4. **Research and monitoring workflows** — reproducible historical experiments alongside session-aware monitoring and alert delivery.

This separation keeps strategy rules independent of instrument economics and execution assumptions. It also makes research inputs and resulting trade outcomes inspectable rather than hiding them behind a single backtest score.

## Quick start

Trade Lab requires Python 3.10 or newer.

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/Emiloart/trade_lab.git
cd trade_lab
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\\Scripts\\Activate.ps1
```

Install the project and development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run market monitoring

Start the monitor in dry-run mode:

```bash
python -m trade_lab.live --dry-run
```

## Run multi-instrument research

Create a JSON research configuration containing the instrument specifications, historical CSV inputs, data provenance, account-currency conversion rates, and execution-cost assumptions for each instrument.

Run the research pipeline:

```bash
python -m trade_lab.research_cli --config research.json --output reports/walk-forward.csv
```

The command writes the walk-forward report and its reproducibility artifacts. Configuration and data requirements are documented in the research guides.

## Documentation

- [Architecture](docs/architecture.md) — system boundaries and component responsibilities.
- [Strategy](docs/strategy.md) — strategy rules, indicators, and signal behavior.
- [Backtesting](docs/backtesting.md) — historical execution model and cost assumptions.
- [Research methodology](docs/research.md) — experiment design, walk-forward evaluation, and interpretation.
- [Research CLI](docs/research_cli.md) — configuration format and command usage.
- [Instrument calibration](docs/instrument-calibration.md) — broker contract inputs and risk-sizing calibration.

## Development checks

Run the test suite, lint checks, and documentation verification:

```bash
python -m pytest -q
ruff check .
python scripts/verify_docs.py
```
