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
import datetime as dt
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
from db.orders import get_open_orders, get_order_by_id, close_order, save_order, get_active_positions
from db.orders import get_active_btc_position_size, get_daily_profit, init_db
import pytz
from dateutil.parser import parse
from db.orders import get_user_open_orders, get_user_balance
from strategy_logic.user_strategy_params import load_user_params
from strategy_logic.pump_dump import pump_dump_main
from strategy_logic.cm_settings import load_cm_settings  # Импортируем функцию загрузки настроек CM
from strategy_logic.divergence_settings import load_divergence_settings  # Импортируем функцию загрузки настроек дивергенции
from strategy_logic.rsi_settings import load_rsi_settings  # Импортируем функцию загрузки настроек RSI
from strategy_logic.pump_dump_settings import load_pump_dump_settings  # Импортируем функцию загрузки настроек Pump/Dump
from strategy_logic.pump_dump_trading import process_pump_dump_signal  # Импортируем функцию обработки сигналов Pump/Dump
from strategy_logic.trading_type_settings import load_trading_type_settings  # Импортируем функцию загрузки настроек типа торговли
from strategy_logic.trading_settings import load_trading_settings  # Импортируем функцию загрузки настроек торговли
from pathlib import Path
import json
from typing import Callable, Awaitable, Dict, Tuple, Any
import requests
import time


bot = Bot(token=config.tg_bot_token, default=DefaultBotProperties(parse_mode="HTML"))

async def close_order_with_notification(user_id, order_id, current_price, close_reason):
    # Получаем информацию об ордере
    order = await get_order_by_id(order_id)
    
    if order:
        try:
            # Проверяем, не закрыт ли уже ордер
            if order.get('status', 'OPEN') == 'CLOSED':
                print(f"Ордер {order_id} уже закрыт, пропускаем закрытие")
                return False
                
            # Получаем текущий баланс пользователя для логирования
            current_balance = await get_user_balance(user_id)
            print(f"Текущий баланс пользователя {user_id} перед закрытием ордера: {current_balance}")
                
            # Закрываем ордер и обновляем данные
            result = await close_order(order_id, current_price)
            
            # Если закрытие не удалось (ордер уже закрыт), выходим
            if not result:
                print(f"Не удалось закрыть ордер {order_id}, возможно он уже закрыт")
                return False
            
            # Проверяем наличие поля entry_price или альтернативных полей
            entry_price = None
            if 'entry_price' in order:
                entry_price = order['entry_price']
            elif 'price' in order:
                entry_price = order['price']
            elif 'open_price' in order:
                entry_price = order['open_price']
            elif 'coin_buy_price' in order:
                entry_price = order['coin_buy_price']
            
            if entry_price is None:
                # Если не удалось найти цену входа, выводим информацию об ордере для отладки
                print(f"Ошибка: не найдено поле с ценой входа. Структура ордера: {order}")
                await bot.send_message(user_id, f"Ошибка при закрытии ордера: не найдена цена входа")
                return False
            
            # Определяем направление позиции
            position_side = order.get('position_side', order.get('side', 'LONG'))  # По умолчанию LONG, если не указано
            
            # Рассчитываем прибыль/убыток
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
            if position_side == 'SHORT':
                pnl_percent = -pnl_percent
            
            # Получаем количество монет
            qty = order.get('qty', order.get('amount', 0))
            
            pnl = (current_price - entry_price) * qty
            if position_side == 'SHORT':
                pnl = -pnl
                
            # Получаем текущую дату и время в МСК
            moscow_tz = pytz.timezone('Europe/Moscow')
            now = dt.datetime.now(moscow_tz)
            current_date = now.strftime('%d.%m.%Y')
            current_time = now.strftime('%H:%M')
            
            # Конвертируем время открытия ордера из UTC в МСК
            open_time = None
            if 'open_time' in order:
                open_time = order['open_time']
            elif 'buy_time' in order:
                open_time = int(dt.datetime.timestamp(order['buy_time']))
            else:
                open_time = int(dt.datetime.now().timestamp())
                
            buy_time_utc = dt.datetime.fromtimestamp(open_time)
            buy_time_moscow = pytz.utc.localize(buy_time_utc).astimezone(moscow_tz)
            buy_date = buy_time_moscow.strftime('%d.%m.%Y')
            buy_time = buy_time_moscow.strftime('%H:%M')
            
            # Получаем суммарный профит за день
            daily_profit = await get_daily_profit(user_id, now.date())
            
            # Получаем обновленный баланс после возврата средств
            new_balance = await get_user_balance(user_id)
            
            # Логирование изменения баланса
            balance_change = new_balance - current_balance
            print(f"Новый баланс пользователя {user_id} после закрытия ордера: {new_balance} (изменение: {balance_change})")
            
            # Определяем направление и символ
            direction = "Long 🔰" if position_side == 'LONG' else "Short 🔻"
            symbol = order.get('symbol', 'UNKNOWN')
            symbol_base = symbol.replace('USDT', '')
            timeframe = order.get('timeframe', order.get('interval', '1h'))
            
            # Форматируем разные сообщения в зависимости от причины закрытия
            if close_reason == "TP":
                message = (
                    f"🔴 <b>ЗАКРЫТИЕ ОРДЕРА</b> {symbol} {timeframe}\n\n"
                    f"Биржа: {order.get('exchange', 'Bybit')}\n"
                    f"Тип торговли: {order.get('trading_type', 'spot').upper()}"
                    f"{' | Плечо: x' + str(order.get('leverage', 1)) if order.get('trading_type') == 'futures' else ''}\n\n"
                    f"🎯✅ Достигнут Тейк-Профит\n"
                    f"💸🔋Прибыль по сделке: {pnl_percent:.2f}% ({pnl:.2f} USDT)\n\n"
                    f"♻️Точка входа: {entry_price:.2f}$\n"
                    f"📈Цена продажи: {current_price:.4f}$\n"
                    f"🛑Продано: {qty:.6f} {symbol_base} ({(qty * current_price):.2f} USDT)\n\n"
                    f"📆Сделка была открыта: {buy_date}\n"
                    f"🕐Время открытия: {buy_time} Мск\n"
                    f"📉ТФ открытия сделки: {timeframe}\n"
                    f"Направление: {direction}\n\n"
                    f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                    f"💰 Текущий баланс: {new_balance:.2f} USDT"
                )
            else:  # SL
                message = (
                    f"🔴 <b>ЗАКРЫТИЕ ОРДЕРА</b> {symbol} {timeframe}\n\n"
                    f"Биржа: {order.get('exchange', 'Bybit')}\n"
                    f"Тип торговли: {order.get('trading_type', 'spot').upper()}"
                    f"{' | Плечо: x' + str(order.get('leverage', 1)) if order.get('trading_type') == 'futures' else ''}\n\n"
                    f"📛Закрыто по Стоп-лоссу\n"
                    f"🤕🪫Убыток по сделке: {pnl_percent:.2f}% ({pnl:.2f} USDT)\n\n"
                    f"♻️Точка входа: {entry_price:.2f}$\n"
                    f"📈Цена продажи: {current_price:.4f}$\n"
                    f"🛑Продано: {qty:.6f} {symbol_base} ({(qty * current_price):.2f} USDT)\n\n"
                    f"📆Сделка была открыта: {buy_date}\n"
                    f"🕐Время открытия: {buy_time} Мск\n"
                    f"📉ТФ открытия сделки: {timeframe}\n"
                    f"Направление: {direction}\n\n"
                    f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                    f"💰 Текущий баланс: {new_balance:.2f} USDT"
                )
            
            # Отправляем сообщение пользователю
            await bot.send_message(user_id, message)
            
            return True
        except Exception as e:
            print(f"Ошибка при закрытии ордера: {e}")
            await bot.send_message(user_id, f"Ошибка при закрытии ордера: {e}")
            return False
    return False

"""Параметры стратегии - будут использоваться только как значения по умолчанию"""
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


def calculate_ppo(df, cm_settings):
    """Вычисление Laguerre PPO и процентильного ранга с пользовательскими настройками."""
    df['lmas'] = laguerre_filter(df['hl2'].values, cm_settings['SHORT_GAMMA'])
    df['lmal'] = laguerre_filter(df['hl2'].values, cm_settings['LONG_GAMMA'])

    df['ppoT'] = (df['lmas'] - df['lmal']) / df['lmal'] * 100
    df['ppoB'] = (df['lmal'] - df['lmas']) / df['lmal'] * 100

    df['pctRankT'] = df['ppoT'].rolling(cm_settings['LOOKBACK_T']).apply(lambda x: percentileofscore(x, x.iloc[-1]), raw=False)
    df['pctRankB'] = df['ppoB'].rolling(cm_settings['LOOKBACK_B']).apply(lambda x: percentileofscore(x, x.iloc[-1]), raw=False) * -1

    return df


def find_cm_signal(df, cm_settings):
    """Находит последний экстремальный сигнал, начиная с текущей свечи и шагая назад."""
    for i in range(len(df) - 1, -1, -1):
        if df['pctRankT'].iloc[i] >= cm_settings['PCTILE']:
            return "short", df.iloc[i]
        if df['pctRankB'].iloc[i] <= -cm_settings['PCTILE']:
            return "long", df.iloc[i]
    return "No Signal", None


async def wait_for_next_candle(timeframe):
    """Ожидает завершения текущей свечи и начала новой."""
    # Вычисляем, сколько времени осталось до следующей свечи
    tf_to_seconds = {
        '1d': 86400,
        '4h': 14400,
        '1h': 3600,
        '30m': 1800,
        '15m': 900,
        '5m': 300,
        '3m': 180,
        '1m': 60,
    }
    
    start_time = tf_to_seconds.get(timeframe, 60 * 60)  # По умолчанию 1 час
    
    # Текущее время в секундах с начала эпохи
    now = dt.datetime.now()
    current_time = int(now.timestamp())
    
    # Время начала текущей свечи
    current_candle_start = current_time - (current_time % start_time)
    
    # Время начала следующей свечи
    next_candle_start = current_candle_start + start_time
    
    # Сколько секунд осталось до следующей свечи
    seconds_to_wait = next_candle_start - current_time

    if seconds_to_wait > 0:
        print(f"Waiting for next {timeframe} candle: {seconds_to_wait:.2f} seconds")
        await asyncio.sleep(seconds_to_wait)
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
                
                # Загружаем индивидуальные настройки CM для пользователя
                cm_settings = load_cm_settings(uid)
                
                # Загружаем индивидуальные настройки дивергенции для пользователя
                divergence_settings = load_divergence_settings(uid)
                
                # Загружаем индивидуальные настройки RSI для пользователя
                rsi_settings = load_rsi_settings(uid)
                
                # Загружаем индивидуальные настройки Pump/Dump для пользователя
                pump_dump_settings = load_pump_dump_settings(uid)
                
                # Загружаем индивидуальные настройки типа торговли для пользователя
                trading_type_settings = load_trading_type_settings(uid)
                
                # Загружаем индивидуальные настройки торговли для пользователя
                trading_settings = load_trading_settings(uid)
                trading_type = trading_settings["trading_type"]
                leverage = trading_settings["leverage"]
                
                # ---------- вход ----------
                if open_order is None:
                    # Проверка на паттерны Price Action с учетом типа рынка
                    pattern = await get_pattern_price_action(dft[['timestamp', 'open', 'high', 'low', 'close']].values.tolist()[-5:], trading_type)
                    dft = calculate_ppo(dft, cm_settings)  # Используем индивидуальные настройки
                    dft = calculate_ema(dft)
                    cm_signal, last_candle = find_cm_signal(dft, cm_settings)  # Используем индивидуальные настройки
                    
                    # Рассчитываем RSI с пользовательскими настройками
                    dft = calculate_rsi(dft, period=rsi_settings['RSI_PERIOD'])
                    dft = calculate_ema(dft, 
                                       fast_period=rsi_settings['EMA_FAST'], 
                                       slow_period=rsi_settings['EMA_SLOW'])
                    
                    # Генерируем сигналы RSI с пользовательскими настройками
                    rsi = generate_signals_rsi(dft, 
                                              overbought=rsi_settings['RSI_OVERBOUGHT'], 
                                              oversold=rsi_settings['RSI_OVERSOLD'])
                    rsi_signal = rsi['signal_rsi'].iloc[-1]

                    diver_signals = generate_trading_signals(
                        dft, 
                        rsi_length=divergence_settings['RSI_LENGTH'], 
                        lbR=divergence_settings['LB_RIGHT'], 
                        lbL=divergence_settings['LB_LEFT'], 
                        take_profit_level=divergence_settings['TAKE_PROFIT_RSI_LEVEL'],
                        stop_loss_type=divergence_settings['STOP_LOSS_TYPE'],
                        stop_loss_perc=divergence_settings['STOP_LOSS_PERC'],
                        atr_length=divergence_settings['ATR_LENGTH'],
                        atr_multiplier=divergence_settings['ATR_MULTIPLIER']
                    )
                    
                    # Определяем, какой тип позиции открывать (LONG или SHORT)
                    # По умолчанию LONG, для spot доступен только LONG
                    position_side = "LONG"
                    
                    # Для futures типа торговли, можно открывать SHORT позиции
                    if trading_type == "futures":
                        # Если есть сигнал на SHORT - меняем тип позиции
                        if cm_signal == "short" or rsi_signal == "Short":
                            position_side = "SHORT"
                    
                    # Определяем, какие сигналы активны в зависимости от типа позиции
                    if position_side == "LONG":
                        price_action_active = pattern is not None and pattern != "" and pattern.startswith("Bull")
                        cm_active = cm_signal == "long"
                        moonbot_active = user_moon.check_coin(symbol, df5, ctx) and user_moon.should_place_order(dft)
                        rsi_active = rsi_signal == "Long"
                        
                        # Проверка на бычью дивергенцию
                        regular_bullish = diver_signals['divergence']['regular_bullish']
                        hidden_bullish = diver_signals['divergence']['hidden_bullish']
                        divergence_active = False
                        divergence_type = ""
                        
                        if isinstance(regular_bullish, bool) and regular_bullish:
                            divergence_active = True
                            divergence_type += "Regular Bullish "
                        if isinstance(hidden_bullish, bool) and hidden_bullish:
                            divergence_active = True
                            divergence_type += "Hidden Bullish "
                    else:  # SHORT позиция
                        price_action_active = pattern is not None and pattern != "" and pattern.startswith("Bear")
                        cm_active = cm_signal == "short"
                        moonbot_active = False  # MoonBot только для LONG
                        rsi_active = rsi_signal == "Short"
                        
                        # Проверка на медвежью дивергенцию
                        regular_bearish = diver_signals['divergence']['regular_bearish']
                        hidden_bearish = diver_signals['divergence']['hidden_bearish']
                        divergence_active = False
                        divergence_type = ""
                        
                        if isinstance(regular_bearish, bool) and regular_bearish:
                            divergence_active = True
                            divergence_type += "Regular Bearish "
                        if isinstance(hidden_bearish, bool) and hidden_bearish:
                            divergence_active = True
                            divergence_type += "Hidden Bearish "
                    
                    # Общий флаг для проверки наличия хотя бы одного сигнала на покупку/продажу
                    any_signal = price_action_active or cm_active or moonbot_active or rsi_active or divergence_active
                    
                    # Определяем текущую цену
                    current_price = dft["close"].iloc[-1]
                    
                    # Открываем сделку, если есть хотя бы один активный сигнал
                    if any_signal:
                        # Если сработала стратегия мун бота, используем ее данные, иначе создаем базовый ордер
                        if moonbot_active:
                            order_dict = user_moon.build_order(dft)
                            entry = order_dict["price"]
                            tp = order_dict["take_profit"]
                            sl = order_dict["stop_loss"]
                        else:
                            # Базовый ордер на основе текущей цены при срабатывании других сигналов
                            entry = current_price
                            
                            # Рассчитываем TP и SL в зависимости от типа позиции
                            if position_side == "LONG":
                                # Базовый TP: +3% от цены входа
                                tp = entry * 1.03
                                # Базовый SL: -2% от цены входа
                                sl = entry * 0.98
                            else:  # SHORT
                                # Базовый TP: -3% от цены входа
                                tp = entry * 0.97
                                # Базовый SL: +2% от цены входа
                                sl = entry * 1.02
                        
                        # Получаем баланс пользователя
                        user_balance = await get_user_balance(uid)
                        
                        # Рассчитываем объем позиции с учетом типа торговли и плеча
                        if trading_type == "futures":
                            # Для фьючерсов учитываем плечо при расчете объема
                            investment_amount = user_balance * 0.05  # 5% от баланса
                            qty = (investment_amount * leverage) / entry
                        else:
                            # Для спот торговли - обычный расчет
                            investment_amount = user_balance * 0.05  # 5% от баланса
                            qty = investment_amount / entry
                        
                        # Форматируем количество с учетом минимального шага для торговли
                        qty = round(qty, 6)  # Округляем до 6 знаков после запятой
                        
                        # Если объем слишком мал, установим минимальный
                        if qty * entry < 10:  # Минимальный размер ордера 10 USDT
                            qty = 10 / entry
                            qty = round(qty, 6)
                        
                        # Создаем ордер с учетом типа рынка и кредитного плеча
                        try:
                            order_id = await create_order(uid, symbol, tf, position_side, qty, entry, tp, sl, trading_type, leverage)
                            
                            # Получаем обновленный баланс после списания средств
                            new_balance = await get_user_balance(uid)
                            
                            # Определяем эмодзи для типа позиции
                            position_emoji = "🔰" if position_side == "LONG" else "🔻"
                            transaction_emoji = "🟢" if position_side == "LONG" else "🔴"
                            
                            # Формируем сообщение по новому шаблону
                            message = (
                                f"{transaction_emoji} <b>ОТКРЫТИЕ ОРДЕРА</b> {symbol} {tf}\n\n"
                                f"Биржа: Bybit\n"
                                f"Тип торговли: {trading_type.upper()}"
                                f"{' | Плечо: x' + str(leverage) if trading_type == 'futures' else ''}\n\n"
                                f"💸Объем: {qty:.6f} {symbol.replace('USDT', '')} ({(qty * entry):.2f} USDT)\n\n"
                                f"♻️Точка входа: {entry:.2f}$\n"
                                f"Направление: {position_side} {position_emoji}\n\n"
                                f"🎯TP: {tp:.4f}$\n"
                                f"📛SL: {sl:.4f}$\n\n"
                                f"⚠️Сделка открыта по сигналам с:\n"
                                f"{price_action_active and '✅' or '❌'} Price Action {pattern if price_action_active else ''}\n"
                                f"{cm_active and '✅' or '❌'} CM\n"
                                f"{moonbot_active and '✅' or '❌'} MoonBot\n"
                                f"{rsi_active and '✅' or '❌'} RSI\n"
                                f"{divergence_active and '✅' or '❌'} Divergence {divergence_type if divergence_active else ''}\n\n"
                                f"💰 Баланс: {new_balance:.2f} USDT (-{(investment_amount):.2f} USDT)"
                            )
                            
                            await bot.send_message(uid, message)
                            
                        except Exception as e:
                            print(f"Ошибка при создании ордера: {e}")
                            await bot.send_message(uid, f"Ошибка при создании ордера: {e}")
                
                # ---------- выход ----------
                else:
                    last_price = dft["close"].iloc[-1]
                    
                    # Skip processing if the order is already closed
                    if open_order.get('status', 'OPEN') != 'OPEN':
                        print(f"Пропускаем обработку - ордер {open_order['id']} уже закрыт")
                        continue
                    
                    # Проверяем различные поля для определения направления позиции
                    position_direction = "LONG"  # По умолчанию LONG
                    if "position_side" in open_order:
                        position_direction = open_order["position_side"]
                    elif "side" in open_order and open_order["side"].upper() == "SELL":
                        position_direction = "SHORT"
                    elif "position_type" in open_order:
                        position_direction = open_order["position_type"]
                    
                    # Определяем, является ли позиция длинной
                    is_long = position_direction.upper() == "LONG"
                    
                    if is_long:
                        hit_tp = last_price >= open_order["tp_price"]
                        hit_sl = last_price <= open_order["sl_price"]
                    else:  # SHORT
                        hit_tp = last_price <= open_order["tp_price"]  # Для SHORT TP ниже цены входа
                        hit_sl = last_price >= open_order["sl_price"]  # Для SHORT SL выше цены входа

                    if hit_tp or hit_sl:
                        try:
                            # Проверяем статус ордера еще раз непосредственно перед закрытием
                            current_order = await get_order_by_id(open_order["id"])
                            if current_order and current_order.get('status') == 'CLOSED':
                                print(f"Пропускаем закрытие - ордер {open_order['id']} уже закрыт")
                                continue
                            
                            print(f"Закрываем ордер {open_order['id']} по {'TP' if hit_tp else 'SL'}")
                            # Закрываем ордер и получаем информацию о P&L
                            close_result = await close_order_with_notification(
                                uid, open_order["id"], last_price, "TP" if hit_tp else "SL"
                            )
                            
                            if not close_result:
                                print(f"Ордер {open_order['id']} не был закрыт (возможно, уже закрыт)")
                        except Exception as e:
                            print(f"Ошибка при закрытии ордера: {e}")
                            await bot.send_message(uid, f"Ошибка при закрытии ордера: {e}")
            await asyncio.sleep(0.05)   # не душим API
        await wait_for_next_candle(tf)


# =============================================================================
#  Exchange-specific signal handlers (stubs – replace with real logic)
# =============================================================================

# Преобразование интервалов для MEXC Futures
MEXC_INTERVAL_MAP = {
    "1m": "Min1", "3m": "Min3", "5m": "Min5", "15m": "Min15", "30m": "Min30",
    "1h": "Min60", "4h": "Hour4", "8h": "Hour8", "1d": "Day1", "1w": "Week1", "1M": "Month1"
}

def get_binance_ohlcv(symbol: str, interval: str, futures: bool=False, limit: int=1000):
    """Получение OHLCV с Binance (spot или futures)"""
    if futures:
        base_url = "https://fapi.binance.com"  # USD-M Futures
        endpoint = "/fapi/v1/klines"
    else:
        base_url = "https://api.binance.com"
        endpoint = "/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(base_url + endpoint, params=params)
    resp.raise_for_status()
    klines = resp.json()  # список списков
    ohlcv = []
    for k in klines:
        ts = int(k[0])
        o, h, l, c, v = float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])
        ohlcv.append([ts, o, h, l, c, v])
    return ohlcv

def get_mexc_ohlcv(symbol: str, interval: str, futures: bool=False, limit: int=1000):
    """Получение OHLCV с MEXC (spot или futures)"""
    try:
        if futures:
            base_url = "https://contract.mexc.com"
            # Убедимся, что символ с "_" (например BTCUSDT -> BTC_USDT)
            if "_" not in symbol:
                if symbol.endswith("USDT"):
                    symbol_name = symbol[:-4] + "_" + symbol[-4:]
                else:
                    symbol_name = symbol  # для других пар, если появятся
            else:
                symbol_name = symbol
            endpoint = f"/api/v1/contract/kline/{symbol_name}"
            # Конвертируем интервал
            interval_param = MEXC_INTERVAL_MAP.get(interval, interval)
            params = {"interval": interval_param}
            try:
                # Можно добавить start/end при необходимости
                resp = requests.get(base_url + endpoint, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json().get("data", {})
                # data содержит списки: 'time', 'open', 'high', 'low', 'close', 'vol'
                times = data.get("time", [])
                opens = data.get("open", [])
                highs = data.get("high", [])
                lows  = data.get("low", [])
                closes= data.get("close", [])
                vols  = data.get("vol", [])
                ohlcv = []
                for i in range(len(times)):
                    ts_ms = int(times[i]) * 1000  # sec -> ms
                    o = float(opens[i]); h = float(highs[i]); 
                    l = float(lows[i]);  c = float(closes[i]); 
                    v = float(vols[i])
                    ohlcv.append([ts_ms, o, h, l, c, v])
                return ohlcv
            except Exception as e:
                print(f"Ошибка при получении MEXC Futures данных: {e}, используем Binance как fallback")
                # Используем Binance в качестве fallback
                return get_binance_ohlcv(symbol, interval, True, limit)
        else:
            # Многие 3m, 5m и другие интервалы могут не поддерживаться на MEXC Spot
            # Маппинг интервалов для MEXC Spot
            mexc_spot_intervals = {
                "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w", "1M": "1M"
            }
            
            # Если интервал не поддерживается MEXC, используем Binance API
            if interval not in mexc_spot_intervals:
                print(f"Интервал {interval} не поддерживается MEXC Spot API, используем Binance")
                return get_binance_ohlcv(symbol, interval, False, limit)
                
            try:
                # MEXC spot API
                base_url = "https://api.mexc.com"
                endpoint = "/api/v3/klines"
                params = {"symbol": symbol, "interval": mexc_spot_intervals.get(interval, interval), "limit": limit}
                resp = requests.get(base_url + endpoint, params=params, timeout=10)
                resp.raise_for_status()
                klines = resp.json()
                ohlcv = []
                for k in klines:
                    ts = int(k[0])
                    o, h, l, c, v = float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])
                    ohlcv.append([ts, o, h, l, c, v])
                return ohlcv
            except Exception as e:
                print(f"Ошибка при получении MEXC Spot данных: {e}, используем Binance как fallback")
                # Используем Binance в качестве fallback
                return get_binance_ohlcv(symbol, interval, False, limit)
    except Exception as e:
        print(f"Критическая ошибка в get_mexc_ohlcv: {e}")
        # Возвращаем пустые данные вместо падения
        return []

# ============================ BYBIT OHLCV ===================================
BYBIT_INTERVAL_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "4h": "240", "1d": "D", "1w": "W", "1M": "M"
}

def get_bybit_ohlcv(symbol: str, interval: str, futures: bool = False, limit: int = 1000):
    """Получает OHLCV данные с Bybit Spot или Futures REST v5."""
    base_url = "https://api.bybit.com"
    endpoint = "/v5/market/kline"
    params = {
        "category": "linear" if futures else "spot",
        "symbol": symbol,
        "interval": BYBIT_INTERVAL_MAP.get(interval, interval),
        "limit": limit,
    }
    resp = requests.get(base_url + endpoint, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    klines = data.get("result", {}).get("list", [])  # список списков
    ohlcv = []
    for k in klines:
        ts = int(k[0])
        o, h, l, c, v = map(float, k[1:6])
        ohlcv.append([ts, o, h, l, c, v])
    return ohlcv

# ======================== Signal-handler wrappers ============================
async def _fetch_ohlcv_to_thread(fetch_fn, *args, **kwargs):
    """Запускает blocking-функцию в default executor и возвращает результат."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fetch_fn(*args, **kwargs))

async def get_binance_spot_signals(user_id: int, settings: dict):
    """Пример обработчика: получает OHLCV Binance Spot и делает анализ (заглушка)."""
    try:
        symbols = settings.get("user", {}).get("monitor_pairs", "BTCUSDT").split(",") or ["BTCUSDT"]
        symbols = [s.strip().upper() for s in symbols if s.strip()] or ["BTCUSDT"]
        for symbol in symbols:
            for tf in TIMEFRAMES:
                try:
                    data = await _fetch_ohlcv_to_thread(get_binance_ohlcv, symbol, tf, False, 500)
                    # TODO: добавить анализ сигналов
                    await asyncio.sleep(0)  # даём контролю вернуться в event-loop
                except Exception as e:
                    print(f"Ошибка при получении данных для {symbol}/{tf} Binance Spot: {e}")
                    await asyncio.sleep(0)
    except Exception as e:
        print(f"Ошибка в обработчике Binance Spot: {e}")

async def get_binance_futures_signals(user_id: int, settings: dict):
    try:
        symbols = settings.get("user", {}).get("monitor_pairs", "BTCUSDT").split(",") or ["BTCUSDT"]
        symbols = [s.strip().upper() for s in symbols if s.strip()] or ["BTCUSDT"]
        for symbol in symbols:
            for tf in TIMEFRAMES:
                try:
                    data = await _fetch_ohlcv_to_thread(get_binance_ohlcv, symbol, tf, True, 500)
                    # TODO: анализ
                    await asyncio.sleep(0)
                except Exception as e:
                    print(f"Ошибка при получении данных для {symbol}/{tf} Binance Futures: {e}")
                    await asyncio.sleep(0)
    except Exception as e:
        print(f"Ошибка в обработчике Binance Futures: {e}")

async def get_bybit_spot_signals(user_id: int, settings: dict):
    try:
        symbols = settings.get("user", {}).get("monitor_pairs", "BTCUSDT").split(",") or ["BTCUSDT"]
        symbols = [s.strip().upper() for s in symbols if s.strip()] or ["BTCUSDT"]
        for symbol in symbols:
            for tf in TIMEFRAMES:
                try:
                    data = await _fetch_ohlcv_to_thread(get_bybit_ohlcv, symbol, tf, False, 500)
                    # TODO: анализ
                    await asyncio.sleep(0)
                except Exception as e:
                    print(f"Ошибка при получении данных для {symbol}/{tf} Bybit Spot: {e}")
                    await asyncio.sleep(0)
    except Exception as e:
        print(f"Ошибка в обработчике Bybit Spot: {e}")

async def get_bybit_futures_signals(user_id: int, settings: dict):
    try:
        symbols = settings.get("user", {}).get("monitor_pairs", "BTCUSDT").split(",") or ["BTCUSDT"]
        symbols = [s.strip().upper() for s in symbols if s.strip()] or ["BTCUSDT"]
        for symbol in symbols:
            for tf in TIMEFRAMES:
                try:
                    data = await _fetch_ohlcv_to_thread(get_bybit_ohlcv, symbol, tf, True, 500)
                    # TODO: анализ
                    await asyncio.sleep(0)
                except Exception as e:
                    print(f"Ошибка при получении данных для {symbol}/{tf} Bybit Futures: {e}")
                    await asyncio.sleep(0)
    except Exception as e:
        print(f"Ошибка в обработчике Bybit Futures: {e}")

async def get_mexc_spot_signals(user_id: int, settings: dict):
    try:
        symbols = settings.get("user", {}).get("monitor_pairs", "BTCUSDT").split(",") or ["BTCUSDT"]
        symbols = [s.strip().upper() for s in symbols if s.strip()] or ["BTCUSDT"]
        for symbol in symbols:
            for tf in TIMEFRAMES:
                try:
                    data = await _fetch_ohlcv_to_thread(get_mexc_ohlcv, symbol, tf, False, 500)
                    # TODO: анализ
                    await asyncio.sleep(0)
                except Exception as e:
                    print(f"Ошибка при получении данных для {symbol}/{tf} MEXC Spot: {e}")
                    await asyncio.sleep(0)
    except Exception as e:
        print(f"Ошибка в обработчике MEXC Spot: {e}")

async def get_mexc_futures_signals(user_id: int, settings: dict):
    try:
        symbols = settings.get("user", {}).get("monitor_pairs", "BTCUSDT").split(",") or ["BTCUSDT"]
        symbols = [s.strip().upper() for s in symbols if s.strip()] or ["BTCUSDT"]
        for symbol in symbols:
            for tf in TIMEFRAMES:
                try:
                    data = await _fetch_ohlcv_to_thread(get_mexc_ohlcv, symbol, tf, True, 500)
                    # TODO: анализ
                    await asyncio.sleep(0)
                except Exception as e:
                    print(f"Ошибка при получении данных для {symbol}/{tf} MEXC Futures: {e}")
                    await asyncio.sleep(0)
    except Exception as e:
        print(f"Ошибка в обработчике MEXC Futures: {e}")

# Map (exchange, trading_type) to handler function
_FETCHER_MAP = {
    ("binance", "spot"):    get_binance_spot_signals,
    ("binance", "futures"): get_binance_futures_signals,
    ("bybit",   "spot"):    get_bybit_spot_signals,
    ("bybit",   "futures"): get_bybit_futures_signals,
    ("mexc",    "spot"):    get_mexc_spot_signals,
    ("mexc",    "futures"): get_mexc_futures_signals,
}

# -----------------------------------------------------------------------------
# Helper functions to read user settings and start proper handlers
# -----------------------------------------------------------------------------

def _get_trading_type(settings: dict) -> str:
    """Return lower-case trading_type from settings (defaults to 'spot')."""
    return str(
        settings.get("trading", {}).get("trading_type")
        or settings.get("trading_type", "spot")
    ).lower()

async def _dispatch_for_user(user_id: int, settings: dict):
    """Start tasks for all enabled exchanges for user."""
    try:
        trading_type = _get_trading_type(settings)
        exchanges_enabled = {
            "binance": settings.get("binance", False),
            "bybit":   settings.get("bybit", False),
            "mexc":    settings.get("mexc", False),
        }

        tasks = []
        for exch, enabled in exchanges_enabled.items():
            if not enabled:
                continue
            handler = _FETCHER_MAP.get((exch, trading_type))
            if handler is None:
                continue  # No implementation yet
            tasks.append(asyncio.create_task(handler(user_id, settings)))

        if tasks:
            # Использую gather с return_exceptions=True чтобы предотвратить общий сбой
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"Ошибка в диспетчере для пользователя {user_id}: {e}")

async def run_all_users_settings():
    """Read all user_settings/*.json files and dispatch tasks."""
    try:
        settings_path = Path("user_settings")
        if not settings_path.exists():
            print("[run_all_users_settings] settings directory not found – skipping")
            return

        tasks = []
        for json_file in settings_path.glob("*.json"):
            try:
                with json_file.open("r", encoding="utf-8") as fh:
                    settings = json.load(fh)
                user_id = int(json_file.stem)
                tasks.append(asyncio.create_task(_dispatch_for_user(user_id, settings)))
            except Exception as exc:
                print(f"[run_all_users_settings] Failed to load {json_file.name}: {exc}")
                continue

        if tasks:
            # Использую gather с return_exceptions=True чтобы предотвратить общий сбой
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"Критическая ошибка в run_all_users_settings: {e}")

async def main():
    try:
        # Инициализируем базу данных (добавляем новые колонки, если их нет)
        await init_db()
        
        # Запускаем детектор Pump/Dump
        asyncio.create_task(pump_dump_main())
        
        # Запускаем задачи с учётом выбранных пользователями бирж/режимов
        asyncio.create_task(run_all_users_settings())
        
        # Запускаем основные стратегии
        await asyncio.gather(*[process_tf(tf) for tf in TIMEFRAMES])
    finally:
        await exchange.close()  # Ensures resources are released

asyncio.run(main())
