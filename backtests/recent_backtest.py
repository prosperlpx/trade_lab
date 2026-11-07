import pandas as pd
import numpy as np
import os

# --- CONFIGURATION ---
DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'us100_5m.csv')

# 🎯 SET THIS TO THE DATE YOU WANT TO START TESTING FROM
START_DATE = '2026-10-28'

# Funding Pips $5K Account Risk Rules
ACCOUNT_SIZE = 5000.0
RISK_PER_TRADE_DOLLARS = 25.0      # 0.5% of account
MAX_DAILY_LOSS_DOLLARS = 100.0     # 2% of account (Hard kill switch)

def load_and_prepare_data():
    """Loads data, calculates daily VWAP/ATR, and filters for recent period"""
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(f"Data file not found at {DATA_FILE}. Run data_downloader.py first.")
    
    print(f"⏳ Loading and preparing data (Filtering from {START_DATE} onwards)...")
    
    # 1. Load CSV normally first
    df = pd.read_csv(DATA_FILE)
    
    # 2. Force pandas to parse the 'Datetime' column into real dates as UTC
    # This prevents the 'Index object has no attribute tz_convert' error
    df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
    
    # 3. Set it as the index
    df = df.set_index('Datetime')
    
    # 4. Convert UTC to WAT (Africa/Lagos)
    df.index = df.index.tz_convert('Africa/Lagos')
    
    df = df.sort_index()
    
    # Calculate Daily VWAP (Resets every day)
    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3.0
    df['TP_Vol'] = df['Typical_Price'] * df['Volume']
    daily_groups = df.groupby(df.index.date)
    df['Cumulative_TP_Vol'] = daily_groups['TP_Vol'].cumsum()
    df['Cumulative_Volume'] = daily_groups['Volume'].cumsum().replace(0, 1)
    df['VWAP'] = df['Cumulative_TP_Vol'] / df['Cumulative_Volume']
    
    # Calculate ATR (14-period) for dynamic Stop Losses
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    # Filter dataframe to only process recent data (but keep enough history for ATR/VWAP to be valid)
    filter_date = pd.to_datetime(START_DATE).date() - pd.Timedelta(days=2)
    df_recent = df[df.index.date >= filter_date].copy()
    
    print(f"✅ Data loaded: {len(df_recent)} recent candles from {df_recent.index[0]} to {df_recent.index[-1]} (WAT)")
    return df_recent

def run_recent_backtest(df):
    """Simulates the V4 VWAP Pullback strategy on recent data only"""
    print("⏳ Running Recent Backtest (V4 VWAP Pullback, ATR Stops, 1 Trade/Day)...")
    
    trades = []
    
    for date, daily_df in df.groupby(df.index.date):
        # Skip days before our target start date
        if str(date) < START_DATE:
            continue
            
        current_daily_pnl = 0.0
        in_trade = False
        trades_taken_today = 0
        MAX_TRADES_PER_DAY = 1 
        
        entry_price = 0.0
        stop_loss = 0.0
        take_profit = 0.0
        position_size = 0.0
        trade_direction = 0
        entry_time = None
        
        # Trading Window: 15:00 to 20:00 WAT (10 AM to 3 PM NY Time)
        trade_window = daily_df[(daily_df.index.hour >= 15) & (daily_df.index.hour < 20)]
        
        for index, row in trade_window.iterrows():
            if trades_taken_today >= MAX_TRADES_PER_DAY:
                break
            
            if pd.isna(row['ATR']) or row['ATR'] == 0:
                continue

            if not in_trade:
                # VWAP PULLBACK LONG: Price is above VWAP, but candle low dips to touch VWAP
                if row['Close'] > row['VWAP'] and row['Low'] <= row['VWAP'] * 1.001:
                    in_trade = True
                    entry_price = row['Close']
                    trade_direction = 1
                    entry_time = index
                    
                    risk_distance = 1.5 * row['ATR']
                    stop_loss = entry_price - risk_distance
                    take_profit = entry_price + (risk_distance * 1.5)
                    position_size = RISK_PER_TRADE_DOLLARS / risk_distance

                # VWAP PULLBACK SHORT: Price is below VWAP, but candle high spikes to touch VWAP
                elif row['Close'] < row['VWAP'] and row['High'] >= row['VWAP'] * 0.999:
                    in_trade = True
                    entry_price = row['Close']
                    trade_direction = -1
                    entry_time = index
                    
                    risk_distance = 1.5 * row['ATR']
                    stop_loss = entry_price + risk_distance
                    take_profit = entry_price - (risk_distance * 1.5)
                    position_size = RISK_PER_TRADE_DOLLARS / risk_distance
            else:
                pnl_points = 0.0
                exit_reason = ""
                
                if trade_direction == 1: # Long
                    if row['Low'] <= stop_loss:
                        pnl_points = stop_loss - entry_price
                        exit_reason = "ATR Stop Loss"
                    elif row['High'] >= take_profit:
                        pnl_points = take_profit - entry_price
                        exit_reason = "Take Profit"
                elif trade_direction == -1: # Short
                    if row['High'] >= stop_loss:
                        pnl_points = entry_price - stop_loss
                        exit_reason = "ATR Stop Loss"
                    elif row['Low'] <= take_profit:
                        pnl_points = entry_price - take_profit
                        exit_reason = "Take Profit"
                
                if exit_reason != "":
                    dollar_pnl = pnl_points * position_size
                    current_daily_pnl += dollar_pnl
                    
                    trades.append({
                        'Date': date,
                        'Entry_Time': entry_time.strftime('%Y-%m-%d %H:%M'),
                        'Exit_Time': index.strftime('%Y-%m-%d %H:%M'),
                        'Direction': 'Long' if trade_direction == 1 else 'Short',
                        'Entry': round(entry_price, 2),
                        'Exit': round(stop_loss if exit_reason == "ATR Stop Loss" else take_profit, 2),
                        'PnL_$': round(dollar_pnl, 2),
                        'Exit_Reason': exit_reason
                    })
                    
                    in_trade = False
                    trades_taken_today += 1
                    
                    if current_daily_pnl <= -MAX_DAILY_LOSS_DOLLARS:
                        print(f"   ⚠️ KILL SWITCH ACTIVATED on {date}.")
                        break

    return pd.DataFrame(trades)

if __name__ == "__main__":
    try:
        df = load_and_prepare_data()
        results_df = run_recent_backtest(df)
        
        if results_df.empty:
            print("❌ No trades were generated in this recent period.")
        else:
            total_trades = len(results_df)
            winning_trades = len(results_df[results_df['PnL_$'] > 0])
            win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
            total_pnl = results_df['PnL_$'].sum()
            
            results_df['Cumulative_PnL'] = results_df['PnL_$'].cumsum()
            results_df['Peak_PnL'] = results_df['Cumulative_PnL'].cummax()
            results_df['Drawdown'] = results_df['Cumulative_PnL'] - results_df['Peak_PnL']
            max_drawdown = results_df['Drawdown'].min()
            
            gross_profit = results_df[results_df['PnL_$'] > 0]['PnL_$'].sum()
            gross_loss = abs(results_df[results_df['PnL_$'] < 0]['PnL_$'].sum())
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
            
            print("\n" + "="*55)
            print(f"📊 RECENT BACKTEST RESULTS (From {START_DATE} Onwards)")
            print("="*55)
            print(f"Total Trades:      {total_trades}")
            print(f"Winning Trades:    {winning_trades}")
            print(f"Losing Trades:     {total_trades - winning_trades}")
            print(f"Win Rate:          {win_rate:.2f}%")
            print(f"Total Net PnL:     ${total_pnl:.2f}")
            print(f"Max Drawdown:      ${max_drawdown:.2f}")
            print(f"Average Win:       ${results_df[results_df['PnL_$'] > 0]['PnL_$'].mean():.2f}")
            print(f"Average Loss:      ${results_df[results_df['PnL_$'] < 0]['PnL_$'].mean():.2f}")
            print(f"Profit Factor:     {profit_factor:.2f}")
            print("="*55)
            
            results_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'recent_backtest_results.csv')
            results_df.to_csv(results_file, index=False)
            print(f"💾 Detailed trade log saved to: {results_file}")
            
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        import traceback
        traceback.print_exc()