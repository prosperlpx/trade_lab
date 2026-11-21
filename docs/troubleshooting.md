# Troubleshooting and recovery

## Stop conditions

Disable scheduled alerting before investigating any condition that could invalidate the system's memory or price inputs:

- State file is unreadable, malformed, or has an unsupported schema.
- State appears unexpectedly missing or has rolled back.
- QQQ/NQ timestamps or converted levels are inconsistent.
- Telegram delivery status is uncertain.
- Workflow cache restoration or persistence appears to have failed.

Do not solve these conditions by deleting state and immediately resuming. An empty state can make an already-alerted day appear eligible again.

## State validation failure

The monitor distinguishes a missing file from an existing invalid file.

- **Missing file:** a local first run may initialize an empty store. The scheduled workflow permits bootstrap only before 10:00 New York time and only when no same-day cache key was restored. A missing primary with an existing `.bak` is an error.
- **Malformed JSON, invalid structure, unreadable file, or unsupported version:** raises StateError; the CLI exits non-zero and refuses to continue.

Recovery procedure:

1. Disable the scheduled workflow (or temporarily remove its schedule trigger) while preserving the repository and Actions history.
2. Preserve any locally available primary and backup files. GitHub Actions cache entries are not normal workflow artifacts; inspect cached state through a temporary, reviewed diagnostic workflow that restores the cache without running the alert-delivery step.
3. Compare the primary, backup, last successful workflow run, and Telegram history. The backup is the previous state, not necessarily the latest state.
4. Restore the best-supported known-good copy to the primary path, keeping untouched copies of both originals.
5. Validate schema version 1, canonical New York date keys, exact day-record and entry fields, finite P&L/price/lot values, and timezone-aware bar timestamps. Do not reconstruct an empty history unless Telegram history proves no alert was sent.
6. Run the state/cache validation tests and a dry run against a copy. A dry run alone is not proof that the restored state was loaded.
7. Re-enable scheduled delivery only after verifying the recovered alert history and the next scheduled run.

If it is impossible to determine whether an alert was delivered, reconcile Telegram history manually before resuming. Never delete a `delivery_unknown` or `delivery_pending` entry merely to make the bot run again. The scheduled system uses a checkpoint-before-send, at-most-once recovery policy for pending alerts. It cannot guarantee exactly-once delivery: after an interruption, an alert may require manual confirmation and may be left unsent rather than risk a duplicate.

## Actions cache appears missing or stale

The workflow restores the newest same-day cache using a date-scoped prefix. Cache entries are immutable. A cache miss may bootstrap an empty state only before 10:00 New York time; a miss during the session stops the run. Each scheduled attempt checkpoints its pending intent before Telegram delivery and writes a final cache entry after the outcome is persisted. Both the primary state and its `.bak` recovery copy are cached.

If state continuity is uncertain:

1. Disable scheduled alerting.
2. Inspect the relevant workflow runs and their logs for restore and save outcomes.
3. Compare the restored state with Telegram history for the same New York date.
4. Restore or reconstruct the state before resuming. The cache guard will reject a same-day cache miss during the session; do not bypass it by creating an empty state file.

A cache miss during the session is not proof that no alert was sent; the workflow stops rather than assuming an empty ledger. Cache retention and availability are not a durable database. If all same-day cache entries are lost, reconcile Telegram history and reconstruct state before any manual bootstrap.

## Telegram failures or uncertain delivery

- **send_failed** means Telegram explicitly rejected the request; the pending entry was cleared and a later run may retry while the signal remains fresh.
- **delivery_unknown** means a timeout, connection interruption, malformed response, HTTP 408/425, or server error may have happened after Telegram accepted the message. The day remains closed for manual reconciliation.
- Check the destination chat before retrying or manually editing state. A pending record restored from a previous workflow attempt is changed to `delivery_unknown` and is never automatically resent.
- If a token is exposed, revoke it with BotFather and replace the BOT_TOKEN secret. Review repository history and workflow logs.

## Stale or inconsistent market data

1. Stop scheduled delivery.
2. Inspect the raw QQQ and NQ bars around the signal timestamp.
3. Confirm timestamps are timezone-aware and normalized to UTC.
4. Confirm the selected conversion uses the newest exact shared timestamp.
5. Check for missing, zero, or implausible closes and for a provider outage or rate limit.
6. Resume only after the source data and reference conversion are credible.

Yahoo Finance is not an execution feed. A valid API response does not guarantee a tradable broker quote.

## Unexpected signal

Check the exact inequalities in the strategy specification. In particular, the VWAP pullback tests are one-sided: they do not cap how far the candle can cross VWAP. Do not assume a signal represents a narrow touch-and-rejection pattern.

Also inspect the first qualifying bar of the New York date. The monitor intentionally does not skip an old first setup in favor of a later one.

## Workflow controls

To pause scheduled alerts, disable the US100 VWAP Trading Bot workflow in the repository's Actions interface or remove its schedule trigger in a reviewed change. A manual dispatch currently runs with dry-run mode; it is not a live-delivery test.

A workflow on a feature branch does not by itself establish that the default-branch schedule is active. GitHub scheduled workflows are driven from the repository's default branch. Confirm the default branch and its workflow file before assuming production scheduling is enabled.
