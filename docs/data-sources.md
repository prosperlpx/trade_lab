# Data sources and instrument mapping

## Provider

The live monitor retrieves intraday bars through `yfinance`, which accesses Yahoo Finance data. The current implementation requests 5-minute history for the symbols below.

| Role | Symbol | Use |
| --- | --- | --- |
| Signal source | `QQQ` | VWAP, ATR, and pullback signal |
| Reference conversion | `NQ=F` | Scale QQQ-derived entry, stop, and target to a Nasdaq futures reference |

## Normalization

The data adapter:

- requires Open, High, Low, Close, and Volume columns;
- flattens yfinance MultiIndex columns;
- rejects timezone-naive indexes rather than guessing their timezone;
- converts timestamps to UTC;
- removes duplicate timestamps and rows missing high, low, or close;
- fills missing volume with zero and converts OHLCV values to floating point.

The session and indicator modules convert timestamps to `America/New_York` when calendar-day grouping or session boundaries are needed.

## Closed bars and freshness

The monitor discards bars whose five-minute end time is later than the evaluation timestamp. It then requires the newest closed bar to be no more than 15 minutes old. This is a guard against acting on an in-progress candle and against many stale-feed conditions; it is not a formal market-hours or exchange-holiday service.

A signal must also be no more than 10 minutes past the end of its bar to be eligible for an alert.

## QQQ-to-NQ conversion

The conversion factor is calculated as:

`NQ close / QQQ close`

using the newest timestamp present in both normalized frames. The monitor applies that ratio to the QQQ signal's entry, stop, and target. If there is no shared timestamp or either close is non-positive, conversion fails and no alert is sent.

This is a simple price-ratio approximation. It is not a validated continuous mapping between ETF shares, futures contracts, and a broker's CFD. It does not account for basis, dividends, contract rolls, broker pricing, or differing market sessions. Treat converted levels as references only.

## Known limitations

- Yahoo Finance is not a broker execution feed and may be delayed, rate-limited, incomplete, or revised.
- No secondary provider or independent feed cross-check is implemented.
- No explicit exchange holiday calendar is implemented.
- The source and reference instruments must both have usable, overlapping bars.
- Contract value, lot size, and currency assumptions must be checked with the actual broker before relying on displayed size.
