import json
import os

import pandas as pd
import pytest

from trade_lab.state import StateError, StateStore
from trade_lab.strategy import Signal

SIG = Signal(
    time=pd.Timestamp("2026-11-18 16:10", tz="UTC"),
    direction=1,
    entry=100.4,
    stop=98.9,
    target=102.35,
    risk_distance=1.5,
)


def test_initialize_writes_a_valid_first_run_state(tmp_path):
    store = StateStore(tmp_path / "state.json")
    assert store.initialize() is True
    assert store.initialize() is False
    store.validate_cached_state()
    assert json.loads(store.path.read_text()) == {"days": {}, "version": 1}
    assert json.loads(store.backup_path.read_text()) == {"days": {}, "version": 1}


def test_state_backup_preserves_last_known_good_version(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.record_pnl("2026-11-18", -50)
    previous = store.path.read_text()
    store.record_missed("2026-11-18", "stale_signal", SIG)
    assert store.backup_path.read_text() == previous
    assert store.day_closed("2026-11-18")


def test_missing_primary_with_backup_fails_closed(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.record_pnl("2026-11-18", -50)
    store.path.unlink()
    with pytest.raises(StateError, match="backup exists"):
        store.day_closed("2026-11-18")


def test_cached_state_must_exist(tmp_path):
    store = StateStore(tmp_path / "state.json")
    with pytest.raises(StateError, match="missing"):
        store.validate_cached_state()


@pytest.mark.parametrize(
    "payload",
    [
        (
            '{"version": 1, "days": {"2026-11-18": {"entries": [{"status": [], '
            '"side": "LONG", "bar_time": "2026-11-18T16:10:00+00:00"}], "realized_pnl": 0}}}'
        ),
        (
            '{"version": 1, "days": {"2026-11-18": {"entries": [{"status": "sent", '
            '"side": "LONG", "bar_time": "2026-11-18T16:10:00+00:00", '
            '"entry": 1, "lots": Infinity}], "realized_pnl": 0}}}'
        ),
        '{"version": 1, "days": {"20261118": {"entries": [], "realized_pnl": 0}}}',
        '{"version": 1, "days": {"2026-11-18": {"entries": [], "realized_pnl": 1e999}}}',
        '{"version": 1.0, "days": {}}',
        (
            '{"version": 1, "days": {"2026-11-18": {"entries": [], '
            '"realized_pnl": 0, "extra": true}}}'
        ),
        (
            '{"version": 1, "days": {"2026-11-18": {"entries": [{"status": "missed", '
            '"side": "LONG", "bar_time": "2026-11-18T16:10:00+00:00", '
            '"reason": "stale", "extra": true}], "realized_pnl": 0}}}'
        ),
    ],
)
def test_state_rejects_invalid_nested_values(tmp_path, payload):
    store = StateStore(tmp_path / "state.json")
    store.path.write_text(payload)
    with pytest.raises(StateError):
        store.day_closed("2026-11-18")


def test_failed_primary_replace_keeps_original_state(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state.json")
    store.record_pnl("2026-11-18", -50)
    original = store.path.read_text()
    real_replace = os.replace

    def fail_primary(source, destination):
        if str(destination) == str(store.path):
            raise OSError("simulated replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_primary)
    with pytest.raises(StateError, match="persist state safely"):
        store.record_pnl("2026-11-18", -25)
    assert store.path.read_text() == original
    assert store.backup_path.read_text() == original


def test_delivery_unknown_closes_day_and_is_persisted(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.record_pending("2026-11-18", SIG, 3514, 0.18, "alert body", "run-1")
    store.mark_delivery_unknown("2026-11-18", SIG.time.isoformat(), "telegram_delivery_uncertain")
    assert store.day_closed("2026-11-18")
    entry = store.entries("2026-11-18")[0]
    assert entry["status"] == "delivery_unknown"
    assert "message" not in entry


def test_corrupt_primary_is_not_silently_replaced_by_valid_backup(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.record_pnl("2026-11-18", -50)
    store.path.write_text("{corrupt")
    with pytest.raises(StateError, match="malformed"):
        store.realized_pnl("2026-11-18")
    assert json.loads(store.backup_path.read_text()) == {"days": {}, "version": 1}
