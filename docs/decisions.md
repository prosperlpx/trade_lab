# Engineering decisions

This document records decisions that materially affect the current implementation. It is a concise decision log, not a claim that every future design choice has been finalized.

## DEC-001 — Alerting boundary, not order execution

**Status:** Accepted

Trade Lab evaluates a market setup and can send a Telegram alert. It does not submit orders, inspect fills, or reconcile positions. The distinction is deliberate: a signal, an alert, a simulated trade, and an executed broker trade are separate events and must remain separate in reporting.

## DEC-002 — QQQ signal data with NQ reference conversion

**Status:** Accepted as a provisional data approach; execution suitability not established

QQQ 5-minute bars provide the signal inputs. The newest shared QQQ/NQ timestamp supplies a simple NQ-to-QQQ price ratio for converting reference levels. This is not a validated mapping to a broker's US100/NAS100 CFD. Basis, contract roll, dividends, session differences, broker pricing, and contract specifications are not modeled.

## DEC-003 — New York wall-clock session

**Status:** Accepted

The default signal window is 10:00 inclusive to 15:00 exclusive in `America/New_York`. Use the IANA timezone rather than a fixed UTC offset so daylight-saving transitions are handled by the runtime.

## DEC-004 — First qualifying setup closes the daily opportunity

**Status:** Accepted

The first qualifying setup in the configured window is the day's setup. If it is too old to alert, the system records it as missed rather than selecting a later setup. This keeps live selection aligned with the current one-setup-per-day rule.

## DEC-005 — Current VWAP pullback inequalities remain unchanged

**Status:** Accepted; strategy review remains open

Long: close above VWAP and low at or below VWAP multiplied by one plus tolerance. Short: close below VWAP and high at or above VWAP multiplied by one minus tolerance.

These are one-sided conditions. They do not require the candle to remain on the opposite side of VWAP, nor do they cap how far it may trade through VWAP. A bar that crosses substantially through VWAP can still qualify if its close satisfies the directional condition. This behavior is documented rather than silently changed; any stricter definition requires an explicit strategy decision and updated historical evaluation.

## DEC-006 — True range excludes overnight gaps; ATR rolling window does not reset

**Status:** Accepted as current behavior; review open

The previous close used in true range is grouped by New York calendar date. Therefore the first bar of each date uses high minus low. The resulting true-range series is then passed to a conventional rolling mean; the ATR window can contain observations from the preceding date. These are separate choices and must not be described as a daily-reset ATR.

## DEC-007 — JSON state fails closed when present but invalid

**Status:** Accepted

In scheduled mode, a missing state file is accepted only during the pre-session bootstrap window. Local first-run operations may begin with no primary or backup file; the first state mutation creates both. An existing unreadable, malformed, structurally invalid, missing-primary-with-backup, or unsupported-schema file is not equivalent to missing state: the monitor stops rather than assuming no alerts have been sent. State writes are atomic, synchronised where supported, and preserve the previous primary in a `.bak` file. Operators must preserve and explicitly restore state before resuming.

## DEC-008 — GitHub Actions cache is a guarded continuity mechanism

**Status:** Accepted with limitations

The scheduled workflow serializes runs and uses date-scoped cache keys. It fails closed on a cache miss during the trading session, checkpoints a pending delivery before calling Telegram, and stores the final outcome under a later cache key. A pending intent restored from an interrupted earlier attempt is marked `delivery_unknown` and is never automatically resent. Cache is not a transactional database; loss of all same-day cache entries requires manual reconciliation.

## DEC-009 — No implicit strategy or broker assumptions

**Status:** Accepted

Configuration values for account size, point value, and lot sizing are assumptions supplied by the operator. No broker integration currently verifies them. Strategy changes, contract assumptions, and data-source changes require explicit review and corresponding tests.

## DEC-010 — External delivery is checkpointed before side effects

**Status:** Accepted for scheduled and local runs

The application persists a pending alert before calling Telegram. GitHub Actions saves that pending state under a unique checkpoint cache key before the delivery step. A later run never sends a pending entry restored from an earlier attempt; it converts it to `delivery_unknown`. Explicit Telegram rejection clears the pending entry so a later scheduled attempt can retry. Network failures, timeouts, malformed responses, and server errors are treated as uncertain and are not retried automatically. This favors avoiding duplicate alerts over automatic recovery from ambiguous delivery.

## DEC-011 — Documentation is checked against repository interfaces

**Status:** Accepted

CI runs `scripts/verify_docs.py`. It checks local Markdown links, documented Python command targets, Ruff paths, package module inventory, CLI options, environment variables, and workflow references against the repository. It does not prove the truth of every prose claim; implementation changes still require a deliberate documentation review and corresponding tests.

## Changing a decision

For a material change:
1. State the problem and the alternatives.
2. Record the selected behavior and its consequences here.
3. Update implementation and tests in the same change.
4. Update the strategy, risk, operations, and architecture documents affected.
5. Identify whether historical results remain comparable after the change.
