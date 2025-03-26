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
from db import *
import datetime
from strategy_logic.rsi import *
from strategy_logic.vsa import *
from strategy_logic.price_action import get_pattern_price_action
from deepseek.deepsekk import analyze_trading_signals
from config import config

bot = Bot(token=config.tg_bot_token, default=DefaultBotProperties(parse_mode="HTML"))

"""Параметры стратегии"""
SHORT_GAMMA = 0.4
LONG_GAMMA = 0.8
LOOKBACK_T = 50
LOOKBACK_B = 20
PCTILE = 90

exchange = ccxt.bybit()  # Передаём сессию в CCXT


timeframes = ['1d', '4h', '1h', '30m']

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
    }

    interval = timeframe_seconds.get(timeframe)

    if interval:
        # Вычисляем время до следующей свечи
        next_candle_time = (current_time // interval + 1) * interval
        # Ждём до начала следующей свечи
        print(timeframe, next_candle_time - current_time)

        await asyncio.sleep(next_candle_time - current_time)


async def process_timeframe(timeframe):
    while True:
        """Обрабатывает все символы для одного таймфрейма."""
        user_ids = await get_all_user_id()
        now = datetime.datetime.now().strftime('%d-%m-%Y %H:%M')


        await wait_for_next_candle(timeframe)

        for symbol in symbols:

            print(symbol, timeframe)
            df = await fetch_ohlcv(symbol, timeframe)
            df = calculate_ppo(df)  # Assuming this doesn't overwrite 'ema21' and 'ema49'
            df = calculate_ema(df)  # Ensure this is called to add 'ema21' and 'ema49'
            df = calculate_rsi(df)  # Ensure the 'rsi' column is added before generating signals
            df = generate_signals_rsi(df)  # Add signals after EMAs and RSI are calculated
            df = detect_vsa_signals(df)
            finish, last_candle = find_last_extreme(df)
            price_action_pattern = await get_pattern_price_action(df[-3:].values.tolist(), "spot")
            divergence_convergence_signal = detect_divergence_convergence(df)
            sale_price = df['close'].iloc[-1]
            buy_price = df['close'].iloc[-1]


            # print(f"df: {df}\n\nfinish: {finish}, ")
            logging.info(f"{symbol}: start neiro")
            if symbol in config.ai_tokens:
                finish_ai = await analyze_trading_signals(df, finish,
                                                          divergence_convergence_signal,
                                                          price_action_pattern, symbol,
                                                          timeframe,
                                                          buy_price
                                                          )

                text = f"""
Пара: {symbol}
Тип сигнала: {finish_ai['signal_type']}
⏱ТФ: {timeframe}

Точка входа: {finish_ai['entry_point']}
💸Take Profit: {finish_ai['take_profit']}

📛Stop-loss: {finish_ai['stop_loss']}

{finish_ai['reason']}
"""
                try:
                    await bot.send_message(chat_id=-1002467387559, text=text, parse_mode=ParseMode.MARKDOWN)
                except Exception:
                    await bot.send_message(chat_id=-1002467387559, text=text)


            logging.info(f"{symbol}: {finish}")

            if finish == 'buy':
                old = await get_signal(symbol, timeframe)

                for user_id in user_ids:
                    pairs = str(user_id['crypto_pairs']).split(',')
                    if (symbol in pairs) and (await get_order(timeframe, symbol, user_id['user_id']) is None):
                        price = (user_id['percent'] / 100) * user_id['balance']
                        #await minus_plus_user(-price, user_id['user_id'])
                        #await buy_order(user_id['user_id'], timeframe, symbol, price, now, sale_price)

                if old and old['status'] == 'sale':

                    users = await get_subscribed_users(symbol, timeframe)
                    for user_id in users:
                        signal = {"symbol": symbol,
                                  "interval": timeframe,
                                  "flag": "Long 🔰",
                                  "user_id": user_id}
                        await bot.send_message(chat_id=user_id['user_id'],
                                               text=f"Новый сигнал:\nИнструмент: {signal['symbol']}\nИнтервал: {signal['interval']}\nСигнал: {signal['flag']}")

                elif not old:
                    users = await get_subscribed_users(symbol, timeframe)
                    for user_id in users:
                        signal = {"symbol": symbol,
                                  "interval": timeframe,
                                  "flag": "Long 🔰",
                                  "user_id": user_id}
                        await bot.send_message(chat_id=user_id['user_id'],
                                               text=f"Новый сигнал:\nИнструмент: {signal['symbol']}\nИнтервал: {signal['interval']}\nСигнал: {signal['flag']}")

            elif finish == 'sale':
                old = await get_signal(symbol, timeframe)

                for user_id in user_ids:
                    order = await get_order(timeframe, symbol, user_id['user_id'])
                    if order:
                        coin_buy_price = order['coin_buy_price']
                        buy_price = order['buy_price']
                        percent_change = ((sale_price - coin_buy_price) / coin_buy_price) * 100
                        profit_or_loss = ((percent_change / 100) * buy_price) + buy_price

                        await sale_order(user_id['user_id'], profit_or_loss, now, sale_price, symbol, timeframe)
                        await minus_plus_user(profit_or_loss, user_id['user_id'])

                if old and old['status'] == 'buy':
                    users = await get_subscribed_users(symbol, timeframe)
                    for user_id in users:
                        signal = {"symbol": symbol,
                                  "interval": timeframe,
                                  "flag": "Продажа 🔻",
                                  "user_id": user_id}
                        await bot.send_message(chat_id=user_id['user_id'],
                                               text=f"Новый сигнал:\nИнструмент: {signal['symbol']}\nИнтервал: {signal['interval']}\nСигнал: {signal['flag']}")
                elif not old:
                    users = await get_subscribed_users(symbol, timeframe)
                    for user_id in users:
                        signal = {"symbol": symbol,
                                  "interval": timeframe,
                                  "flag": "Продажа 🔻",
                                  "user_id": user_id}
                        await bot.send_message(chat_id=user_id['user_id'],
                                               text=f"Новый сигнал:\nИнструмент: {signal['symbol']}\nИнтервал: {signal['interval']}\nСигнал: {signal['flag']}")
            await update_signal(symbol, timeframe, finish, buy_price, sale_price)


async def main():
    try:
        await asyncio.gather(*[process_timeframe(tf) for tf in timeframes])
    finally:
        await exchange.close()  # Ensures resources are released

asyncio.run(main())
