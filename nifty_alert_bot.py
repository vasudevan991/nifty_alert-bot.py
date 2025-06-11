import yfinance as yf
import pandas as pd
import requests
import time
import traceback

# ============ TELEGRAM SETTINGS ============
TELEGRAM_TOKEN = '7511613332:AAGxdNIUsUFZL5JY5gAfL0aKeqqqD2Km8pY'
CHAT_ID = '383202961'

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        print(f"✅ Message sent to Telegram: {message[:50]}...")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send Telegram message: {e}")

# ============ SUPPORT & RESISTANCE ============
def detect_support_resistance(df, window=10):
    support_levels = []
    resistance_levels = []
    for i in range(window, len(df) - window):
        is_support = all(df['Low'].iloc[i] < df['Low'].iloc[i - j] and df['Low'].iloc[i] < df['Low'].iloc[i + j] for j in range(1, window))
        is_resistance = all(df['High'].iloc[i] > df['High'].iloc[i - j] and df['High'].iloc[i] > df['High'].iloc[i + j] for j in range(1, window))
        if is_support:
            support_levels.append(df['Low'].iloc[i])
        if is_resistance:
            resistance_levels.append(df['High'].iloc[i])
    return support_levels[-1] if support_levels else None, resistance_levels[-1] if resistance_levels else None

# ============ SIGNAL GENERATION ============
def get_signals(stock):
    try:
        df = yf.download(stock + ".NS", period='120d', interval='1d', auto_adjust=True, progress=False)
    except Exception as e:
        print(f"⚠️ Failed to download data for {stock}: {type(e).__name__} - {e}")
        return None

    if df.empty or len(df) < 100:
        print(f"⚠️ Dropped too much data for {stock}")
        return None

    df['SMA50'] = df['Close'].rolling(50).mean()
    df['SMA100'] = df['Close'].rolling(100).mean()
    df['SMA200'] = df['Close'].rolling(200).mean()

    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()

    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(14).mean()

    df = df.dropna().copy()
    if df.empty or len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    alerts = []

    print(f"🔎 {stock} | Close: {latest['Close']:.2f}, MACD: {latest['MACD']:.2f}, Signal: {latest['Signal']:.2f}")

    if latest['MACD'] > latest['Signal'] and prev['MACD'] < prev['Signal']:
        alerts.append("📊 MACD Bullish Crossover")

    if latest['SMA50'] > latest['SMA100'] and prev['SMA50'] <= prev['SMA100']:
        alerts.append("📘 SMA50 crossed above SMA100")

    if latest['SMA50'] > latest['SMA200'] and prev['SMA50'] <= prev['SMA200']:
        alerts.append("🟢 SMA50 Golden Cross over SMA200")

    support, resistance = detect_support_resistance(df)
    if support is not None and latest['Close'] <= support * 1.03:
        alerts.append(f"🛡️ Near Support ₹{support:.2f}")
    if resistance is not None and latest['Close'] > resistance:
        alerts.append(f"🚀 Resistance Breakout ₹{resistance:.2f}")

    atr = latest['ATR']
    close = latest['Close']
    if pd.notnull(atr):
        stop_loss = close - atr
        target = close + 2 * atr
        alerts.append(f"🎯 Target: ₹{target:.2f} | 🚑 SL: ₹{stop_loss:.2f}")

    if alerts:
        return f"📈 {stock} Alert:\n" + "\n".join(alerts)

    # Test fallback if no alert
    return f"📢 TEST ALERT for {stock} (No real signal, just a test)"

# ============ MAIN EXECUTION ============
if __name__ == "__main__":
    all_stocks = ['TCS', 'INFY', 'RELIANCE', 'ICICIBANK', 'SBIN', 'AXISBANK']

    print(f"\n🔍 Scanning {len(all_stocks)} stocks...\n")

    for stock in all_stocks:
        try:
            signal = get_signals(stock)
            if signal:
                print(signal)
                send_telegram(signal)
                print(f"📤 Alert sent to Telegram for {stock}")
            time.sleep(1.5)
        except Exception as e:
            print(f"⚠️ Error processing {stock}: {type(e).__name__} - {e}")
            traceback.print_exc()
