import yfinance as yf
import pandas as pd
import requests
import time
import os

# === TELEGRAM SETTINGS ===
TELEGRAM_TOKEN = '7511613332:AAGxdNIUsUFZL5JY5gAfL0aKeqqqD2Km8pY'
CHAT_ID = '383202961'

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        print(f"\u2705 Sent: {message[:50]}...")
    except requests.exceptions.RequestException as e:
        print(f"❌ Telegram error: {e}")

def safe_float(x):
    """Converts a pandas value to float, handling future deprecation warnings."""
    return float(x.item()) if hasattr(x, "item") else float(x)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_pivot_support_resistance(df):
    # Uses the previous day's data for calculation
    prev = df.iloc[-2]
    high = safe_float(prev['High'])
    low = safe_float(prev['Low'])
    close = safe_float(prev['Close'])
    pivot = (high + low + close) / 3
    s1 = 2 * pivot - high
    s2 = pivot - (high - low)
    r1 = 2 * pivot - low
    r2 = pivot + (high - low)
    return pivot, s1, s2, r1, r2

# === SIGNAL FUNCTION ===
def get_signals(stock):
    try:
        df = yf.download(stock + ".NS", period='300d', interval='1d', auto_adjust=True, progress=False)
    except Exception as e:
        print(f"⚠️ Download error for {stock}: {e}")
        return None

    if df.empty or len(df) < 100:
        print(f"⚠️ Dropped too much data for {stock}")
        return None

    df['SMA50'] = df['Close'].rolling(50).mean()
    df['SMA100'] = df['Close'].rolling(100).mean()
    df['SMA200'] = df['Close'].rolling(200).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['RSI'] = calculate_rsi(df['Close'])

    df = df.dropna()
    if df.empty or len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    alerts = []

    # --- MAIN SIGNALS ---
    if safe_float(latest['MACD']) > safe_float(latest['Signal']) and safe_float(prev['MACD']) < safe_float(prev['Signal']):
        alerts.append("📊 MACD Bullish Crossover")
    if safe_float(latest['SMA50']) > safe_float(latest['SMA100']) and safe_float(prev['SMA50']) <= safe_float(prev['SMA100']):
        alerts.append("📘 SMA50 crossed above SMA100")
    if safe_float(latest['SMA50']) > safe_float(latest['SMA200']) and safe_float(prev['SMA50']) <= safe_float(prev['SMA200']):
        alerts.append("🟢 SMA50 Golden Cross over SMA200")

    # --- RSI SIGNALS ---
    rsi = safe_float(latest['RSI'])
    if rsi > 70:
        alerts.append(f"🔴 RSI Overbought ({rsi:.1f})")
    elif rsi < 30:
        alerts.append(f"🟢 RSI Oversold ({rsi:.1f})")

    # --- PIVOT, SUPPORT, RESISTANCE ---
    pivot, s1, s2, r1, r2 = calculate_pivot_support_resistance(df)
    close = safe_float(latest['Close'])
    # You can adjust the logic for these signals as you like:
    if close < s1:
        alerts.append(f"⚠️ Price below Support 1 (S1={s1:.2f})")
    elif close > r1:
        alerts.append(f"⚠️ Price above Resistance 1 (R1={r1:.2f})")

    # --- FINAL ALERT MESSAGE ---
    if alerts:
        msg = (f"📈 {stock} Alert:\n" +
               "\n".join(alerts) +
               f"\nClose: {close:.2f} | RSI: {rsi:.1f}\n"
               f"Pivot: {pivot:.2f} | S1: {s1:.2f} | S2: {s2:.2f} | R1: {r1:.2f} | R2: {r2:.2f}")
        return msg
    return None

def read_tickers_from_csv(files):
    tickers = set()
    for file in files:
        if os.path.exists(file):
            df = pd.read_csv(file)
            tickers.update(df['Ticker'].dropna().astype(str).str.strip())
        else:
            print(f"⚠️ File not found: {file}")
    return sorted(tickers)

# === MAIN ===
if __name__ == "__main__":
    csv_files = ["nifty50.csv", "niftynext50.csv", "niftymidcap500.csv"]
    stocks = read_tickers_from_csv(csv_files)
    print(f"\n🔍 Scanning {len(stocks)} stocks...\n")
    for stock in stocks:
        print(f"🕵️ {stock}")
        try:
            signal = get_signals(stock)
            if signal:
                print(signal)
                send_telegram(signal)
            time.sleep(1)  # Avoid hitting Yahoo's rate limit
        except Exception as e:
            print(f"⚠️ Error processing {stock}: {e}")
