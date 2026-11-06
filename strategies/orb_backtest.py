import pandas as pd
import numpy as np
import os

# --- CONFIGURATION ---
DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'us100_5m.csv')

# Funding Pips $5K Account Risk Rules
ACCOUNT_SIZE = 5000.0
RISK_PER_TRADE_DOLLARS = 25.0      # 0.5% of account
MAX_DAILY_LOSS_DOLLARS = 100.0     # 2% of account (Hard kill switch)
DOLLAR_PER_POINT = 1.0             # Assumed value per point for position sizing math

# Strategy Parameters (in WAT / UTC+1)
ORB_START_HOUR = 14   # 14:30 WAT
ORB_START_MINUTE = 30
ORB_END_HOUR = 14     # 14:55 WAT (Last 5m candle of the 30-min range)
ORB_END_MINUTE = 55
TRADE_START_HOUR = 15 # 15:00 WAT onwards

def load_and_prepare_data():
    """Loads data and ensures timestamps are in WAT (West Africa Time, UTC+1)"""
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(f"Data file not found at {DATA_FILE}. Run data_downloader.py first.")
    
    print("⏳ Loading and preparing data...")
    
    # 1. Load CSV normally first
    df = pd.read_csv(DATA_FILE)
    
    # 2. Force pandas to parse the 'Datetime' column into real dates as UTC
    # utc=True is crucial here because Yahoo Finance data spans Daylight Saving Time,
    # resulting in mixed offsets (-04:00 and -05:00).
    df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
    
    # 3. Set it as the index
    df = df.set_index('Datetime')
    
    # 4. Convert UTC to WAT (Africa/Lagos)
    df.index = df.index.tz_convert('Africa/Lagos')
    
    # Sort index to ensure chronological order
    df = df.sort_index()
    
    # Calculate the 50-period EMA on the Close price (Trend Filter)
    df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    print(f"✅ Data loaded: {len(df)} candles from {df.index[0]} to {df.index[-1]} (WAT)")
    return df

def run_orb_backtest(df):
    """Simulates the 30-Minute Opening Range Breakout strategy"""
    print("⏳ Running Backtest with Funding Pips $5K Risk Rules...")
    
    trades = []
    
    # Group data by day to process each trading session individually
    for date, daily_df in df.groupby(df.index.date):
        current_daily_pnl = 0.0
        in_trade = False
        
        # 1. Identify the 30-minute Opening Range (14:30 to 14:55 WAT)
        # We look for candles where hour is 14 and minute is >= 30
        orb_mask = (daily_df.index.hour == ORB_START_HOUR) & (daily_df.index.minute >= ORB_START_MINUTE)
        orb_data = daily_df[orb_mask]
        
        # We need at least six 5-minute candles to have a full 30-minute range
        if len(orb_data) < 6:
            continue 
            
        orb_high = orb_data['High'].max()
        orb_low = orb_data['Low'].min()
        orb_midpoint = (orb_high + orb_low) / 2.0
        
        # Get the EMA value and Close at the end of the ORB period for trend filtering
        last_orb_row = orb_data.iloc[-1]
        ema_50 = last_orb_row['EMA_50']
        last_orb_close = last_orb_row['Close']
        
        # Determine bias based on 50 EMA
        is_bullish_bias = last_orb_close > ema_50
        is_bearish_bias = last_orb_close < ema_50
        
        # 2. Look for entries from 15:00 WAT onwards
        trade_window = daily_df[daily_df.index.hour >= TRADE_START_HOUR]
        
        entry_price = 0.0
        stop_loss = 0.0
        take_profit = 0.0
        position_size = 0.0
        trade_direction = 0 # 1 for Long, -1 for Short
        entry_time = None
        
        for index, row in trade_window.iterrows():
            if not in_trade:
                # Check for Long Breakout
                if is_bullish_bias and row['High'] > orb_high:
                    in_trade = True
                    entry_price = orb_high # Enter at breakout level
                    stop_loss = orb_midpoint
                    risk_points = entry_price - stop_loss
                    
                    if risk_points > 0:
                        # Calculate position size to risk exactly $25
                        position_size = RISK_PER_TRADE_DOLLARS / (risk_points * DOLLAR_PER_POINT)
                        take_profit = entry_price + (risk_points * 1.5)
                        trade_direction = 1
                        entry_time = index
                        
                # Check for Short Breakout
                elif is_bearish_bias and row['Low'] < orb_low:
                    in_trade = True
                    entry_price = orb_low
                    stop_loss = orb_midpoint
                    risk_points = stop_loss - entry_price
                    
                    if risk_points > 0:
                        position_size = RISK_PER_TRADE_DOLLARS / (risk_points * DOLLAR_PER_POINT)
                        take_profit = entry_price - (risk_points * 1.5)
                        trade_direction = -1
                        entry_time = index
            else:
                # We are in a trade, check for exit conditions
                pnl_points = 0.0
                exit_reason = ""
                
                if trade_direction == 1: # Long
                    if row['Low'] <= stop_loss:
                        pnl_points = stop_loss - entry_price
                        exit_reason = "Stop Loss"
                    elif row['High'] >= take_profit:
                        pnl_points = take_profit - entry_price
                        exit_reason = "Take Profit"
                    elif index.hour >= 17: # Time exit at 17:00 WAT
                        pnl_points = row['Close'] - entry_price
                        exit_reason = "Time Exit (17:00 WAT)"
                        
                elif trade_direction == -1: # Short
                    if row['High'] >= stop_loss:
                        pnl_points = entry_price - stop_loss
                        exit_reason = "Stop Loss"
                    elif row['Low'] <= take_profit:
                        pnl_points = entry_price - take_profit
                        exit_reason = "Take Profit"
                    elif index.hour >= 17: # Time exit at 17:00 WAT
                        pnl_points = entry_price - row['Close']
                        exit_reason = "Time Exit (17:00 WAT)"
                
                # If we exited, calculate dollar PnL and log it
                if exit_reason != "":
                    dollar_pnl = pnl_points * position_size * DOLLAR_PER_POINT
                    current_daily_pnl += dollar_pnl
                    
                    trades.append({
                        'Date': date,
                        'Entry_Time': entry_time.strftime('%Y-%m-%d %H:%M'),
                        'Exit_Time': index.strftime('%Y-%m-%d %H:%M'),
                        'Direction': 'Long' if trade_direction == 1 else 'Short',
                        'Entry': round(entry_price, 2),
                        'Exit': round(row['Close'] if exit_reason == "Time Exit (17:00 WAT)" else (stop_loss if exit_reason == "Stop Loss" else take_profit), 2),
                        'PnL_$': round(dollar_pnl, 2),
                        'Exit_Reason': exit_reason
                    })
                    
                    in_trade = False # Reset for next trade
                    
                    # HARD KILL SWITCH: Check daily drawdown
                    if current_daily_pnl <= -MAX_DAILY_LOSS_DOLLARS:
                        print(f"   ⚠️ KILL SWITCH ACTIVATED on {date}. Daily loss limit of ${MAX_DAILY_LOSS_DOLLARS} reached.")
                        break # Stop processing this day

    return pd.DataFrame(trades)

if __name__ == "__main__":
    try:
        # 1. Load Data
        df = load_and_prepare_data()
        
        # 2. Run Backtest
        results_df = run_orb_backtest(df)
        
        # 3. Analyze Results
        if results_df.empty:
            print("❌ No trades were generated. Check strategy parameters or data.")
        else:
            total_trades = len(results_df)
            winning_trades = len(results_df[results_df['PnL_$'] > 0])
            win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
            total_pnl = results_df['PnL_$'].sum()
            
            # Calculate Max Drawdown
            results_df['Cumulative_PnL'] = results_df['PnL_$'].cumsum()
            results_df['Peak_PnL'] = results_df['Cumulative_PnL'].cummax()
            results_df['Drawdown'] = results_df['Cumulative_PnL'] - results_df['Peak_PnL']
            max_drawdown = results_df['Drawdown'].min()
            
            print("\n" + "="*50)
            print("📊 BACKTEST RESULTS (Funding Pips $5K Rules)")
            print("="*50)
            print(f"Total Trades:      {total_trades}")
            print(f"Winning Trades:    {winning_trades}")
            print(f"Losing Trades:     {total_trades - winning_trades}")
            print(f"Win Rate:          {win_rate:.2f}%")
            print(f"Total Net PnL:     ${total_pnl:.2f}")
            print(f"Max Drawdown:      ${max_drawdown:.2f}")
            print(f"Average Win:       ${results_df[results_df['PnL_$'] > 0]['PnL_$'].mean():.2f}")
            print(f"Average Loss:      ${results_df[results_df['PnL_$'] < 0]['PnL_$'].mean():.2f}")
            print(f"Profit Factor:     {(results_df[results_df['PnL_$'] > 0]['PnL_$'].sum() / abs(results_df[results_df['PnL_$'] < 0]['PnL_$'].sum())):.2f}")
            print("="*50)
            
            # Save results to CSV for your own review
            results_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'backtest_results.csv')
            results_df.to_csv(results_file, index=False)
            print(f"💾 Detailed trade log saved to: {results_file}")
            
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        import traceback
        traceback.print_exc()