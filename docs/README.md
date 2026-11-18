# Documentation

This documentation describes the current implementation on `refactor/core-engine`. It distinguishes implemented behavior from legacy scripts, assumptions, and planned work.

## Start here

- [Architecture](architecture.md) — components, runtime flow, and system boundaries.
- [Strategy](strategy.md) — the VWAP pullback signal definition and parameters.
- [Risk management](risk-management.md) — sizing, daily limits, and operational limitations.
- [Configuration](configuration.md) — environment variables, defaults, and secrets.
- [Data sources](data-sources.md) — Yahoo Finance inputs and instrument mapping.
- [Operations](operations.md) — local runs, GitHub Actions, Telegram, and state handling.
- [Backtesting](backtesting.md) — current scripts, data requirements, and evidence limitations.
- [Development](development.md) — setup, tests, linting, and contribution workflow.
- [Roadmap](roadmap.md) — ordered engineering priorities.
- [Engineering decisions](decisions.md) — recorded implementation decisions and constraints.
- [Testing and verification](testing.md) — automated coverage, local checks, and validation requirements.
- [Troubleshooting and recovery](troubleshooting.md) — safe operational recovery procedures.

## Scope and safety

Trade Lab is currently a market-monitoring and Telegram-alerting application. It does not connect to a broker, submit orders, observe broker fills, or reconcile account positions. An alert is not an executed trade. Position size and price levels are estimates based on configured contract assumptions and market-data conversion.

Do not use the system with live capital based solely on these documents or the small historical sample previously reported in the README. Validate data quality, broker contract specifications, execution costs, and strategy performance independently.
