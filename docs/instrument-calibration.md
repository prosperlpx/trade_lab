# Broker instrument calibration

M2.4 adds an offline calibration report for broker-specific instrument
specifications and risk sizing. It is deliberately separate from the live
monitor and does not submit orders or query a broker.

## Purpose

Trade Lab's research engine already accepts an `InstrumentSpec`, but the
legacy alert monitor still has generic CFD lot assumptions. Before using
displayed lot sizes as operational guidance, the instrument's contract
economics, quantity constraints, currency conversion, and expected execution
costs must be grounded in the intended broker's current specification.

The calibration workflow makes those assumptions explicit and produces a
risk-budget/stop-distance sizing matrix. It does not silently substitute
generic values when information is missing.

## Run

Create a JSON file using the schema below, then run:

```bash
python -m trade_lab.calibration --config broker-instrument.json --output reports/instrument-calibration.json
```

The command exits with code 2 for invalid or inconsistent inputs. The report
records the configuration SHA-256, broker and symbol mapping, specification
attestation, conversion source and timestamp, cost assumptions, and each
sizing case.

## Configuration

```json
{
  "broker": {
    "id": "your-broker-id",
    "environment": "demo",
    "account_currency": "USD"
  },
  "mapping": {
    "signal_symbol": "QQQ",
    "reference_symbol": "NQ=F",
    "broker_symbol": "exact-broker-symbol",
    "method": "reference_ratio",
    "source": "URL or exact title of the broker contract specification",
    "verified_at": "2026-11-18T09:00:00Z",
    "attestation": "operator_attested"
  },
  "conversion": {
    "tick_value_to_account_rate": 1.0,
    "source": "same currency",
    "observed_at": "2026-11-18T09:00:00Z"
  },
  "instrument": {
    "symbol": "exact-broker-symbol",
    "asset_class": "index_cfd",
    "quote_currency": "USD",
    "tick_size": 0.1,
    "tick_value": 1.0,
    "tick_value_currency": "USD",
    "quantity_unit": "lot",
    "min_quantity": 0.01,
    "quantity_step": 0.01,
    "max_quantity": 100.0
  },
  "execution_costs": {
    "spread_points": 0.2,
    "slippage_points": 0.1,
    "commission_per_quantity_side": 0.0
  },
  "risk_budgets": [25.0, 50.0, 100.0],
  "stop_distances": [25.0, 50.0, 100.0]
}
```

The numerical instrument and cost values above are illustrative only. Replace
them with the exact values from the intended broker and account; they are not
Exness specifications or defaults.

### Required fields and rules

- `broker.environment` must be `demo` or `live`.
- `mapping.broker_symbol` must exactly match `instrument.symbol`.
- `mapping.method` is `direct`, `reference_ratio`, or `manual`.
- `mapping.source` identifies the specification or mapping evidence.
- `mapping.verified_at` is timezone-aware and records when the operator
  checked the broker specification.
- `mapping.attestation` must be `operator_attested`. This is an explicit
  operator assertion, not a remote verification by Trade Lab.
- `conversion.tick_value_to_account_rate` converts one unit of
  `tick_value_currency` into the account currency. The rate, source, and
  observation timestamp are mandatory. Identical currencies require a rate
  of exactly 1.
- `commission_per_quantity_side` is denominated in account currency per
  quantity unit per side. Spread and slippage are in instrument price points.
- Risk budgets and stop distances must be finite, positive, unique arrays.

## Sizing calculation

For each risk budget and stop distance, the report computes:

1. Stop risk per quantity using tick size, tick value, and currency conversion.
2. Round-trip spread, two adverse slippage fills, and two commission sides.
3. Maximum affordable quantity, rounded down to the broker's quantity step.
4. Minimum-quantity eligibility and maximum-quantity cap.
5. Stop risk, modeled execution cost, total planned risk, and a budget check.

A case that cannot fund the minimum quantity returns zero rather than rounding
up and exceeding the risk budget. A quantity capped by the broker maximum is
reported explicitly.

## Interpretation and boundary

The report is a deterministic calculation over operator-supplied values. It
does not independently verify a broker's contract specification, retrieve a
quote, validate margin/leverage, inspect an account, or test actual fills.
Reference-ratio mapping is a price-level approximation; it does not establish
economic equivalence between QQQ, NQ futures, and a broker CFD.

The calibration report does not change the live monitor's legacy lot settings.
Do not treat it as an approved live-trading profile. First reconcile the
instrument symbol, tick economics, quantity limits, currency conversion,
spread/commission schedule, and price mapping against the broker's current
demo-account specification and observed quotes. Broker connectivity and
automatic order execution remain outside this milestone.
