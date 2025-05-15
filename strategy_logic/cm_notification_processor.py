import os
import json
import logging
import asyncio
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import ccxt.async_support as ccxt
import pandas as pd
from scipy.stats import percentileofscore
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError

from config import config
from user_settings import is_cm_notifications_enabled, is_cm_group_notifications_enabled
from strategy_logic.cm_settings import load_cm_settings
from db.update import update_signal
from db.connect import connect

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize bot
bot = Bot(token=config.tg_bot_token, default=DefaultBotProperties(parse_mode="HTML"))

# Constants
EXCHANGE_TYPES = ["spot", "futures"]
TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"]
SYMBOLS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "LTCUSDT", "XRPUSDT", "SOLUSDT", "TRXUSDT"]
EXCHANGES = ["binance", "bybit", "mexc"]
GROUP_ID = -1002467387559  # Fixed group ID
CM_NOTIFICATIONS_DIR = "cm_notifications"
USER_LAST_SIGNALS_FILE = os.path.join(CM_NOTIFICATIONS_DIR, "user_last_signals.json")
GROUP_LAST_SIGNALS_FILE = os.path.join(CM_NOTIFICATIONS_DIR, "group_last_signals.json")

# Ensure directory exists
os.makedirs(CM_NOTIFICATIONS_DIR, exist_ok=True)

# Cache for last signals
last_signals = {}

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


def find_cm_signal(df, cm_settings) -> Tuple[Optional[str], Optional[pd.Series]]:
    """Находит последний экстремальный сигнал, начиная с текущей свечи и шагая назад."""
    for i in range(len(df) - 1, -1, -1):
        if df['pctRankT'].iloc[i] >= cm_settings['PCTILE']:
            return "short", df.iloc[i]
        if df['pctRankB'].iloc[i] <= -cm_settings['PCTILE']:
            return "long", df.iloc[i]
    return None, None


async def fetch_ohlcv(exchange, symbol, timeframe='1h', limit=500, retries=3, delay=5):
    """Fetch OHLCV data with retries"""
    for attempt in range(retries):
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['hl2'] = (df['high'] + df['low']) / 2  # Средняя цена свечи
            return df
        except ccxt.RequestTimeout:
            logger.warning(f"Timeout fetching {symbol} {timeframe}, retrying {attempt + 1}/{retries}...")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
        except Exception as e:
            logger.error(f"Error fetching {symbol} {timeframe}: {e}")
            break
    
    return None


async def safe_send_message(chat_id, text, max_retries=3):
    """Безопасная отправка сообщений с обработкой флуд-контроля и ошибок HTML парсинга"""
    for attempt in range(max_retries):
        try:
            return await bot.send_message(chat_id, text)
        except TelegramAPIError as e:
            # Проверяем наличие ошибки парсинга HTML
            if "can't parse entities" in str(e):
                # Если проблема с HTML-тегами, пробуем отправить без HTML форматирования
                try:
                    # Заменяем HTML-теги и эмодзи, которые могут вызвать проблемы
                    clean_text = text.replace("<b>", "").replace("</b>", "")
                    clean_text = clean_text.replace("<i>", "").replace("</i>", "")
                    clean_text = clean_text.replace("<code>", "").replace("</code>", "")
                    logger.warning("HTML parsing issue detected. Trying to send clean message.")
                    return await bot.send_message(chat_id, clean_text, parse_mode=None)
                except Exception as clean_e:
                    logger.error(f"Failed to send clean message: {clean_e}")
            
            # Проверяем наличие флуд-ограничения
            if "Flood control" in str(e) or "Too Many Requests" in str(e) or "retry after" in str(e).lower():
                wait_time = 5  # Стандартное время ожидания
                error_str = str(e).lower()
                if "retry after" in error_str:
                    try:
                        wait_part = error_str.split("retry after")[1].strip()
                        wait_digits = ''.join(c for c in wait_part if c.isdigit())
                        if wait_digits:
                            wait_time = int(wait_digits) + 1  # +1 секунда для надежности
                    except:
                        pass  # Используем стандартное значение
                
                logger.warning(f"Telegram flood control hit. Waiting {wait_time} seconds before retry.")
                # Логируем сокращенную версию сообщения, чтобы не спамить консоль
                log_text = text[:100] + "..." if len(text) > 100 else text
                logger.warning(f"Message queued for delivery: {log_text}")
                
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
                logger.error(f"Telegram API error: {e}")
                await asyncio.sleep(1)
    
    # Если все попытки не удались, логируем ошибку
    logger.error(f"Failed to send message to chat {chat_id} after {max_retries} attempts")
    return None


async def get_user_favorite_pairs(user_id: int) -> list:
    """Get user's favorite cryptocurrency pairs from database."""
    try:
        conn = await connect()
        try:
            # Try to get crypto_pairs from user settings
            query = """
                SELECT crypto_pairs FROM users WHERE user_id = $1
            """
            row = await conn.fetchrow(query, user_id)
            
            if row and row['crypto_pairs']:
                pairs = [pair.strip() for pair in row['crypto_pairs'].split(',') if pair.strip()]
                if pairs:
                    logger.info(f"User {user_id} has favorite pairs: {pairs}")
                    return pairs
            
            # If no favorite pairs, use default
            logger.info(f"User {user_id} has no favorite pairs, using defaults")
            return []
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Error getting favorite pairs for user {user_id}: {e}")
        return []


async def get_subscribed_users() -> List[int]:
    """Get list of users who have enabled CM notifications"""
    try:
        # Get all user settings files
        settings_dir = "user_settings"
        user_ids = []
        
        if os.path.exists(settings_dir):
            for filename in os.listdir(settings_dir):
                if filename.endswith(".json"):
                    try:
                        user_id = int(filename.split(".")[0])
                        # Check if user has enabled CM notifications
                        if await is_cm_notifications_enabled(user_id):
                            user_ids.append(user_id)
                    except (ValueError, Exception) as e:
                        logger.error(f"Error processing user file {filename}: {e}")
        
        logger.info(f"Found {len(user_ids)} users with CM notifications enabled")
        return user_ids
    except Exception as e:
        logger.error(f"Error getting subscribed users: {e}")
        return []


def get_signal_key(exchange_name: str, trading_type: str, symbol: str, timeframe: str) -> str:
    """Create a unique key for caching signals"""
    return f"{exchange_name}_{trading_type}_{symbol}_{timeframe}"


async def should_send_notification(exchange_name: str, trading_type: str, symbol: str, timeframe: str, signal: str) -> bool:
    """Check if notification should be sent based on previous signal"""
    global last_signals
    
    key = get_signal_key(exchange_name, trading_type, symbol, timeframe)
    
    # Check if we have a previous signal for this key
    last_signal = last_signals.get(key)
    
    # If no previous signal or signal has changed, we should send
    should_send = last_signal is None or last_signal != signal
    
    # Update last signal
    if should_send:
        last_signals[key] = signal
        
        # Also store the signal in the database
        try:
            current_price = -1  # Placeholder, you might want to pass the actual price
            await update_signal(symbol, timeframe, signal, current_price, current_price)
        except Exception as e:
            logger.error(f"Error updating signal in database: {e}")
    
    return should_send


async def process_cm_signal_notification(user_id: int, exchange_name: str, trading_type: str, symbol: str, timeframe: str, signal: str, price: float):
    """Process CM signal notification for a user"""
    
    # Check if we should send notification (based on last signal)
    if not await should_send_notification(exchange_name, trading_type, symbol, timeframe, signal):
        return
    
    # Create message with signal info
    if signal == "long":
        emoji = "🔰"
        direction = "LONG"
        action_text = "✅ Рекомендация: ПОКУПАТЬ"
    elif signal == "short":
        emoji = "🔻"
        direction = "SHORT"
        action_text = "✅ Рекомендация: ПРОДАВАТЬ"
    else:
        return  # No valid signal
    
    # Create exchange type label
    exchange_type_label = trading_type.upper()
    
    # Get current time in Moscow timezone (UTC+3)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    message = (
        f"🔔 CM СИГНАЛ {symbol} {timeframe}\n\n"
        f"⚙️ Индикатор CM обнаружил сигнал\n"
        f"📈 Текущая цена: {price:.4f} USDT\n"
        f"📊 Сигнал: {direction} {emoji}\n"
        f"{action_text}\n\n"
        f"🏛 Биржа: {exchange_name.capitalize()} ({exchange_type_label})\n"
        f"⏱ {current_time}"
    )
    
    # Send to user if they have enabled notifications
    if user_id > 0 and await is_cm_notifications_enabled(user_id):
        await safe_send_message(user_id, message)
    
    # Send to group if enabled (only once per signal)
    if user_id == 0 and await is_cm_group_notifications_enabled():  # user_id=0 is our sentinel for group check
        try:
            group_message = (
                f"🔔 CM СИГНАЛ {symbol} {timeframe}\n\n"
                f"⚙️ Индикатор CM обнаружил сигнал\n"
                f"📈 Текущая цена: {price:.4f} USDT\n"
                f"📊 Сигнал: {direction} {emoji}\n"
                f"{action_text}\n\n"
                f"🏛 Биржа: {exchange_name.capitalize()} ({exchange_type_label})\n"
                f"⏱ {current_time}\n\n"
                f"#CM #{exchange_name} #{trading_type} #{symbol} #{timeframe}"
            )
            await safe_send_message(GROUP_ID, group_message)
        except Exception as e:
            logger.error(f"Error sending CM notification to group: {e}")


async def init_exchange(exchange_name: str, trading_type: str) -> Optional[ccxt.Exchange]:
    """Initialize exchange with proper settings"""
    try:
        if exchange_name == "binance":
            if trading_type == "futures":
                return ccxt.binanceusdm({"enableRateLimit": True})
            else:
                return ccxt.binance({"enableRateLimit": True})
        elif exchange_name == "bybit":
            return ccxt.bybit({
                "enableRateLimit": True, 
                "options": {"defaultType": "future" if trading_type == "futures" else "spot"}
            })
        elif exchange_name == "mexc":
            return ccxt.mexc({
                "enableRateLimit": True,
                "options": {"defaultType": "swap" if trading_type == "futures" else "spot"}
            })
        return None
    except Exception as e:
        logger.error(f"Error initializing {exchange_name} {trading_type}: {e}")
        return None


async def has_pair_in_favorites(user_id: int, symbol: str) -> bool:
    """Check if user has a specific pair in their favorites list"""
    user_pairs = await get_user_favorite_pairs(user_id)
    return symbol in user_pairs


async def process_exchange(exchange_name: str, trading_type: str, user_id: int = 0):
    """Process signals for one exchange and trading type"""
    exchange = await init_exchange(exchange_name, trading_type)
    if not exchange:
        return
    
    try:
        # Get user favorite pairs or use default
        symbols_to_check = SYMBOLS
        if user_id > 0:
            user_pairs = await get_user_favorite_pairs(user_id)
            if user_pairs:
                symbols_to_check = user_pairs
                logger.info(f"User {user_id} has {len(user_pairs)} favorite pairs: {user_pairs}")
            else:
                logger.info(f"User {user_id} has no favorite pairs, using defaults: {SYMBOLS}")
        
        for symbol in symbols_to_check:
            for timeframe in TIMEFRAMES:
                try:
                    # Fetch OHLCV data
                    df = await fetch_ohlcv(exchange, symbol, timeframe, limit=200)
                    if df is None or len(df) < 50:  # Need enough data for reliable signals
                        continue
                    
                    # Get CM settings (using default if processing for group)
                    cm_settings = load_cm_settings(user_id if user_id > 0 else 0)
                    
                    # Calculate indicators
                    df = calculate_ppo(df, cm_settings)
                    
                    # Find CM signal
                    cm_signal, last_candle = find_cm_signal(df, cm_settings)
                    
                    # Process signal if found
                    if cm_signal in ["long", "short"]:
                        current_price = df["close"].iloc[-1]
                        logger.info(f"Signal detected: {exchange_name} {trading_type} {symbol} {timeframe} {cm_signal} at {current_price}")
                        await process_cm_signal_notification(
                            user_id, exchange_name, trading_type, symbol, timeframe, cm_signal, current_price
                        )
                
                except Exception as e:
                    logger.error(f"Error processing {exchange_name} {trading_type} {symbol} {timeframe}: {e}")
                
                # Don't overload exchanges with requests
                await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Error in process_exchange for {exchange_name} {trading_type}: {e}")
    finally:
        # Close exchange connection
        if exchange:
            await exchange.close()


async def process_for_user(user_id: int):
    """Process CM signals for a specific user"""
    logger.info(f"Processing CM signals for user {user_id}")
    
    tasks = []
    for exchange_name in EXCHANGES:
        for trading_type in EXCHANGE_TYPES:
            tasks.append(process_exchange(exchange_name, trading_type, user_id))
    
    # Run all tasks concurrently
    await asyncio.gather(*tasks, return_exceptions=True)


async def process_for_group():
    """Process CM signals for the group (using default settings)"""
    logger.info("Processing CM signals for group")
    
    tasks = []
    for exchange_name in EXCHANGES:
        for trading_type in EXCHANGE_TYPES:
            tasks.append(process_exchange(exchange_name, trading_type, 0))  # 0 is sentinel for group
    
    # Run all tasks concurrently
    await asyncio.gather(*tasks, return_exceptions=True)


def load_last_signals_cache():
    """Load last signals cache from disk"""
    global last_signals
    try:
        if os.path.exists(USER_LAST_SIGNALS_FILE):
            with open(USER_LAST_SIGNALS_FILE, 'r', encoding='utf-8') as f:
                last_signals = json.load(f)
                logger.info(f"Loaded {len(last_signals)} last signals from disk")
        else:
            logger.info("No last signals cache file found, starting with empty cache")
            last_signals = {}
    except Exception as e:
        logger.error(f"Error loading last signals cache: {e}")
        last_signals = {}


def save_last_signals_cache():
    """Save last signals cache to disk"""
    try:
        with open(USER_LAST_SIGNALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(last_signals, f, indent=2)
            logger.info(f"Saved {len(last_signals)} last signals to disk")
    except Exception as e:
        logger.error(f"Error saving last signals cache: {e}")


async def cm_notification_processor():
    """Main processor function that runs continuously"""
    logger.info("Starting CM notification processor")
    
    # Load last signals cache from disk
    load_last_signals_cache()
    
    last_save_time = datetime.now()
    
    while True:
        try:
            # Process for group
            if await is_cm_group_notifications_enabled():
                await process_for_group()
            
            # Process for all subscribed users
            subscribed_users = await get_subscribed_users()
            for user_id in subscribed_users:
                await process_for_user(user_id)
            
            # Save last signals cache to disk every hour
            now = datetime.now()
            if (now - last_save_time).total_seconds() > 3600:  # 1 hour
                save_last_signals_cache()
                last_save_time = now
            
            # Wait before next cycle (check every 5 minutes)
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Error in CM notification processor: {e}")
            await asyncio.sleep(60)  # Shorter wait on error


def start_notification_processor():
    """Start the notification processor in a background task"""
    asyncio.create_task(cm_notification_processor())
    logger.info("CM notification processor started as background task") 