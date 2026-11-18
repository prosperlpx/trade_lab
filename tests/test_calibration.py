import json

import pytest

from trade_lab.calibration import build_calibration_report, main


def _config():
    return {
        "broker": {
            "id": "example-broker",
            "environment": "demo",
            "account_currency": "USD",
        },
        "mapping": {
            "signal_symbol": "QQQ",
            "reference_symbol": "NQ=F",
            "broker_symbol": "US100-DEMO",
            "method": "reference_ratio",
            "source": "Synthetic fixture; not a real broker specification",
            "verified_at": "2026-11-18T09:00:00Z",
            "attestation": "operator_attested",
        },
        "conversion": {
            "tick_value_to_account_rate": 1.0,
            "source": "same currency",
            "observed_at": "2026-11-18T09:00:00Z",
        },
        "instrument": {
            "symbol": "US100-DEMO",
            "asset_class": "index_cfd",
            "quote_currency": "USD",
            "tick_size": 0.1,
            "tick_value": 1.0,
            "tick_value_currency": "USD",
            "quantity_unit": "lot",
            "min_quantity": 0.01,
            "quantity_step": 0.01,
            "max_quantity": 100.0,
        },
        "execution_costs": {
            "spread_points": 0.2,
            "slippage_points": 0.1,
            "commission_per_quantity_side": 0.5,
        },
        "risk_budgets": [100.0, 200.0],
        "stop_distances": [10.0, 20.0],
    }


def _report(config=None):
    payload = _config() if config is None else config
    return build_calibration_report(payload, json.dumps(payload).encode())


def test_calibration_sizes_with_stop_and_round_trip_costs():
    report = _report()
    first = report["sizing_matrix"][0]
    assert first["quantity"] == pytest.approx(0.95)
    assert first["stop_risk"] == pytest.approx(95.0)
    assert first["round_trip_execution_cost"] == pytest.approx(4.75)
    assert first["total_planned_risk"] == pytest.approx(99.75)
    assert first["risk_budget_respected"] is True


def test_calibration_reports_minimum_quantity_and_maximum_caps():
    config = _config()
    config["risk_budgets"] = [0.1, 50_000.0]
    config["stop_distances"] = [10.0]
    rows = _report(config)["sizing_matrix"]
    assert rows[0]["quantity"] == 0.0
    assert rows[0]["minimum_quantity_fundable"] is False
    assert rows[1]["quantity"] == 100.0
    assert rows[1]["maximum_quantity_capped"] is True
    assert rows[1]["risk_budget_respected"] is True


def test_calibration_converts_tick_value_currency_to_account_currency():
    config = _config()
    config["instrument"]["tick_value_currency"] = "GBP"
    config["conversion"] = {
        "tick_value_to_account_rate": 1.25,
        "source": "operator-supplied FX quote",
        "observed_at": "2026-11-18T09:00:00Z",
    }
    row = _report(config)["sizing_matrix"][0]
    assert row["quantity"] == pytest.approx(0.76)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("mapping", "attestation"), "unverified", "operator_attested"),
        (("mapping", "verified_at"), "2026-11-18T09:00:00", "timezone"),
        (("instrument", "symbol"), "OTHER", "must exactly match"),
        (("conversion", "tick_value_to_account_rate"), 1.0, "non-1 rate"),
        (("broker", "environment"), "paper", "demo"),
    ],
)
def test_calibration_rejects_unverifiable_or_inconsistent_inputs(path, value, message):
    config = _config()
    config[path[0]][path[1]] = value
    if path == ("conversion", "tick_value_to_account_rate"):
        config["instrument"]["tick_value_currency"] = "GBP"
    with pytest.raises(ValueError, match=message):
        _report(config)


def test_calibration_requires_unique_positive_scenario_values():
    config = _config()
    config["risk_budgets"] = [100.0, 100.0]
    with pytest.raises(ValueError, match="duplicates"):
        _report(config)


def test_cli_writes_calibration_report_and_does_not_overwrite_config(tmp_path, capsys):
    config_path = tmp_path / "broker.json"
    output_path = tmp_path / "calibration.json"
    config_path.write_text(json.dumps(_config()), encoding="utf-8")
    assert main(["--config", str(config_path), "--output", str(output_path)]) == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["broker"]["id"] == "example-broker"
    assert len(report["sizing_matrix"]) == 4
    assert "not independently verified" in capsys.readouterr().out

    original = config_path.read_bytes()
    assert main(["--config", str(config_path), "--output", str(config_path)]) == 2
    assert config_path.read_bytes() == original
