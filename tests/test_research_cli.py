import hashlib
import json

import pandas as pd

from trade_lab.research_cli import main


def _fixture(tmp_path):
    frames = []
    for day in pd.date_range("2026-01-05", periods=12, freq="B"):
        index = pd.date_range(day.strftime("%Y-%m-%d") + " 15:00", periods=4, freq="5min", tz="UTC")
        frames.append(pd.DataFrame({
            "Open": [100.0, 100.0, 100.5, 101.0],
            "High": [101.0, 101.0, 102.0, 103.0],
            "Low": [99.0, 99.0, 100.0, 100.5],
            "Close": [100.0, 100.5, 101.0, 102.0],
            "Volume": [1000.0] * 4,
        }, index=index))
    pd.concat(frames).rename_axis("Datetime").to_csv(tmp_path / "fixture.csv")
    config = {
        "train_days": 4, "validation_days": 2, "test_days": 2,
        "step_days": 2, "final_holdout_days": 2,
        "risk": {"account_size": 10000, "risk_pct": 0.01, "max_daily_loss_pct": 0.02},
        "variants": [
            {"name": "baseline", "strategy": {"atr_period": 1}},
            {
                "name": "filtered",
                "strategy": {"atr_period": 1, "filters": {"max_pullback_atr": 0.5}},
            },
        ],
        "symbols": {"ETF": {
            "csv": "fixture.csv", "data_source": "synthetic fixture, 5m UTC, unadjusted",
            "value_to_account_rate": 1.0,
            "instrument": {
                "asset_class": "etf", "quote_currency": "USD", "tick_size": 0.01,
                "tick_value": 0.01, "tick_value_currency": "USD", "quantity_unit": "share",
                "min_quantity": 1, "quantity_step": 1, "max_quantity": 100000,
            },
            "costs": {"spread_points": 0.02, "slippage_points": 0.01, "commission_per_unit": 0.0},
        }},
    }
    path = tmp_path / "research.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path, config


def test_cli_runs_and_writes_research_report(tmp_path, capsys):
    config, _ = _fixture(tmp_path)
    output = tmp_path / "reports" / "walk-forward.csv"
    assert main(["--config", str(config), "--output", str(output)]) == 0
    report = pd.read_csv(output)
    assert {"candidate", "selected_test", "final_holdout"} == set(report["role"])
    assert set(report["symbol"]) == {"ETF"}
    assert report["data_hash"].str.len().eq(64).all()
    artifacts = output.with_suffix(".artifacts")
    manifest = json.loads((artifacts / "manifest.json").read_text(encoding="utf-8"))
    snapshot = next((artifacts / "datasets").glob("*.csv"))
    source = (tmp_path / "fixture.csv").read_bytes()
    assert snapshot.read_bytes() == source
    assert manifest["datasets"]["ETF"]["sha256"] == hashlib.sha256(source).hexdigest()
    assert manifest["datasets"]["ETF"]["snapshot"] == f"datasets/{snapshot.name}"
    assert manifest["config_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert "Research report written" in capsys.readouterr().out


def test_cli_requires_explicit_cost_fields(tmp_path, capsys):
    config_path, config = _fixture(tmp_path)
    del config["symbols"]["ETF"]["costs"]["spread_points"]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["--config", str(config_path), "--output", str(tmp_path / "out.csv")]) == 2
    assert "missing required fields" in capsys.readouterr().err


def test_cli_rejects_duplicate_json_keys(tmp_path, capsys):
    config_path, _ = _fixture(tmp_path)
    config_path.write_text('{"train_days": 1, "train_days": 2}', encoding="utf-8")
    assert main(["--config", str(config_path), "--output", str(tmp_path / "out.csv")]) == 2
    assert "duplicate JSON key" in capsys.readouterr().err

def test_cli_refuses_to_overwrite_an_input_dataset(tmp_path, capsys):
    config_path, _ = _fixture(tmp_path)
    csv_path = tmp_path / "fixture.csv"
    original = csv_path.read_bytes()
    assert main(["--config", str(config_path), "--output", str(csv_path)]) == 2
    assert csv_path.read_bytes() == original
    assert "must not overwrite" in capsys.readouterr().err


def test_cli_rejects_duplicate_timestamps_instead_of_dropping_them(tmp_path, capsys):
    config_path, _ = _fixture(tmp_path)
    csv_path = tmp_path / "fixture.csv"
    frame = pd.read_csv(csv_path)
    frame.loc[1, "Datetime"] = frame.loc[0, "Datetime"]
    frame.to_csv(csv_path, index=False)
    assert main(["--config", str(config_path), "--output", str(tmp_path / "out.csv")]) == 2
    assert "duplicate_timestamps" in capsys.readouterr().err


def test_cli_records_intraday_gap_as_warning(tmp_path):
    config_path, config = _fixture(tmp_path)
    csv_path = tmp_path / "fixture.csv"
    frame = pd.read_csv(csv_path)
    frame = frame.drop(index=1)
    frame.to_csv(csv_path, index=False)
    config["symbols"]["ETF"]["interval_minutes"] = 5
    config_path.write_text(json.dumps(config), encoding="utf-8")
    output = tmp_path / "out.csv"
    assert main(["--config", str(config_path), "--output", str(output)]) == 0
    manifest = json.loads(
        (output.with_suffix(".artifacts") / "manifest.json").read_text(encoding="utf-8")
    )
    codes = {
        finding["code"]
        for finding in manifest["datasets"]["ETF"]["validation_findings"]
    }
    assert "intraday_gaps" in codes
