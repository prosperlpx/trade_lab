# Backtesting

## Shared strategy boundary

The maintained live monitor and backtests use the same `trade_lab.strategy.prepare()` and `first_signal()` functions. Signal conditions, VWAP, ATR, New York session selection, stop distance, target distance, and first-setup selection have one source of truth.

## Run

Generate the local QQQ 5-minute CSV first:

```bash
python strategies/data_downloader.py
python backtests/vwap_backtest.py
python backtests/recent_backtest.py
```

Input is `data/us100_5m.csv` in the downloader's `Datetime` plus OHLCV format. Timestamps are parsed as UTC. Indicators are calculated on the complete input before recent-period filtering, preserving ATR warm-up observations. Session logic uses `America/New_York`.

## Execution simulation

`run_backtest()` accepts a `BacktestCosts` value:

- `spread_points`: full bid/ask spread in instrument price points.
- `slippage_points`: adverse slippage applied independently to entry and exit fills.
- `commission_per_unit`: account-currency commission per unit, per side.

Position size is reduced so modeled stop risk, including round-trip spread, slippage, and commission, does not exceed the configured risk budget. The ledger reports signal price, modeled fills, gross P&L, execution costs, net P&L, risk budget, and R multiple. The summary reports average/expectancy R and aggregate execution costs.

Defaults are zero-cost for backwards compatibility. A zero-cost run is not a realistic performance estimate. Supply costs measured from the actual Exness demo instrument specification and observed fills before interpreting results. QQQ input data is still not the broker's US100 price series, so this cost model does not establish broker fill parity.

When an `InstrumentSpec` is supplied to `run_backtest()`, sizing and P&L use that instrument's tick size, tick value, quantity unit, minimum/step/maximum quantity, and an explicit `value_to_account_rate`. This supports share- and lot-denominated instruments without treating one lot as one share. The conversion rate must convert the tick-value currency into the account currency; it is not fetched or guessed automatically. Without an instrument specification, the legacy price-unit calculation remains for compatibility.

For instrument-aware runs, spread and slippage are specified in price points, while `commission_per_unit` is account-currency commission per quantity unit per side. The legacy no-instrument path retains its historical price-unit commission convention; do not mix that legacy convention with broker commission figures.

OHLC stop/target triggers remain conservative: stop wins same-candle collisions, stop gaps fill at the worse open, and a target crossed by a later bar's open fills at that open (price improvement). Entry is modeled at the next available in-session bar open after the signal candle closes; the original stop and target remain anchored to the signal close. Setups that gap through the bracket before entry are rejected rather than chased. This is a bar-based research convention, not a guarantee that a live order can fill there. Open trades are marked separately and excluded from realized metrics.

## Interpretation

Compare the same dataset and strategy revision across cost scenarios. Record the data source, symbol, download timestamp, interval, configuration, cost assumptions, and in/out-of-sample split. Do not tune parameters on the final holdout set. Backtest results are not evidence of future profitability.
