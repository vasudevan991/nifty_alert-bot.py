import yfinance as yf
import pandas as pd
import requests
import time
import os

# === SETTINGS ===
TELEGRAM_TOKEN = '7511613332:AAGxdNIUsUFZL5JY5gAfL0aKeqqqD2Km8pY'
CHAT_ID = '383202961'
STOP_LOSS_PERCENT = 3
TARGET_PERCENT = 5

# === TELEGRAM FUNCTION ===
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        print(f"✅ Sent: {message[:50]}...")
    except requests.exceptions.RequestException as e:
        print(f"❌ Telegram error: {e}")

# === HELPER FUNCTIONS ===
def safe_float(x):
    return float(x.item()) if hasattr(x, "item") else float(x)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_pivot_support_resistance(df):
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

# === CANDLESTICK PATTERNS ===
def is_bullish_engulfing(prev, curr):
    try:
        return (
            prev['Close'] < prev['Open'] and
            curr['Close'] > curr['Open'] and
            curr['Close'] > prev['Open'] and
            curr['Open'] < prev['Close']
        )
    except:
        return False

def is_hammer(candle):
    try:
        body = abs(candle['Close'] - candle['Open'])
        lower_shadow = min(candle['Close'], candle['Open']) - candle['Low']
        upper_shadow = candle['High'] - max(candle['Close'], candle['Open'])
        return lower_shadow > 2 * body and upper_shadow < body
    except:
        return False

def is_morning_star(df):
    try:
        if len(df) < 3:
            return False
        c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        return (
            c1['Close'] < c1['Open'] and
            abs(c2['Close'] - c2['Open']) < 0.3 * abs(c1['Open'] - c1['Close']) and
            c3['Close'] > c3['Open'] and
            c3['Close'] > ((c1['Open'] + c1['Close']) / 2)
        )
    except:
        return False

# === SIGNAL FUNCTION ===
def get_signals(stock):
    try:
        df = yf.download(stock + ".NS", period='300d', interval='1d', auto_adjust=True, progress=False)
    except Exception as e:
        print(f"⚠️ Download error for {stock}: {e}")
        return None

    if df.empty or len(df) < 100:
        return None

    df['SMA50'] = df['Close'].rolling(50).mean()
    df['SMA100'] = df['Close'].rolling(100).mean()
    df['SMA200'] = df['Close'].rolling(200).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['RSI'] = calculate_rsi(df['Close'])

    df = df.dropna()
    if len(df) < 3:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = safe_float(latest['Close'])
    rsi = safe_float(latest['RSI'])

    indicators = []
    patterns = []

    # === INDICATORS ===
    if safe_float(latest['MACD']) > safe_float(latest['Signal']) and safe_float(prev['MACD']) < safe_float(prev['Signal']):
        indicators.append("📊 MACD Bullish Crossover")
    if safe_float(latest['SMA50']) > safe_float(latest['SMA100']) and safe_float(prev['SMA50']) <= safe_float(prev['SMA100']):
        indicators.append("📘 SMA50 crossed above SMA100")
    if safe_float(latest['SMA50']) > safe_float(latest['SMA200']) and safe_float(prev['SMA50']) <= safe_float(prev['SMA200']):
        indicators.append("🟢 SMA50 Golden Cross over SMA200")
    if rsi < 30:
        indicators.append(f"🟢 RSI Oversold ({rsi:.1f})")
    elif rsi > 70:
        indicators.append(f"🔴 RSI Overbought ({rsi:.1f})")

    # === CANDLESTICK PATTERNS ===
    try:
        if is_bullish_engulfing(prev, latest):
            patterns.append("🕯️ Bullish Engulfing Pattern")
        if is_hammer(latest):
            patterns.append("🔨 Hammer Pattern")
        if is_morning_star(df):
            patterns.append("🌟 Morning Star Pattern")
    except Exception as e:
        print(f"⚠️ Pattern detection error for {stock}: {e}")

    # === PIVOT POINTS ===
    pivot, s1, s2, r1, r2 = calculate_pivot_support_resistance(df)
    support_resist = []
    if close < s1:
        support_resist.append(f"⚠️ Price below Support 1 (S1={s1:.2f})")
    elif close > r1:
        support_resist.append(f"⚠️ Price above Resistance 1 (R1={r1:.2f})")

    # === ALERT TRIGGER LOGIC ===
    should_trigger = len(indicators) >= 2 or len(patterns) > 0
    if not should_trigger:
        return None

    # === BUILD MESSAGE ===
    msg = f"📈 {stock} Alert:\n"
    if indicators:
        msg += "\n".join(indicators) + "\n"
    if patterns:
        msg += "\n" + "\n".join(patterns) + "\n"
    if support_resist:
        msg += "\n" + "\n".join(support_resist) + "\n"

    msg += (
        f"\nClose: ₹{close:.2f} | RSI: {rsi:.1f}\n"
        f"Pivot: ₹{pivot:.2f} | S1: ₹{s1:.2f} | S2: ₹{s2:.2f} | R1: ₹{r1:.2f} | R2: ₹{r2:.2f}"
    )

    # === STOP LOSS / TARGET (only if indicator triggered) ===
    if len(indicators) >= 2:
        entry = close
        stop = entry * (1 - STOP_LOSS_PERCENT / 100)
        target = entry * (1 + TARGET_PERCENT / 100)
        msg += f"\n🎯 Target: ₹{target:.2f} | 🔻 Stop Loss: ₹{stop:.2f}"

    return msg

# === READ STOCK LIST FROM CSV ===
def read_tickers_from_csv(files):
    tickers = set()
    for file in files:
        if os.path.exists(file):
            df = pd.read_csv(file)
            tickers.update(df['Ticker'].dropna().astype(str).str.strip())
        else:
            print(f"⚠️ File not found: {file}")
    return sorted(tickers)

# === MAIN EXECUTION ===
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
            time.sleep(1)  # Prevent rate-limit block
        except Exception as e:
            print(f"⚠️ Error processing {stock}: {e}")
