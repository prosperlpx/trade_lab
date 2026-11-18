# Architecture

## System boundary

Trade Lab evaluates a VWAP pullback setup and can send Telegram alerts. It does not place orders or connect to a broker.

The maintained implementation is the `trade_lab/` package:

| Module | Responsibility |
| --- | --- |
| `config.py` | Instrument-independent strategy parameters, account risk, and legacy live configuration |
| `cache_guard.py` | Same-day cache validation and safe pre-session bootstrap |
| `data.py` | Yahoo Finance retrieval, live OHLCV normalization, and cross-instrument ratio | 
| `data_quality.py` | Non-repairing historical OHLCV validation and structured findings |
| `market_data.py` | Provider-neutral historical/live market-data contract |
| `instruments.py` | Asset classes and broker-supplied tick/quantity economics |
| `execution.py` | Broker adapter contract, order lifecycle types, and execution-mode guards |
| `filters.py` | Optional, instrument-independent signal research filters |
| `indicators.py` | Session VWAP, true range, and ATR |
| `sessions.py` | New York time handling, session window, closed-bar and freshness checks |
| `strategy.py` | Canonical VWAP pullback signal definition |
| `backtest.py` | Historical execution simulation using the canonical strategy functions |
| `research.py` | Reclaim-outcome measurement and chronological multi-instrument walk-forward evaluation |
| `research_cli.py` | Strict JSON-driven research runner and atomic CSV report writer |
| `sizing.py` | Risk-based unit/lot sizing and daily loss comparison |
| `state.py` | Validated JSON state, atomic replacement, recovery backup, and pending-delivery journal |
| `alert.py` | Human-readable Telegram alert formatting |
| `notify.py` | Telegram Bot API delivery |
| `live.py` | Live orchestration and command-line interface |

## Strategy parity

Live monitoring and historical simulation share `strategy.prepare()`, `strategy.first_signal()`, `StrategyParameters`, indicator functions, New York session handling, and unit-risk sizing. `AccountRiskConfig` is separate; `StrategyConfig` remains a legacy combined adapter for the live monitor. The historical execution layer separately defines next-bar-open entry, static spread/slippage, gap handling, and conservative OHLC collision assumptions; it does not reimplement signal rules. The two legacy VWAP entry points are thin wrappers around this layer.

## Live and backtest data flow

Live: `Yahoo Finance → normalized QQQ bars → shared indicators → shared signal → NQ/QQQ reference conversion → CFD lot estimate → Telegram`.

Backtest: `historical OHLCV bars → validated UTC bars → shared indicators → shared first signal → explicit per-instrument OHLC execution simulation → trade ledger`.

Live freshness and in-progress-candle checks are real-time safeguards. Historical data is assumed to contain completed bars; this is a data assumption, not a simulated real-time feed.

## Persistence and consistency

`StateStore` validates complete state and writes through a flushed temporary file followed by atomic replacement. It preserves a last-known-good `.bak` before every replacement. A missing primary with a backup, malformed state, or unsupported schema fails closed. Recovery is explicit, not automatic.

GitHub Actions validates same-day cache restoration or permits an empty bootstrap only before the 10:00 New York session. Scheduled alerts checkpoint pending intent before Telegram delivery. Actions cache is not a transactional database; loss of same-day cache stops the monitor and requires manual reconciliation.

## Broker and instrument abstraction

The domain layer is being separated from provider integrations:

- `instruments.py` defines asset classes and an `InstrumentSpec` containing tick size, tick value, tick-value currency, quantity unit, and venue-specific minimum/step/maximum quantity constraints.
- `sizing.py` exposes instrument-aware sizing and stop-risk calculations. Tick economics and an explicit conversion rate are required; the system does not infer CFD lot values from equity/share assumptions.
- `execution.py` defines broker-neutral account, quote, order, result, position, and asynchronous `BrokerAdapter` contracts.
- Execution modes are explicit. Broker submission is rejected in disabled/paper modes; demo mode requires a demo account; live mode requires a separate explicit enable flag and a live account.

A broker adapter is responsible for mapping canonical symbols to broker symbols, retrieving actual contract specifications, translating order semantics, and reconciling broker order/position state. Strategy code must not import broker SDKs. A provider without a supported order API remains usable through market-data and alert/manual workflows.

These are domain contracts, not completed broker integrations. No broker adapter currently places orders, and no claim of cross-broker compatibility is made until each adapter is implemented and tested against its broker's demo environment.

## Current boundaries

- No broker API, order placement, fill ingestion, or position reconciliation.
- Backtest fill assumptions remain static OHLC approximations and do not establish real executable prices.
- No exchange holiday calendar.
- QQQ/NQ conversion and CFD contract assumptions are not broker-validated.
