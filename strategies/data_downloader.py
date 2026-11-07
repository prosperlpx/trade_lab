import yfinance as yf
import pandas as pd
import os
import warnings

# Suppress noisy warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*inplace.*")

# --- CONFIGURATION ---
# QQQ is the most reliable 5m ticker on yfinance.
TICKER = "QQQ"
TIMEFRAME = "5m"
# CRITICAL FIX: Yahoo Finance ONLY allows 5m data for the last 60 days.
PERIOD = "60d"

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
FILE_PATH = os.path.join(DATA_DIR, 'us100_5m.csv')

def download_us100_data():
    print(f"⏳ Downloading {PERIOD} of {TIMEFRAME} data for {TICKER}...")
    os.makedirs(DATA_DIR, exist_ok=True)
    
    try:
        # Download data
        df = yf.download(TICKER, period=PERIOD, interval=TIMEFRAME, progress=False)
        
        if df is None or df.empty:
            print("❌ Error: No data downloaded. Yahoo Finance may be rate-limiting. Try again in 10 minutes.")
            return
            
        # Clean up MultiIndex columns if yfinance adds them
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Reset index to make Datetime a standard column
        df = df.reset_index()
        
        # Drop any rows with missing data (NaNs) to ensure clean backtesting
        initial_rows = len(df)
        df = df.dropna()
        dropped_rows = initial_rows - len(df)
        if dropped_rows > 0:
            print(f"   -> Dropped {dropped_rows} rows with missing data.")
            
        # Save to CSV
        df.to_csv(FILE_PATH, index=False)
        print(f"✅ Success! Saved {len(df)} clean candles to {FILE_PATH}")
        print(f"\n📅 Data Range: {df['Datetime'].iloc[0]} to {df['Datetime'].iloc[-1]}")
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")

if __name__ == "__main__":
    download_us100_data()