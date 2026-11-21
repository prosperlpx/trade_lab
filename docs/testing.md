# Testing and verification

## Automated coverage

The pytest suite covers data normalization, indicators, strategy boundaries, timezone/session behavior, sizing, state persistence, notification delivery, live orchestration, and the historical execution simulator. Backtest tests cover shared signal entry, stop/target collision ordering, stop gaps, open-position marking, realized-only metrics, and timestamp validation.

Tests use synthetic bars and fakes. They establish deterministic conformance to implemented rules; they do not validate Yahoo Finance data quality, Telegram availability, broker pricing, fills, or profitability.

## Local verification

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check trade_lab backtests/_common.py backtests/vwap_backtest.py backtests/recent_backtest.py tests
python scripts/verify_docs.py
```

CI runs the same Ruff, pytest, and documentation checks. The maintained backtest entry points and their shared helper are included in lint. Unrelated historical utilities remain separate research tools.

## Strategy and parity checks

- Live and backtest signal selection must call `trade_lab.strategy.prepare()` and `first_signal()`.
- Any change to strategy inequalities, indicator calculation, session boundaries, or defaults must be tested once in the shared package, not duplicated in backtest scripts.
- Backtest execution tests must cover same-candle stop/target collisions, gaps through stops, entry-bar exclusion, and unresolved positions.
- Historical comparisons must use identical input bars, configuration, strategy revision, and execution assumptions.
- Keep signal counts, simulated closed trades, open marks, and any future broker-confirmed fills as separate measurements.

A green test suite proves implementation conformance, not positive expectancy or profitability.
