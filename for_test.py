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
        # user_ids = await get_all_user_id()
        now = datetime.datetime.now().strftime('%d-%m-%Y %H:%M')
        btc_df_5m = await fetch_ohlcv("BTCUSDT", "5m", limit=300)  # ← один запрос
        btc_delta_24h = moon._delta(btc_df_5m["close"], 288)       # пример расчёта


        for symbol in symbols:
            try:
                df_5m = await fetch_ohlcv(symbol, "5m", limit=300)
                if df_5m is None:                 # <-- проверки как у вас
                    continue

                # ----- Moon Bot‑контекст -----
                hourly_vol = df_5m["volume"].iloc[-12:].sum()
                ticker_24h = await exchange.fetch_ticker(symbol)
                ctx = Context(                          # ← просто вызываем dataclass
                    ticker_24h=ticker_24h,
                    hourly_volume=hourly_vol,
                    btc_df=btc_df_5m,
                )

                # ----- Moon Bot‑фильтры + сигнал -----
                if moon.check_coin(symbol, df_5m, ctx) and moon.should_place_order(df_5m):
                    order = moon.build_order(df_5m)   # ← уже содержит TP/SL

                    # ======= только показать, НЕ покупать =======
                    text = (
                        f"🚀 <b>MoonBot LONG сигнал</b>\n"
                        f"<code>{symbol}</code>\n"
                        f"Цена входа: {order['price']:.4f}\n"
                        f"Объём (USDT): {moon.p['OrderSize']}\n"
                        f"TP (+{moon.p['TakeProfit']} %): {order['take_profit']:.4f}\n"
                        f"SL ({moon.p['StopLoss']} %): {order['stop_loss']:.4f}"
                    )
                    await bot.send_message(chat_id=6634277726, text=text)

                # Получение и подготовка данных
                # df = await fetch_ohlcv(symbol, timeframe)
                # if df is None or len(df) < 3:
                #     print(f"Недостаточно данных для {symbol} на {timeframe}")
                #     continue
                    
                # # Расчет индикаторов
                # df = calculate_ppo(df)
                # df = calculate_ema(df)
                # df = calculate_rsi(df)
                # df = generate_signals_rsi(df)
                # df = detect_vsa_signals(df)
                
                # # Определение сигналов
                # finish, last_candle = find_last_extreme(df)
                
                # # Не получаем паттерн здесь, так как он будет получен в check_signals_near_level
                # # price_action_pattern = await get_pattern_price_action(df[-3:].values.tolist(), "spot")
                
                # # Find support and resistance levels - передаем текущий таймфрейм
                # levels = find_support_resistance(df, timeframe=timeframe)
                # signals_near_level = await check_signals_near_level(df, levels, timeframe=timeframe)
                
                # # Process signals near levels
                # for signal in signals_near_level:
                #     position_type = 'long' if signal['level_type'] == 'support' else 'short'
                #     entry_price = df['close'].iloc[-1]
                    
                #     # Передаем весь уровень вместо только цены
                #     level = {
                #         'level_price': signal['level_price'],
                #         'range_min': signal['range_min'],
                #         'range_max': signal['range_max']
                #     }
                #     stop_loss = calculate_stop_loss(level, position_type, STOP_LOSS_PERC)

                #     text = f"""
                #     📌 <b>{symbol} [{timeframe}]</b>
                #     Уровень: {signal['level_type'].upper()} 
                #     Средняя цена: {signal['level_price']:.4f}
                #     Диапазон: {signal['range_min']:.4f} - {signal['range_max']:.4f} (ширина: {signal['range_width']:.4f})
                #     Количество касаний: {signal['strength']}
                    
                #     Текущая цена: {entry_price:.4f} (📏 {signal['distance_percent']:.2f}%)

                #     🔔 <b>Сигналы рядом с уровнем:</b>
                #     RSI: {signal['rsi_signal']}
                #     CM: {signal['cm_signal']}
                #     Price Action: {signal['price_action_signal']}

                #     🚨 <b>Открываем позицию:</b> {position_type.upper()}
                #     🎯 Стоп-лосс: {stop_loss:.4f} ({STOP_LOSS_PERC}%)
                #     """

                #     try:
                #         await bot.send_message(chat_id=6634277726, text=text)
                #     except Exception as e:
                #         print(f"Ошибка при отправке сообщения: {e}")
                
                # # Generate comprehensive trading signals with stop loss parameters
                # trading_signals = generate_trading_signals(
                #     df, 
                #     rsi_length=RSI_LENGTH, 
                #     lbR=LB_RIGHT, 
                #     lbL=LB_LEFT, 
                #     take_profit_level=TAKE_PROFIT_RSI_LEVEL,
                #     stop_loss_type=STOP_LOSS_TYPE,
                #     stop_loss_perc=STOP_LOSS_PERC,
                #     atr_length=ATR_LENGTH,
                #     atr_multiplier=ATR_MULTIPLIER
                # )
                
                # # Legacy divergence detection methods (can be kept for reference)
                # rsi_divergence = detect_rsi_divergence(df)
                # cm_divergence = detect_cm_ppo_divergence(df)
                
                # Print detailed trading information
#                 if trading_signals['entry_signal'] or trading_signals['exit_signal']:
#                     test_coin_list = ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT', 'LTCUSDT', 'XRPUSDT', 'SOLUSDT', 'TRXUSDT']
#                     if symbol in test_coin_list:
#                         text = f"""
# ====== {symbol} [{timeframe}] ======
# Signal Type: {trading_signals['signal_type']}
# Position Type: {trading_signals['position_type']}
# # Entry Signal: {trading_signals['entry_signal']}
# # Exit Signal: {trading_signals['exit_signal']}
# Current Price: {trading_signals['current_price']}
# Current RSI: {trading_signals['current_rsi']:.2f}

# Risk Management:
# Stop Loss Level: {trading_signals['stop_loss_level']}
# Target Price: {trading_signals['target_price']}
# Take Profit Triggered: {trading_signals['take_profit_triggered']}
# Stop Loss Hit: {trading_signals['stop_loss_hit']}

# Divergence Detected:
# Regular Bullish: {trading_signals['divergence']['regular_bullish']}
# Hidden Bullish: {trading_signals['divergence']['hidden_bullish']}
# Regular Bearish: {trading_signals['divergence']['regular_bearish']}
# Hidden Bearish: {trading_signals['divergence']['hidden_bearish']}

# # Legacy Signals:
# # RSI Divergence: {rsi_divergence}
# # CM Divergence: {cm_divergence}
# ==============================
#                 """
#                         await bot.send_message(chat_id=747471391, text=text)
                
                # Rest of your existing code for signal processing...

            except Exception as e:
                print(f"Ошибка при обработке {symbol} на {timeframe}: {e}")
                continue
                
            # Ожидаем короткую паузу, чтобы не перегружать API
            await asyncio.sleep(0.1)
            
        # Ожидаем завершения текущей свечи
        await wait_for_next_candle(timeframe)

async def main():
    try:
        await asyncio.gather(*[process_timeframe(tf) for tf in timeframes])
    finally:
        await exchange.close()  # Ensures resources are released

asyncio.run(main())
