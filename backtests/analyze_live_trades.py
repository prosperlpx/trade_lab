import pandas as pd
import os
from datetime import datetime

# --- CONFIGURATION ---
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
TRADED_DATES_FILE = os.path.join(LOG_DIR, 'traded_dates.txt')

def analyze_live_performance():
    print("🔍 Analyzing Live Forward Test Performance...")
    
    # 1. Check Traded Dates Log
    traded_days = []
    if os.path.exists(TRADED_DATES_FILE):
        with open(TRADED_DATES_FILE, 'r') as f:
            traded_days = [line.strip() for line in f.readlines() if line.strip()]
    
    total_alerts_sent = len(traded_days)
    print(f"✅ Total Alerts Sent by Bot: {total_alerts_sent}") # Fixed! 
    
    # 2. Calculate Expected vs Actual Trading Days
    today = datetime.now().strftime('%Y-%m-%d')
    unique_days = set(traded_days)
    print(f"📅 Unique Trading Days Active: {len(unique_days)}")
    
    # 3. Risk Management Validation
    # Since we risk $25 per trade, max daily loss should never exceed $100
    # If we had 4+ trades on one day, something broke.
    from collections import Counter
    day_counts = Counter(traded_days)
    max_trades_per_day = max(day_counts.values()) if day_counts else 0
    
    print("\n" + "="*50)
    print("🛡️ PROP FIRM COMPLIANCE CHECK")
    print("="*50)
    print(f"Max Trades in Single Day: {max_trades_per_day}")
    
    if max_trades_per_day > 1:
        print("❌ CRITICAL ERROR: Bot sent multiple alerts on same day!")
        print("   -> Check 'traded_dates.txt' for duplicates.")
    else:
        print("✅ PASS: Strict 1-Trade-Per-Day Rule Enforced.")
        
    print("\n" + "="*50)
    print("📊 NEXT STEPS FOR MANUAL REVIEW")
    print("="*50)
    print("To calculate Win Rate & PnL, please check your Telegram chat:")
    print(f"1. Count how many of the {total_alerts_sent} alerts you MANUALLY took.")
    print("2. For each taken trade, note if it hit TP (+$37.50) or SL (-$25.00).")
    print("3. Reply with: 'Took X trades, Y wins, Z losses'")
    print("="*50)

if __name__ == "__main__":
    analyze_live_performance()