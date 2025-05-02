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
from db.orders import get_active_btc_position_size, get_daily_profit
import pytz
from dateutil.parser import parse
from db.orders import get_user_open_orders, get_user_balance
from strategy_logic.user_strategy_params import load_user_params
from strategy_logic.pump_dump import pump_dump_main
from strategy_logic.cm_settings import load_cm_settings  # Импортируем функцию загрузки настроек CM
from strategy_logic.divergence_settings import load_divergence_settings  # Импортируем функцию загрузки настроек дивергенции
from strategy_logic.rsi_settings import load_rsi_settings  # Импортируем функцию загрузки настроек RSI
from strategy_logic.trading_settings import load_trading_settings  # Импортируем функцию загрузки настроек торговли


bot = Bot(token=config.tg_bot_token, default=DefaultBotProperties(parse_mode="HTML"))

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
                
                # Загружаем индивидуальные настройки торговли для пользователя
                trading_settings = load_trading_settings(uid)
                trading_type = trading_settings["trading_type"]
                leverage = trading_settings["leverage"]
                
                # ---------- вход ----------
                if open_order is None:
                    # Проверка на паттерны Price Action (перенесено выше для использования в условии)
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
                            current_price = dft["close"].iloc[-1]
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
                        
                        # Рассчитываем сумму инвестиции (5% от баланса)
                        investment_amount = user_balance * 0.05
                        
                        # Рассчитываем объем позиции с учетом типа торговли и плеча
                        if trading_type == "futures":
                            # Для фьючерсов учитываем плечо при расчете объема
                            qty = (investment_amount * leverage) / entry
                        else:
                            # Для спот торговли - обычный расчет
                            qty = investment_amount / entry
                        
                        # Форматируем количество с учетом минимального шага для торговли
                        qty = round(qty, 6)  # Округляем до 6 знаков после запятой
                        
                        # Если объем слишком мал, установим минимальный
                        if qty * entry < 10:  # Минимальный размер ордера 10 USDT
                            qty = 10 / entry
                            qty = round(qty, 6)
                        
                        # Создаем ордер с автоматическим списанием средств с баланса
                        try:
                            await create_order(uid, symbol, tf, position_side, qty, entry, tp, sl, trading_type, leverage)
                            
                            # Получаем обновленный баланс после списания средств
                            new_balance = await get_user_balance(uid)
                            
                            # Формируем сообщение с сигналами по новому шаблону
                            # Для каждого сигнала: ✅ если активен, ❌ если не активен
                            price_action_status = "✅" if price_action_active else "❌"
                            cm_status = "✅" if cm_active else "❌"
                            moonbot_status = "✅" if moonbot_active else "❌"
                            rsi_status = "✅" if rsi_active else "❌"
                            divergence_status = "✅" if divergence_active else "❌"
                            
                            # Определяем эмодзи для типа позиции
                            position_emoji = "🔰" if position_side == "LONG" else "🔻"
                            transaction_emoji = "🟢" if position_side == "LONG" else "🔴"
                            position_text = "ПОКУПКА" if position_side == "LONG" else "ПРОДАЖА"
                            
                            # Добавляем информацию о типе торговли и плече
                            trading_info = f"Тип торговли: {trading_type.upper()}"
                            if trading_type == "futures":
                                trading_info += f" | Плечо: x{leverage}"
                            
                            # Формируем сообщение по новому шаблону
                            message = (
                                f"{transaction_emoji} {position_text} {symbol} {tf}\n"
                                f"{trading_info}\n"
                                f"💸Объем: {qty:.6f} {symbol.replace('USDT', '')} ({(qty * entry):.2f} USDT)\n\n"
                                f"♻️Точка входа: {entry:.2f}$\n"
                                f"Направление: {position_side} {position_emoji}\n\n"
                                f"🎯TP: {tp:.4f}$\n"
                                f"📛SL: {sl:.4f}$\n\n"
                                f"⚠️Сделка открыта по сигналам с:\n"
                                f"{price_action_status} Price Action {pattern if price_action_active else ''}\n"
                                f"{cm_status} CM\n"
                                f"{moonbot_status} MoonBot\n"
                                f"{rsi_status} RSI\n"
                                f"{divergence_status} Divergence {divergence_type if divergence_active else ''}\n\n"
                                f"💰 Баланс: {new_balance:.2f} USDT (-{(investment_amount):.2f} USDT)"
                            )
                            
                            await bot.send_message(uid, message)
                            
                        except Exception as e:
                            print(f"Ошибка при создании ордера: {e}")
                            await bot.send_message(uid, f"Ошибка при создании ордера: {e}")
                # ---------- выход ----------
                else:
                    last_price = dft["close"].iloc[-1]
                    side = open_order["side"]
                    
                    # Проверка на достижение TP/SL в зависимости от типа позиции
                    if side == "LONG":
                        hit_tp = last_price >= open_order["tp_price"]
                        hit_sl = last_price <= open_order["sl_price"]
                    else:  # SHORT
                        hit_tp = last_price <= open_order["tp_price"]
                        hit_sl = last_price >= open_order["sl_price"]

                    if hit_tp or hit_sl:
                        try:
                            # Определяем причину закрытия для сообщения
                            close_reason = "TP" if hit_tp else "SL"
                            
                            # Закрываем ордер и получаем информацию о P&L с автоматическим возвратом средств
                            closed_order = await close_order(open_order["id"], last_price)
                            
                            # Получаем данные из ордера
                            user_id = closed_order["user_id"]
                            entry_price = closed_order["coin_buy_price"]
                            exit_price = closed_order["coin_sale_price"]
                            qty = closed_order["qty"]
                            position_side = closed_order["side"]
                            pnl_percent = closed_order["pnl_percent"]
                            pnl_usdt = closed_order["pnl_usdt"]
                            return_amount = closed_order["return_amount_usdt"]
                            trading_type = closed_order["trading_type"]
                            leverage = closed_order["leverage"]
                            
                            # Получаем обновленный баланс после возврата средств
                            new_balance = await get_user_balance(uid)
                            
                            # Определяем цвет и эмодзи в зависимости от P&L и типа позиции
                            if position_side == "LONG":
                                position_emoji = "🔰"
                                transaction_emoji = "🔴"  # Продажа при закрытии LONG
                                action_text = "ПРОДАЖА"
                            else:  # SHORT
                                position_emoji = "🔻"
                                transaction_emoji = "🟢"  # Покупка при закрытии SHORT
                                action_text = "ПОКУПКА"
                                
                            pnl_emoji = "🔋" if pnl_percent > 0 else "🪫"
                            pnl_text = "Прибыль" if pnl_percent > 0 else "Убыток"
                            
                            # Получаем текущую дату и время в московском времени (+3 часа)
                            moscow_tz = pytz.timezone('Europe/Moscow')
                            now = dt.datetime.now(moscow_tz)
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
                            
                            # Добавляем информацию о типе торговли и плече
                            trading_info = f"Тип торговли: {trading_type.upper()}"
                            if trading_type == "futures":
                                trading_info += f" | Плечо: x{leverage}"
                            
                            # Создаем сообщение в зависимости от причины закрытия (TP или SL)
                            if hit_tp:
                                message = (
                                    f"{transaction_emoji} <b>{action_text}</b> {symbol} {tf}\n"
                                    f"{trading_info}\n\n"
                                    f"🎯✅ Достигнут Тейк-Профит\n"
                                    f"💸{pnl_emoji}{pnl_text} по сделке: {pnl_percent:.2f}% ({pnl_usdt:.2f} USDT)\n\n"
                                    f"♻️Точка входа: {entry_price:.2f}$\n"
                                    f"📈Цена {action_text.lower()}: {exit_price:.4f}$\n"
                                    f"🛑{action_text.capitalize()}: {qty:.6f} {symbol.replace('USDT', '')} ({(qty * exit_price):.2f} USDT)\n\n"
                                    f"📆Сделка была открыта: {buy_date}\n"
                                    f"🕐Время открытия: {buy_time} Мск\n"
                                    f"📉ТФ открытия сделки: {tf}\n"
                                    f"Направление: {position_side} {position_emoji}\n\n"
                                    f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                                    f"💰 Текущий баланс: {new_balance:.2f} USDT"
                                )
                            else:  # hit_sl
                                message = (
                                    f"{transaction_emoji} <b>{action_text}</b> {symbol} {tf}\n"
                                    f"{trading_info}\n"
                                    f"📛Закрыто по Стоп-лоссу\n"
                                    f"🤕{pnl_emoji}Убыток по сделке: {pnl_percent:.2f}% ({pnl_usdt:.2f} USDT)\n\n"
                                    f"♻️Точка входа: {entry_price:.2f}$\n"
                                    f"📈Цена {action_text.lower()}: {exit_price:.4f}$\n"
                                    f"🛑{action_text.capitalize()}: {qty:.6f} {symbol.replace('USDT', '')} ({(qty * exit_price):.2f} USDT)\n\n"
                                    f"📆Сделка была открыта: {buy_date}\n"
                                    f"🕐Время открытия: {buy_time} Мск\n"
                                    f"📉ТФ открытия сделки: {tf}\n"
                                    f"Направление: {position_side} {position_emoji}\n\n"
                                    f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                                    f"💰 Текущий баланс: {new_balance:.2f} USDT"
                                )
                            
                            await bot.send_message(uid, message)
                            
                        except Exception as e:
                            await bot.send_message(uid, f"Ошибка при закрытии ордера: {e}")
                            print(f"Ошибка при закрытии ордера: {e}")
            await asyncio.sleep(0.05)   # не душим API
        await wait_for_next_candle(tf)

async def main():
    try:
        asyncio.create_task(pump_dump_main())
        
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
        
        # Получаем данные из заказа
        entry_price = order['coin_buy_price']
        position_side = order['side']
        trading_type = order['trading_type']
        leverage = order['leverage']
        
        # Рассчитываем прибыль/убыток с учетом типа позиции и плеча
        if position_side == 'LONG':
            price_change_percent = ((current_price - entry_price) / entry_price) * 100
            if trading_type == 'futures':
                pnl_percent = price_change_percent * leverage
            else:
                pnl_percent = price_change_percent
                
            pnl = (current_price - entry_price) * order['qty']
        else:  # SHORT
            price_change_percent = ((entry_price - current_price) / entry_price) * 100
            pnl_percent = price_change_percent * leverage  # SHORT возможен только на futures
            pnl = (entry_price - current_price) * order['qty']
            
        # Получаем текущую дату и время в МСК
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = dt.datetime.now(moscow_tz)
        current_date = now.strftime('%d.%m.%Y')
        current_time = now.strftime('%H:%M')
        
        # Конвертируем время открытия ордера из UTC в МСК
        buy_time_utc = dt.datetime.fromtimestamp(order['buy_time'].timestamp())
        buy_time_moscow = pytz.utc.localize(buy_time_utc).astimezone(moscow_tz)
        buy_date = buy_time_moscow.strftime('%d.%m.%Y')
        buy_time = buy_time_moscow.strftime('%H:%M')
        
        # Получаем суммарный профит за день
        daily_profit = await get_daily_profit(user_id, now.date())
        
        # Получаем обновленный баланс после возврата средств
        new_balance = await get_user_balance(user_id)
        
        # Определяем направление и символ
        position_emoji = "🔰" if position_side == "LONG" else "🔻"
        transaction_emoji = "🔴" if position_side == "LONG" else "🟢"
        action_text = "ПРОДАЖА" if position_side == "LONG" else "ПОКУПКА"
        
        # Получаем базовый символ (без USDT)
        symbol_base = order['symbol'].replace('USDT', '')
        
        # Добавляем информацию о типе торговли и плече
        trading_info = f"Тип торговли: {trading_type.upper()}"
        if trading_type == "futures":
            trading_info += f" | Плечо: x{leverage}"
            
        # Определяем эмодзи в зависимости от P&L
        pnl_emoji = "🔋" if pnl_percent > 0 else "🪫"
        pnl_text = "Прибыль" if pnl_percent > 0 else "Убыток"
        
        # Формируем разные сообщения в зависимости от причины закрытия
        if close_reason == "TP":
            message = (
                f"{transaction_emoji} <b>{action_text}</b> {order['symbol']} {order['interval']}\n"
                f"{trading_info}\n\n"
                f"🎯✅ Достигнут Тейк-Профит\n"
                f"💸{pnl_emoji}{pnl_text} по сделке: {pnl_percent:.2f}% ({pnl:.2f} USDT)\n\n"
                f"♻️Точка входа: {entry_price:.2f}$\n"
                f"📈Цена {action_text.lower()}: {current_price:.4f}$\n"
                f"🛑{action_text.capitalize()}: {order['qty']:.6f} {symbol_base} ({(order['qty'] * current_price):.2f} USDT)\n\n"
                f"📆Сделка была открыта: {buy_date}\n"
                f"🕐Время открытия: {buy_time} Мск\n"
                f"📉ТФ открытия сделки: {order['interval']}\n"
                f"Направление: {position_side} {position_emoji}\n\n"
                f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                f"💰 Текущий баланс: {new_balance:.2f} USDT"
            )
        else:  # SL
            message = (
                f"{transaction_emoji} <b>{action_text}</b> {order['symbol']} {order['interval']}\n"
                f"{trading_info}\n"
                f"📛Закрыто по Стоп-лоссу\n"
                f"🤕{pnl_emoji}{pnl_text} по сделке: {pnl_percent:.2f}% ({pnl:.2f} USDT)\n\n"
                f"♻️Точка входа: {entry_price:.2f}$\n"
                f"📈Цена {action_text.lower()}: {current_price:.4f}$\n"
                f"🛑{action_text.capitalize()}: {order['qty']:.6f} {symbol_base} ({(order['qty'] * current_price):.2f} USDT)\n\n"
                f"📆Сделка была открыта: {buy_date}\n"
                f"🕐Время открытия: {buy_time} Мск\n"
                f"📉ТФ открытия сделки: {order['interval']}\n"
                f"Направление: {position_side} {position_emoji}\n\n"
                f"Общий профит за день: {'+' if daily_profit > 0 else ''} {daily_profit:.2f} USDT {'💸🔋' if daily_profit > 0 else '🤕'}\n"
                f"💰 Текущий баланс: {new_balance:.2f} USDT"
            )
        
        # Отправляем сообщение пользователю
        await bot.send_message(user_id, message)
        
        return True
    return False
