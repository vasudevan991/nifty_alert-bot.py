import yfinance as yf
import pandas as pd
import requests
import time

# ============ TELEGRAM SETTINGS ============
TELEGRAM_TOKEN = '7511613332:AAGxdNIUsUFZL5JY5gAfL0aKeqqqD2Km8pY'
CHAT_ID = '383202961'

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}

    try:
        response = requests.post(url, data=data)
        response.raise_for_status()  # Raises error if response code is 4xx or 5xx
        print(f"✅ Message sent to Telegram: {message[:50]}...")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send Telegram message: {e}")


# ============ LOAD INDEX STOCKS FROM CSV ============
def get_index_stocks():
    files = ['nifty50.csv', 'niftynext50.csv', 'midcap100.csv']
    all_stocks = []

    for file in files:
        try:
            df = pd.read_csv(file)
            if 'Symbol' in df.columns:
                symbols = df['Symbol'].dropna().astype(str)
                symbols = symbols[symbols.str.isalpha()]
                all_stocks.extend(symbols.tolist())
            else:
                print(f"⚠️ Column 'Symbol' not found in {file}")
        except Exception as e:
            print(f"⚠️ Error loading {file}: {e}")
    return list(set(all_stocks))

# ============ CHECK IF STOCK IS VALID ============
def is_valid_stock(stock):
    try:
        df = yf.download(stock + ".NS", period="5d", interval="1d", progress=False)
        return not df.empty
    except:
        return False

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
    try:
        df = yf.download(stock + ".NS", period='120d', interval='1d', auto_adjust=True, progress=False)
    except Exception as e:
        print(f"⚠️ Failed to download data for {stock}: {e}")
        return None

    if df.empty or len(df) < 100:
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
    df['AvgVol20'] = df['Volume'].rolling(20).mean()

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
        alerts.append(f"🎯 Target: ₹{target:.2f} | 🛑 SL: ₹{stop_loss:.2f}")

    if alerts:
        return f"📈 {stock} Alert:\n" + "\n".join(alerts)
    return None

# ============ MAIN EXECUTION ============
if __name__ == "__main__":
    all_stocks = get_index_stocks()

    print(f"\n🔍 Validating {len(all_stocks)} stock symbols...\n")
    valid_stocks = []

    for stock in all_stocks:
        if is_valid_stock(stock):
            valid_stocks.append(stock)
        else:
            print(f"❌ Skipping invalid/delisted symbol: {stock}")
        time.sleep(0.5)

    print(f"\n✅ {len(valid_stocks)} valid stocks found. Running alerts...\n")

    for stock in valid_stocks:
        try:
            signal = get_signals(stock)
            if signal:
                print(signal)
                try:
                    send_telegram(signal)
                    print(f"📤 Alert sent to Telegram for {stock}")
                except Exception as e:
                    print(f"❌ Telegram error for {stock}: {e}")
            time.sleep(1.5)
        except Exception as e:
            print(f"⚠️ Error processing {stock}: {e}")
