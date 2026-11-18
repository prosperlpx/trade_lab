# Operations

## Local dry run

Install dependencies, then evaluate without Telegram delivery:

```bash
python -m pip install -e .
python -m trade_lab.live --dry-run
```

A dry run still requires the market-data request to succeed and the current time to pass the session/data/signal gates. It prints a message only when a valid, fresh setup is found. It does not send a Telegram message or record a sent/missed setup.

For a deterministic test timestamp:

```bash
python -m trade_lab.live --dry-run --now "2026-11-18T16:17:00Z"
```

The timestamp must be timezone-aware for unambiguous use; naive CLI values are treated as UTC.

## Telegram setup

1. Create a bot with Telegram's BotFather.
2. Obtain the bot token and destination chat ID.
3. Store them as environment variables locally or repository Actions secrets.
4. Run a dry run first; then verify delivery in a controlled private chat before enabling scheduled notifications.

The live monitor requires both `BOT_TOKEN` and `CHAT_ID`. Telegram errors are wrapped so the bot token is not included in logged exception text.

## GitHub Actions

The workflows are `.github/workflows/trading_bot.yml` (scheduled monitor) and `.github/workflows/ci.yml` (quality and documentation checks). The trading workflow:

- schedules weekday runs every five minutes across a broad UTC window;
- relies on the application to enforce the New York-local 10:00–15:00 window;
- serializes runs with a concurrency group;
- restores `.state/state.json` and `.state/state.json.bak` using date-scoped Actions cache keys;
- validates a restored cache before running. A cache miss is allowed to initialize an empty state only before 10:00 New York time; a miss at or after session start stops the run;
- checkpoints a pending alert and state backup to a unique cache key before calling Telegram, then stores the final delivery outcome under a later key;
- prepares and delivers alerts in separate steps for scheduled events; manual dispatch runs dry-run mode and never writes scheduled state.

Configure `BOT_TOKEN` and `CHAT_ID` in repository Actions secrets before expecting scheduled Telegram delivery. Manual dispatch is deliberately dry-run.

The cron schedule is not an exchange calendar. The application’s stale-data check is a secondary guard, not a holiday-calendar implementation. GitHub-hosted runners and Actions cache are operational dependencies, not a durable database. The restore action's `cache-matched-key` output is passed as `CACHE_MATCHED_KEY` to the cache guard. A same-day cache miss during the session fails closed; it is not treated as a new day. Scheduled workflows run from the repository's default branch; pushing this workflow to a feature branch does not activate that branch's schedule on the default branch. Manual dispatch remains dry-run.

Run the guard manually only when reproducing workflow behavior; it uses the current New York clock and the actual cache-matched key must come from the restore action:

```bash
python -m trade_lab.cache_guard --matched-key "$CACHE_MATCHED_KEY" --state-file .state/state.json
```

## State and manual P&L

By default state is stored at `.state/state.json`; its last-known-good predecessor is `.state/state.json.bak`. A missing primary with a backup, or an existing unreadable, malformed, structurally invalid, or unsupported-version file causes the monitor to stop with a non-zero exit. The scheduled cache guard creates an explicit empty baseline only before the session begins. A local first run may begin with no primary or backup and creates both on its first state mutation. Do not delete state to clear a daily lockout. Preserve both files before any manual recovery, and do not commit them.

Record realized P&L manually:

```bash
python -m trade_lab.live --record-pnl -100
python -m trade_lab.live --record-pnl 45.50
```

Each command adds to the current New York date. The loss gate uses the accumulated value. There is no automatic import from a broker.

## Common statuses

| Status | Meaning |
| --- | --- |
| `outside_window` | Current time is outside configured New York session |
| `already_closed` | A sent, missed, pending, or uncertain delivery already closed the day |
| `daily_loss_limit` | Manually recorded realized loss reached the configured threshold |
| `data_error` | Provider request failed or returned unusable data |
| `stale_data` | Latest closed market-data bar is too old |
| `no_setup` | No qualifying setup on the current day |
| `missed_stale` | First setup was too old to alert; it was recorded as missed |
| `no_conversion` | QQQ and NQ have no shared usable bar timestamp |
| `below_min_lot` | Nominal risk budget cannot fund the configured minimum lot |
| `dry_run` | Alert was formatted but not sent or persisted |
| `send_failed` | Telegram explicitly rejected the request; pending state is cleared and a later run may retry |
| `delivery_unknown` | Telegram may have accepted the message but no trustworthy response was received; the day is closed pending manual reconciliation |
| `delivery_prepared` | Pending alert was persisted for a scheduled workflow checkpoint; it has not yet been sent |
| `no_pending_delivery` | The current workflow attempt has no pending alert to send |
| `sent` | Telegram accepted the alert and state was recorded |

## Incident response

- If a Telegram token may have leaked, revoke it with BotFather and replace the Actions secret.
- If state is corrupt or unexpectedly missing, stop scheduled delivery while investigating; do not assume an empty state is safe because it can permit duplicate alerts. See [troubleshooting and recovery](troubleshooting.md) for the recovery procedure.
- If data timestamps or converted levels look wrong, disable scheduled delivery and inspect both QQQ and NQ source bars before resuming.
- If a run is interrupted after the pre-delivery checkpoint, the next run converts the pending entry to `delivery_unknown` and will not resend it. Reconcile Telegram history before manually clearing or reopening the day.
- Network timeouts, HTTP 408/425/5xx responses, malformed responses, and transport errors are treated as uncertain delivery. Explicit rejection responses such as ordinary 4xx/429 are retryable after the pending intent is cleared.
- Never treat a GitHub Actions green check as evidence of strategy profitability or broker execution correctness.
