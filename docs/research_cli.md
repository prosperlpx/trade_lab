# Running multi-instrument research

Run the walk-forward engine without writing a Python harness:

~~~bash
python -m trade_lab.research_cli --config research.json --output reports/walk-forward.csv
~~~

The JSON document contains positive train, validation, and test session counts;
optional step and final-holdout counts; a complete account-risk object; named
strategy variants; and a symbol-keyed instrument universe.

Every symbol requires:

- csv: OHLCV CSV path. Relative paths resolve from the JSON file's directory.
- data_source: vendor or collection method, symbol, interval, and adjustment policy.
- optional provider, retrieved_at, interval, interval_minutes, adjustment, and symbol_mapping fields for explicit source metadata. retrieved_at must be timezone-aware ISO-8601. interval_minutes enables same-session gap warnings; it does not apply an exchange calendar.
- value_to_account_rate: explicit conversion from tick-value currency to account currency.
- instrument: actual venue tick and quantity economics.
- costs: explicit spread, slippage, and per-unit-per-side commission assumptions.

All instrument fields and all three cost fields are mandatory. Zero costs and a
conversion rate of 1.0 are accepted only when explicitly entered. The CLI does
not infer contract values from tickers or apply hidden zero-cost assumptions.
Unknown and duplicate JSON keys are rejected. CSV input uses the repository's
Datetime, Open, High, Low, Close, Volume format; timestamps are parsed as UTC.

Strategy parameters omitted from a variant use StrategyParameters defaults.
Optional filters are nested under that variant's strategy.filters object.
The report separates candidate training/validation rows, selected subsequent
test rows, and an optional final holdout row. Validation expectancy selects a
variant; test data does not participate in that window's selection.

The report is written to a temporary file in the destination directory,
flushed, then atomically replaces the destination. The command does not
download market data, verify broker specifications, or connect to a broker.

See docs/research.md for the research methodology and report interpretation.
Example numbers in any schema illustration are placeholders, not verified
market assumptions or recommendations.

## Configuration example

This is a complete structural example for one ETF. The values are deliberately
illustrative. Replace the CSV path, source description, conversion rate, venue
specification, and every cost assumption with values verified for the instrument
and data source being tested.

~~~json
{
  "train_days": 120,
  "validation_days": 60,
  "test_days": 60,
  "step_days": 60,
  "final_holdout_days": 60,
  "minimum_validation_trades": 30,
  "minimum_test_trades": 30,
  "confidence_level": 0.95,
  "bootstrap_samples": 2000,
  "bootstrap_block_length": 5,
  "cost_stress_multipliers": [1.0, 1.5, 2.0],
  "risk": {
    "account_size": 10000,
    "risk_pct": 0.01,
    "max_daily_loss_pct": 0.02
  },
  "variants": [
    {
      "name": "baseline",
      "sensitivity_group": "pullback-depth-neighborhood",
      "strategy": {
        "atr_period": 14,
        "atr_stop_mult": 1.5,
        "reward_risk": 1.3
      }
    },
    {
      "name": "shallow-pullback",
      "sensitivity_group": "pullback-depth-neighborhood",
      "strategy": {
        "atr_period": 14,
        "filters": {
          "max_pullback_atr": 0.5
        }
      }
    }
  ],
  "symbols": {
    "SYMBOL_A": {
      "csv": "data/symbol_a_5m.csv",
      "data_source": "vendor A, SYMBOL_A, 5m, adjusted: no",
      "value_to_account_rate": 1.0,
      "instrument": {
        "asset_class": "etf",
        "quote_currency": "USD",
        "tick_size": 0.01,
        "tick_value": 0.01,
        "tick_value_currency": "USD",
        "quantity_unit": "share",
        "min_quantity": 1,
        "quantity_step": 1,
        "max_quantity": 100000
      },
      "costs": {
        "spread_points": 0.02,
        "slippage_points": 0.01,
        "commission_per_unit": 0.0
      }
    }
  }
}
~~~

The same structure accepts multiple symbols under symbols. Give each one its
own instrument object, costs, conversion rate, data source, and CSV file.
Do not copy one venue's contract economics or execution costs to another
symbol merely because their price scales look similar.


## Reproducibility artifacts

Each successful run writes a sibling artifact directory by default. For
`reports/walk-forward.csv`, the default is
`reports/walk-forward.artifacts/`. Override it with `--artifacts`.

The directory contains:

- `research-config.json`: exact configuration bytes used for the run.
- `datasets/<symbol-key>-<sha256>.csv`: exact source CSV bytes, stored under a
  content-addressed filename. The symbol key is a short hash so arbitrary symbol
  strings cannot become filesystem path components.
- `manifest.json`: manifest version, config SHA-256, source-file SHA-256,
  snapshot path, source label, optional provider/retrieval/interval/adjustment/
  symbol-mapping metadata, explicit UTC timestamp assumption, row count,
  data bounds, validation findings, strategy variants, risk assumptions,
  walk-forward protocol, and code revision when supplied by the runtime.

The manifest's creation timestamp is generated in UTC. A retrieval timestamp
is never inferred: supply retrieved_at only when it is known. A missing code
revision is recorded as null rather than guessed. The source CSV remains
unchanged. The SHA-256 identifies the preserved bytes; it is not proof that a
vendor's historical feed was correct or immutable before collection.

Validation warnings do not automatically reject a dataset. Review them against
the actual instrument's trading calendar before interpreting results. The
artifact directory is part of the research result and should be retained with
the CSV report.

## Statistical robustness settings

The following top-level fields are optional. Defaults are shown:

- `minimum_validation_trades`: 30 closed trades required in the validation
  sample before the selected candidate can pass.
- `minimum_test_trades`: 30 closed trades required in test and final holdout.
  The current strategy can execute at most one trade per New York session, so
  the corresponding windows must be at least 30 sessions long.
- `confidence_level`: 0.95 percentile interval confidence level.
- `bootstrap_samples`: 2,000 moving-block bootstrap resamples; minimum 200.
- `bootstrap_block_length`: 5 consecutive New York trading dates per sampled
  block.
- `cost_stress_multipliers`: `[1.0, 1.5, 2.0]`; unique multipliers at or above
  1.0, including 1.0. Spread, slippage, and commission are all scaled.

Each variant may optionally set `sensitivity_group`. Variants in the same
group are treated as a declared parameter neighborhood for descriptive
sensitivity reporting. Assign groups before examining results. The report
includes block-bootstrap intervals, the Bonferroni-adjusted validation
interval across the candidate family, sample counts, sensitivity-group
dispersion, cost-stress metrics, and explicit `ACCEPT`/`REJECT` decisions
with reason codes.

The selected configuration is ranked by its Bonferroni-adjusted validation
expectancy lower bound. Acceptance requires the minimum validation count, a
positive adjusted validation lower bound, the minimum evaluation count, a
positive evaluation-period lower bound, and a positive lower bound under the
maximum cost-stress multiplier. Rejection reasons distinguish validation,
test, and holdout failures.
A reported `ACCEPT` is a protocol outcome, not a claim of future profitability.
See [the statistical robustness protocol](research.md#statistical-robustness-protocol)
for interpretation and restrictions.
