# Roadmap

This roadmap reflects the current repository state. Planned items are not implemented features.

## M0 — Shared engine and reliability

- Shared Python package for configuration, indicators, strategy, data, sizing, sessions, state, and Telegram.
- New York timezone-aware session handling and completed-bar filtering.
- Validated atomic JSON state, recovery backup, same-day cache guard, and checkpointed Telegram delivery.
- CI for tests, Ruff, and repository-backed documentation verification.

## M1 — Live/backtest signal parity

- Completed for the two primary VWAP backtest entry points: both use the shared preparation and first-signal functions.
- Keep execution simulation assumptions explicit and independently tested.
- Validate parity against identical historical input and configuration before drawing strategy-performance conclusions.

## M2 — Reproducible historical evaluation

- Capture immutable input data snapshots, provider metadata, download timestamps, configuration, and strategy revision per run.
- Add spread, commission, financing, and empirically justified slippage models.
- Establish out-of-sample and walk-forward evaluation with adequate sample sizes.
- Validate instrument mapping and sizing assumptions against the intended broker.

## M3 — Durable event and trade journal

- Replace Actions cache as authoritative state with durable database persistence.
- Store immutable signal, alert, manual execution, broker execution (if ever integrated), and P&L events separately.
- Add idempotency keys, event timestamps, strategy/configuration versions, and audit history.

## M4 — Research and monitoring interface

- Build a read-only monitoring and research interface first.
- Keep the Python engine independently runnable and authoritative for strategy evaluation.

## Non-goals

- No automatic order execution.
- No claims of guaranteed returns or validated profitability.
- No public multi-tenant product until security, tenancy, compliance, and operational requirements are reviewed.
