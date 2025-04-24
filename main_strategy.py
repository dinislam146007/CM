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
from strategy_logic.moon_bot_strategy import StrategyMoonBot, load_strategy_params, Context
# Initialize moon bot with default params initially - will be replaced with user-specific in the processing loop
moon = StrategyMoonBot(load_strategy_params())
from db.orders import *
import datetime as dt
from db.orders import get_open_orders, get_order_by_id, close_order, save_order, get_active_positions
from db.orders import get_active_btc_position_size, get_daily_profit
import pytz


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
symbols    = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "LTCUSDT", "XRPUSDT", "SOLUSDT", "TRXUSDT"]
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

                # Get user-specific strategy parameters
                user_moon = StrategyMoonBot(load_strategy_params(uid))
                
                # ---------- вход ----------
                if open_order is None:
                    if user_moon.check_coin(symbol, df5, ctx) and user_moon.should_place_order(dft):
                        order_dict = user_moon.build_order(dft)
                        entry = order_dict["price"]
                        tp  = order_dict["take_profit"]
                        sl  = order_dict["stop_loss"]
                        
                        # Получаем баланс пользователя и рассчитываем объем на 5% от баланса
                        user_balance = await get_user_balance(uid)
                        investment_amount = user_balance * 0.05  # 5% от баланса
                        qty = investment_amount / entry  # Количество монет, которое можно купить
                        
                        # Форматируем количество с учетом минимального шага для торговли
                        qty = round(qty, 6)  # Округляем до 6 знаков после запятой
                        
                        # Если объем слишком мал, установим минимальный
                        if qty * entry < 10:  # Минимальный размер ордера 10 USDT
                            qty = 10 / entry
                            qty = round(qty, 6)
                        
                        # Создаем ордер с автоматическим списанием средств с баланса
                        try:
                            await create_order(uid, symbol, tf, "long", qty, entry, tp, sl)
                            
                            # Получаем обновленный баланс после списания средств
                            new_balance = await get_user_balance(uid)
                            
                            await bot.send_message(
                                uid,
                                f"🟢 <b>ПОКУПКА</b> {symbol} {tf}\n"
                                f"Цена входа: {entry:.4f} USDT\n"
                                f"Количество: {qty:.6f} ({(qty * entry):.2f} USDT)\n"
                                f"TP: {tp:.4f} | SL: {sl:.4f}\n\n"
                                f"💰 Баланс: {new_balance:.2f} USDT (-{(qty * entry):.2f} USDT)"
                            )
                        except Exception as e:
                            print(f"Ошибка при создании ордера: {e}")
                # ---------- выход ----------
                else:
                    last_price = dft["close"].iloc[-1]
                    hit_tp = last_price >= open_order["tp_price"]
                    hit_sl = last_price <= open_order["sl_price"]

                    if hit_tp or hit_sl:
                        try:
                            # Закрываем ордер и получаем информацию о P&L с автоматическим возвратом средств
                            closed_order = await close_order(open_order["id"], last_price)
                            
                            # Получаем данные из ордера
                            user_id = closed_order["user_id"]
                            entry_price = closed_order["coin_buy_price"]
                            exit_price = closed_order["coin_sale_price"]
                            qty = closed_order["qty"]
                            pnl_percent = closed_order["pnl_percent"]
                            pnl_usdt = closed_order["pnl_usdt"]
                            return_amount = closed_order["return_amount_usdt"]
                            
                            # Получаем обновленный баланс после возврата средств
                            new_balance = await get_user_balance(uid)
                            
                            # Определяем цвет и эмодзи в зависимости от P&L
                            pnl_emoji = "🔴" if pnl_percent < 0 else "🟢"
                            pnl_text = "Убыток" if pnl_percent < 0 else "Прибыль"
                            
                            # Получаем текущую дату и время в московском времени (+3 часа)
                            now = dt.datetime.now() + dt.timedelta(hours=3)
                            current_date = now.strftime('%d.%m.%Y')
                            current_time = now.strftime('%H:%M')
                            
                            # Преобразуем время открытия ордера (предполагаем, что оно хранится в UTC)
                            buy_time_utc = dt.datetime.fromisoformat(str(open_order["buy_time"]).replace('Z', ''))
                            buy_time_moscow = buy_time_utc + dt.timedelta(hours=3)  # Переводим в московское время
                            buy_date = buy_time_moscow.strftime('%d.%m.%Y')
                            buy_time = buy_time_moscow.strftime('%H:%M')
                            
                            # Получаем общий профит за день
                            today = dt.date.today()
                            daily_profit = await get_daily_profit(uid, today)
                            
                            # Создаем сообщение в зависимости от типа закрытия (TP или SL)
                            if hit_tp:
                                message = (
                                    f"🔴 <b>ПРОДАЖА</b> {symbol} {tf}\n\n"
                                    f"🎯✅ Достигнут Тейк-Профит\n"
                                    f"💸🔋Прибыль по сделке: {pnl_percent:.2f}% ({pnl_usdt:.2f} USDT)\n\n"
                                    f"♻️Точка входа: {entry_price:.2f}$\n"
                                    f"📈Цена продажи: {exit_price:.4f}$\n"
                                    f"🛑Продано: {qty:.6f} {symbol.replace('USDT', '')} ({(qty * exit_price):.2f} USDT)\n\n"
                                    f"📆Сделка была открыта: {buy_date}\n"
                                    f"🕐Время открытия: {buy_time} Мск\n"
                                    f"📉ТФ открытия сделки: {tf}\n"
                                    f"Направление: Long 🔰\n\n"
                                    f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                                    f"💰 Текущий баланс: {new_balance:.2f} USDT"
                                )
                            else:  # hit_sl
                                message = (
                                    f"🔴 <b>ПРОДАЖА</b> {symbol} {tf}\n"
                                    f"📛Закрыто по Стоп-лоссу\n"
                                    f"🤕🪫Убыток по сделке: {pnl_percent:.2f}% ({pnl_usdt:.2f} USDT)\n\n"
                                    f"♻️Точка входа: {entry_price:.2f}$\n"
                                    f"📈Цена продажи: {exit_price:.4f}$\n"
                                    f"🛑Продано: {qty:.6f} {symbol.replace('USDT', '')} ({(qty * exit_price):.2f} USDT)\n\n"
                                    f"📆Сделка была открыта: {buy_date}\n"
                                    f"🕐Время открытия: {buy_time} Мск\n"
                                    f"📉ТФ открытия сделки: {tf}\n"
                                    f"Направление: Long 🔰\n\n"
                                    f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                                    f"💰 Текущий баланс: {new_balance:.2f} USDT"
                                )
                            
                            await bot.send_message(uid, message)
                            
                        except Exception as e:
                            print(f"Ошибка при закрытии ордера: {e}")
            await asyncio.sleep(0.05)   # не душим API
        await wait_for_next_candle(tf)

async def main():
    try:
        await asyncio.gather(*[process_tf(tf) for tf in TIMEFRAMES])
    finally:
        await exchange.close()  # Ensures resources are released

asyncio.run(main())

async def close_order_with_notification(user_id, order_id, current_price, close_reason):
    # Получаем информацию об ордере
    order = await get_order_by_id(order_id)
    
    if order:
        # Закрываем ордер и обновляем данные
        await close_order(order_id, current_price)
        
        # Рассчитываем прибыль/убыток
        entry_price = order['entry_price']
        pnl_percent = ((current_price - entry_price) / entry_price) * 100
        if order['position_side'] == 'SHORT':
            pnl_percent = -pnl_percent
        pnl = (current_price - entry_price) * order['qty']
        if order['position_side'] == 'SHORT':
            pnl = -pnl
            
        # Получаем текущую дату и время в МСК
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.datetime.now(moscow_tz)
        current_date = now.strftime('%d.%m.%Y')
        current_time = now.strftime('%H:%M')
        
        # Конвертируем время открытия ордера из UTC в МСК
        buy_time_utc = datetime.datetime.fromtimestamp(order['open_time'])
        buy_time_moscow = pytz.utc.localize(buy_time_utc).astimezone(moscow_tz)
        buy_date = buy_time_moscow.strftime('%d.%m.%Y')
        buy_time = buy_time_moscow.strftime('%H:%M')
        
        # Получаем суммарный профит за день
        daily_profit = await get_daily_profit(user_id, now.date())
        
        # Получаем обновленный баланс после возврата средств
        new_balance = await get_user_balance(user_id)
        
        # Определяем направление и символ
        direction = "Long 🔰" if order['position_side'] == 'LONG' else "Short 🔻"
        symbol_base = order['symbol'].replace('USDT', '')
        
        # Форматируем разные сообщения в зависимости от причины закрытия
        if close_reason == "TP":
            message = (
                f"🔴 <b>ПРОДАЖА</b> {order['symbol']} {order['timeframe']}\n\n"
                f"🎯✅ Достигнут Тейк-Профит\n"
                f"💸🔋Прибыль по сделке: {pnl_percent:.2f}% ({pnl:.2f} USDT)\n\n"
                f"♻️Точка входа: {entry_price:.2f}$\n"
                f"📈Цена продажи: {current_price:.4f}$\n"
                f"🛑Продано: {order['qty']:.6f} {symbol_base} ({(order['qty'] * current_price):.2f} USDT)\n\n"
                f"📆Сделка была открыта: {buy_date}\n"
                f"🕐Время открытия: {buy_time} Мск\n"
                f"📉ТФ открытия сделки: {order['timeframe']}\n"
                f"Направление: {direction}\n\n"
                f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                f"💰 Текущий баланс: {new_balance:.2f} USDT"
            )
        else:  # SL
            message = (
                f"🔴 <b>ПРОДАЖА</b> {order['symbol']} {order['timeframe']}\n"
                f"📛Закрыто по Стоп-лоссу\n"
                f"🤕🪫Убыток по сделке: {pnl_percent:.2f}% ({pnl:.2f} USDT)\n\n"
                f"♻️Точка входа: {entry_price:.2f}$\n"
                f"📈Цена продажи: {current_price:.4f}$\n"
                f"🛑Продано: {order['qty']:.6f} {symbol_base} ({(order['qty'] * current_price):.2f} USDT)\n\n"
                f"📆Сделка была открыта: {buy_date}\n"
                f"🕐Время открытия: {buy_time} Мск\n"
                f"📉ТФ открытия сделки: {order['timeframe']}\n"
                f"Направление: {direction}\n\n"
                f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                f"💰 Текущий баланс: {new_balance:.2f} USDT"
            )
        
        # Отправляем сообщение пользователю
        await bot.send_message(user_id, message)
        
        return True
    return False
