# Strategy research and validation

## Configuration and instrument boundary

New research code separates `StrategyParameters` from `AccountRiskConfig`.
The live monitor retains the combined `StrategyConfig` as a backwards-compatible
adapter, including legacy CFD lot-sizing fields. Backtests accept the separated
objects directly. Research runs must supply an explicit
`InstrumentSpec` and `BacktestCosts` for every symbol. Never infer tick
economics from a ticker or reuse one instrument's costs for another.

## Optional filters

`StrategyFilters` exposes opt-in, instrument-independent criteria. All are
disabled by default. Pullback depth is measured in ATR units; directional VWAP
slope is normalized by ATR; ATR percentage is ATR divided by absolute close.
They are candidate filters, not established improvements.

## Reclaim quality study

Use `measure_reclaim_outcomes()` on prepared bars to measure every qualifying
reclaim candidate's pullback penetration in ATR, directional VWAP slope, ATR
percentage, close distance from VWAP in ATR, reclaim candle range in ATR,
subsequent follow-through, maximum favorable excursion (MFE), and maximum
adverse excursion (MAE) at fixed bar horizons. Outcomes are
normalized by the initial stop distance in R and horizons are restricted to
the same New York session date. This makes reclaim quality measurable without
confusing candidate outcomes with the strategy's one-trade-per-day execution
rule. Choose horizons before examining results; do not tune on final holdout data.

## Walk-forward research

Use `trade_lab.research.run_walk_forward_research` with symbol-keyed OHLCV
datasets, instrument specifications, execution costs, and an explicit data_sources
label for every symbol. The CLI additionally preserves the exact source CSV bytes
and writes a content-addressed snapshot plus a run manifest. The research engine
continues to record a SHA-256 fingerprint of each normalized in-memory dataset
alongside its source label and data bounds; the manifest separately records the
original-file SHA-256. The runner uses the
intersection of observed New York sessions so every symbol is evaluated over
the same train/validation/test date boundaries. Each symbol/variant backtest
is computed once and reused across the windows. Supply an explicit
list of `ResearchVariant` configurations. The runner creates chronological
expanding-history windows, reports candidate training and validation metrics,
selects by validation expectancy in R, then evaluates the selected variant on
the subsequent test interval. Test data does not participate in selection.

```python
from trade_lab.backtest import BacktestCosts
from trade_lab.config import StrategyConfig
from trade_lab.filters import StrategyFilters
from trade_lab.research import ResearchVariant, run_walk_forward_research

variants = [
    ResearchVariant("baseline", StrategyConfig()),
    ResearchVariant("shallow-pullback", StrategyConfig(
        filters=StrategyFilters(max_pullback_atr=0.5)
    )),
]
report = run_walk_forward_research(
    datasets={"SYMBOL_A": bars_a, "SYMBOL_B": bars_b},
    instruments={"SYMBOL_A": spec_a, "SYMBOL_B": spec_b},
    costs={
        "SYMBOL_A": BacktestCosts(spread_points=spread_a, slippage_points=slippage_a,
                                  commission_per_unit=commission_a),
        "SYMBOL_B": BacktestCosts(spread_points=spread_b, slippage_points=slippage_b,
                                  commission_per_unit=commission_b),
    },
    variants=variants, train_days=120, validation_days=60,
    test_days=60, step_days=60, final_holdout_days=60,
    data_sources={"SYMBOL_A": "vendor A, 5m, adjusted: no",
                  "SYMBOL_B": "vendor B, 5m, adjusted: no"},
)
report.to_csv("walk_forward_report.csv", index=False)
```

The report records data source labels, dataset fingerprints, data bounds and bar count,
a strategy configuration hash, contract economics, cost assumptions, and
account-risk assumptions.

When `final_holdout_days` is positive, the last N shared sessions are excluded
from rolling development windows. The runner chooses one final variant using
aggregate validation expectancy and emits a separate `final_holdout` row.
That holdout is not used to tune or select the configuration.

Data-source labels should identify the vendor or collection method, symbol,
interval, and any relevant adjustment policy.

The caller must document each symbol's actual instrument specification,
account-currency conversion rate, spread, slippage, commission, and data
provenance. No placeholder economics should be presented as observed costs.

## Limitations and interpretation

- The live monitor still assumes QQQ signal bars and NQ reference-price
  conversion. It is not a generic multi-instrument live monitor.
- `StrategyConfig` retains legacy account-risk and CFD lot fields only as a
  backwards-compatible adapter for the live monitor. New research code uses
  `StrategyParameters` and `AccountRiskConfig` separately.
- No verified multi-instrument historical datasets or broker cost schedules
  are bundled. This repository therefore cannot yet support a factual
  cross-instrument performance conclusion.
- Reclaim-quality metrics are implemented, but empirical conclusions still
  require real historical data and horizons chosen before inspecting results.
- Rolling test windows are out-of-sample relative to their own validation
  selection, but are not one untouched final holdout. Reserve a later,
  untouched date range for final confirmation.


## Historical data integrity

The research CLI validates source CSVs before passing bars to the strategy. It
does not use the live normalizer's repair behavior. Duplicate or unordered
timestamps, missing columns, missing/non-finite values, non-positive prices,
invalid OHLC envelopes, and negative volume are hard errors. Optional
`interval_minutes` detects unusually large gaps within the same New York
calendar date and records warnings. These checks deliberately do not classify
overnight, weekend, holiday, or early-close gaps because no exchange calendar
is currently integrated.

Every successful CLI run preserves the original CSV bytes in its artifact
directory and writes `research-config.json` and `manifest.json`. The manifest
records source hashes, snapshot paths, source labels, optional provider and
retrieval metadata, interval and adjustment assumptions, symbol mapping,
validation findings, strategy/risk settings, walk-forward protocol, and the
code revision when supplied by the runtime. `retrieved_at` is optional and
must be provided by the operator when known; the tool does not fabricate it.
Keep the artifact directory with the report to reproduce the input dataset
and configuration used for a run.


## Execution realism and interpretation

The backtester enters at the next available in-session bar open after a signal
bar closes. Stop and target levels remain anchored to the signal close; if the
next open has already crossed either level, the setup is recorded as
`NOT_EXECUTED` rather than chased. The ledger preserves both signal and
execution timestamps and prices.

Spread is charged half on each side, slippage adversely on each fill, and
commission per unit per side. Sizing includes the distance from the actual
entry reference open to the signal-anchored stop plus modeled round-trip costs.
Stop gaps fill at the worse bar open. Target gaps after entry fill at the open
or better. If both stop and target are touched within one OHLC candle, stop wins
because intrabar ordering is unknowable from OHLC data.

Walk-forward selection continues to use `expectancy_r`, now the net executable
R multiple after modeled costs. `signal_expectancy_r` separately reports the
hypothetical signal-close reference outcome over the same exit path. Signals
rejected because the next open has crossed the bracket are counted as
`not_executed` and excluded from trade expectancy.

This remains a static OHLC simulation, not a fill guarantee. It does not model
variable quote spreads, latency, market impact, partial fills, queue priority,
financing, or broker-specific execution rules. Validate assumptions against
venue-specific tick or quote data before drawing conclusions.

## Statistical robustness protocol

Walk-forward research applies explicit sample-size gates and uncertainty estimates
to candidate validation, selected test windows, and the optional final holdout.
The CLI defaults to 30 closed trades in validation and 30 in test/holdout. These
are protocol defaults, not universal guarantees of statistical power; choose
larger minimums when the strategy's expected effect size or dependence structure
requires them. The current strategy allows at most one executed trade per New
York session, so validation/test windows must contain at least as many sessions
as their configured minimum trade counts. A result below either minimum is
reported as rejected rather than silently treated as evidence.

Expectancy and win-rate intervals use a moving-block bootstrap over the ordered
sequence of trade-bearing New York dates. The default block length is five
observed trade dates and the default is 2,000 resamples. Resampling contiguous
date blocks preserves some short-range serial dependence that an IID trade
bootstrap would destroy; dates without a closed trade are not inserted as
zero-return observations. A single observed trade date does not produce an
interval. The interval is an empirical
uncertainty estimate conditional on the supplied history and block length; it
is not a probability that future returns will fall inside the interval.

Variant selection uses the lower bound of a Bonferroni-adjusted expectancy
interval. The family size is the number of variants compared for that symbol
and window. This controls family-wise error conservatively under the specified
comparison family; it does not correct for unrecorded experiments, repeated
researcher decisions, or dependence across symbols and overlapping windows.
Keep a complete candidate universe and do not add variants after seeing the
holdout.

Set `sensitivity_group` on each variant to identify a local parameter
neighborhood that should be compared together. The report records the group's
variant count, minimum, median, and maximum validation expectancy, and the
share of variants with positive expectancy. These are sensitivity diagnostics,
not an optimizer and not proof that every parameter combination in a continuous
space has been tested. Define groups before reviewing their results.

Execution-cost stress tests rerun the selected configuration with every
configured cost component scaled together. The default scenarios are 1.0x,
1.5x, and 2.0x the supplied spread, slippage, and commission. The maximum
configured multiplier is an acceptance gate: the selected test and final
holdout must still meet the minimum trade count and have a positive adjusted
expectancy lower bound at that stress level. This is a deterministic scenario
analysis, not a forecast of future transaction costs.

A selected test or final holdout row is marked `ACCEPT` only when all of the
following are true:

1. The selected variant met the minimum validation trade count.
2. The Bonferroni-adjusted validation expectancy lower bound is positive.
3. The test or holdout period met the minimum closed-trade count and its
   unadjusted block-bootstrap expectancy lower bound is positive.
4. The maximum configured transaction-cost stress scenario met the minimum
   trade count and retained a positive unadjusted expectancy lower bound.

Otherwise the row is marked `REJECT` with machine-readable reason codes.
Acceptance means only that the configured historical protocol did not reject
the candidate. It is not evidence of profitability, future stability, or
readiness for live deployment. Preserve the final holdout as a one-time
confirmation set; do not tune parameters, filters, costs, bootstrap settings,
or acceptance thresholds against it.
