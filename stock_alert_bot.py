import yfinance as yf
import pandas as pd
import requests

# ============ TELEGRAM SETTINGS ============
TELEGRAM_TOKEN = 'YOUR_BOT_TOKEN'  # Replace with your bot token
CHAT_ID = 'YOUR_CHAT_ID'           # Replace with your chat ID

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=data)

# ============ SUPPORT & RESISTANCE ============
def detect_support_resistance(df, window=10):
    support_levels = []
    resistance_levels = []
    for i in range(window, len(df) - window):
        is_support = all(df['Low'][i] < df['Low'][i - j] and df['Low'][i] < df['Low'][i + j] for j in range(1, window))
        is_resistance = all(df['High'][i] > df['High'][i - j] and df['High'][i] > df['High'][i + j] for j in range(1, window))
        if is_support:
            support_levels.append(df['Low'][i])
        if is_resistance:
            resistance_levels.append(df['High'][i])
    return support_levels[-1] if support_levels else None, resistance_levels[-1] if resistance_levels else None

# ============ MAIN SIGNAL FUNCTION ============
def get_signals(stock):
    df = yf.download(stock + ".NS", period='120d', interval='1d', auto_adjust=True)
    if df.empty or len(df) < 100:
        return None

    # Technical Indicators
    df['SMA50'] = df['Close'].rolling(50).mean()
    df['SMA100'] = df['Close'].rolling(100).mean()
    df['SMA200'] = df['Close'].rolling(200).mean()

    # RSI
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()

    # Volume filter
    df['AvgVol20'] = df['Volume'].rolling(20).mean()

    # ATR
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

    # === Trading Signals ===
    if latest['MACD'] > latest['Signal'] and prev['MACD'] < prev['Signal']:
        alerts.append("📊 MACD Bullish Crossover")

    if latest['RSI'] < 30:
        alerts.append("📉 RSI Oversold (<30)")
    elif latest['RSI'] > 30 and prev['RSI'] < 30:
        alerts.append("📈 RSI Reversal (>30)")

    if latest['SMA50'] > latest['SMA100'] and prev['SMA50'] <= prev['SMA100']:
        alerts.append("📘 SMA50 crossed above SMA100")

    if latest['SMA50'] > latest['SMA200'] and prev['SMA50'] <= prev['SMA200']:
        alerts.append("🟢 SMA50 Golden Cross over SMA200")

    if latest['Volume'] > 1.5 * latest['AvgVol20']:
        alerts.append(f"🔊 Volume Surge ({int(latest['Volume'])} > 1.5× avg)")

    # === Support / Resistance ===
    support, resistance = detect_support_resistance(df)
    if support is not None and latest['Close'] <= support * 1.03:
        alerts.append(f"🛡️ Near Support ₹{support:.2f}")
    if resistance is not None and latest['Close'] > resistance:
        alerts.append(f"🚀 Resistance Breakout ₹{resistance:.2f}")

    # === ATR-Based Target & Stop Loss ===
    atr = latest['ATR']
    close = latest['Close']
    if pd.notnull(atr):
        stop_loss = close - atr
        target = close + 2 * atr
        alerts.append(f"🎯 Target: ₹{target:.2f} | 🛑 SL: ₹{stop_loss:.2f}")

    if alerts:
        return f"📈 {stock} Alert:\n" + "\n".join(alerts)
    return None

# ============ STOCK LIST ============
stocks = ['TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'RELIANCE', 'AXISBANK', 'SBIN', 'LT', 'ITC']

any_signal = False

for stock in stocks:
    signal = get_signals(stock)
    if signal:
        print(signal)
        send_telegram(signal)
        any_signal = True

# ✅ Final message to confirm script worked
if any_signal:
    send_telegram("✅ Stock scan complete. Alerts sent.")
else:
    send_telegram("ℹ️ Stock scan complete. No signals found today.")
