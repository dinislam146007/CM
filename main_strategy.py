import logging

import ccxt.async_support as ccxt
import pandas as pd
from aiogram.enums import ParseMode
from scipy.stats import percentileofscore
import asyncio
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.bot import DefaultBotProperties
from aiogram import Bot
from strategy_logic.get_all_coins import get_usdt_pairs
from config import config
# from db import *
import datetime
from strategy_logic.rsi import *
from strategy_logic.vsa import *
from strategy_logic.price_action import get_pattern_price_action
from deepseek.deepsekk import analyze_trading_signals
from config import config
from strategy_logic.stop_loss import *
from strategy_logic.moon_bot_strategy import StrategyMoonBot, load_strategy_params,Context
moon = StrategyMoonBot(load_strategy_params())
from db.orders import *


bot = Bot(token=config.tg_bot_token, default=DefaultBotProperties(parse_mode="HTML"))

"""Параметры стратегии"""
SHORT_GAMMA = 0.4
LONG_GAMMA = 0.8
LOOKBACK_T = 21
LOOKBACK_B = 15
PCTILE = 90

# Параметры RSI дивергенции
RSI_LENGTH = 7
LB_RIGHT = 3
LB_LEFT = 3
RANGE_UPPER = 60
RANGE_LOWER = 5
TAKE_PROFIT_RSI_LEVEL = 80

# Параметры стоп-лосса
STOP_LOSS_TYPE = "PERC"  # "ATR", "PERC", "NONE"
STOP_LOSS_PERC = 5.0  # Процент для стоп-лосса
ATR_LENGTH = 14  # Период ATR
ATR_MULTIPLIER = 3.5  # Множитель ATR

exchange = ccxt.bybit()  # Передаём сессию в CCXT


# timeframes = ['1d', '4h', '1h', '30m']
timeframes = ['1d',]


symbols = get_usdt_pairs()

async def fetch_ohlcv(symbol, timeframe='1h', limit=500, retries=3, delay=5):
    """Получение свечных данных с повторными попытками в случае тайм-аута."""
    for attempt in range(retries):
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['hl2'] = (df['high'] + df['low']) / 2  # Средняя цена свечи
            return df
        except ccxt.RequestTimeout:
            print(f"Timeout fetching {symbol} {timeframe}, retrying {attempt + 1}/{retries}...")
            await asyncio.sleep(delay)  # Wait before retrying
    print(f"Failed to fetch {symbol} {timeframe} after {retries} attempts.")
    return None


def laguerre_filter(series, gamma):
    """Laguerre-фильтр."""
    L0, L1, L2, L3, f = np.zeros_like(series), np.zeros_like(series), np.zeros_like(series), np.zeros_like(series), np.zeros_like(series)

    for i in range(1, len(series)):
        L0[i] = (1 - gamma) * series[i] + gamma * L0[i - 1]
        L1[i] = -gamma * L0[i] + L0[i - 1] + gamma * L1[i - 1]
        L2[i] = -gamma * L1[i] + L1[i - 1] + gamma * L2[i - 1]
        L3[i] = -gamma * L2[i] + L2[i - 1] + gamma * L3[i - 1]
        f[i] = (L0[i] + 2 * L1[i] + 2 * L2[i] + L3[i]) / 6

    return f


def calculate_ppo(df):
    """Вычисление Laguerre PPO и процентильного ранга."""
    df['lmas'] = laguerre_filter(df['hl2'].values, SHORT_GAMMA)
    df['lmal'] = laguerre_filter(df['hl2'].values, LONG_GAMMA)

    df['ppoT'] = (df['lmas'] - df['lmal']) / df['lmal'] * 100
    df['ppoB'] = (df['lmal'] - df['lmas']) / df['lmal'] * 100

    df['pctRankT'] = df['ppoT'].rolling(LOOKBACK_T).apply(lambda x: percentileofscore(x, x.iloc[-1]), raw=False)
    df['pctRankB'] = df['ppoB'].rolling(LOOKBACK_B).apply(lambda x: percentileofscore(x, x.iloc[-1]), raw=False) * -1

    return df


def find_last_extreme(df):
    """Находит последний экстремальный сигнал, начиная с текущей свечи и шагая назад."""
    for i in range(len(df) - 1, -1, -1):
        if df['pctRankT'].iloc[i] >= PCTILE:
            return "sale", df.iloc[i]
        if df['pctRankB'].iloc[i] <= -PCTILE:
            return "buy", df.iloc[i]
    return "No Signal", None


async def wait_for_next_candle(timeframe):
    """Ожидает завершения текущей свечи и начала новой."""
    now = datetime.datetime.now()
    # Преобразуем текущее время в секунды
    current_time = now.timestamp()

    timeframe_seconds = {
        '1d': 86400,
        '4h': 14400,
        '1h': 3600,
        '30m': 1800,
        '15m': 900,
        '5m': 300,
        '3m': 180,
        '1m': 60,
    }

    interval = timeframe_seconds.get(timeframe)

    if interval:
        # Вычисляем время до следующей свечи
        next_candle_time = (current_time // interval + 1) * interval
        # Ждём до начала следующей свечи
        wait_time = next_candle_time - current_time
        print(f"Waiting for next {timeframe} candle: {wait_time:.2f} seconds")

        await asyncio.sleep(wait_time)
    else:
        print(f"Unknown timeframe: {timeframe}, waiting 60 seconds as fallback")
        await asyncio.sleep(60)  # Используем запасной вариант, если таймфрейм неизвестен


TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h"]
symbols    = get_usdt_pairs()
users      = [6634277726, 747471391]

async def process_tf(tf: str):
    while True:
        btc_df = await fetch_ohlcv("BTCUSDT", "5m", 300)
        for symbol in symbols:
            df5 = await fetch_ohlcv(symbol, "5m", 300)
            dft = await fetch_ohlcv(symbol, tf,   200)
            if df5 is None or dft is None: continue

            ticker  = await exchange.fetch_ticker(symbol)
            ctx = Context(
                ticker_24h=ticker,
                hourly_volume=df5["volume"].iloc[-12:].sum(),
                btc_df=btc_df,
            )

            for uid in users:
                open_order = await get_open_order(uid, symbol, tf)

                # ---------- вход ----------
                if open_order is None:
                    if moon.check_coin(symbol, df5, ctx) and moon.should_place_order(dft):
                        order_dict = moon.build_order(dft)
                        qty = order_dict["amount"]
                        entry = order_dict["price"]
                        tp  = order_dict["take_profit"]
                        sl  = order_dict["stop_loss"]

                        await create_order(uid, symbol, tf, "long", qty, entry, tp, sl)

                        await bot.send_message(
                            uid,
                            f"🟢 <b>BUY</b> {symbol} {tf}\n"
                            f"Entry {entry}\nTP {tp} | SL {sl}"
                        )
                # ---------- выход ----------
                else:
                    last_price = dft["close"].iloc[-1]
                    hit_tp = last_price >= open_order["tp_price"]
                    hit_sl = last_price <= open_order["sl_price"]

                    if hit_tp or hit_sl:
                        await close_order(open_order["id"], last_price)
                        await bot.send_message(
                            uid,
                            f"🔴 <b>SELL</b> {symbol} {tf}\n"
                            f"Exit {last_price} ({'TP' if hit_tp else 'SL'})"
                        )
            await asyncio.sleep(0.05)   # не душим API
        await wait_for_next_candle(tf)

async def main():
    try:
        await asyncio.gather(*[process_tf(tf) for tf in timeframes])
    finally:
        await exchange.close()  # Ensures resources are released

asyncio.run(main())
