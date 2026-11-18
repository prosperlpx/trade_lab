# Development

## Setup

Use Python 3.10 or newer:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Tests and lint

Run the test suite:

```bash
python -m pytest
```

Run Ruff:

```bash
ruff check trade_lab tests
python scripts/verify_docs.py
```

The GitHub Actions workflow `.github/workflows/ci.yml` installs the project with development dependencies and runs pytest, Ruff against the maintained package and tests, and `scripts/verify_docs.py`. A local pass does not replace reviewing the workflow result for the exact commit under test.

## Code organization

Keep strategy rules in `trade_lab/strategy.py` and indicator definitions in `trade_lab/indicators.py`. Live orchestration belongs in `trade_lab/live.py`; provider-specific behavior belongs behind `trade_lab/data.py`. Keep external effects (Telegram, persistence, network data) isolated so they can be tested with fakes.

## Engineering rules

- Use timezone-aware timestamps. Convert to UTC at the data boundary and use `America/New_York` for session logic.
- Never evaluate an in-progress candle.
- Preserve the one-setup-per-New-York-day rule unless a strategy revision explicitly changes it and updates tests and docs.
- Keep risk sizing conservative: round down to valid lot increments and reject sizes below the minimum.
- Do not silently equate a signal, an alert, a simulated trade, and a broker fill.
- Add tests for both expected behavior and failure paths whenever changing strategy, data, state, sizing, or notification behavior. Update the relevant documentation in the same change; CI checks documented commands, variables, modules, CLI options, and workflow references against the repository.
- Do not add real credentials, state files, or downloaded market data to commits.

## Change workflow

Work on a feature branch. Make a focused change, run tests and lint, inspect the diff, then commit and push. For strategy changes, record the parameter/version change and explain whether historical results are comparable to earlier runs. Avoid combining strategy changes with unrelated web UI or infrastructure work.
