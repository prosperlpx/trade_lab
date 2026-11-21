import urllib.error
import urllib.request

import pandas as pd
import pytest
from conftest import make_bars

from trade_lab.data import DataError, conversion_factor, normalize_bars
from trade_lab.notify import NotifyError, send_telegram
from trade_lab.state import StateError, StateStore
from trade_lab.strategy import Signal

# ---- data ---------------------------------------------------------------


def _raw(tz="America/New_York"):
    idx = pd.date_range("2026-11-18 10:00", periods=3, freq="5min", tz=tz)
    return pd.DataFrame(
        {
            "Open": [1.0, 2.0, 3.0],
            "High": [2.0, 3.0, 4.0],
            "Low": [0.5, 1.5, 2.5],
            "Close": [1.5, 2.5, 3.5],
            "Volume": [10, None, 30],
            "Dividends": [0, 0, 0],
        },
        index=idx,
    )


def test_normalize_converts_to_utc_and_keeps_ohlcv_only():
    out = normalize_bars(_raw())
    assert str(out.index.tz) == "UTC"
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert out.index[0] == pd.Timestamp("2026-11-18 15:00", tz="UTC")
    assert out["Volume"].iloc[1] == 0.0


def test_normalize_flattens_multiindex_columns():
    raw = _raw()
    raw.columns = pd.MultiIndex.from_product([raw.columns, ["QQQ"]])
    assert "Close" in normalize_bars(raw).columns


def test_normalize_drops_duplicates_and_incomplete_rows():
    raw = _raw()
    dup = pd.concat([raw, raw.iloc[[-1]]])
    dup.iloc[0, dup.columns.get_loc("Close")] = float("nan")
    out = normalize_bars(dup)
    assert len(out) == 2
    assert out.index.is_unique


def test_normalize_rejects_naive_index_and_missing_columns():
    with pytest.raises(DataError):
        normalize_bars(_raw().tz_localize(None))
    with pytest.raises(DataError):
        normalize_bars(_raw().drop(columns=["Close"]))


def test_conversion_factor_uses_newest_shared_timestamp():
    a = make_bars("2026-11-18 15:00", [(1, 1, 100, 1), (1, 1, 100, 1)])
    b = make_bars("2026-11-18 15:05", [(1, 1, 3500, 1), (1, 1, 9999, 1)])
    # shared timestamp is only 15:05: a.Close=100, b.Close=3500
    assert conversion_factor(a, b) == pytest.approx(35.0)


def test_conversion_factor_none_without_overlap():
    a = make_bars("2026-11-18 15:00", [(1, 1, 100, 1)])
    b = make_bars("2026-11-18 16:00", [(1, 1, 3500, 1)])
    assert conversion_factor(a, b) is None


# ---- state --------------------------------------------------------------

SIG = Signal(
    time=pd.Timestamp("2026-11-18 16:10", tz="UTC"),
    direction=1,
    entry=100.4,
    stop=98.9,
    target=102.35,
    risk_distance=1.5,
)


def test_state_roundtrip_and_day_closed(tmp_path):
    store = StateStore(tmp_path / "s" / "state.json")
    assert not store.day_closed("2026-11-18")
    store.record_sent("2026-11-18", SIG, 3514.0, 0.18)
    assert store.day_closed("2026-11-18")
    assert not store.day_closed("2026-11-19")
    assert store.entries("2026-11-18")[0]["lots"] == 0.18


def test_state_missed_closes_day(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.record_missed("2026-11-18", "stale_signal", SIG)
    assert store.day_closed("2026-11-18")
    assert store.entries("2026-11-18")[0]["status"] == "missed"


def test_state_pnl_accumulates(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.record_pnl("2026-11-18", -100.0)
    store.record_pnl("2026-11-18", -50.5)
    assert store.realized_pnl("2026-11-18") == pytest.approx(-150.5)


@pytest.mark.parametrize(
    "payload",
    ["{not json", '{"version": 99, "days": {}}', '{"version": 1, "days": []}'],
)
def test_state_fails_closed_on_corrupt_or_unsupported_file(tmp_path, payload):
    path = tmp_path / "state.json"
    path.write_text(payload, encoding="utf-8")
    store = StateStore(path)
    with pytest.raises(StateError):
        store.day_closed("2026-11-18")


def test_state_missing_file_is_a_new_empty_store(tmp_path):
    store = StateStore(tmp_path / "missing.json")
    assert not store.day_closed("2026-11-18")


def test_state_rejects_non_finite_realized_pnl(tmp_path):
    store = StateStore(tmp_path / "state.json")
    with pytest.raises(ValueError, match="finite"):
        store.record_pnl("2026-11-18", float("nan"))


def test_state_prunes_old_days_relative_to_newest(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.record_missed("2026-10-01", "x", SIG)
    store.record_missed("2026-11-18", "x", SIG)
    assert not store.day_closed("2026-10-01")
    assert store.day_closed("2026-11-18")


# ---- notify -------------------------------------------------------------


def test_http_error_does_not_leak_token(monkeypatch):
    token = "123456:SECRET-TOKEN"

    def boom(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(NotifyError) as info:
        send_telegram(token, "42", "hello")
    assert token not in str(info.value)
    assert info.value.__suppress_context__
    assert info.value.__cause__ is None
    assert "401" in str(info.value)


def test_network_error_is_wrapped(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.URLError("dns failure for bot123:SECRET")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(NotifyError) as info:
        send_telegram("123:SECRET", "42", "hello")
    assert "SECRET" not in str(info.value)


def test_missing_credentials_fail_fast():
    with pytest.raises(NotifyError):
        send_telegram("", "42", "hello")
    with pytest.raises(NotifyError):
        send_telegram("token", "", "hello")


def test_telegram_not_ok_raises(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *args):
            return b'{"ok": false}'

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout=None: FakeResponse())
    with pytest.raises(NotifyError):
        send_telegram("t", "1", "hello")
