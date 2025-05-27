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
from strategy_logic.cm_notifications import process_cm_signal  # Импортируем функцию обработки CM уведомлений
from user_settings import is_cm_notifications_enabled, is_cm_group_notifications_enabled  # Импортируем функции проверки настроек CM уведомлений
from pathlib import Path
import json
from typing import Callable, Awaitable, Dict, Tuple, Any
import requests
import time
import sqlite3
from aiogram.exceptions import TelegramAPIError


async def get_user_favorite_pairs(user_id: int) -> list:
    """Get user's favorite cryptocurrency pairs from database."""
    try:
        with sqlite3.connect("trading_data.db") as conn:
            # Check if the users table exists
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                print(f"[WARNING] Таблица 'users' не существует в базе данных")
                return []
                
            cursor.execute("SELECT crypto_pairs FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if row and row[0]:  # Если есть данные
                # Разделяем строку с парами и удаляем пустые значения
                pairs = [pair.strip() for pair in row[0].split(',') if pair.strip()]
                if pairs:
                    print(f"[INFO] Пользователь {user_id} имеет избранные пары: {pairs}")
                    return pairs
            
            # Если нет избранных пар, используем дефолтные
            print(f"[INFO] Пользователь {user_id} не имеет избранных пар, используем дефолтные")
            return []
    except Exception as e:
        print(f"[ERROR] Ошибка при получении избранных пар пользователя {user_id}: {e}")
        return []


def decide_position_side(cm_sig: str, rsi_sig: str) -> str | None:
    long_sig  = cm_sig == "long"  or rsi_sig == "Long"
    short_sig = cm_sig == "short" or rsi_sig == "Short"

    if long_sig and not short_sig:      # только long‑сигнал
        return "LONG"
    if short_sig and not long_sig:      # только short‑сигнал
        return "SHORT"
    return None                         # конфликт или нет сигналов


bot = Bot(token=config.tg_bot_token, default=DefaultBotProperties(parse_mode="HTML"))

async def safe_send_message(user_id, text, max_retries=3):
    """Безопасная отправка сообщений с обработкой флуд-контроля"""
    for attempt in range(max_retries):
        try:
            return await bot.send_message(user_id, text)
        except TelegramAPIError as e:
            # Проверяем наличие ошибки парсинга HTML
            if "can't parse entities" in str(e):
                # Если проблема с HTML-тегами, пробуем отправить без HTML форматирования
                try:
                    # Заменяем HTML-теги и эмодзи, которые могут вызвать проблемы
                    clean_text = text.replace("<b>", "").replace("</b>", "")
                    clean_text = clean_text.replace("<i>", "").replace("</i>", "")
                    clean_text = clean_text.replace("<code>", "").replace("</code>", "")
                    print(f"[WARN] HTML parsing issue detected. Trying to send clean message.")
                    return await bot.send_message(user_id, clean_text, parse_mode=None)
                except Exception as clean_e:
                    print(f"[ERROR] Failed to send clean message: {clean_e}")
            
            # Проверяем наличие флуд-ограничения
            if "Flood control" in str(e) or "Too Many Requests" in str(e) or "retry after" in str(e).lower():
                # Извлекаем время ожидания из сообщения об ошибке (обычно "retry after X")
                wait_time = 5  # Стандартное время ожидания
                error_str = str(e).lower()
                # Проверяем на наличие числа после "retry after"
                if "retry after" in error_str:
                    try:
                        wait_part = error_str.split("retry after")[1].strip()
                        # Извлекаем числовое значение
                        wait_digits = ''.join(c for c in wait_part if c.isdigit())
                        if wait_digits:
                            wait_time = int(wait_digits) + 1  # +1 секунда для надежности
                    except:
                        pass  # Используем стандартное значение
                
                print(f"[WARN] Telegram flood control hit. Waiting {wait_time} seconds before retry.")
                # Логируем сокращенную версию сообщения, чтобы не спамить консоль
                log_text = text[:100] + "..." if len(text) > 100 else text
                print(f"[WARN] Message queued for delivery: {log_text}")
                
                # Ждем и пробуем снова
                await asyncio.sleep(wait_time)
                # Если это последняя попытка, уменьшаем текст сообщения
                if attempt == max_retries - 1:
                    # Укорачиваем сообщение до базовой информации
                    lines = text.split('\n')
                    # Берем только первые 5-6 строк и последние 2-3
                    if len(lines) > 10:
                        short_text = '\n'.join(lines[:6] + ["..."] + lines[-3:])
                        text = short_text
            else:
                # Если ошибка не связана с флуд-контролем, пробуем еще раз через 1 сек
                print(f"[ERROR] Telegram API error: {e}")
                await asyncio.sleep(1)
    
    # Если все попытки не удались, логируем ошибку
    print(f"[ERROR] Failed to send message to user {user_id} after {max_retries} attempts")
    return None

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
            
            # Извлекаем все необходимые данные из ордера
            symbol = order.get('symbol', 'UNKNOWN')
            timeframe = order.get('timeframe', order.get('interval', '1h'))
            trading_type = order.get('trading_type', 'spot')
            leverage = order.get('leverage', 1)
            qty = order.get('qty', order.get('amount', 0))
            
            # Обработка временных меток
            buy_time_value = order.get('buy_time', order.get('open_time', ''))
            
            # Инициализируем значения по умолчанию
            buy_date = "Неизвестно"
            buy_time = "Неизвестно"
            
            if buy_time_value:
                if isinstance(buy_time_value, str):
                    # Если строка с датой времени
                    if len(buy_time_value) >= 10:
                        try:
                            # Попытка разобрать строку даты-времени
                            dt_obj = datetime.datetime.fromisoformat(buy_time_value.replace('Z', '+00:00'))
                            buy_date = dt_obj.strftime('%Y-%m-%d')
                            buy_time = dt_obj.strftime('%H:%M')
                        except:
                            # Если не получилось разобрать, просто отрезаем части строки
                            buy_date = buy_time_value[:10]
                            if len(buy_time_value) > 10:
                                buy_time = buy_time_value[11:16]
                elif isinstance(buy_time_value, datetime.datetime):
                    # Если это объект datetime
                    buy_date = buy_time_value.strftime('%Y-%m-%d')
                    buy_time = buy_time_value.strftime('%H:%M')
                else:
                    # Если другой тип, пытаемся преобразовать в строку
                    try:
                        buy_time_str = str(buy_time_value)
                        if len(buy_time_str) >= 10:
                            buy_date = buy_time_str[:10]
                            if len(buy_time_str) > 10:
                                buy_time = buy_time_str[11:16]
                    except:
                        # В случае ошибки оставляем значения по умолчанию
                        pass
            
            # Определяем базовую валюту (BTC в BTCUSDT)
            symbol_base = symbol.replace('USDT', '') if 'USDT' in symbol else symbol.split('/')[0] if '/' in symbol else symbol
            
            # Определяем направление (LONG/SHORT)
            position_side = order.get('position_side', order.get('side', 'LONG'))  # По умолчанию LONG, если не указано
            direction = f"{position_side} {'🔰' if position_side == 'LONG' else '🔻'}"
                
            # Закрываем ордер и обновляем данные
            result = await close_order(order_id, current_price)
            
            # Если закрытие не удалось (ордер уже закрыт), выходим
            if not result:
                print(f"Не удалось закрыть ордер {order_id}, возможно он уже закрыт")
                return False
            
            # Получаем обновленный баланс и суточную прибыль
            new_balance = await get_user_balance(user_id)
            # Используем текущую дату для получения суточной прибыли
            current_date = datetime.datetime.now().date()
            daily_profit = await get_daily_profit(user_id, current_date)
            
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
                await safe_send_message(user_id, f"Ошибка при закрытии ордера: не найдена цена входа")
                return False
            
            # Рассчитываем прибыль/убыток
            if position_side == 'SHORT':
                # Для SHORT позиции: прибыль когда текущая цена НИЖЕ цены входа (цена снизилась)
                # Убыток когда текущая цена ВЫШЕ цены входа (цена выросла)
                price_change_percent = ((entry_price - current_price) / entry_price) * 100
                price_change_amount = (entry_price - current_price) * qty
                
                # Для короткой позиции учитываем направление изменения
                pnl_percent = price_change_percent
                pnl = price_change_amount
            else:
                # Для LONG позиции: прибыль когда текущая цена ВЫШЕ цены входа
                pnl_percent = ((current_price - entry_price) / entry_price) * 100
                pnl = (current_price - entry_price) * qty

            # Если используется плечо, умножаем PnL на плечо
            if trading_type == 'futures':
                pnl_percent = pnl_percent * leverage
                pnl = pnl * leverage
                
            # Дополнительный лог для отладки расчетов
            print(f"[PNL_DEBUG] {symbol} {position_side}: entry={entry_price}, exit={current_price}, " 
                  f"change={price_change_percent if position_side == 'SHORT' else ((current_price - entry_price) / entry_price) * 100:.4f}%, "
                  f"qty={qty}, leverage={leverage}, final_pnl={pnl_percent:.4f}% / {pnl:.4f} USDT")

            # Формируем разные сообщения в зависимости от причины закрытия и фактического результата
            # Обратите внимание, что теперь мы проверяем pnl_percent, а не просто причину закрытия
            is_profitable = pnl > 0

            if close_reason == "TP" and is_profitable:
                message = (
                    f"🔴 ЗАКРЫТИЕ ОРДЕРА {symbol} {timeframe}\n\n"
                    f"Биржа: {order.get('exchange', 'Bybit')}\n"
                    f"Тип торговли: {trading_type.upper()}"
                    f"{' | Плечо: x' + str(leverage) if trading_type == 'futures' else ''}\n\n"
                    f"🎯✅ Достигнут Тейк-Профит\n"
                    f"💸🔋Прибыль по сделке: +{abs(pnl_percent):.2f}% (+{abs(pnl):.2f} USDT)\n\n"
                    f"♻️Точка входа: {entry_price:.2f}$\n"
                    f"📈Цена {'продажи' if position_side == 'LONG' else 'закрытия'}: {current_price:.4f}$\n"
                    f"🛑{'Продано' if position_side == 'LONG' else 'Закрыто'}: {qty:.6f} {symbol_base} ({(qty * current_price):.2f} USDT)\n\n"
                    f"📆Сделка была открыта: {buy_date}\n"
                    f"🕐Время открытия: {buy_time} Мск\n"
                    f"📉ТФ открытия сделки: {timeframe}\n"
                    f"Направление: {direction}\n\n"
                    f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                    f"💰 Текущий баланс: {new_balance:.2f} USDT"
                )
            elif close_reason == "SL" or not is_profitable:
                message = (
                    f"🔴 ЗАКРЫТИЕ ОРДЕРА {symbol} {timeframe}\n\n"
                    f"Биржа: {order.get('exchange', 'Bybit')}\n"
                    f"Тип торговли: {trading_type.upper()}"
                    f"{' | Плечо: x' + str(leverage) if trading_type == 'futures' else ''}\n\n"
                    f"📛{'Закрыто по Стоп-лоссу' if close_reason == 'SL' else 'Убыточное закрытие'}\n"
                    f"🤕🪫Убыток по сделке: -{abs(pnl_percent):.2f}% (-{abs(pnl):.2f} USDT)\n\n"
                    f"♻️Точка входа: {entry_price:.2f}$\n"
                    f"📈Цена {'продажи' if position_side == 'LONG' else 'закрытия'}: {current_price:.4f}$\n"
                    f"🛑{'Продано' if position_side == 'LONG' else 'Закрыто'}: {qty:.6f} {symbol_base} ({(qty * current_price):.2f} USDT)\n\n"
                    f"📆Сделка была открыта: {buy_date}\n"
                    f"🕐Время открытия: {buy_time} Мск\n"
                    f"📉ТФ открытия сделки: {timeframe}\n"
                    f"Направление: {direction}\n\n"
                    f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                    f"💰 Текущий баланс: {new_balance:.2f} USDT"
                )
            else:  # TP с убытком или другие случаи
                message = (
                    f"🔴 ЗАКРЫТИЕ ОРДЕРА {symbol} {timeframe}\n\n"
                    f"Биржа: {order.get('exchange', 'Bybit')}\n"
                    f"Тип торговли: {trading_type.upper()}"
                    f"{' | Плечо: x' + str(leverage) if trading_type == 'futures' else ''}\n\n"
                    f"🔄 Сделка закрыта\n"
                    f"{'💸🔋Прибыль' if pnl_percent > 0 else '🤕🪫Убыток'} по сделке: {'+' if pnl_percent > 0 else '-'}{abs(pnl_percent):.2f}% ({'+' if pnl > 0 else '-'}{abs(pnl):.2f} USDT)\n\n"
                    f"♻️Точка входа: {entry_price:.2f}$\n"
                    f"📈Цена {'продажи' if position_side == 'LONG' else 'закрытия'}: {current_price:.4f}$\n"
                    f"🛑{'Продано' if position_side == 'LONG' else 'Закрыто'}: {qty:.6f} {symbol_base} ({(qty * current_price):.2f} USDT)\n\n"
                    f"📆Сделка была открыта: {buy_date}\n"
                    f"🕐Время открытия: {buy_time} Мск\n"
                    f"📉ТФ открытия сделки: {timeframe}\n"
                    f"Направление: {direction}\n\n"
                    f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                    f"💰 Текущий баланс: {new_balance:.2f} USDT"
                )
            
            # Отправляем сообщение пользователю
            await safe_send_message(user_id, message)
            
            return True
        except Exception as e:
            print(f"Ошибка при закрытии ордера: {e}")
            await safe_send_message(user_id, f"Ошибка при закрытии ордера: {e}")
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
    now = datetime.datetime.now()
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

async def process_tf(tf: str):
    while True:
        # Динамически загружаем список пользователей с включенным bybit
        active_users = []
        settings_path = Path("user_settings")
        if settings_path.exists():
            for json_file in settings_path.glob("*.json"):
                try:
                    with json_file.open("r", encoding="utf-8") as fh:
                        settings = json.load(fh)
                    user_id = int(json_file.stem)
                    if settings.get("bybit", False):
                        active_users.append(user_id)
                        print(f"[INFO] Пользователь {user_id} использует Bybit")
                except Exception as e:
                    print(f"[ERROR] Не удалось загрузить настройки пользователя {json_file.name}: {e}")
        
        if not active_users:
            print("[INFO] Нет пользователей с включенным Bybit в настройках")
            await asyncio.sleep(60)  # Ждем минуту перед следующей проверкой
            continue
            
        print(f"[INFO] Активные пользователи Bybit: {active_users}")
        
        btc_df = await fetch_ohlcv("BTCUSDT", "5m", 300)
        
        # Индивидуальная обработка для каждого пользователя
        for uid in active_users:
            # Получаем избранные пары пользователя
            user_favorite_pairs = await get_user_favorite_pairs(uid)
            
            # Определяем символы для торговли - если есть избранные, используем их, иначе дефолтные
            trading_symbols = user_favorite_pairs if user_favorite_pairs else symbols
            
            # Если у пользователя нет избранных пар, используем глобальные символы
            if not trading_symbols:
                trading_symbols = symbols
            
            print(f"[INFO] Пользователь {uid} торгует следующими парами: {trading_symbols}")
            
            for symbol in trading_symbols:
                df5 = await fetch_ohlcv(symbol, "5m", 300)
                dft = await fetch_ohlcv(symbol, tf, 200)
                if df5 is None or dft is None: continue

                ticker = await exchange.fetch_ticker(symbol)
                ctx = Context(
                    ticker_24h=ticker,
                    hourly_volume=df5["volume"].iloc[-12:].sum(),
                    btc_df=btc_df,
                )

                open_order = await get_open_order(uid, "bybit", symbol, tf)

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
                
                # Получаем множественные типы торговли
                from user_settings import load_trading_types
                trading_types = load_trading_types(uid)
                
                print(f"[CONFIG] Пользователь {uid} имеет активные типы торговли: {trading_types}")
                
                # Обрабатываем каждый тип торговли отдельно
                for trading_type in trading_types:
                    leverage = trading_settings["leverage"]
                    
                    print(f"[PROCESSING] Обработка {symbol} {tf} для типа торговли: {trading_type}")
                    
                    # Проверяем открытые ордера для конкретного типа торговли
                    open_order_for_type = await get_open_order(uid, "bybit", symbol, tf)
                    
                    # Если есть открытый ордер, проверяем его тип торговли
                    if open_order_for_type and open_order_for_type.get('trading_type') != trading_type:
                        open_order_for_type = None  # Игнорируем ордер другого типа торговли
                    
                    # Проверка на паттерны Price Action с учетом типа рынка
                    pattern = await get_pattern_price_action(
                        dft[['timestamp', 'open', 'high', 'low', 'close']].values.tolist()[-5:], 
                        trading_type
                    )
                
                    # Calculate indicators
                    dft = calculate_ppo(dft, cm_settings)
                    dft = calculate_ema(dft)
                    cm_signal, last_candle = find_cm_signal(dft, cm_settings)
                    
                    # Отправляем уведомление о сигнале CM, если он есть
                    if cm_signal in ["long", "short"]:
                        current_price = dft["close"].iloc[-1]
                        # Асинхронно обрабатываем уведомления о CM сигнале
                        asyncio.create_task(process_cm_signal(uid, symbol, tf, cm_signal, current_price))
                
                    # Calculate RSI
                    dft = calculate_rsi(dft, period=rsi_settings['RSI_PERIOD'])
                    dft = calculate_ema(dft, 
                                       fast_period=rsi_settings['EMA_FAST'], 
                                       slow_period=rsi_settings['EMA_SLOW'])
                    
                    # Get RSI signals
                    rsi = generate_signals_rsi(dft, 
                                              overbought=rsi_settings['RSI_OVERBOUGHT'],
                                              oversold=rsi_settings['RSI_OVERSOLD'])
                    rsi_signal = rsi['signal_rsi'].iloc[-1]
                
                    # Get divergence signals
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
                    
                    # Добавляем отладочную информацию для анализа сигналов
                    print(f"[SIGNAL_DEBUG] {exchange.id.upper()} {symbol} {tf} => CM={cm_signal}, RSI={rsi_signal}")

                                        # ---------- вход ----------
                    if open_order_for_type is None:
                        # Determine position side (LONG/SHORT)
                        position_side = "LONG"  # Default to LONG
                        
                        # For futures, consider short signals
                        if trading_type == "futures":
                            # Явно проверяем на сигналы LONG и SHORT
                            side = decide_position_side(cm_signal, rsi_signal)

                            if side is None:
                                print(f"[POSITION] conflict / no clear signal – skip")
                                continue      

                            position_side = side
                        
                        # Check active signals based on position side
                        if position_side == "LONG":
                            price_action_active = pattern is not None and pattern != "" and pattern.startswith("Bull")
                            cm_active = cm_signal == "long"
                            moonbot_active = user_moon.check_coin(symbol, df5, ctx) and user_moon.should_place_order(dft)
                            rsi_active = rsi_signal == "Long"
                            
                            # Check bullish divergence
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
                        else:  # SHORT position
                            price_action_active = pattern is not None and pattern != "" and pattern.startswith("Bear")
                            cm_active = cm_signal == "short"
                            moonbot_active = False  # MoonBot only for LONG
                            rsi_active = rsi_signal == "Short"
                            
                            # Check bearish divergence
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
                    
                    # Debug output of signal flags
                    print(f"[DEBUG] {exchange.id.upper()} {symbol} {tf} flags => PA={price_action_active} CM={cm_active} Moon={moonbot_active} RSI={rsi_active} Div={divergence_active}")
                    
                    # Общий флаг для проверки наличия хотя бы одного сигнала на покупку/продажу
                    any_signal = price_action_active or cm_active or moonbot_active or rsi_active or divergence_active
                    
                    # Get current price
                    current_price = dft["close"].iloc[-1]
                    
                    # Open position if any signal is active
                    if any_signal:
                        # Use MoonBot strategy or basic order
                        if moonbot_active:
                            order_dict = user_moon.build_order(dft)
                            entry = order_dict["price"]
                            tp = order_dict["take_profit"]
                            sl = order_dict["stop_loss"]
                        else:
                            # Basic order based on current price
                            entry = current_price
                            
                            # Calculate TP/SL based on position side
                            if position_side == "LONG":
                                tp = entry * 1.03  # +3%
                                sl = entry * 0.98  # -2%
                            else:  # SHORT
                                tp = entry * 0.97  # -3%
                                sl = entry * 1.02  # +2%
                        
                        # Get user balance
                        user_balance = await get_user_balance(uid)
                        
                        # Validate leverage for futures
                        if trading_type == "futures" and leverage < 1:
                            leverage = 1
                        
                        # Calculate position size
                        if trading_type == "futures":
                            # For futures, consider leverage
                            investment_amount = min(user_balance * 0.05, user_balance - 1)  # 5% of balance but leave 1 USDT
                            
                            # Проверяем, достаточно ли средств на балансе для открытия позиции
                            if investment_amount < 5:  # Minimum 5 USDT
                                print(f"[WARNING] Недостаточно средств на счете пользователя {uid}. Баланс: {user_balance}, минимум: 5 USDT")
                                await safe_send_message(uid, f"⚠️ Недостаточно средств для открытия позиции. Минимум: 5 USDT, доступно: {user_balance:.2f} USDT")
                                continue
                            
                            if leverage <= 0:
                                leverage = 1
                                
                            qty = (investment_amount * leverage) / entry
                        else:
                            # For spot trading
                            investment_amount = min(user_balance * 0.05, user_balance - 1)  # 5% of balance but leave 1 USDT
                            
                            # Проверяем, достаточно ли средств на балансе для открытия позиции
                            if investment_amount < 5:  # Minimum 5 USDT
                                print(f"[WARNING] Недостаточно средств на счете пользователя {uid}. Баланс: {user_balance}, минимум: 5 USDT")
                                await safe_send_message(uid, f"⚠️ Недостаточно средств для открытия позиции. Минимум: 5 USDT, доступно: {user_balance:.2f} USDT")
                                continue
                            
                            qty = investment_amount / entry
                        
                        # Validate quantity
                        if qty <= 0:
                            print(f"Error: Invalid quantity {qty} for {symbol}")
                            return
                        
                        # Format quantity
                        qty = round(qty, 6)
                        
                        # Set minimum order size
                        if qty * entry < 5:  # Minimum order size 5 USDT
                            qty = 5 / entry
                            qty = round(qty, 6)
                        
                        try:
                            # Create order with exchange info
                            order_id = await create_order(uid, exchange.id, symbol, tf, position_side, qty, entry, tp, sl, trading_type, leverage)
                            
                            # Получаем обновленный баланс после списания средств
                            new_balance = await get_user_balance(uid)
                            
                            # Определяем эмодзи для типа позиции
                            position_emoji = "🔰" if position_side == "LONG" else "🔻"
                            transaction_emoji = "🟢" if position_side == "LONG" else "🔴"
                            
                            # Формируем сообщение по новому шаблону
                            message = (
                                f"{transaction_emoji} ОТКРЫТИЕ ОРДЕРА {symbol} {tf}\n\n"
                                f"Биржа: {exchange.id.capitalize()}\n"
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
                            
                            await safe_send_message(uid, message)
                            
                        except Exception as e:
                            print(f"Ошибка при создании ордера для {exchange.id} {symbol}: {e}")
                            await safe_send_message(uid, f"Ошибка при создании ордера: {e}")
                
                    # ---------- выход ----------
                    else:
                        last_price = dft["close"].iloc[-1]
                        
                        # Skip processing if the order is already closed
                        if open_order_for_type.get('status', 'OPEN') != 'OPEN':
                            print(f"Пропускаем обработку - ордер {open_order_for_type['id']} уже закрыт")
                            continue
                        
                        # Проверяем различные поля для определения направления позиции
                        position_direction = "LONG"  # По умолчанию LONG
                        if "position_side" in open_order_for_type:
                            position_direction = open_order_for_type["position_side"]
                        elif "side" in open_order_for_type and open_order_for_type["side"].upper() == "SELL":
                            position_direction = "SHORT"
                        elif "position_type" in open_order_for_type:
                            position_direction = open_order_for_type["position_type"]
                        
                        # Определяем, является ли позиция длинной
                        is_long = position_direction.upper() == "LONG"
                        
                        if is_long:
                            hit_tp = last_price >= open_order_for_type["tp_price"]
                            hit_sl = last_price <= open_order_for_type["sl_price"]
                        else:  # SHORT
                            hit_tp = last_price <= open_order_for_type["tp_price"]  # Для SHORT TP ниже цены входа
                            hit_sl = last_price >= open_order_for_type["sl_price"]  # Для SHORT SL выше цены входа

                        if hit_tp or hit_sl:
                            try:
                                # Проверяем статус ордера еще раз непосредственно перед закрытием
                                current_order = await get_order_by_id(open_order_for_type["id"])
                                if current_order and current_order.get('status') == 'CLOSED':
                                    print(f"Пропускаем закрытие - ордер {open_order_for_type['id']} уже закрыт")
                                    continue
                                
                                print(f"Закрываем ордер {open_order_for_type['id']} по {'TP' if hit_tp else 'SL'}")
                                # Закрываем ордер и получаем информацию о P&L
                                close_result = await close_order_with_notification(
                                    uid, open_order_for_type["id"], last_price, "TP" if hit_tp else "SL"
                                )
                                
                                if not close_result:
                                    print(f"Ордер {open_order_for_type['id']} не был закрыт (возможно, уже закрыт)")
                            except Exception as e:
                                print(f"Ошибка при закрытии ордера: {e}")
                                await safe_send_message(uid, f"Ошибка при закрытии ордера: {e}")
            await asyncio.sleep(0.05)   # не душим API
        # await wait_for_next_candle(tf)


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
    ("bybit", "futures"): lambda: ccxt.bybit({"enableRateLimit": True,
                                         "defaultType": "future"}),
    ("mexc",    "spot"):    get_mexc_spot_signals,
    ("mexc",    "futures"): get_mexc_futures_signals,
}

# -----------------------------------------------------------------------------
# Helper functions to read user settings and start proper handlers
# -----------------------------------------------------------------------------

def _get_trading_type(settings: dict) -> str:
    """Return lower-case trading_type from settings (defaults to 'spot')."""
    # Look in multiple places for trading_type
    trading_type = (
        settings.get("trading", {}).get("trading_type") or 
        settings.get("user", {}).get("trading_type") or
        settings.get("trading_type", "spot")
    ).lower()
    
    print(f"[CONFIG] Got trading_type from settings: {trading_type}")
    return trading_type

# ============================= Exchange factory =============================
# Создаём CCXT-экземпляр под каждую (биржа, тип торговли)
EXCHANGE_FACTORY: Dict[Tuple[str, str], Callable[[], ccxt.Exchange]] = {
    ("bybit",   "spot"):    lambda: ccxt.bybit({"enableRateLimit": True, "defaultType": "spot"}),
    ("bybit",   "futures"): lambda: ccxt.bybit({"enableRateLimit": True, "defaultType": "future"}),
    ("binance", "spot"):    lambda: ccxt.binance({"enableRateLimit": True}),
    # Binance USD-M futures
    ("binance", "futures"): lambda: ccxt.binanceusdm({"enableRateLimit": True}),
    ("mexc",    "spot"):    lambda: ccxt.mexc({"enableRateLimit": True}),
    # MEXC futures – usd-m swap (если нет в вашей версии ccxt, обновите)
    ("mexc", "futures"): lambda: ccxt.mexc({"enableRateLimit": True, "defaultType": "swap"}),
}

# --------------------------- Универсальный fetch ----------------------------
async def fetch_ohlcv_ccxt(exchange: ccxt.Exchange, symbol: str, timeframe: str = "1h", limit: int = 500,
                           retries: int = 3, delay: int = 5):
    """Получить OHLCV через CCXT. Пробуем несколько вариантов символа, чтобы избежать ошибок BadSymbol."""
    # Подготовим список вариантов записи торговой пары
    symbol_variants = [symbol]
    if symbol.endswith("USDT") and "/" not in symbol:
        core = symbol[:-4]
        symbol_variants.append(f"{core}/USDT")          # BTC/USDT
        symbol_variants.append(f"{core}/USDT:USDT")      # для USD-M фьючерсов Binance, MEXC
    else:
        # если уже с "/", добавим вариант без слеша
        symbol_variants.append(symbol.replace("/USDT", "USDT"))

    last_exception = None

    # ---------------------- MEXC кастомный хак ----------------------
# ---------------------- MEXC кастомный хак ----------------------
    if exchange.id == 'mexc':
        # Проверяем, работаем ли мы с фьючерсами
        is_futures = exchange.options.get('defaultType') == 'swap'
        
        # Проверяем поддерживаемые таймфреймы
        supported_timeframes = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"}
        if timeframe not in supported_timeframes:
            print(f"Warning: {timeframe} not supported by MEXC, using 1h as fallback for {symbol}")
            timeframe = "1h"
    # ------------------------- Основные попытки ---------------------
    for sym in symbol_variants:
        for attempt in range(retries):
            try:
                ohlcv = await exchange.fetch_ohlcv(sym, timeframe, limit=limit)
                df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["hl2"] = (df["high"] + df["low"]) / 2
                return df
            except (ccxt.BadSymbol, ccxt.BadRequest) as e:
                last_exception = e
                # пробуем следующий вариант символа
                break
            except (ccxt.RequestTimeout, ccxt.DDoSProtection) as e:
                print(f"Timeout/DDoS {exchange.id} {sym} – retry {attempt+1}/{retries}")
                last_exception = e
                await asyncio.sleep(delay)
                continue
            except Exception as e:
                last_exception = e
                break

    # Если все попытки не удались – логируем
    print(f"[fetch_ohlcv_ccxt] Failed {exchange.id} {symbol} ({symbol_variants}) {timeframe}: {last_exception}")
    return None

# ------------------------------ Общий worker -------------------------------
async def process_user_exchange(user_id: int, settings: dict, exch_name: str, trading_type: str, symbols: list[str]):
    """Полный цикл сканирования / трейдинга для пользователя на конкретной бирже."""
    try:
        # Инициализируем CCXT-объект
        print(f"[CONFIG] Creating exchange {exch_name} with type {trading_type} for user {user_id}")
        
        # Fix for Binance - force futures if in user settings
        if exch_name == "binance" and trading_type != "futures":
            # Check user settings explicitly for binance trading type
            user_trading_settings = load_trading_settings(user_id)
            if user_trading_settings.get("trading_type", "").lower() == "futures":
                print(f"[CONFIG] FIXING: User {user_id} has futures in settings but got {trading_type}, changing to futures")
                trading_type = "futures"
        
        exchange: ccxt.Exchange = EXCHANGE_FACTORY[(exch_name, trading_type)]()
        print(f"[START] user={user_id} exch={exch_name} type={trading_type} (settings_type={settings.get('trading', {}).get('trading_type')})")
        
        while True:
            try:
                # Получаем избранные пары пользователя
                user_favorite_pairs = await get_user_favorite_pairs(user_id)
                
                # Определяем символы для торговли - если есть избранные, используем их, иначе используем переданные
                trading_symbols = user_favorite_pairs if user_favorite_pairs else symbols
                
                btc_df = await fetch_ohlcv_ccxt(exchange, "BTCUSDT", "5m", 300)
                if btc_df is None:
                    await asyncio.sleep(10)
                    continue
                
                for tf in TIMEFRAMES:
                    for symbol in trading_symbols:
                        df5 = await fetch_ohlcv_ccxt(exchange, symbol, "5m", 300)
                        dft = await fetch_ohlcv_ccxt(exchange, symbol, tf, 200)
                        if df5 is None or dft is None:
                            continue
                        ticker = await exchange.fetch_ticker(symbol)
                        ctx = Context(
                            ticker_24h=ticker,
                            hourly_volume=df5["volume"].iloc[-12:].sum(),
                            btc_df=btc_df,
                        )

                        # *** переиспользуем внутр. функцию, чтобы не дублировать код ***
                        await internal_trade_logic(
                            exchange_name=exch_name,
                            user_id=user_id,
                            df5=df5,
                            dft=dft,
                            ctx=ctx,
                            tf=tf,
                            symbol=symbol,
                            settings=settings,
                            trading_type=trading_type,
                        )

                    await asyncio.sleep(0.05)  # не душим API
                # await wait_for_next_candle("1m")
            except Exception as loop_exc:
                print(f"[ERROR] user={user_id} exch={exch_name}: {loop_exc}")
                await asyncio.sleep(5)
    finally:
        await exchange.close()

# ----------------------- Диспетчер для одного пользователя -------------------
async def _dispatch_for_user(user_id: int, settings: dict):
    """Start tasks for all enabled exchanges for user with support for multiple trading types."""
    try:
        # Импортируем функцию для загрузки множественных типов торговли
        from user_settings import load_trading_types
        
        # Получаем множественные типы торговли
        trading_types = load_trading_types(user_id)
        print(f"[CONFIG] Активные типы торговли для пользователя {user_id}: {trading_types}")
        
        # Получаем избранные пары пользователя
        user_favorite_pairs = await get_user_favorite_pairs(user_id)
        
        # список символов, если не заданы избранные и нет в настройках - BTCUSDT
        if user_favorite_pairs:
            symbols = user_favorite_pairs
        else:
            symbols_cfg = settings.get("user", {}).get("monitor_pairs", "BTCUSDT")
            symbols = [s.strip().upper() for s in symbols_cfg.split(",") if s.strip()] or ["BTCUSDT"]

        print(f"[CONFIG] Торговые пары для пользователя {user_id}: {symbols}")
        
        tasks = []
        for exch_name in ("binance", "bybit", "mexc"):
            if not settings.get(exch_name, False):
                continue
            # Bybit остаётся в первоначальном process_tf (функция ниже) если нужно
            if exch_name == "bybit":
                continue  # Bybit обслуживается старым process_tf
            
            # Запускаем задачи для каждого типа торговли
            for trading_type in trading_types:
                print(f"[CONFIG] Запуск {exch_name} с типом торговли {trading_type} для пользователя {user_id}")
                
                tasks.append(
                    asyncio.create_task(
                        process_user_exchange(user_id, settings, exch_name, trading_type, symbols)
                    )
                )
        if tasks:
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

# =============================================================================
#  Actual implementation of internal_trade_logic with proper trading logic.
# =============================================================================
async def internal_trade_logic(*args, **kwargs):
    """Real trading logic for all exchange handlers (Binance, MEXC, etc.)"""
    try:
        # Extract parameters from *args and **kwargs
        if kwargs:
            exchange_name = kwargs.get('exchange_name')
            user_id = kwargs.get('user_id')
            df5 = kwargs.get('df5')
            dft = kwargs.get('dft')
            ctx = kwargs.get('ctx')
            tf = kwargs.get('tf')
            symbol = kwargs.get('symbol')
            settings = kwargs.get('settings')
            trading_type = kwargs.get('trading_type')
        else:
            # Extract from positional args if needed
            exchange_name = args[0] if len(args) > 0 else None
            user_id = args[1] if len(args) > 1 else None
            df5 = args[2] if len(args) > 2 else None
            dft = args[3] if len(args) > 3 else None
            ctx = args[4] if len(args) > 4 else None
            tf = args[5] if len(args) > 5 else None
            symbol = args[6] if len(args) > 6 else None
            settings = args[7] if len(args) > 7 else None
            trading_type = args[8] if len(args) > 8 else None
            
        if not all([user_id, symbol, tf, df5 is not None, dft is not None]):
            print(f"Missing required parameters in internal_trade_logic")
            return
            
        print(f"Processing {exchange_name} {symbol}/{tf} for user {user_id}")
            
        # Check for existing open order
        open_order = await get_open_order(user_id, exchange_name, symbol, tf)
        
        # Если есть открытый ордер, проверяем его тип торговли
        if open_order and open_order.get('trading_type') != trading_type:
            open_order = None  # Игнорируем ордер другого типа торговли
        
        # Get user-specific settings
        user_moon = StrategyMoonBot(load_strategy_params(user_id))
        cm_settings = load_cm_settings(user_id)
        divergence_settings = load_divergence_settings(user_id)
        rsi_settings = load_rsi_settings(user_id)
        trading_settings = load_trading_settings(user_id)
        leverage = trading_settings.get("leverage", 1)
        
        # Get Price Action patterns
        pattern = await get_pattern_price_action(
            dft[['timestamp', 'open', 'high', 'low', 'close']].values.tolist()[-5:], 
            trading_type
        )
        
        # Calculate indicators
        dft = calculate_ppo(dft, cm_settings)
        dft = calculate_ema(dft)
        cm_signal, last_candle = find_cm_signal(dft, cm_settings)
        
        # Отправляем уведомление о сигнале CM, если он есть
        if cm_signal in ["long", "short"]:
            current_price = dft["close"].iloc[-1]
            # Асинхронно обрабатываем уведомления о CM сигнале
            asyncio.create_task(process_cm_signal(user_id, symbol, tf, cm_signal, current_price))
        
        # Calculate RSI
        dft = calculate_rsi(dft, period=rsi_settings['RSI_PERIOD'])
        dft = calculate_ema(dft, 
                           fast_period=rsi_settings['EMA_FAST'], 
                           slow_period=rsi_settings['EMA_SLOW'])
        
        # Get RSI signals
        rsi = generate_signals_rsi(dft, 
                                  overbought=rsi_settings['RSI_OVERBOUGHT'],
                                  oversold=rsi_settings['RSI_OVERSOLD'])
        rsi_signal = rsi['signal_rsi'].iloc[-1]
        
        # Get divergence signals
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
        
        # Добавляем отладочную информацию для анализа сигналов
        print(f"[SIGNAL_DEBUG] {exchange_name} {symbol} {tf} => CM={cm_signal}, RSI={rsi_signal}")
        
        # Determine position side (LONG/SHORT)
        position_side = "LONG"  # Default to LONG
        
        # For futures, consider short signals
        if trading_type == "futures":
            # Явно проверяем на сигналы LONG и SHORT
            side = decide_position_side(cm_signal, rsi_signal)

            if side is None:
                print(f"[POSITION] conflict / no clear signal – skip")
                return      

            position_side = side
        
        # Initialize signal flags before if/else blocks
        price_action_active = False
        cm_active = False
        moonbot_active = False
        rsi_active = False
        divergence_active = False
        divergence_type = ""
        # pattern is already initialized from get_pattern_price_action

        # Check active signals based on position side
        if position_side == "LONG":
            price_action_active = pattern is not None and pattern != "" and pattern.startswith("Bull")
            cm_active = cm_signal == "long"
            moonbot_active = user_moon.check_coin(symbol, df5, ctx) and user_moon.should_place_order(dft)
            rsi_active = rsi_signal == "Long"
            
            # Check bullish divergence
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
        else:  # SHORT position
            price_action_active = pattern is not None and pattern != "" and pattern.startswith("Bear")
            cm_active = cm_signal == "short"
            moonbot_active = False  # MoonBot only for LONG
            rsi_active = rsi_signal == "Short"
            
            # Check bearish divergence
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
        
        # Debug output of signal flags
        print(f"[DEBUG] {exchange_name.upper()} {symbol} {tf} flags => PA={price_action_active} CM={cm_active} Moon={moonbot_active} RSI={rsi_active} Div={divergence_active}")
        
        # Общий флаг для проверки наличия хотя бы одного сигнала на покупку/продажу
        any_signal = price_action_active or cm_active or moonbot_active or rsi_active or divergence_active
        
        # Get current price
        current_price = dft["close"].iloc[-1]
        
        # Open position if any signal is active
        if any_signal:
            # Use MoonBot strategy or basic order
            if moonbot_active:
                order_dict = user_moon.build_order(dft)
                entry = order_dict["price"]
                tp = order_dict["take_profit"]
                sl = order_dict["stop_loss"]
            else:
                # Basic order based on current price
                entry = current_price
                
                # Calculate TP/SL based on position side
                if position_side == "LONG":
                    tp = entry * 1.03  # +3%
                    sl = entry * 0.98  # -2%
                else:  # SHORT
                    tp = entry * 0.97  # -3%
                    sl = entry * 1.02  # +2%
            
            # Get user balance
            user_balance = await get_user_balance(user_id)
            
            # Validate leverage for futures
            if trading_type == "futures" and leverage < 1:
                leverage = 1
            
            # Calculate position size
            if trading_type == "futures":
                # For futures, consider leverage
                investment_amount = user_balance * 0.05  # 5% of balance
                
                # Проверяем, достаточно ли средств на балансе для открытия позиции
                if investment_amount > user_balance:
                    print(f"[WARNING] Недостаточно средств на счете пользователя {user_id}. Баланс: {user_balance}, требуется: {investment_amount}")
                    await safe_send_message(user_id, f"⚠️ Недостаточно средств для открытия позиции. Необходимо: {investment_amount:.2f} USDT, доступно: {user_balance:.2f} USDT")
                    return
                
                if leverage <= 0:
                    leverage = 1
                    
                qty = (investment_amount * leverage) / entry
            else:
                # For spot trading
                investment_amount = user_balance * 0.05  # 5% of balance
                
                # Проверяем, достаточно ли средств на балансе для открытия позиции
                if investment_amount > user_balance:
                    print(f"[WARNING] Недостаточно средств на счете пользователя {user_id}. Баланс: {user_balance}, требуется: {investment_amount}")
                    await safe_send_message(user_id, f"⚠️ Недостаточно средств для открытия позиции. Необходимо: {investment_amount:.2f} USDT, доступно: {user_balance:.2f} USDT")
                    return
                
                qty = investment_amount / entry
            
            # Validate quantity
            if qty <= 0:
                print(f"Error: Invalid quantity {qty} for {symbol}")
                return
            
            # Format quantity
            qty = round(qty, 6)
            
            # Set minimum order size
            if qty * entry < 10:  # Minimum order size 10 USDT
                qty = 10 / entry
                qty = round(qty, 6)
            
            try:
                # Create order with exchange info
                order_id = await create_order(user_id, exchange_name, symbol, tf, position_side, qty, entry, tp, sl, trading_type, leverage)
                
                # Получаем обновленный баланс после списания средств
                new_balance = await get_user_balance(user_id)
                
                # Определяем эмодзи для типа позиции
                position_emoji = "🔰" if position_side == "LONG" else "🔻"
                transaction_emoji = "🟢" if position_side == "LONG" else "🔴"
                
                # Формируем сообщение по новому шаблону
                message = (
                    f"{transaction_emoji} ОТКРЫТИЕ ОРДЕРА {symbol} {tf}\n\n"
                    f"Биржа: {exchange_name.capitalize()}\n"
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
                
                await safe_send_message(user_id, message)
                
            except Exception as e:
                print(f"Ошибка при создании ордера для {exchange_name} {symbol}: {e}")
                await safe_send_message(user_id, f"Ошибка при создании ордера: {e}")
        
        # EXIT LOGIC (with open order)
        else:
            last_price = dft["close"].iloc[-1]
            
            # Skip if already closed
            if open_order.get('status', 'OPEN') != 'OPEN':
                return
            
            # Determine position direction
            position_direction = "LONG"  # Default
            if "position_side" in open_order:
                position_direction = open_order["position_side"]
            elif "side" in open_order and open_order["side"].upper() == "SELL":
                position_direction = "SHORT"
            elif "position_type" in open_order:
                position_direction = open_order["position_type"]
            
            # Check if long position
            is_long = position_direction.upper() == "LONG"
            
            # Check TP/SL conditions based on position direction
            if is_long:
                hit_tp = last_price >= open_order["tp_price"]
                hit_sl = last_price <= open_order["sl_price"]
            else:  # SHORT
                hit_tp = last_price <= open_order["tp_price"]
                hit_sl = last_price >= open_order["sl_price"]
            
            # Close if TP/SL hit
            if hit_tp or hit_sl:
                try:
                    # Double-check order status
                    current_order = await get_order_by_id(open_order["id"])
                    if current_order and current_order.get('status') == 'CLOSED':
                        return
                    
                    # Get trading type and leverage before closing the order
                    trading_type = open_order.get('trading_type', 'spot')
                    leverage = open_order.get('leverage', 1)
                    
                    # Print debug info
                    print(f"[CLOSE] {exchange_name} {symbol} {position_direction} with leverage {leverage} (trading_type={trading_type})")
                    
                    # Close with notification
                    await close_order_with_notification(
                        user_id, open_order["id"], last_price, "TP" if hit_tp else "SL"
                    )
                    
                except Exception as e:
                    print(f"Error closing order: {e}")
                    await safe_send_message(user_id, f"Ошибка при закрытии ордера: {e}")
    except Exception as e:
        print(f"Error in internal_trade_logic: {e}")

asyncio.run(main())
