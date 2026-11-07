import yfinance as yf
import pandas as pd
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

print("⏳ Downloading 20+ years of daily Nasdaq 100 Futures (NQ=F) data...")

# Fetch max available daily data for Nasdaq 100 Futures
ticker = yf.Ticker("NQ=F")
df = ticker.history(period="max")

if df.empty:
    print("❌ Failed to download data. Check your internet connection.")
else:
    print(f"✅ Data loaded: {len(df)} daily candles from {df.index[0].date()} to {df.index[-1].date()}")
    
    # Calculate Daily True Range (Volatility proxy)
    df['High_Low'] = df['High'] - df['Low']
    df['High_Close'] = (df['High'] - df['Close'].shift(1)).abs()
    df['Low_Close'] = (df['Low'] - df['Close'].shift(1)).abs()
    df['True_Range'] = df[['High_Low', 'High_Close', 'Low_Close']].max(axis=1)
    
    # Extract Month Name and Year
    df['Month_Name'] = df.index.month_name()
    df['Year'] = df.index.year
    
    # Filter out incomplete current month and very old sparse data (pre-2005)
    df = df[df['Year'] >= 2005]
    
    # Group by Month to find averages
    monthly_stats = df.groupby('Month_Name').agg(
        Avg_Volume=('Volume', 'mean'),
        Avg_True_Range=('True_Range', 'mean'),
        Total_Days=('True_Range', 'count')
    ).round(2)
    
    # Sort by Volatility (Avg True Range) to see which months move the most
    volatility_ranked = monthly_stats.sort_values(by='Avg_True_Range', ascending=False)
    volume_ranked = monthly_stats.sort_values(by='Avg_Volume', ascending=False)

    print("\n" + "="*70)
    print("📊 NASDAQ 100 MONTHLY SEASONALITY (2005 - Present)")
    print("="*70)
    
    print("\n🔥 HIGHEST VOLATILITY MONTHS (Best for Breakouts/Pullbacks):")
    print(volatility_ranked[['Avg_True_Range', 'Total_Days']].to_string())
    
    print("\n🥱 LOWEST VOLATILITY MONTHS (Choppy, Low Volume, Dangerous):")
    print(volatility_ranked[['Avg_True_Range', 'Total_Days']].tail(3).to_string())
    
    print("\n" + "="*70)
    print("💡 MANAGER'S TAKEAWAY:")
    print("If a month is in the bottom 3 for volatility, expect fewer valid")
    print("VWAP setups, more fake-outs, and slower price action.")
    print("="*70)