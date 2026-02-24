import yfinance as yf
import pandas as pd
import ta
import requests
import time
from dotenv import load_dotenv
import os

load_dotenv()

TELEGRAM_TOKEN = os.getenv("YOUR_BOT_TOKEN")
CHAT_ID = os.getenv("YOUR_CHAT_ID")


symbols = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "BTCUSD": "BTC-USD"
}

last_signal = {s: "HOLD" for s in symbols}


TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/"
offset = None
bot_running = False
def send_telegram(msg):
     requests.post(f"{TELEGRAM_URL}sendMessage", data={"chat_id": CHAT_ID, "text": msg})


def get_updates():
    global offset, bot_running
    url = f"{TELEGRAM_URL}getUpdates?timeout=10"
    if offset:
        url += f"&offset={offset}"

    res = requests.get(url).json()

    for update in res.get("result", []):
        offset = update["update_id"] + 1
        text = update["message"]["text"].lower()

        if text == "start":
            bot_running = True
            send_telegram("✅ ExpertOption bot STARTED")
        elif text == "stop":
            bot_running = False
            send_telegram("⏹ ExpertOption bot STOPPED")
        elif text == "status":
            state = "RUNNING" if bot_running else "STOPPED"
            send_telegram(f"📊 Bot status: {state}")
def get_data(symbol):
    df = yf.download(symbol, interval="5m", period="2d", progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(df["Close"], 14).rsi()

    # Alligator (proper version with shift)
    df["jaw"] = df["Close"].rolling(13).mean().shift(8)
    df["teeth"] = df["Close"].rolling(8).mean().shift(5)
    df["lips"] = df["Close"].rolling(5).mean().shift(3)

    # Stochastic
    stoch = ta.momentum.StochasticOscillator(df["High"], df["Low"], df["Close"])
    df["stoch"] = stoch.stoch()
    df["stoch_signal"] = stoch.stoch_signal()

    # MACD
    macd = ta.trend.MACD(df["Close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    df.dropna(inplace=True)
    return df

def analyze(pair, yf_symbol):
    df = get_data(yf_symbol)
    last = df.iloc[-1]

    price = float(last["Close"])
    rsi = float(last["rsi"])
    stoch = float(last["stoch"])
    jaw = float(last["jaw"])
    teeth = float(last["teeth"])
    lips = float(last["lips"])
    macd = float(last["macd"])
    macd_signal = float(last["macd_signal"])

    uptrend = price > lips > teeth > jaw
    downtrend = price < lips < teeth < jaw

    call_score = 0
    put_score = 0

    # Trend
    if uptrend:
        call_score += 1
    if downtrend:
        put_score += 1

    # RSI
    if rsi < 40:
        call_score += 1
    if rsi > 60:
        put_score += 1

    # Stochastic
    if stoch < 30:
        call_score += 1
    if stoch > 70:
        put_score += 1

    # MACD
    if macd > macd_signal:
        call_score += 1
    if macd < macd_signal:
        put_score += 1

    signal = "HOLD"
    strength = ""

    if call_score >= 2:
        signal = "BUY"
        if call_score == 4:
            strength = "STRONG"
        elif call_score == 3:
            strength = "MEDIUM"
        else:
            strength = "WEAK"

    elif put_score >= 2:
        signal = "SELL"
        if put_score == 4:
            strength = "STRONG"
        elif put_score == 3:
            strength = "MEDIUM"
        else:
            strength = "WEAK"

    if signal != "HOLD" and signal != last_signal[pair]:
        msg = (
            f"📊 ExpertOption Signal\n"
            f"Pair: {pair}\n"
            f"Price: {price:.5f}\n"
            # f"Indicators: RSI + ALLI + STO + MACD\n"
            f"Signal: {signal}\n"
            f"Strength: {strength}\n"
            f"Timeframe: 5M\n"
            # f"Expiry: 5 minutes"
        )
        send_telegram(msg)
        last_signal[pair] = signal
        
from datetime import datetime, timezone

def in_trading_session():
    now = datetime.now(timezone.utc).hour

    london_open = 7
    london_close = 16
    ny_open = 12
    ny_close = 21

    if (london_open <= now <= london_close) or (ny_open <= now <= ny_close):
        return True
    return False

send_telegram("🤖 ExpertOption bot is online. Send START to run.")

while True:
    get_updates()

    if bot_running:
        if in_trading_session():
            for pair, yf_symbol in symbols.items():
                analyze(pair, yf_symbol)
        else:
            send_telegram("⏰ Outside trading session. Bot waiting...")

    time.sleep(60)