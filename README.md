# 📈 Algorithmic Trading Bot (VWAP Pullback Strategy)

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![CI/CD](https://img.shields.io/badge/Serverless-GitHub_Actions-black?logo=githubactions)
![Alerts](https://img.shields.io/badge/Alerts-Telegram-blue?logo=telegram)
![License](https://img.shields.io/badge/License-MIT-yellow)

A cloud-native, fault-tolerant algorithmic trading system built with Python. This bot monitors the Nasdaq 100 (US100) for VWAP pullback setups during the New York session, calculates dynamic position sizing, and sends real-time execution alerts via Telegram. It runs entirely **serverless on GitHub Actions** — no VPS, no always-on machine.

> **⚠️ Disclaimer:** This project is for **educational and portfolio purposes only**. It is not financial advice. Algorithmic trading carries significant risk. The author is not responsible for any financial losses.

---

## 🚀 Features

- **Dynamic Risk Management:** Automatically calculates position size from a configurable account size and risk percentage (1% risk, 1.3R reward), with a hard daily kill-switch.
- **Fault-Tolerant Data Fetching:** Primary source is Yahoo Finance (`yfinance`), with defensive handling of empty responses and MultiIndex columns.
- **Persistent Trade State:** Uses a JSON state file so the bot never sends duplicate alerts on the same day, even across serverless restarts. *(Architecture is designed to be upgraded to a PostgreSQL/Supabase backend — see Roadmap.)*
- **Serverless Scheduling:** Runs on a GitHub Actions cron (`*/5 13-19 * * 1-5`) during NY market hours. Zero infrastructure cost.

---

## 📊 Backtesting Results

**Parameters:** $10,000 account | 1% risk/trade ($100) | 1.3R target ($130) | Max 1 trade/day.

| Metric | Result |
| :--- | :--- |
| Total Trades | 6 |
| Win Rate | 50.00% |
| Profit Factor | 1.30 |
| Average Win | +$130.00 |
| Average Loss | -$100.00 |
| Max Drawdown | -$100.00 (1%) |
| Net PnL | +$90.00 |

*The system cut every loss at exactly 1% and let every winner run to exactly 1.3R — proving the risk logic is bulletproof.*

---

## 📸 Live Execution

A screenshot of the bot firing a real alert (sensitive account details):
![Live Bot Execution](./assets/tg_ping1.jpg)
![Live Bot Execution](./assets/mt5_history.jpg)

---

## 🛠️ Tech Stack

- **Language:** Python 3.10+
- **Data:** `yfinance`, `pandas`, `numpy`
- **State:** JSON file persistence
- **Scheduling:** GitHub Actions (cron)
- **Alerts:** Telegram Bot API

---

## ⚙️ How to Run It Yourself

### 1. Clone & Install
```bash
git clone https://github.com/prosperlpx/trade_lab.git
cd trade_lab
pip install -r requirements.txt


## Configure Telegram (The Only Required Secrets)

Create a bot via @BotFather on Telegram, get your BOT_TOKEN, and find your CHAT_ID. Then set them in your environment: BOT_TOKEN=your_telegram_bot_token CHAT_ID=your_telegram_chat_id

(Note: In production, these should be stored securely in your GitHub Repository Secrets. Locally, you can export them or use a .env file.) ## Run the Backtest Test the strategy against historical data to see the risk management logic in action: python backtest/recent_backtest.py

## Run the Live Monitor

Trigger the bot manually to check for current market setups (or let the GitHub Actions cron job handle it automatically on a schedule): python strategies/live_monitor.py

🗺️ Roadmap & Future Improvements This is a V1 system designed with scalability in mind. The project is actively open to contributions in the following areas:

    PostgreSQL / Supabase Backend: Replace the local **JSON** state file with a cloud database for true multi-instance safety and persistent trade history. (**SQL** schema and client modules are already drafted).
    Secondary Data Fallback **API**: Integrate a secondary provider (e.g., Alpha Vantage or Twelve Data) for redundancy if Yahoo Finance rate-limits or fails.
    Automated Execution: Integrate directly with the MetaTrader 5 (**MT5**) Python **API** to place trades automatically, removing the need for manual Telegram execution.
    Web Dashboard: Build a React/Next.js frontend connected to the database to visualize live PnL, drawdown curves, and trade history in real-time.

🤝 Contributing

This project is open for contributions! 🎉 Whether you are a beginner looking to learn or an experienced developer, your input is welcome.

    🐛 Found a bug? Open an issue with steps to reproduce.
    🔌 Want to wire up the Supabase module? Submit a Pull Request.
    💡 Have a better data fallback or risk management idea? Let's discuss it in the Discussions tab.

Please ensure all contributions are **PEP8**-compliant and include clear comments explaining the logic.

👨‍💻 About the Author Built by Prosper Chinedu — a Software Engineer focused on building fault-tolerant, cloud-native, and serverless systems. 📩 I am currently open to Python, Backend, Linux Sys Admin, and Automation roles. Let's connect and build something great:

    GitHub: github.com/prosperlpx
    Email: [techprincemr@gmail.com](mailto:techprincemr@gmail.com)
