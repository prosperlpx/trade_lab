from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from trade_lab.cache_guard import guard_cache
from trade_lab.state import StateError, StateStore
from trade_lab.strategy import Signal

NY = ZoneInfo("America/New_York")
SESSION_START = time(10, 0)


def test_cache_miss_before_session_bootstraps_empty_state(tmp_path):
    store = StateStore(tmp_path / "state.json")
    result = guard_cache(store, None, datetime(2026, 11, 18, 9, 0, tzinfo=NY), SESSION_START)
    assert result == "initialized"
    store.validate_cached_state()


def test_cache_miss_during_session_fails_closed(tmp_path):
    store = StateStore(tmp_path / "state.json")
    with pytest.raises(StateError, match="No same-day Actions cache"):
        guard_cache(store, None, datetime(2026, 11, 18, 10, 0, tzinfo=NY), SESSION_START)
    assert not store.path.exists()


def test_cache_hit_requires_real_valid_primary_file(tmp_path):
    store = StateStore(tmp_path / "state.json")
    with pytest.raises(StateError, match="missing"):
        guard_cache(
            store,
            "trade-state-2026-11-18-old",
            datetime(2026, 11, 18, 10, 0, tzinfo=NY),
            SESSION_START,
        )


def test_cache_hit_validates_state_before_monitor_runs(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.initialize()
    assert (
        guard_cache(
            store,
            "trade-state-2026-11-18-old",
            datetime(2026, 11, 18, 10, 0, tzinfo=NY),
            SESSION_START,
        )
        == "restored"
    )


def test_cache_hit_marks_old_pending_delivery_unknown(tmp_path):
    store = StateStore(tmp_path / "state.json")
    signal = Signal(pd.Timestamp("2026-11-18T15:00:00Z"), 1, 100, 99, 102, 1)
    store.record_pending("2026-11-18", signal, 3500, 0.1, "alert", "old-run")
    result = guard_cache(
        store,
        "trade-state-2026-11-18-old",
        datetime(2026, 11, 18, 10, 5, tzinfo=NY),
        SESSION_START,
    )
    assert result == "restored_with_interrupted_delivery"
    assert store.entries("2026-11-18")[0]["status"] == "delivery_unknown"


def test_cache_key_from_another_date_is_rejected(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.initialize()
    with pytest.raises(StateError, match="outside the current New York date"):
        guard_cache(
            store,
            "trade-state-2026-11-17-old",
            datetime(2026, 11, 18, 10, 5, tzinfo=NY),
            SESSION_START,
        )


def test_cache_guard_rejects_naive_timestamp(tmp_path):
    store = StateStore(tmp_path / "state.json")
    with pytest.raises(ValueError, match="timezone-aware"):
        guard_cache(store, None, datetime(2026, 11, 18, 9, 0), SESSION_START)
