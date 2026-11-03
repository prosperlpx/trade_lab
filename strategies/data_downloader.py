import yfinance as yf
import pandas as pd
import os
import warnings

# Suppress the noisy Pandas/yfinance deprecation warnings so we only see real errors
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*inplace.*")

# --- CONFIGURATION ---
# We try NQ=F (Nasdaq 100 Futures) first, as it's the most direct proxy for US100.
# If Yahoo blocks it, we fall back to QQQ (Invesco QQQ Trust ETF).
TICKERS_TO_TRY = ["NQ=F", "QQQ"]
TIMEFRAME = "5m"
PERIOD = "1mo" # 1 month is the most reliable period for 5m data on yfinance

# Define the path to save our data
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
FILE_PATH = os.path.join(DATA_DIR, 'us100_5m.csv')

def download_us100_data():
    print(f"⏳ Attempting to download {TIMEFRAME} data for the last {PERIOD}...")
    
    # Ensure the data folder exists
    os.makedirs(DATA_DIR, exist_ok=True)

    for ticker in TICKERS_TO_TRY:
        print(f"   -> Trying ticker: {ticker}")
        try:
            # Download the data
            df = yf.download(ticker, period=PERIOD, interval=TIMEFRAME, progress=False)
            
            # Check if we got data
            if df is not None and not df.empty:
                print(f"✅ Success! Downloaded data using ticker: {ticker}")
                
                # Clean up the data: yfinance sometimes creates a MultiIndex for columns
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                # Reset index to make 'Date' a standard column
                df = df.reset_index()
                
                # Drop any rows with missing data (NaNs) to ensure clean backtesting
                df = df.dropna()
                
                # Save to CSV
                df.to_csv(FILE_PATH, index=False)
                print(f"💾 Saved {len(df)} clean candles to {FILE_PATH}")
                
                print("\n--- First 3 Rows of Data ---")
                print(df.head(3))
                return # Success! Exit the function
                
        except Exception as e:
            print(f"   -> Failed with {ticker}: {e}")
            continue
            
    # If the loop finishes without returning, all tickers failed
    print("\n❌ CRITICAL ERROR: No data downloaded from any ticker.")
    print("Please check your internet connection or try running this again later.")

if __name__ == "__main__":
    download_us100_data()