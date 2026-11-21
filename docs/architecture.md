# Architecture

## System boundary

Trade Lab evaluates a VWAP pullback setup and can send Telegram alerts. It does not place orders or connect to a broker.

The maintained implementation is the `trade_lab/` package:

| Module | Responsibility |
| --- | --- |
| `config.py` | Immutable strategy/risk configuration and environment overrides |
| `cache_guard.py` | Same-day cache validation and safe pre-session bootstrap |
| `data.py` | Yahoo Finance retrieval, OHLCV normalization, and cross-instrument ratio |
| `indicators.py` | Session VWAP, true range, and ATR |
| `sessions.py` | New York time handling, session window, closed-bar and freshness checks |
| `strategy.py` | Canonical VWAP pullback signal definition |
| `backtest.py` | Historical execution simulation using the canonical strategy functions |
| `sizing.py` | Risk-based unit/lot sizing and daily loss comparison |
| `state.py` | Validated JSON state, atomic replacement, recovery backup, and pending-delivery journal |
| `alert.py` | Human-readable Telegram alert formatting |
| `notify.py` | Telegram Bot API delivery |
| `live.py` | Live orchestration and command-line interface |

## Strategy parity

Live monitoring and historical simulation share `strategy.prepare()`, `strategy.first_signal()`, `StrategyConfig`, indicator functions, New York session handling, and unit-risk sizing. The historical execution layer separately defines candle fill assumptions; it does not reimplement signal rules. The two legacy VWAP entry points are thin wrappers around this layer.

## Live and backtest data flow

Live: `Yahoo Finance → normalized QQQ bars → shared indicators → shared signal → NQ/QQQ reference conversion → CFD lot estimate → Telegram`.

Backtest: `historical QQQ bars → normalized UTC bars → shared indicators → shared first signal → explicit OHLC execution simulation → trade ledger`.

Live freshness and in-progress-candle checks are real-time safeguards. Historical data is assumed to contain completed bars; this is a data assumption, not a simulated real-time feed.

## Persistence and consistency

`StateStore` validates complete state and writes through a flushed temporary file followed by atomic replacement. It preserves a last-known-good `.bak` before every replacement. A missing primary with a backup, malformed state, or unsupported schema fails closed. Recovery is explicit, not automatic.

GitHub Actions validates same-day cache restoration or permits an empty bootstrap only before the 10:00 New York session. Scheduled alerts checkpoint pending intent before Telegram delivery. Actions cache is not a transactional database; loss of same-day cache stops the monitor and requires manual reconciliation.

## Current boundaries

- No broker API, order placement, fill ingestion, or position reconciliation.
- Backtest fill assumptions do not establish real executable prices.
- No exchange holiday calendar.
- QQQ/NQ conversion and CFD contract assumptions are not broker-validated.
