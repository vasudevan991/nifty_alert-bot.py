import yfinance as yf
import pandas as pd
import requests
import time
import os
import mplfinance as mpf
from io import BytesIO
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

# === SETTINGS ===
TELEGRAM_TOKEN = '7511613332:AAGxdNIUsUFZL5JY5gAfL0aKeqqqD2Km8pY'
CHAT_ID = '383202961'
STOP_LOSS_PERCENT = 3
TARGET_PERCENT = 5

def send_telegram(message):
    if TELEGRAM_TOKEN is None or CHAT_ID is None:
        print("[ERROR] TELEGRAM_TOKEN or CHAT_ID not set in environment variables.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        print(f"[INFO] Sent: {message[:50]}...")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Telegram error: {e}")

def send_telegram_image(photo_buf, caption="Chart"):
    if TELEGRAM_TOKEN is None or CHAT_ID is None:
        print("[ERROR] TELEGRAM_TOKEN or CHAT_ID not set in environment variables.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    files = {"photo": photo_buf}
    data = {"chat_id": CHAT_ID, "caption": caption}
    try:
        response = requests.post(url, files=files, data=data)
        response.raise_for_status()
        print("[INFO] Chart sent to Telegram")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Telegram image error: {e}")

def safe_float(x):
    if hasattr(x, "item"):
        return float(x.item())
    try:
        return float(x)
    except Exception:
        return 0.0

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

def is_bearish_engulfing(prev, curr):
    prev_close = safe_float(prev['Close'])
    prev_open = safe_float(prev['Open'])
    curr_close = safe_float(curr['Close'])
    curr_open = safe_float(curr['Open'])
    return (
        prev_close > prev_open and
        curr_close < curr_open and
        curr_close < prev_open and
        curr_open > prev_close
    )

def is_shooting_star(candle):
    close = safe_float(candle['Close'])
    open_ = safe_float(candle['Open'])
    high = safe_float(candle['High'])
    low = safe_float(candle['Low'])
    body = abs(close - open_)
    upper_shadow = high - max(close, open_)
    lower_shadow = min(close, open_) - low
    return upper_shadow > 2 * body and lower_shadow < body

def is_evening_star(df):
    if len(df) < 3:
        return False
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    c1_close = safe_float(c1['Close'])
    c1_open = safe_float(c1['Open'])
    c2_close = safe_float(c2['Close'])
    c2_open = safe_float(c2['Open'])
    c3_close = safe_float(c3['Close'])
    c3_open = safe_float(c3['Open'])
    return (
        c1_close > c1_open and
        abs(c2_close - c2_open) < 0.3 * abs(c1_close - c1_open) and
        c3_close < c3_open and
        c3_close < ((c1_open + c1_close) / 2)
    )

def detect_chart_patterns(df):
    patterns = []
    recent = df[-20:]

    closes = pd.to_numeric(recent['Close'], errors='coerce')
    highs = pd.to_numeric(recent['High'], errors='coerce')
    lows = pd.to_numeric(recent['Low'], errors='coerce')

    resistance = closes.max()
    support = closes.min()

    if closes.iloc[-1] > resistance * 1.01:
        patterns.append("Price Breakout Above Resistance")
    if closes.iloc[-1] < support * 0.99:
        patterns.append("Price Breakdown Below Support")

    min_lows = lows.rolling(window=3).min()
    if not min_lows.empty:
        min_low = float(min_lows.min())
        last_low = float(lows.iloc[-1])
        last_high = float(highs.iloc[-1])
        if last_low > min_low * 1.02 and abs(float(highs.max()) - last_high) < 0.5:
            patterns.append("Ascending Triangle (Possible Breakout)")

    max_highs = highs.rolling(window=3).max()
    if not max_highs.empty:
        max_high = float(max_highs.max())
        last_high = float(highs.iloc[-1])
        last_low = float(lows.iloc[-1])
        if last_high < max_high * 0.98 and abs(float(lows.min()) - last_low) < 0.5:
            patterns.append("Descending Triangle (Possible Breakdown)")

    return patterns

def generate_candlestick_chart(df, stock):
    df_plot = df.copy().tail(60)
    df_plot.index = pd.to_datetime(df_plot.index)
    columns = ['Open', 'High', 'Low', 'Close']
    for col in ['SMA50', 'SMA200']:
        if col in df_plot.columns:
            columns.append(col)
    df_plot = df_plot[columns]
    mav = tuple([int(c[3:]) for c in columns if c.startswith('SMA')])
    buf = BytesIO()
    mpf.plot(
        df_plot,
        type='candle',
        mav=mav if mav else None,
        volume=False,
        title=f"{stock} Candlestick Chart (Last 60 days)",
        ylabel='Price (₹)',
        style='yahoo',
        savefig=dict(fname=buf, dpi=150, format='png'),
    )
    buf.seek(0)
    return buf

def read_tickers_from_csv(files):
    tickers = set()
    for file in files:
        if os.path.exists(file):
            df = pd.read_csv(file)
            tickers.update(df['Ticker'].dropna().astype(str).str.strip())
        else:
            print(f"[WARN] File not found: {file}")
    return sorted(tickers)

def get_signals(stock):
    try:
        df = yf.download(stock + ".NS", period='300d', interval='1d', auto_adjust=True, progress=False)
    except Exception as e:
        print(f"[WARN] Download error for {stock}: {e}")
        return None

    if df.empty or len(df) < 100:
        return None

    # --- Robust column handling ---
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ['_'.join(map(str, filter(None, col))).strip('_') for col in df.columns.values]
    else:
        df.columns = [str(col) for col in df.columns]

    # Map columns like 'Open_INFY.NS' to 'Open', etc.
    base_names = ['Open', 'High', 'Low', 'Close']
    mapped_cols = {}
    for base in base_names:
        for col in df.columns:
            if col.lower().startswith(base.lower()):
                mapped_cols[col] = base
    df.rename(columns=mapped_cols, inplace=True)

    for col in base_names:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            print(f"[WARN] Column '{col}' not found in DataFrame for {stock}. Filling with NaN.")
            df[col] = pd.Series([float('nan')] * len(df), index=df.index)

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
    bearish_patterns = []

    if safe_float(latest['MACD']) > safe_float(latest['Signal']) and safe_float(prev['MACD']) < safe_float(prev['Signal']):
        indicators.append("MACD Bullish Crossover")
    if safe_float(latest['SMA50']) > safe_float(latest['SMA100']) and safe_float(prev['SMA50']) <= safe_float(prev['SMA100']):
        indicators.append("SMA50 crossed above SMA100")
    if safe_float(latest['SMA50']) > safe_float(latest['SMA200']) and safe_float(prev['SMA50']) <= safe_float(prev['SMA200']):
        indicators.append("SMA50 Golden Cross over SMA200")
    if rsi < 30:
        indicators.append(f"RSI Oversold ({rsi:.1f})")

    if safe_float(latest['MACD']) < safe_float(latest['Signal']) and safe_float(prev['MACD']) > safe_float(prev['Signal']):
        bearish_patterns.append("MACD Bearish Crossover")
    if rsi > 70:
        bearish_patterns.append(f"RSI Overbought ({rsi:.1f})")

    if is_bearish_engulfing(prev, latest):
        bearish_patterns.append("Bearish Engulfing Pattern")
    if is_shooting_star(latest):
        bearish_patterns.append("Shooting Star Pattern")
    if is_evening_star(df):
        bearish_patterns.append("Evening Star Pattern")

    chart_patterns = detect_chart_patterns(df)

    pivot, s1, s2, r1, r2 = calculate_pivot_support_resistance(df)
    support_resist = []
    if close < s1:
        support_resist.append(f"Price below Support 1 (S1={s1:.2f})")
    elif close > r1:
        support_resist.append(f"Price above Resistance 1 (R1={r1:.2f})")

    should_trigger = len(indicators) >= 2 or len(bearish_patterns) > 0 or len(chart_patterns) > 0
    if not should_trigger:
        return None

    msg = f"[ALERT] {stock} Signal:\n"
    if indicators:
        msg += "\n" + "\n".join(["[BULL] " + x for x in indicators]) + "\n"
    if bearish_patterns:
        msg += "\n" + "\n".join(["[BEAR] " + x for x in bearish_patterns]) + "\n"
    if chart_patterns:
        msg += "\n" + "\n".join(["[CHART] " + x for x in chart_patterns]) + "\n"
    if support_resist:
        msg += "\n" + "\n".join(support_resist) + "\n"

    msg += (
        f"\nClose: ₹{close:.2f} | RSI: {rsi:.1f}\n"
        f"Pivot: ₹{pivot:.2f} | S1: ₹{s1:.2f} | S2: ₹{s2:.2f} | R1: ₹{r1:.2f} | R2: ₹{r2:.2f}"
    )

    if len(indicators) >= 2:
        entry = close
        stop = entry * (1 - STOP_LOSS_PERCENT / 100)
        target = entry * (1 + TARGET_PERCENT / 100)
        msg += f"\nTarget: ₹{target:.2f} | Stop Loss: ₹{stop:.2f}"

    return msg, df

if __name__ == "__main__":
    # Update: Process all stocks from the CSV files
    ticker_files = ["nifty50.csv", "nifty_next_50.csv", "midcap.csv"]
    tickers = read_tickers_from_csv(ticker_files)
    print(f"[INFO] Total tickers loaded: {len(tickers)}")
    for stock in tickers:
        print(f"\n[RUNNING] Checking {stock}...")
        result = get_signals(stock)
        if result:
            message, df = result
            print(message)
            send_telegram(message)
            try:
                chart_buf = generate_candlestick_chart(df, stock)
                send_telegram_image(chart_buf, caption=f"{stock} Chart")
            except Exception as e:
                print(f"[ERROR] Error generating/sending chart for {stock}: {e}")
        else:
            print(f"[INFO] No signal triggered for {stock}.")
