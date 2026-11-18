# Strategy specification

## Instrument and timeframe

The live monitor and migrated VWAP backtests use Yahoo Finance 5-minute QQQ bars as the signal instrument. Live alerts may scale reference levels using NQ futures (`NQ=F`), but this conversion is not part of the historical signal rule and does not make QQQ, NQ, and a broker's US100/NAS100 CFD interchangeable.

## Session

The configured signal window defaults to 10:00 inclusive to 15:00 exclusive in `America/New_York`. Timestamps are normalized to UTC; date grouping and window checks convert them to New York time. This handles daylight-saving changes without fixed-offset assumptions.

## Indicators

Session VWAP resets by New York calendar date and accumulates from the first bar available for that date:

`Typical Price = (High + Low + Close) / 3`

`VWAP = cumulative(Typical Price × Volume) / cumulative(Volume)`

True range uses high-low and same-New-York-date previous close; the first bar of each date uses high-low only. ATR is a simple rolling mean of true range. The rolling ATR window is not reset at midnight and can include prior-date observations.

## Entry, stop, and target

The canonical implementation is `trade_lab.strategy`, used by both live monitoring and `trade_lab.backtest`.

- Long: close is above VWAP and low is at or below VWAP × (1 + tolerance).
- Short: close is below VWAP and high is at or above VWAP × (1 − tolerance).
- The signal reference is the completed signal bar close.\n- The backtest enters at the next available in-window bar open, not at the signal close. The original stop and target remain anchored to the signal close.
- Risk distance is ATR × `ATR_STOP_MULT`.
- Long stop/target = entry − risk / entry + risk × reward/risk.
- Short stop/target = entry + risk / entry − risk × reward/risk.

Defaults are ATR period 14, stop multiplier 1.5, reward/risk 1.3, and VWAP tolerance 0.001. Signal configuration is defined by `StrategyParameters`; account limits live in `AccountRiskConfig`. The live monitor retains `StrategyConfig` as a backwards-compatible combined adapter. No backtest-specific signal constants are maintained.

## Signal selection

The shared `first_signal` scans in-window bars chronologically and returns the first qualifying signal for a New York calendar date. At most one signal is selected per date. Live monitoring and migrated backtests call this same function.

A signal is a rule match, not proof of an executable trade. The live monitor filters incomplete and stale bars; historical evaluation uses the supplied completed historical bars and does not recreate real-time data latency.


## Optional research filters

StrategyFilters exposes opt-in, instrument-independent criteria. All are disabled by default, preserving the baseline rule. max_pullback_atr limits VWAP penetration measured in ATR units. min_directional_vwap_slope_atr requires the VWAP change over vwap_slope_lookback bars, normalized by ATR, to align with trade direction. min_atr_pct and max_atr_pct constrain ATR divided by absolute close, expressed as a percentage. A filter requiring a missing feature rejects the candidate rather than silently passing it. These filters are experimental, not assumed improvements. Evaluate them independently and in combinations with chronological train/validation/test partitions and walk-forward windows; do not select thresholds on the final holdout. Report trade count, expectancy in R, drawdown, profit factor, and sensitivity to execution costs. Cross-instrument comparisons require verified instrument economics and realistic costs.


## Execution simulation assumptions

The signal candle must close before its signal is known. Historical execution therefore
uses the next available in-window bar open as the earliest executable event in the
current OHLC dataset. If that open has already crossed the original stop or target,
the setup is marked `NOT_EXECUTED`; the simulator does not chase the move. Entry
and exit timestamps refer to the execution bar, while `Signal_Time` and
`Signal_Entry` preserve the signal event and its close reference.

Static spread is modeled as half the quoted spread against the trader on each
side. Slippage is adverse on each fill and commission is charged per unit per
side. Position sizing includes the entry-to-stop distance from the actual
next-bar reference open plus modeled round-trip costs. This keeps sizing aligned
with the simulated entry rather than the signal-close reference.

Stops that gap through their level fill at the bar open, not at the stop price.
A target crossed by a later bar's open fills at that open (price improvement).
When a bar's high/low touches both stop and target and OHLC cannot establish
which traded first, the stop is assumed first. This is intentionally conservative.

The input OHLC series is treated as a reference-price series for this approximation;\nif a provider supplies last-trade or one-sided bid/ask bars, the half-spread\nmodel is not an exact reconstruction of executable quotes.\n\nThese are static bar-based assumptions. They do not model quote-level bid/ask
paths, variable spread, queue position, partial fills, latency, market impact,
financing, or broker-specific order handling. Signal quality is reported
separately as `signal_expectancy_r`; `expectancy_r` is net executable-trade
expectancy and is the metric used for walk-forward selection.
