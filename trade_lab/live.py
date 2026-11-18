"""Live monitor: each scheduled run makes exactly one decision.

Run with ``python -m trade_lab.live`` (add ``--dry-run`` to print instead of
sending). Credentials come from the BOT_TOKEN and CHAT_ID environment
variables.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .alert import format_alert
from .config import StrategyConfig
from .data import DataError, conversion_factor, fetch_bars
from .notify import NotifyError, send_telegram
from .sessions import drop_open_bar, in_window, is_fresh, ny_date
from .sizing import daily_loss_exceeded, lots_for_risk, scale_price
from .state import StateError, StateStore
from .strategy import Signal, first_signal, prepare

log = logging.getLogger("trade_lab.live")

BAR_MINUTES = 5
MAX_SIGNAL_AGE_MINUTES = 10
SIGNAL_SYMBOL = "QQQ"
EXECUTION_SYMBOL = "NQ=F"


@dataclass(frozen=True)
class RunResult:
    status: str
    detail: str = ""
    signal: Signal | None = None
    message: str | None = None


Fetcher = Callable[[str], pd.DataFrame]
Sender = Callable[[str], None]


def run_once(
    now: pd.Timestamp,
    cfg: StrategyConfig,
    store: StateStore,
    fetch: Fetcher,
    send: Sender,
    dry_run: bool = False,
    defer_delivery: bool = False,
    run_id: str | None = None,
) -> RunResult:
    """Evaluate the market once and alert if the day's setup is fresh."""
    now = pd.Timestamp(now)
    if not in_window(now, cfg):
        return RunResult("outside_window")

    day = ny_date(now).isoformat()
    if store.day_closed(day):
        return RunResult("already_closed")
    if daily_loss_exceeded(store.realized_pnl(day), cfg):
        return RunResult("daily_loss_limit")

    try:
        qqq = drop_open_bar(fetch(SIGNAL_SYMBOL), now, BAR_MINUTES)
    except DataError as exc:
        return RunResult("data_error", str(exc))
    if not is_fresh(qqq, now, BAR_MINUTES):
        return RunResult("stale_data")

    sig = first_signal(prepare(qqq, cfg), cfg, ny_date(now))
    if sig is None:
        return RunResult("no_setup")

    # The first setup of the day is the day's trade (same as the backtest).
    # If we are too late to act on it, close the day rather than alerting on
    # a later bar the backtest would never have traded.
    age = now - (sig.time + pd.Timedelta(minutes=BAR_MINUTES))
    if age > pd.Timedelta(minutes=MAX_SIGNAL_AGE_MINUTES):
        if not dry_run:
            store.record_missed(day, "stale_signal", sig)
        return RunResult("missed_stale", f"signal bar {sig.time}", sig)

    try:
        nq = drop_open_bar(fetch(EXECUTION_SYMBOL), now, BAR_MINUTES)
    except DataError as exc:
        return RunResult("data_error", str(exc), sig)
    factor = conversion_factor(qqq, nq)
    if factor is None:
        return RunResult("no_conversion", "no shared QQQ/NQ bar", sig)

    entry = scale_price(sig.entry, factor)
    stop = scale_price(sig.stop, factor)
    target = scale_price(sig.target, factor)
    risk_points = sig.risk_distance * factor
    lots = lots_for_risk(cfg.risk_dollars, risk_points, cfg)
    if lots == 0.0:
        if not dry_run:
            store.record_missed(day, "below_min_lot", sig)
        return RunResult("below_min_lot", f"risk distance {risk_points:.1f} points", sig)

    message = format_alert(
        sig.side,
        sig.time + pd.Timedelta(minutes=BAR_MINUTES),
        entry,
        stop,
        target,
        lots,
        risk_points,
        cfg,
    )
    if dry_run:
        return RunResult("dry_run", signal=sig, message=message)

    delivery_run_id = run_id or os.environ.get("TRADE_LAB_RUN_ID") or f"local-{os.getpid()}"
    store.record_pending(day, sig, entry, lots, message, delivery_run_id)
    if defer_delivery:
        return RunResult("delivery_prepared", signal=sig, message=message)
    return deliver_pending(store, send, delivery_run_id)


def deliver_pending(store: StateStore, send: Sender, run_id: str) -> RunResult:
    """Deliver only the pending alert prepared by this exact process/run."""
    pending = store.pending_delivery(run_id)
    if pending is None:
        return RunResult("no_pending_delivery")
    day, entry = pending
    try:
        send(entry["message"])
    except NotifyError as exc:
        if exc.delivery_uncertain:
            store.mark_delivery_unknown(day, entry["bar_time"], "telegram_delivery_uncertain")
            return RunResult("delivery_unknown", str(exc))
        store.clear_pending(day, entry["bar_time"])
        return RunResult("send_failed", str(exc))
    store.mark_sent(day, entry["bar_time"])
    return RunResult("sent", message=entry["message"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VWAP pullback live monitor")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="print alerts, do not send")
    modes.add_argument(
        "--prepare-alert", action="store_true",
        help="persist a pending alert without sending it (for checkpointed workflows)",
    )
    modes.add_argument(
        "--deliver-pending", action="store_true",
        help="deliver the pending alert created by this workflow run",
    )
    parser.add_argument("--state-file", help="path to the JSON state file")
    parser.add_argument("--now", help="ISO timestamp to evaluate instead of the clock (UTC)")
    parser.add_argument(
        "--record-pnl",
        type=float,
        help="add realized P&L (negative for a loss) for today and exit",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    try:
        cfg = StrategyConfig.from_env()
    except ValueError as exc:
        log.error("Invalid configuration: %s", exc)
        return 2

    store = StateStore(Path(args.state_file or os.environ.get("STATE_FILE", ".state/state.json")))
    now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")

    if args.record_pnl is not None:
        day = ny_date(now).isoformat()
        try:
            store.record_pnl(day, args.record_pnl)
        except (StateError, ValueError) as exc:
            log.error("State update refused: %s", exc)
            return 2
        log.info("Recorded P&L %.2f for %s", args.record_pnl, day)
        return 0

    token = os.environ.get("BOT_TOKEN", "")
    chat_id = os.environ.get("CHAT_ID", "")
    if not args.dry_run and not (token and chat_id):
        log.error("BOT_TOKEN and CHAT_ID must be set (or use --dry-run)")
        return 2

    try:
        def sender(message: str) -> None:
            send_telegram(token, chat_id, message)

        if args.deliver_pending:
            result = deliver_pending(
                store, sender, os.environ.get("TRADE_LAB_RUN_ID") or f"local-{os.getpid()}"
            )
        else:
            result = run_once(
                now,
                cfg,
                store,
                fetch_bars,
                sender,
                dry_run=args.dry_run,
                defer_delivery=args.prepare_alert,
                run_id=os.environ.get("TRADE_LAB_RUN_ID") or f"local-{os.getpid()}",
            )
    except StateError as exc:
        log.error("State validation failed; refusing to continue: %s", exc)
        return 2
    log.info("status=%s %s", result.status, result.detail)
    if args.dry_run and result.message:
        print(result.message)
    return 1 if result.status == "send_failed" and not args.deliver_pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
