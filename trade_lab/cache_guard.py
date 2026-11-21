"""Fail-closed bootstrap policy for the GitHub Actions state cache."""

from __future__ import annotations

import argparse
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import StrategyConfig
from .state import StateError, StateStore

NEW_YORK = ZoneInfo("America/New_York")


def guard_cache(
    store: StateStore,
    matched_key: str | None,
    now: datetime,
    session_start: time,
) -> str:
    """Validate a cache hit or initialize only before the trading window.

    A cache miss during the trading window is ambiguous: it may be the first
    run, or a lost/evicted cache after alerts were sent. The safe response is
    to stop rather than silently start with empty alert history.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    if matched_key:
        expected_prefix = f"trade-state-{now.astimezone(NEW_YORK).date().isoformat()}-"
        if not matched_key.startswith(expected_prefix):
            raise StateError(
                f"Restored cache key is outside the current New York date: {matched_key}"
            )
        store.validate_cached_state()
        interrupted = store.mark_interrupted_pending()
        return "restored_with_interrupted_delivery" if interrupted else "restored"

    local_time = now.astimezone(NEW_YORK).time().replace(tzinfo=None)
    if local_time >= session_start:
        raise StateError(
            "No same-day Actions cache was restored during the trading window. "
            "Refusing to initialize empty alert history; inspect cache and Telegram history."
        )

    created = store.initialize()
    return "initialized" if created else "validated_existing"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or safely bootstrap Trade Lab state cache"
    )
    parser.add_argument(
        "--matched-key", default="", help="cache-matched-key output from actions/cache"
    )
    parser.add_argument("--state-file", default=".state/state.json")
    args = parser.parse_args(argv)

    try:
        cfg = StrategyConfig.from_env()
        store = StateStore(Path(args.state_file))
        result = guard_cache(
            store,
            args.matched_key or None,
            datetime.now(NEW_YORK),
            cfg.session_start,
        )
    except (StateError, ValueError) as exc:
        parser.exit(2, f"state cache guard failed: {exc}\n")
    print(f"state cache: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
