import dataclasses

import pandas as pd
import pytest
from conftest import make_bars

from trade_lab.config import StrategyConfig
from trade_lab.data import DataError
from trade_lab.live import run_once
from trade_lab.notify import NotifyError
from trade_lab.state import StateStore
from trade_lab.strategy import first_signal, prepare

CFG = StrategyConfig()
DAY = "2026-11-18"
FACTOR = 35.0


def qqq_frame(extra_flat_bars: int = 1) -> pd.DataFrame:
    """20 flat bars from 09:30 NY, a long pullback bar at 11:10 NY (16:10 UTC),
    then flat bars. Flat bars close exactly at VWAP, so they never signal."""
    rows = [(100.5, 99.5, 100.0, 1000)] * 20
    rows.append((101.0, 99.9, 100.4, 1000))
    rows += [(100.5, 99.5, 100.0, 1000)] * extra_flat_bars
    return make_bars("2026-11-18 14:30", rows)


def nq_frame(qqq: pd.DataFrame) -> pd.DataFrame:
    nq = qqq.copy()
    for col in ("Open", "High", "Low", "Close"):
        nq[col] = nq[col] * FACTOR
    return nq


class Harness:
    def __init__(self, tmp_path, qqq=None, cfg=CFG):
        self.cfg = cfg
        self.qqq = qqq if qqq is not None else qqq_frame()
        self.nq = nq_frame(self.qqq)
        self.store = StateStore(tmp_path / "state.json")
        self.sent: list[str] = []
        self.fail_send = False

    def fetch(self, symbol):
        return self.qqq if symbol == "QQQ" else self.nq

    def send(self, text):
        if self.fail_send:
            raise NotifyError("Telegram returned HTTP 400")
        self.sent.append(text)

    def run(self, now, dry_run=False):
        return run_once(
            pd.Timestamp(now), self.cfg, self.store, self.fetch, self.send, dry_run=dry_run
        )


def test_fixture_first_signal_is_the_pullback_bar():
    prepared = prepare(qqq_frame(), CFG)
    sig = first_signal(prepared, CFG, pd.Timestamp("2026-11-18").date())
    assert sig is not None
    assert sig.time == pd.Timestamp("2026-11-18 16:10", tz="UTC")


def test_sends_one_alert_and_records_state(tmp_path):
    h = Harness(tmp_path)
    result = h.run("2026-11-18 16:17:00+00:00")
    assert result.status == "sent"
    assert len(h.sent) == 1
    msg = h.sent[0]
    assert "LONG" in msg and "0.18 lots" in msg
    assert h.store.day_closed(DAY)


def test_second_run_same_day_does_not_resend(tmp_path):
    h = Harness(tmp_path)
    h.run("2026-11-18 16:17:00+00:00")
    again = h.run("2026-11-18 16:22:00+00:00")
    assert again.status == "already_closed"
    assert len(h.sent) == 1


def test_scaled_levels_match_factor(tmp_path):
    h = Harness(tmp_path)
    result = h.run("2026-11-18 16:17:00+00:00", dry_run=True)
    assert result.status == "dry_run"
    assert f"Entry (reference): {100.4 * FACTOR:.2f}" in result.message


def test_dry_run_neither_sends_nor_records(tmp_path):
    h = Harness(tmp_path)
    h.run("2026-11-18 16:17:00+00:00", dry_run=True)
    assert h.sent == []
    assert not h.store.day_closed(DAY)


def test_outside_window_skips(tmp_path):
    h = Harness(tmp_path)
    assert h.run("2026-11-18 13:00:00+00:00").status == "outside_window"
    assert h.run("2026-11-18 20:05:00+00:00").status == "outside_window"


def test_in_progress_bar_is_never_used(tmp_path):
    h = Harness(tmp_path)
    # The 16:10 bar closes at 16:15, so at 16:12 it is still open.
    assert h.run("2026-11-18 16:12:00+00:00").status == "no_setup"


def test_stale_signal_closes_the_day(tmp_path):
    h = Harness(tmp_path, qqq=qqq_frame(extra_flat_bars=4))
    result = h.run("2026-11-18 16:33:00+00:00")
    assert result.status == "missed_stale"
    assert h.sent == []
    assert h.run("2026-11-18 16:38:00+00:00").status == "already_closed"


def test_stale_data_skips(tmp_path):
    h = Harness(tmp_path)
    assert h.run("2026-11-18 19:00:00+00:00").status == "stale_data"


def test_send_failure_is_not_recorded_so_it_can_retry(tmp_path):
    h = Harness(tmp_path)
    h.fail_send = True
    assert h.run("2026-11-18 16:17:00+00:00").status == "send_failed"
    assert not h.store.day_closed(DAY)
    h.fail_send = False
    assert h.run("2026-11-18 16:18:00+00:00").status == "sent"


def test_data_error_is_reported_not_raised(tmp_path):
    h = Harness(tmp_path)

    def broken(symbol):
        raise DataError("QQQ: empty response")

    result = run_once(
        pd.Timestamp("2026-11-18 16:17:00+00:00"), CFG, h.store, broken, h.send
    )
    assert result.status == "data_error"


def test_below_min_lot_closes_day_without_alert(tmp_path):
    tiny = dataclasses.replace(CFG, account_size=100.0)
    h = Harness(tmp_path, cfg=tiny)
    assert h.run("2026-11-18 16:17:00+00:00").status == "below_min_lot"
    assert h.sent == []
    assert h.store.day_closed(DAY)


def test_daily_loss_gate(tmp_path):
    h = Harness(tmp_path)
    h.store.record_pnl(DAY, -200.0)
    assert h.run("2026-11-18 16:17:00+00:00").status == "daily_loss_limit"
    assert h.sent == []


@pytest.mark.parametrize("now", ["2026-07-15 16:17:00+00:00"])
def test_window_is_new_york_time_in_summer(tmp_path, now):
    # 16:17 UTC is 12:17 EDT, inside the window; the data is stale for that
    # date, which proves the window gate passed and the freshness gate ran.
    h = Harness(tmp_path)
    assert h.run(now).status == "stale_data"


def test_uncertain_telegram_delivery_is_recorded_and_not_retried(tmp_path):
    h = Harness(tmp_path)

    def uncertain(_text):
        raise NotifyError("request timed out", delivery_uncertain=True)

    result = run_once(
        pd.Timestamp("2026-11-18 16:17:00+00:00"),
        h.cfg,
        h.store,
        h.fetch,
        uncertain,
    )
    assert result.status == "delivery_unknown"
    assert h.store.day_closed(DAY)
    assert h.store.entries(DAY)[0]["status"] == "delivery_unknown"
    assert h.run("2026-11-18 16:18:00+00:00").status == "already_closed"


def test_prepared_alert_is_persisted_without_sending(tmp_path):
    h = Harness(tmp_path)
    result = run_once(
        pd.Timestamp("2026-11-18 16:17:00+00:00"),
        h.cfg,
        h.store,
        h.fetch,
        h.send,
        defer_delivery=True,
        run_id="workflow-42",
    )
    assert result.status == "delivery_prepared"
    assert h.sent == []
    assert h.store.day_closed(DAY)
    pending = h.store.pending_delivery("workflow-42")
    assert pending is not None
    assert h.store.pending_delivery("another-run") is None


def test_checkpointed_delivery_marks_sent(tmp_path):
    from trade_lab.live import deliver_pending

    h = Harness(tmp_path)
    run_once(
        pd.Timestamp("2026-11-18 16:17:00+00:00"),
        h.cfg,
        h.store,
        h.fetch,
        h.send,
        defer_delivery=True,
        run_id="workflow-43",
    )
    result = deliver_pending(h.store, h.send, "workflow-43")
    assert result.status == "sent"
    assert len(h.sent) == 1
    assert h.store.entries(DAY)[0]["status"] == "sent"


def test_uncertain_delivery_is_quarantined_not_retried(tmp_path):
    from trade_lab.live import deliver_pending

    h = Harness(tmp_path)
    run_once(
        pd.Timestamp("2026-11-18 16:17:00+00:00"),
        h.cfg,
        h.store,
        h.fetch,
        h.send,
        defer_delivery=True,
        run_id="workflow-44",
    )

    def uncertain(_message):
        raise NotifyError("timeout", delivery_uncertain=True)

    result = deliver_pending(h.store, uncertain, "workflow-44")
    assert result.status == "delivery_unknown"
    assert h.store.day_closed(DAY)
    assert h.store.pending_delivery("workflow-44") is None
