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
- Entry reference is the signal bar close.
- Risk distance is ATR × `ATR_STOP_MULT`.
- Long stop/target = entry − risk / entry + risk × reward/risk.
- Short stop/target = entry + risk / entry − risk × reward/risk.

Defaults are ATR period 14, stop multiplier 1.5, reward/risk 1.3, and VWAP tolerance 0.001. Configuration is shared through `StrategyConfig`; no backtest-specific signal constants are maintained.

## Signal selection

The shared `first_signal` scans in-window bars chronologically and returns the first qualifying signal for a New York calendar date. At most one signal is selected per date. Live monitoring and migrated backtests call this same function.

A signal is a rule match, not proof of an executable trade. The live monitor filters incomplete and stale bars; historical evaluation uses the supplied completed historical bars and does not recreate real-time data latency.
