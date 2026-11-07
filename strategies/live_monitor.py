import yfinance as yf
import pandas as pd
import numpy as np
import os
import urllib.request
import json
from datetime import datetime
import pytz

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_FALLBACK_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID', 'YOUR_FALLBACK_CHAT_ID')

# 🎯 SCALABLE RISK MANAGEMENT (SET FOR $10K ACCOUNT)
ACCOUNT_SIZE = 10000.0               # Target: $10,000 Prop Firm Account
RISK_PERCENTAGE = 0.01               # 1% Risk per trade = $100.00
MAX_DAILY_LOSS_PERCENTAGE = 0.02     # 2% Max Daily Loss = $200.00 (Hard kill switch)

# The bot calculates the exact dollars automatically based on ACCOUNT_SIZE
RISK_PER_TRADE_DOLLARS = ACCOUNT_SIZE * RISK_PERCENTAGE
MAX_DAILY_LOSS_DOLLARS = ACCOUNT_SIZE * MAX_DAILY_LOSS_PERCENTAGE

POINT_VALUE_PER_LOT = 10.0
WAT_TZ = pytz.timezone('Africa/Lagos')

# JSON State Management (Points to root logs folder)
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
STATE_FILE = os.path.join(LOG_DIR, 'state.json')

def get_online_wat_time():
    try:
        url = "https://www.cloudflare.com/cdn-cgi/trace"
        req = urllib.request.Request(url, headers={'User-Agent': 'TradingBot/1.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = response.read().decode('utf-8')
        for line in data.split('\n'):
            if line.startswith('ts='):
                unix_ts = float(line.split('=')[1])
                utc_dt = datetime.fromtimestamp(unix_ts, tz=pytz.UTC)
                return utc_dt.astimezone(WAT_TZ)
    except Exception:
        return datetime.now(WAT_TZ)

# --- JSON MEMORY FUNCTIONS ---
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    else:
        return {"traded_dates": [], "last_alert": None}

def save_state(state_data):
    with open(STATE_FILE, 'w') as f:
        json.dump(state_data, f, indent=2)

def has_traded_today():
    state = load_state()
    today_str = get_online_wat_time().strftime('%Y-%m-%d')
    return today_str in state["traded_dates"]

def log_trade_today(direction, entry_price):
    state = load_state()
    today_str = get_online_wat_time().strftime('%Y-%m-%d')
    
    if today_str not in state["traded_dates"]:
        state["traded_dates"].append(today_str)
        
    state["last_alert"] = {
        "date": today_str,
        "time": get_online_wat_time().strftime('%H:%M'),
        "direction": direction,
        "entry": entry_price
    }
    save_state(state)

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
        print("✅ Telegram alert sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send Telegram alert: {e}")

def check_market_setup():
    now_wat = get_online_wat_time()
    print(f"⏳ Checking market setup at {now_wat.strftime('%Y-%m-%d %H:%M:%S')} WAT...")
    
    current_hour = now_wat.hour
    if not (15 <= current_hour < 20):
        print(f"   -> Outside trading window. Standing by...")
        return

    try:
        qqq_df = yf.Ticker("QQQ").history(period="1d", interval="5m")
        nq_df = yf.Ticker("NQ=F").history(period="1d", interval="5m")
    except Exception as e:
        print(f"   -> Network error: {e}")
        return

    if qqq_df.empty or nq_df.empty: return
    if isinstance(qqq_df.columns, pd.MultiIndex): qqq_df.columns = qqq_df.columns.get_level_values(0)
    if isinstance(nq_df.columns, pd.MultiIndex): nq_df.columns = nq_df.columns.get_level_values(0)

    latest_qqq = float(qqq_df['Close'].iloc[-1])
    latest_nq = float(nq_df['Close'].iloc[-1])
    if latest_qqq == 0: return
    conversion_factor = latest_nq / latest_qqq

    qqq_df['Typical_Price'] = (qqq_df['High'] + qqq_df['Low'] + qqq_df['Close']) / 3.0
    qqq_df['TP_Vol'] = qqq_df['Typical_Price'] * qqq_df['Volume']
    qqq_df['Cumulative_TP_Vol'] = qqq_df['TP_Vol'].cumsum()
    qqq_df['Cumulative_Volume'] = qqq_df['Volume'].cumsum().replace(0, 1)
    qqq_df['VWAP'] = qqq_df['Cumulative_TP_Vol'] / qqq_df['Cumulative_Volume']
    
    high_low = qqq_df['High'] - qqq_df['Low']
    high_close = np.abs(qqq_df['High'] - qqq_df['Close'].shift())
    low_close = np.abs(qqq_df['Low'] - qqq_df['Close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    qqq_df['ATR'] = true_range.rolling(14).mean()

    last_row = qqq_df.iloc[-1]
    if pd.isna(last_row['ATR']) or last_row['ATR'] == 0: return

    setup_found = False
    direction = ""
    qqq_entry, qqq_sl, qqq_tp = 0.0, 0.0, 0.0

    # LONG Setup
    if last_row['Close'] > last_row['VWAP'] and last_row['Low'] <= last_row['VWAP'] * 1.001:
        setup_found, direction = True, "🟢 LONG"
        qqq_entry = float(last_row['Close'])
        risk_dist = 1.5 * float(last_row['ATR'])
        qqq_sl = qqq_entry - risk_dist
        qqq_tp = qqq_entry + (risk_dist * 1.3) # Strict 1.3R Target
        
    # SHORT Setup
    elif last_row['Close'] < last_row['VWAP'] and last_row['High'] >= last_row['VWAP'] * 0.999:
        setup_found, direction = True, "🔴 SHORT"
        qqq_entry = float(last_row['Close'])
        risk_dist = 1.5 * float(last_row['ATR'])
        qqq_sl = qqq_entry + risk_dist
        qqq_tp = qqq_entry - (risk_dist * 1.3) # Strict 1.3R Target

    if setup_found:
        if has_traded_today():
            print("   -> Setup found, but already alerted today. Standing by.")
            return
            
        us100_entry = qqq_entry * conversion_factor
        us100_sl = qqq_sl * conversion_factor
        us100_tp = qqq_tp * conversion_factor
        us100_risk_distance = abs(us100_entry - us100_sl)
        lot_size = RISK_PER_TRADE_DOLLARS / (us100_risk_distance * POINT_VALUE_PER_LOT) if us100_risk_distance > 0 else 0.0
            
        message = (f"🚨 *US100 VWAP PULLBACK ALERT* 🚨\n\n"
                   f"📊 *Direction:* {direction}\n"
                   f"💰 *Entry:* {us100_entry:.2f}\n"
                   f"🛑 *Stop Loss:* {us100_sl:.2f}\n"
                   f"🎯 *Take Profit:* {us100_tp:.2f} (1.3R)\n"
                   f"💵 *Position Size:* {lot_size:.2f} lots (Risk: ${RISK_PER_TRADE_DOLLARS:.2f})\n\n"
                   f"⚠️ *Rule:* Max 1 trade today.")
        
        print("   -> 🚨 SETUP CONFIRMED! Sending Telegram alert...")
        send_telegram_alert(message)
        log_trade_today(direction, us100_entry)
    else:
        print("   -> No setup detected. Waiting...")

if __name__ == "__main__":
    print("🚀 GitHub Actions triggered. Checking market setup...")
    check_market_setup()