"""Broker instrument contract calibration from operator-supplied specifications.

This module performs deterministic sizing arithmetic. It does not connect to a
broker or independently verify the supplied contract specification.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .instruments import AssetClass, InstrumentSpec


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _keys(
    value: dict[str, Any], required: set[str], optional: set[str], label: str
) -> None:
    unknown = set(value) - required - optional
    missing = required - set(value)
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {sorted(unknown)}")
    if missing:
        raise ValueError(f"{label} is missing required fields: {sorted(missing)}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _finite_positive(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be a finite positive number")
    return number


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _instrument(raw: Any) -> InstrumentSpec:
    values = dict(_object(raw, "instrument"))
    required = {
        "symbol", "asset_class", "quote_currency", "tick_size", "tick_value",
        "tick_value_currency", "quantity_unit", "min_quantity", "quantity_step",
        "max_quantity",
    }
    _keys(values, required, set(), "instrument")
    try:
        values["asset_class"] = AssetClass(values["asset_class"])
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in AssetClass)
        raise ValueError(f"instrument.asset_class must be one of: {choices}") from exc
    return InstrumentSpec(**values)


def _quantity_for_budget(
    risk_budget: float,
    stop_distance: float,
    instrument: InstrumentSpec,
    conversion_rate: float,
    spread_points: float,
    slippage_points: float,
    commission_per_quantity_side: float,
) -> dict[str, float | str | bool]:
    """Size down to step using stop risk plus modeled round-trip costs."""
    stop_risk_per_unit = instrument.risk_per_quantity(stop_distance, conversion_rate)
    price_cost_per_unit = instrument.price_cost_per_quantity(
        spread_points + 2.0 * slippage_points, conversion_rate
    )
    commission_cost_per_unit = 2.0 * commission_per_quantity_side
    total_risk_per_unit = stop_risk_per_unit + price_cost_per_unit + commission_cost_per_unit
    affordable_quantity = risk_budget / total_risk_per_unit
    raw_quantity = min(affordable_quantity, instrument.max_quantity)
    steps = math.floor(raw_quantity / instrument.quantity_step + 1e-9)
    quantity = round(steps * instrument.quantity_step, 10)
    if quantity < instrument.min_quantity - 1e-9:
        quantity = 0.0
    stop_risk = quantity * stop_risk_per_unit
    execution_cost = quantity * (price_cost_per_unit + commission_cost_per_unit)
    total_risk = stop_risk + execution_cost
    return {
        "quantity": quantity,
        "stop_risk": round(stop_risk, 8),
        "round_trip_execution_cost": round(execution_cost, 8),
        "total_planned_risk": round(total_risk, 8),
        "risk_budget": risk_budget,
        "risk_budget_respected": total_risk <= risk_budget + 1e-7,
        "minimum_quantity_fundable": quantity >= instrument.min_quantity,
        "maximum_quantity_capped": affordable_quantity > instrument.max_quantity,
        "risk_per_quantity": round(total_risk_per_unit, 8),
    }


def build_calibration_report(config: dict[str, Any], config_bytes: bytes) -> dict[str, Any]:
    """Validate a broker specification and produce a deterministic sizing matrix."""
    _keys(
        config,
        {"broker", "mapping", "conversion", "instrument", "execution_costs",
         "risk_budgets", "stop_distances"},
        set(),
        "configuration",
    )
    broker = dict(_object(config["broker"], "broker"))
    _keys(broker, {"id", "environment", "account_currency"}, set(), "broker")
    for key in ("id", "account_currency"):
        if not isinstance(broker[key], str) or not broker[key].strip():
            raise ValueError(f"broker.{key} must be a non-empty string")
    if broker["environment"] not in {"demo", "live"}:
        raise ValueError("broker.environment must be 'demo' or 'live'")

    mapping = dict(_object(config["mapping"], "mapping"))
    _keys(
        mapping,
        {"signal_symbol", "reference_symbol", "broker_symbol", "method",
         "source", "verified_at", "attestation"},
        set(),
        "mapping",
    )
    for key in ("signal_symbol", "reference_symbol", "broker_symbol", "source"):
        if not isinstance(mapping[key], str) or not mapping[key].strip():
            raise ValueError(f"mapping.{key} must be a non-empty string")
    if mapping["method"] not in {"direct", "reference_ratio", "manual"}:
        raise ValueError("mapping.method must be direct, reference_ratio, or manual")
    if mapping["attestation"] != "operator_attested":
        raise ValueError("mapping.attestation must be 'operator_attested'")
    verified_at = _timestamp(mapping["verified_at"], "mapping.verified_at")

    instrument = _instrument(config["instrument"])
    if instrument.symbol != mapping["broker_symbol"]:
        raise ValueError("instrument.symbol must exactly match mapping.broker_symbol")

    conversion = dict(_object(config["conversion"], "conversion"))
    _keys(
        conversion,
        {"tick_value_to_account_rate", "source", "observed_at"},
        set(),
        "conversion",
    )
    rate = _finite_positive(
        conversion["tick_value_to_account_rate"],
        "conversion.tick_value_to_account_rate",
    )
    if not isinstance(conversion["source"], str) or not conversion["source"].strip():
        raise ValueError("conversion.source must describe the conversion-rate source")
    conversion_time = _timestamp(conversion["observed_at"], "conversion.observed_at")
    if instrument.tick_value_currency == broker["account_currency"] and rate != 1.0:
        raise ValueError(
            "conversion rate must equal 1 when tick-value and account currencies match"
        )
    if instrument.tick_value_currency != broker["account_currency"] and rate == 1.0:
        raise ValueError(
            "a non-identity currency conversion requires an explicit non-1 rate"
        )

    costs = dict(_object(config["execution_costs"], "execution_costs"))
    cost_keys = {
        "spread_points", "slippage_points", "commission_per_quantity_side"
    }
    _keys(costs, cost_keys, set(), "execution_costs")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in costs.values()
    ):
        raise ValueError("execution costs must be finite non-negative numbers")
    normalized_costs = {key: float(value) for key, value in costs.items()}

    budgets = config["risk_budgets"]
    distances = config["stop_distances"]
    if not isinstance(budgets, list) or not budgets:
        raise ValueError("risk_budgets must be a non-empty array")
    if not isinstance(distances, list) or not distances:
        raise ValueError("stop_distances must be a non-empty array")
    risk_budgets = [
        _finite_positive(value, f"risk_budgets[{i}]")
        for i, value in enumerate(budgets)
    ]
    stop_distances = [
        _finite_positive(value, f"stop_distances[{i}]")
        for i, value in enumerate(distances)
    ]
    if len(set(risk_budgets)) != len(risk_budgets):
        raise ValueError("risk_budgets must not contain duplicates")
    if len(set(stop_distances)) != len(stop_distances):
        raise ValueError("stop_distances must not contain duplicates")

    matrix = []
    for budget in risk_budgets:
        for distance in stop_distances:
            result = _quantity_for_budget(
                budget,
                distance,
                instrument,
                rate,
                normalized_costs["spread_points"],
                normalized_costs["slippage_points"],
                normalized_costs["commission_per_quantity_side"],
            )
            matrix.append({
                "risk_budget": budget,
                "stop_distance_points": distance,
                **result,
            })

    payload = {
        "report_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "broker": broker,
        "mapping": {
            **mapping,
            "verified_at": verified_at,
            "attestation": "operator_attested",
        },
        "instrument": {
            "symbol": instrument.symbol,
            "asset_class": instrument.asset_class.value,
            "quote_currency": instrument.quote_currency,
            "tick_size": instrument.tick_size,
            "tick_value": instrument.tick_value,
            "tick_value_currency": instrument.tick_value_currency,
            "quantity_unit": instrument.quantity_unit,
            "min_quantity": instrument.min_quantity,
            "quantity_step": instrument.quantity_step,
            "max_quantity": instrument.max_quantity,
        },
        "conversion": {
            **conversion,
            "observed_at": conversion_time,
            "tick_value_to_account_rate": rate,
        },
        "execution_costs": normalized_costs,
        "sizing_matrix": matrix,
        "interpretation": {
            "broker_verification": (
                "The specification and mapping are operator-attested inputs; "
                "Trade Lab has not queried or independently verified the broker."
            ),
            "risk_model": (
                "Planned risk includes stop distance, full round-trip spread, "
                "two-sided slippage, and two-sided commission, converted to account currency."
            ),
            "mapping": (
                "A reference-ratio mapping is a price-level approximation, not proof "
                "that the signal and broker instruments are economically interchangeable."
            ),
            "execution": (
                "This report does not submit orders, retrieve quotes, validate margin, "
                "or model financing, partial fills, market impact, or broker-specific fills."
            ),
        },
    }
    return payload


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def run_calibration(config_path: str | Path, output_path: str | Path) -> int:
    source = Path(config_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if source == destination:
        raise ValueError("output path must not overwrite the configuration")
    source_bytes = source.read_bytes()
    config = _object(
        json.loads(source_bytes, object_pairs_hook=_unique_object),
        "configuration",
    )
    report = build_calibration_report(config, source_bytes)
    _atomic_write(
        destination,
        (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    print(f"Instrument calibration report written: {destination}")
    print(f"Broker: {report['broker']['id']} / {report['mapping']['broker_symbol']}")
    print(f"Sizing cases: {len(report['sizing_matrix'])}")
    print("Broker specifications are operator-attested, not independently verified.")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Calibrate risk sizing from an operator-supplied broker "
            "instrument specification."
        )
    )
    parser.add_argument("--config", required=True, help="Broker calibration JSON.")
    parser.add_argument("--output", required=True, help="Destination JSON report.")
    args = parser.parse_args(argv)
    try:
        return run_calibration(args.config, args.output)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"calibration failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
