# Risk management

## Configured risk model

Defaults in `StrategyConfig`:

| Parameter | Default | Meaning |
| --- | ---: | --- |
| Account size | $10,000 | Nominal account value used for sizing |
| Risk per trade | 1% | $100 nominal risk budget |
| Maximum daily loss | 2% | $200 nominal daily threshold |
| ATR period | 14 | Rolling true-range period |
| ATR stop multiplier | 1.5 | Stop distance as a multiple of ATR |
| Reward/risk | 1.3 | Target distance relative to stop distance |
| Point value per lot | 10 | Assumed currency value per index point per lot |
| Minimum lot | 0.01 | Smallest supported lot |
| Lot step | 0.01 | Lot increment |
| Maximum lot | 100 | Upper sizing cap |

The account size and point-value assumptions are configuration inputs, not values verified against a broker account or contract specification.

## Lot calculation

For a converted stop distance in index points:

`raw lots = risk budget / (risk points × point value per lot)`

The result is rounded down to the configured lot step. If the risk budget cannot fund the minimum lot, the monitor records the setup as missed and does not send an alert. The cap is then applied.

Rounding down is intentional: rounding up could exceed the nominal risk budget.

## Daily loss gate: current limitation

The monitor compares manually recorded realized P&L with the configured daily loss threshold. P&L is entered through the CLI:

`python -m trade_lab.live --record-pnl -100`

This records a negative amount for a loss or a positive amount for a gain against the New York date derived from the current clock (or `--now`, if supplied).

There is no broker fill or account-balance integration. The system cannot know actual realized P&L unless an operator records it correctly. Therefore the daily loss gate is not an autonomous broker-enforced kill switch and must not be represented as one.

## Operational risks and controls

- **Reference-price risk:** QQQ/NQ scaling is an approximation; broker CFD quotes and contract specifications can differ.
- **Execution risk:** spread, commission, slippage, gaps, rejected orders, and partial fills are not modeled by the alert service.
- **Data risk:** Yahoo Finance availability, timestamps, volume, and intraday history may be delayed, incomplete, or revised.
- **Delivery ambiguity:** a timeout, connection interruption, malformed response, or server error may occur after Telegram has accepted a message. The system records `delivery_unknown` and does not retry automatically.
- **State/cache risk:** the scheduled workflow checkpoints pending intent before Telegram delivery and quarantines an interrupted attempt, but Actions cache is not a durable transactional database. A cache miss during the session fails closed and requires manual reconciliation.
- **Strategy risk:** the historical evidence currently available is too limited to establish robustness or profitability.

Validate sizing against the exact broker symbol specification and use a non-live environment until independent testing and operational controls are complete.
