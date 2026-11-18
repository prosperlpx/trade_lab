# Backtesting

## Shared strategy boundary

The two principal VWAP simulation entry points now call the same maintained implementation as live monitoring:

- `backtests/vwap_backtest.py` runs the full available history.
- `backtests/recent_backtest.py` runs from its configured New York calendar start date.
- Both call `trade_lab.backtest.run_backtest()`, which calls `trade_lab.strategy.prepare()` and `trade_lab.strategy.first_signal()`.
- The live monitor uses the same preparation and first-signal functions. Entry conditions, VWAP, ATR, New York session selection, stop distance, target distance, and first-setup selection therefore have one source of truth.

The scripts no longer contain independent VWAP, ATR, entry, or stop/target calculations. `monthly_seasonality.py` remains a separate descriptive NQ daily-volatility analysis; `verify_recent_trade.py` is a manual single-trade outcome checker, not a strategy backtest; `analyze_live_trades.py` summarizes legacy manual alert logs. Those utilities do not define the strategy.

## Run

Generate the local QQQ 5-minute CSV first:

```bash
python strategies/data_downloader.py
python backtests/vwap_backtest.py
python backtests/recent_backtest.py
```

Input is `data/us100_5m.csv` in the existing downloader's `Datetime` plus OHLCV format. Timestamps are parsed as UTC and normalized through `trade_lab.data.normalize_bars()`. Indicators are calculated on the complete available input before the recent-period filter is applied, preserving ATR warm-up observations. The signal window and date grouping use `America/New_York`, not machine-local time or a fixed Lagos offset.

Both runners use `StrategyConfig.from_env()`, exactly as live monitoring does. Account size, risk percentage, daily loss percentage, ATR period and multiplier, reward/risk, VWAP tolerance, and sizing assumptions therefore come from the shared defaults or the same supported environment variables. The prior standalone scripts' differing $5,000/0.5%/1.5R and $10,000/1%/1.3R constants are not preserved as separate strategy variants.

## Execution simulation contract

Signal parity does not make historical fills equivalent to live broker fills. The execution layer has explicit candle-level assumptions:

- Entry is at the signal bar close; exit checks begin on the next 5-minute bar.
- Only subsequent bars inside the configured New York signal window are considered for exits.
- If stop and target are both touched in one candle, the stop is assumed first (conservative ordering).
- A stop gapped through fills at the worse bar open; a target is filled at its target price without favorable gap improvement.
- Positions with neither level touched by the end of the window are reported as `OPEN`, with a separate mark-to-market value. They are excluded from realized P&L, win rate, profit factor, and realized drawdown.
- Sizing uses shared `units_for_risk()` and the configured risk budget. It represents abstract units; it is not broker-validated CFD lot sizing.
- Spread, commission, financing, market impact, and ordinary slippage are not modeled. The gap-stop rule is the only explicit adverse execution adjustment.

These assumptions are simulation conventions, not facts about executable fills. Changing them requires tests and a corresponding documentation update.

## Output and interpretation

The scripts write a trade ledger CSV under `data/`. It distinguishes `CLOSED` from `OPEN`, realized P&L from unrealized P&L, and includes entry, stop, target, exit, units, and exit reason. Summary metrics use closed trades only.

A backtest is not evidence of profitability. Before making performance claims, record data provider, symbol, download timestamp, interval, coverage, configuration, strategy revision, execution assumptions, and out-of-sample methodology. QQQ/NQ data and the configured CFD assumptions are not interchangeable with broker execution prices. Do not compare historical results produced by the old standalone calculations with the migrated results as if they were the same experiment.
