# Configuration

## Runtime requirements

- Python 3.10 or newer.
- Dependencies declared in `pyproject.toml`: pandas, numpy, yfinance, and tzdata.
- Telegram credentials are required for live sending and the scheduled prepare/deliver modes; dry-run and cache validation do not send messages.

Install for development:

```bash
python -m pip install -e ".[dev]"
```

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `ACCOUNT_SIZE` | `10000` | Nominal account value used to derive the risk budget |
| `RISK_PERCENTAGE` | `0.01` | Fraction of account risked per setup |
| `MAX_DAILY_LOSS_PERCENTAGE` | `0.02` | Daily realized-loss threshold as a fraction of account |
| `REWARD_RISK` | `1.3` | Target multiple of stop distance |
| `ATR_STOP_MULT` | `1.5` | ATR multiplier for stop distance |
| `POINT_VALUE_PER_LOT` | `10` | Assumed value per index point per lot |
| `MIN_LOT` | `0.01` | Minimum supported lot |
| `LOT_STEP` | `0.01` | Lot increment |
| `BOT_TOKEN` | — | Telegram bot token |
| `CHAT_ID` | — | Telegram destination chat ID |
| `STATE_FILE` | `.state/state.json` | JSON state-file path |
| `TRADE_LAB_RUN_ID` | workflow-generated | Identifies the current scheduled workflow attempt; do not set manually for scheduled delivery |
| `GITHUB_SHA` | unset outside GitHub Actions | Runtime commit identifier recorded in research manifests when available |
| `TRADE_LAB_REVISION` | unset | Optional explicit code revision recorded in research manifests when `GITHUB_SHA` is unavailable |

New research code separates instrument-independent `StrategyParameters` from `AccountRiskConfig`. The live monitor retains `StrategyConfig` as a backwards-compatible combined adapter, including legacy CFD lot assumptions. All floating-point strategy and sizing parameters must be finite; NaN and positive/negative infinity are rejected both for direct construction and supported numeric environment overrides. The configuration also validates positive account size, risk percentages, stop/reward values, session order, integer ATR period, and lot constraints. Invalid values fail startup with a clear error. Session times, ATR period, tolerance, and maximum lot currently use code defaults unless the Python configuration is constructed directly.

## Local environment example

Set secrets in your shell rather than committing them:

```bash
export BOT_TOKEN="..."
export CHAT_ID="..."
export ACCOUNT_SIZE="10000"
export RISK_PERCENTAGE="0.01"
```

For PowerShell:

```powershell
$env:BOT_TOKEN = "..."
$env:CHAT_ID = "..."
```

Never put real tokens, chat IDs tied to private accounts, or credentials in source control, screenshots, test fixtures, or documentation. If a token has ever been committed, revoke it with BotFather and inspect repository history; deleting it from the current file is not sufficient.

## CLI options

```text
python -m trade_lab.live [--dry-run | --prepare-alert | --deliver-pending] [--state-file PATH] [--now ISO_TIMESTAMP]
python -m trade_lab.live --record-pnl AMOUNT
```

- `--dry-run`: evaluate and print an alert without Telegram delivery or state updates.
- `--prepare-alert`: internal scheduled-workflow mode; persist a pending alert but do not send it. The workflow checkpoints this state before delivery.
- `--deliver-pending`: internal scheduled-workflow mode; send only the pending alert created by the current `TRADE_LAB_RUN_ID`.
- `--state-file`: override the state path.
- `--now`: evaluate at a supplied timestamp; a timezone-naive value is interpreted as UTC.
- `--record-pnl`: add a realized P&L amount to today's state and exit.

The scheduled workflow supplies `TRADE_LAB_RUN_ID`. It is used to prevent a later workflow attempt from sending a pending alert created by an interrupted earlier attempt.

Use `--now` with an explicit offset (for example `2026-11-18T16:17:00Z`) for reproducible manual checks. Do not use a dry run as evidence that live delivery or persistence works.
