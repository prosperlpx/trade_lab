"""Configuration-driven command line for reproducible multi-instrument research."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, fields
from datetime import datetime, time, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import BacktestCosts
from .config import AccountRiskConfig, StrategyParameters
from .data_quality import findings_as_dicts, validate_research_bars
from .filters import StrategyFilters
from .instruments import AssetClass, InstrumentSpec
from .research import ResearchVariant, run_walk_forward_research


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _keys(value: Mapping[str, Any], allowed: set[str], required: set[str], label: str) -> None:
    unknown, missing = set(value) - allowed, required - set(value)
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


def _strategy(raw: Any, label: str) -> StrategyParameters:
    values = dict(_object(raw, label))
    _keys(values, {f.name for f in fields(StrategyParameters)}, set(), label)
    filters = _object(values.pop("filters", {}), f"{label}.filters")
    _keys(filters, {f.name for f in fields(StrategyFilters)}, set(), f"{label}.filters")
    for name in ("session_start", "session_end"):
        if name in values:
            try:
                values[name] = time.fromisoformat(values[name])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label}.{name} must be an ISO time") from exc
    return StrategyParameters(filters=StrategyFilters(**filters), **values)


def _instrument(raw: Any, symbol: str) -> InstrumentSpec:
    values = dict(_object(raw, f"symbols.{symbol}.instrument"))
    required = {
        "asset_class", "quote_currency", "tick_size", "tick_value",
        "tick_value_currency", "quantity_unit", "min_quantity",
        "quantity_step", "max_quantity",
    }
    _keys(values, required | {"symbol"}, required, f"symbols.{symbol}.instrument")
    values["symbol"] = values.get("symbol", symbol)
    try:
        values["asset_class"] = AssetClass(values["asset_class"])
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in AssetClass)
        raise ValueError(f"asset_class must be one of: {choices}") from exc
    return InstrumentSpec(**values)


def _load(path: Path) -> dict[str, Any]:
    try:
        return _object(
            json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object),
            "configuration",
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _load_research_csv(
    path: Path, *, expected_interval_minutes: int | None
) -> tuple[pd.DataFrame, bytes, list[dict[str, object]]]:
    """Read and validate source bytes without normalizing away data defects."""
    source_bytes = path.read_bytes()
    raw = pd.read_csv(BytesIO(source_bytes))
    if "Datetime" not in raw.columns:
        raise ValueError(f"{path}: CSV must contain a Datetime column")
    try:
        timestamps = pd.to_datetime(raw.pop("Datetime"), utc=True, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: invalid Datetime values: {exc}") from exc
    bars = raw.copy()
    bars.index = pd.DatetimeIndex(timestamps, name="Datetime")
    findings = validate_research_bars(
        bars, expected_interval_minutes=expected_interval_minutes
    )
    errors = [finding for finding in findings if finding.severity == "error"]
    if errors:
        detail = "; ".join(
            f"{finding.code} ({finding.count}): {finding.message}" for finding in errors
        )
        raise ValueError(f"{path}: historical data validation failed: {detail}")
    # Numeric conversion happens only after strict validation has accepted all rows.
    bars = bars[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return bars, source_bytes, findings_as_dicts(findings)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _write_artifacts(
    artifact_dir: Path,
    *,
    config_bytes: bytes,
    config_hash: str,
    config: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    variants: list[ResearchVariant],
    risk: AccountRiskConfig,
) -> None:
    """Persist content-addressed source snapshots and a complete run manifest."""
    for symbol, source in sources.items():
        symbol_key = hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:12]
        snapshot = artifact_dir / "datasets" / f"{symbol_key}-{source['sha256']}.csv"
        _atomic_write(snapshot, source["bytes"])
        source["snapshot"] = str(Path("datasets") / snapshot.name)

    _atomic_write(artifact_dir / "research-config.json", config_bytes)
    manifest = {
        "manifest_version": 1,
        "config_sha256": config_hash,
        "config_snapshot": "research-config.json",
        "code_revision": os.environ.get("GITHUB_SHA") or os.environ.get("TRADE_LAB_REVISION"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "risk": asdict(risk),
        "variants": [
            {
                "name": variant.name,
                "sensitivity_group": variant.sensitivity_group,
                "strategy": asdict(variant.config),
            }
            for variant in variants
        ],
        "datasets": {
            symbol: {key: value for key, value in source.items() if key != "bytes"}
            for symbol, source in sources.items()
        },
        "research_protocol": {
            "train_days": config["train_days"],
            "validation_days": config["validation_days"],
            "test_days": config["test_days"],
            "step_days": config.get("step_days"),
            "final_holdout_days": config.get("final_holdout_days", 0),
            "minimum_validation_trades": config.get("minimum_validation_trades", 30),
            "minimum_test_trades": config.get("minimum_test_trades", 30),
            "confidence_level": config.get("confidence_level", 0.95),
            "bootstrap_samples": config.get("bootstrap_samples", 2000),
            "bootstrap_block_length": config.get("bootstrap_block_length", 5),
            "cost_stress_multipliers": config.get("cost_stress_multipliers", [1.0, 1.5, 2.0]),
        },
    }
    payload = json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8") + b"\n"
    _atomic_write(artifact_dir / "manifest.json", payload)


def run_from_config(
    config_path: str | Path,
    output_path: str | Path,
    artifact_dir: str | Path | None = None,
) -> int:
    """Run research, preserving exact inputs and writing a reproducibility manifest."""
    source_path = Path(config_path).expanduser().resolve()
    config_bytes = source_path.read_bytes()
    config = _load(source_path)
    allowed = {
        "train_days", "validation_days", "test_days", "step_days",
        "final_holdout_days", "risk", "variants", "symbols",
        "minimum_validation_trades", "minimum_test_trades", "confidence_level",
        "bootstrap_samples", "bootstrap_block_length", "cost_stress_multipliers",
    }
    required = {"train_days", "validation_days", "test_days", "risk", "variants", "symbols"}
    _keys(config, allowed, required, "configuration")

    risk_values = _object(config["risk"], "risk")
    risk_fields = {f.name for f in fields(AccountRiskConfig)}
    _keys(risk_values, risk_fields, risk_fields, "risk")
    risk = AccountRiskConfig(**risk_values)

    raw_variants = config["variants"]
    if not isinstance(raw_variants, list) or not raw_variants:
        raise ValueError("variants must be a non-empty JSON array")
    variants = []
    for index, raw in enumerate(raw_variants):
        label = f"variants[{index}]"
        item = _object(raw, label)
        _keys(item, {"name", "strategy", "sensitivity_group"}, {"name", "strategy"}, label)
        if not isinstance(item["name"], str):
            raise ValueError(f"{label}.name must be a string")
        strategy = _strategy(item["strategy"], f"{label}.strategy")
        sensitivity_group = item.get("sensitivity_group", "default")
        if not isinstance(sensitivity_group, str) or not sensitivity_group.strip():
            raise ValueError(f"{label}.sensitivity_group must be a non-empty string")
        variants.append(ResearchVariant(item["name"], strategy, sensitivity_group))

    raw_symbols = _object(config["symbols"], "symbols")
    if not raw_symbols:
        raise ValueError("symbols must contain at least one instrument")
    datasets, instruments, costs, rates, data_sources = {}, {}, {}, {}, {}
    source_artifacts: dict[str, dict[str, Any]] = {}
    input_paths = {source_path}
    for symbol, item_raw in raw_symbols.items():
        if not symbol.strip():
            raise ValueError("symbol keys cannot be empty")
        label = f"symbols.{symbol}"
        item = _object(item_raw, label)
        required_item = {
            "csv", "data_source", "instrument", "costs", "value_to_account_rate"
        }
        optional_item = {
            "provider", "retrieved_at", "interval", "interval_minutes",
            "adjustment", "symbol_mapping",
        }
        _keys(item, required_item | optional_item, required_item, label)
        if not isinstance(item["csv"], str) or not item["csv"].strip():
            raise ValueError(f"{label}.csv must be a non-empty path")
        if not isinstance(item["data_source"], str) or not item["data_source"].strip():
            raise ValueError(f"{label}.data_source must describe provenance")
        for metadata_key in ("provider", "interval", "adjustment", "symbol_mapping"):
            if metadata_key in item and not isinstance(item[metadata_key], str):
                raise ValueError(f"{label}.{metadata_key} must be a string")
        retrieved_at = item.get("retrieved_at")
        if retrieved_at is not None:
            if not isinstance(retrieved_at, str):
                raise ValueError(f"{label}.retrieved_at must be an ISO-8601 string")
            try:
                parsed_retrieved_at = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"{label}.retrieved_at must be an ISO-8601 string") from exc
            if parsed_retrieved_at.utcoffset() is None:
                raise ValueError(f"{label}.retrieved_at must include a timezone")
        interval_minutes = item.get("interval_minutes")
        if interval_minutes is not None and (
            isinstance(interval_minutes, bool)
            or not isinstance(interval_minutes, int)
            or interval_minutes < 1
        ):
            raise ValueError(f"{label}.interval_minutes must be a positive integer")
        rate = item["value_to_account_rate"]
        invalid_rate = (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        )
        if invalid_rate:
            raise ValueError(f"{label}.value_to_account_rate must be a positive finite number")
        csv_path = Path(item["csv"]).expanduser()
        if not csv_path.is_absolute():
            csv_path = source_path.parent / csv_path
        csv_path = csv_path.resolve()
        if csv_path in input_paths:
            raise ValueError(
                "a CSV input path cannot be reused as the configuration or another input"
            )
        input_paths.add(csv_path)
        bars, source_bytes, findings = _load_research_csv(
            csv_path, expected_interval_minutes=interval_minutes
        )
        data_hash = hashlib.sha256(source_bytes).hexdigest()
        datasets[symbol] = bars
        instruments[symbol] = _instrument(item["instrument"], symbol)
        cost_values = _object(item["costs"], f"{label}.costs")
        cost_fields = {f.name for f in fields(BacktestCosts)}
        _keys(cost_values, cost_fields, cost_fields, f"{label}.costs")
        costs[symbol] = BacktestCosts(**cost_values)
        rates[symbol], data_sources[symbol] = rate, item["data_source"]
        source_artifacts[symbol] = {
            "bytes": source_bytes,
            "sha256": data_hash,
            "source_path": str(csv_path),
            "data_source": item["data_source"],
            "provider": item.get("provider"),
            "retrieved_at": retrieved_at,
            "interval": item.get("interval"),
            "interval_minutes": interval_minutes,
            "adjustment": item.get("adjustment"),
            "symbol_mapping": item.get("symbol_mapping"),
            "timezone_assumption": "CSV timestamps parsed as UTC",
            "rows": int(len(bars)),
            "first_timestamp": bars.index[0].isoformat() if len(bars) else None,
            "last_timestamp": bars.index[-1].isoformat() if len(bars) else None,
            "validation_findings": findings,
        }

    report = run_walk_forward_research(
        datasets=datasets, instruments=instruments, costs=costs, variants=variants,
        train_days=config["train_days"], validation_days=config["validation_days"],
        test_days=config["test_days"], step_days=config.get("step_days"),
        value_to_account_rates=rates, risk=risk, data_sources=data_sources,
        final_holdout_days=config.get("final_holdout_days", 0),
        minimum_validation_trades=config.get("minimum_validation_trades", 30),
        minimum_test_trades=config.get("minimum_test_trades", 30),
        confidence_level=config.get("confidence_level", 0.95),
        bootstrap_samples=config.get("bootstrap_samples", 2000),
        bootstrap_block_length=config.get("bootstrap_block_length", 5),
        cost_stress_multipliers=tuple(config.get("cost_stress_multipliers", [1.0, 1.5, 2.0])),
    )
    destination = Path(output_path).expanduser().resolve()
    if destination in input_paths:
        raise ValueError("output path must not overwrite the configuration or an input dataset")
    artifacts = (
        Path(artifact_dir).expanduser().resolve()
        if artifact_dir is not None
        else destination.with_suffix(".artifacts")
    )
    if (
        artifacts in input_paths
        or destination == artifacts
        or artifacts in destination.parents
        or any(artifacts in path.parents for path in input_paths)
    ):
        raise ValueError("artifact directory must not overwrite or contain an input or report")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", suffix=".tmp",
            prefix=f".{destination.name}.", dir=destination.parent, delete=False,
        ) as temporary:
            temporary_name = temporary.name
            report.to_csv(temporary, index=False)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)

    config_hash = hashlib.sha256(config_bytes).hexdigest()
    _write_artifacts(
        artifacts, config_bytes=config_bytes, config_hash=config_hash, config=config,
        sources=source_artifacts, variants=variants, risk=risk,
    )
    warning_count = sum(
        finding["severity"] == "warning"
        for source in source_artifacts.values()
        for finding in source["validation_findings"]
    )
    print(f"Research report written: {destination}")
    print(f"Reproducibility artifacts written: {artifacts}")
    print(f"Symbols: {', '.join(datasets)}")
    print(f"Rows: {len(report)}; roles: {report['role'].value_counts().to_dict()}")
    print(f"Data warnings: {warning_count}")
    print("Historical simulation only; this is not evidence of future performance.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run multi-instrument VWAP walk-forward research.")
    parser.add_argument("--config", required=True, help="JSON research configuration.")
    parser.add_argument("--output", required=True, help="Destination CSV report.")
    parser.add_argument(
        "--artifacts", help="Artifact directory (default: <output-name>.artifacts)."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_from_config(args.config, args.output, args.artifacts)
    except (OSError, TypeError, ValueError) as exc:
        print(f"research failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
