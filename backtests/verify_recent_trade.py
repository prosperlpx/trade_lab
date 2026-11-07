import yfinance as yf
import pandas as pd

# --- THE ALERT DETAILS WE ARE VERIFYING ---
ENTRY_PRICE = 686.36
STOP_LOSS = 685.01
TAKE_PROFIT = 688.38
DIRECTION = "LONG"
POSITION_SIZE = 18.58 # From your bot's calculation

print(f"⏳ Fetching recent 5-minute data for QQQ to verify the trade...")

# Fetch the last 5 days of 5-minute data to ensure we catch the setup
ticker = yf.Ticker("QQQ")
df = ticker.history(period="5d", interval="5m")

if df.empty:
    print("❌ Could not fetch live data. Check your internet connection.")
else:
    # Find the candle where the Close price is closest to our ENTRY_PRICE
    df['Price_Diff'] = abs(df['Close'] - ENTRY_PRICE)
    
    # Filter to only look at candles very close to the entry (within $1.00) 
    # to ensure we don't accidentally match a different day
    close_matches = df[df['Price_Diff'] < 1.0].copy()
    
    if close_matches.empty:
        print("❌ Could not find a matching candle near the entry price of 686.36 in the last 5 days.")
    else:
        # Get the closest match
        closest_match = close_matches.sort_values('Price_Diff').iloc[0]
        entry_idx = df.index.get_loc(closest_match.name)
        
        print(f"\n🔍 Found matching setup candle at: {closest_match.name}")
        print(f"   Entry: {closest_match['Close']:.2f} | Low: {closest_match['Low']:.2f} | High: {closest_match['High']:.2f}")
        
        # Slice the data from that exact candle onwards to simulate the trade forward
        trade_data = df.iloc[entry_idx:].copy()
        
        hit_tp = False
        hit_sl = False
        exit_reason = "Still Open / Incomplete Data"
        
        for index, row in trade_data.iterrows():
            if DIRECTION == "LONG":
                # Check Stop Loss first (did the intraday low hit it?)
                if row['Low'] <= STOP_LOSS:
                    hit_sl = True
                    exit_reason = "Stop Loss Hit"
                    break
                # Check Take Profit (did the intraday high hit it?)
                elif row['High'] >= TAKE_PROFIT:
                    hit_tp = True
                    exit_reason = "Take Profit Hit"
                    break
                    
        print("\n" + "="*50)
        print("📊 TRADE VERIFICATION RESULT")
        print("="*50)
        print(f"Direction:       {DIRECTION}")
        print(f"Entry Price:     {ENTRY_PRICE}")
        print(f"Stop Loss:       {STOP_LOSS}")
        print(f"Take Profit:     {TAKE_PROFIT}")
        print("-" * 50)
        
        if hit_tp:
            print("✅ RESULT: TAKE PROFIT HIT!")
            print("   The strategy successfully predicted the move.")
            simulated_profit = (TAKE_PROFIT - ENTRY_PRICE) * POSITION_SIZE
            print(f"   Simulated Profit: +${simulated_profit:.2f}")
        elif hit_sl:
            print("🛡️ RESULT: STOP LOSS HIT.")
            print("   The strategy took a controlled loss, exactly as risk management dictates.")
            simulated_loss = (ENTRY_PRICE - STOP_LOSS) * POSITION_SIZE
            print(f"   Simulated Loss: -${simulated_loss:.2f}")
        else:
            print("⏳ RESULT: TRADE STILL OPEN or Data Incomplete.")
            print("   The price has not yet reached either the Stop Loss or Take Profit.")
            
        print("="*50)