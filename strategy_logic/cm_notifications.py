import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import asyncio
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from config import config
from user_settings import is_cm_notifications_enabled, is_cm_group_notifications_enabled

# Constants
CM_NOTIFICATIONS_DIR = "cm_notifications"
USER_LAST_SIGNALS_FILE = os.path.join(CM_NOTIFICATIONS_DIR, "user_last_signals.json")
GROUP_LAST_SIGNALS_FILE = os.path.join(CM_NOTIFICATIONS_DIR, "group_last_signals.json")
GROUP_ID = -1002467387559  # Fixed group ID

# Ensure directory exists
os.makedirs(CM_NOTIFICATIONS_DIR, exist_ok=True)

# Initialize bot
bot = Bot(token=config.tg_bot_token, default=DefaultBotProperties(parse_mode="HTML"))

def load_user_last_signals() -> Dict[int, Dict[str, Dict[str, str]]]:
    """Load the last CM signals sent to each user"""
    if os.path.exists(USER_LAST_SIGNALS_FILE):
        try:
            with open(USER_LAST_SIGNALS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading user last signals: {e}")
    return {}

def save_user_last_signals(signals: Dict[int, Dict[str, Dict[str, str]]]) -> None:
    """Save the last CM signals sent to each user"""
    try:
        with open(USER_LAST_SIGNALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(signals, f, indent=2)
    except Exception as e:
        logging.error(f"Error saving user last signals: {e}")

def load_group_last_signals() -> Dict[str, Dict[str, str]]:
    """Load the last CM signals sent to the group"""
    if os.path.exists(GROUP_LAST_SIGNALS_FILE):
        try:
            with open(GROUP_LAST_SIGNALS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading group last signals: {e}")
    return {}

def save_group_last_signals(signals: Dict[str, Dict[str, str]]) -> None:
    """Save the last CM signals sent to the group"""
    try:
        with open(GROUP_LAST_SIGNALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(signals, f, indent=2)
    except Exception as e:
        logging.error(f"Error saving group last signals: {e}")

def get_user_last_signal(user_id: int, symbol: str, timeframe: str) -> Optional[str]:
    """Get the last signal sent to user for a specific symbol and timeframe"""
    signals = load_user_last_signals()
    user_signals = signals.get(str(user_id), {})
    symbol_signals = user_signals.get(symbol, {})
    return symbol_signals.get(timeframe)

def set_user_last_signal(user_id: int, symbol: str, timeframe: str, signal: str) -> None:
    """Set the last signal sent to user for a specific symbol and timeframe"""
    signals = load_user_last_signals()
    if str(user_id) not in signals:
        signals[str(user_id)] = {}
    if symbol not in signals[str(user_id)]:
        signals[str(user_id)][symbol] = {}
    signals[str(user_id)][symbol][timeframe] = signal
    save_user_last_signals(signals)

def get_group_last_signal(symbol: str, timeframe: str) -> Optional[str]:
    """Get the last signal sent to the group for a specific symbol and timeframe"""
    signals = load_group_last_signals()
    symbol_signals = signals.get(symbol, {})
    return symbol_signals.get(timeframe)

def set_group_last_signal(symbol: str, timeframe: str, signal: str) -> None:
    """Set the last signal sent to the group for a specific symbol and timeframe"""
    signals = load_group_last_signals()
    if symbol not in signals:
        signals[symbol] = {}
    signals[symbol][timeframe] = signal
    save_group_last_signals(signals)

async def should_send_notification_to_user(user_id: int, symbol: str, timeframe: str, new_signal: str) -> bool:
    """Check if notification should be sent based on previous signal"""
    if not await is_cm_notifications_enabled(user_id):
        return False
        
    last_signal = get_user_last_signal(user_id, symbol, timeframe)
    # Send notification if:
    # 1. No previous signal (first notification)
    # 2. Signal has changed (e.g., from "short" to "long")
    return last_signal is None or last_signal != new_signal

async def should_send_notification_to_group(symbol: str, timeframe: str, new_signal: str) -> bool:
    """Check if notification should be sent to the group based on previous signal"""
    if not await is_cm_group_notifications_enabled():
        return False
        
    last_signal = get_group_last_signal(symbol, timeframe)
    # Same logic as for users
    return last_signal is None or last_signal != new_signal

async def send_cm_notification_to_user(user_id: int, symbol: str, timeframe: str, signal: str, price: float) -> None:
    """Send CM signal notification to a user"""
    try:
        # Only send if necessary
        if not await should_send_notification_to_user(user_id, symbol, timeframe, signal):
            return
            
        # Create the message
        if signal == "long":
            emoji = "🔰"
            direction = "LONG"
        elif signal == "short":
            emoji = "🔻"
            direction = "SHORT"
        else:
            return  # No valid signal
            
        message = (
            f"🔔 CM СИГНАЛ {symbol} {timeframe}\n\n"
            f"⚙️ Индикатор CM обнаружил сигнал\n"
            f"📈 Цена: {price:.4f} USDT\n"
            f"📊 Сигнал: {direction} {emoji}\n\n"
            f"⏱ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Send the message
        await bot.send_message(chat_id=user_id, text=message)
        
        # Update the last signal
        set_user_last_signal(user_id, symbol, timeframe, signal)
        
    except Exception as e:
        logging.error(f"Error sending CM notification to user {user_id}: {e}")

async def send_cm_notification_to_group(symbol: str, timeframe: str, signal: str, price: float) -> None:
    """Send CM signal notification to the group"""
    try:
        # Only send if necessary
        if not await should_send_notification_to_group(symbol, timeframe, signal):
            return
            
        # Create the message
        if signal == "long":
            emoji = "🔰"
            direction = "LONG"
        elif signal == "short":
            emoji = "🔻"
            direction = "SHORT"
        else:
            return  # No valid signal
            
        message = (
            f"🔔 CM СИГНАЛ {symbol} {timeframe}\n\n"
            f"⚙️ Индикатор CM обнаружил сигнал\n"
            f"📈 Цена: {price:.4f} USDT\n"
            f"📊 Сигнал: {direction} {emoji}\n\n"
            f"⏱ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Send the message
        await bot.send_message(chat_id=GROUP_ID, text=message)
        
        # Update the last signal
        set_group_last_signal(symbol, timeframe, signal)
        
    except Exception as e:
        logging.error(f"Error sending CM notification to group: {e}")

async def process_cm_signal(user_id: int, symbol: str, timeframe: str, signal: str, price: float) -> None:
    """Process CM signal and send notifications if needed"""
    # Send to user if they have enabled notifications
    await send_cm_notification_to_user(user_id, symbol, timeframe, signal, price)
    
    # Send to group if group notifications are enabled
    await send_cm_notification_to_group(symbol, timeframe, signal, price) 