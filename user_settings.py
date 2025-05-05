import json
import os
from typing import Dict, Any, List, Union, Optional

# Main directory for user settings
SETTINGS_DIR = "user_settings"

# Ensure the directory exists
os.makedirs(SETTINGS_DIR, exist_ok=True)

# Default settings for all categories
DEFAULT_SETTINGS = {
    "strategy": {
        "OrderSize": 10.0,
        "TakeProfit": 3.0,
        "StopLoss": 1.5,
        "MinVolume": 5000000,
        "MaxVolume": 100000000,
        "MinHourlyVolume": 500000,
        "MaxHourlyVolume": 10000000,
        "Delta_3h_Max": 5.0,
        "Delta_24h_Max": 10.0,
        "Delta2_Max": 1.0,
        "Delta_BTC_Min": -0.5,
        "Delta_BTC_Max": 0.5,
        "CoinsBlackList": []
    },
    "cm": {
        "SHORT_GAMMA": 0.4,
        "LONG_GAMMA": 0.8,
        "LOOKBACK_T": 21,
        "LOOKBACK_B": 15,
        "PCTILE": 90
    },
    "divergence": {
        "RSI_LENGTH": 7,
        "LB_RIGHT": 3,
        "LB_LEFT": 3,
        "RANGE_UPPER": 60,
        "RANGE_LOWER": 5,
        "TAKE_PROFIT_RSI_LEVEL": 80,
        "STOP_LOSS_TYPE": "PERC",
        "STOP_LOSS_PERC": 5.0,
        "ATR_LENGTH": 14,
        "ATR_MULTIPLIER": 3.5
    },
    "rsi": {
        "RSI_PERIOD": 14,
        "RSI_OVERBOUGHT": 70,
        "RSI_OVERSOLD": 30,
        "EMA_FAST": 9,
        "EMA_SLOW": 21
    },
    "pump_dump": {
        "VOLUME_THRESHOLD": 3.0,
        "PRICE_CHANGE_THRESHOLD": 3.0,
        "TIME_WINDOW": 15,
        "MONITOR_INTERVALS": ["5m", "15m", "1h", "4h"],
        "ENABLED": True,
        "TRADE_TYPE": "SPOT",
        "LEVERAGE": 3,
        "ENABLE_SHORT_TRADES": False
    },
    "trading": {
        "trading_type": "spot",
        "leverage": 3,
        "enable_short_trades": False
    },
    "user": {
        "balance": 50000.0,
        "percent": 5.0,
        "crypto_pairs": "",
        "monitor_pairs": ""
    },
    "subscriptions": [],
    "pump_dump_subscriber": False
}

def get_settings_path(user_id: int) -> str:
    """Get the path to a user's settings file"""
    return os.path.join(SETTINGS_DIR, f"{user_id}.json")

def load_user_settings(user_id: int) -> Dict[str, Any]:
    """Load all settings for a user"""
    settings_path = get_settings_path(user_id)
    
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            # Ensure all required settings are present
            for category, defaults in DEFAULT_SETTINGS.items():
                if category not in settings:
                    settings[category] = defaults
                elif isinstance(defaults, dict):
                    # Check that all parameters in category are present
                    for param, default_value in defaults.items():
                        if param not in settings[category]:
                            settings[category][param] = default_value
            
            return settings
        except Exception as e:
            print(f"Error loading settings for user {user_id}: {e}")
    
    return DEFAULT_SETTINGS.copy()

def save_user_settings(user_id: int, settings: Dict[str, Any]) -> bool:
    """Save all settings for a user"""
    settings_path = get_settings_path(user_id)
    
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"Error saving settings for user {user_id}: {e}")
        return False

async def update_user_settings(user_id: int, category: str, param: str, value: Any) -> bool:
    """Update a specific parameter in user settings"""
    settings = load_user_settings(user_id)
    
    if category not in settings:
        print(f"Category {category} not found in settings")
        return False
    
    # Type conversion based on parameter type
    if category == "strategy" and param == "CoinsBlackList":
        if isinstance(value, str):
            value = [coin.strip() for coin in value.split(',') if coin.strip()]
    
    if category == "pump_dump" and param == "MONITOR_INTERVALS":
        if isinstance(value, str):
            value = [interval.strip() for interval in value.split(',') if interval.strip()]
    
    if (category == "pump_dump" and param in ["ENABLED", "ENABLE_SHORT_TRADES"]) or \
       (category == "trading" and param == "enable_short_trades"):
        if isinstance(value, str):
            value = value.lower() == 'true'
    
    # Update the parameter
    settings[category][param] = value
    
    # Save settings
    return save_user_settings(user_id, settings)

async def reset_user_settings(user_id: int, category: str = None) -> bool:
    """Reset settings to default values"""
    settings = load_user_settings(user_id)
    
    if category is None:
        # Reset all settings
        settings = DEFAULT_SETTINGS.copy()
    elif category in DEFAULT_SETTINGS:
        # Reset only the specified category
        settings[category] = DEFAULT_SETTINGS[category].copy()
    else:
        print(f"Category {category} not found in default settings")
        return False
    
    return save_user_settings(user_id, settings)

def get_settings_category(user_id: int, category: str) -> Dict[str, Any]:
    """Get settings for a specific category"""
    settings = load_user_settings(user_id)
    return settings.get(category, {})

# === Strategy Parameters Functions ===

def load_user_params(user_id: int) -> Dict[str, Any]:
    """Load strategy parameters"""
    params = get_settings_category(user_id, "strategy")
    # Convert CoinsBlackList to set if it's a list
    if "CoinsBlackList" in params and isinstance(params["CoinsBlackList"], list):
        params["CoinsBlackList"] = set(params["CoinsBlackList"])
    return params

async def update_user_param(user_id: int, param_name: str, param_value: Any) -> bool:
    """Update a strategy parameter"""
    return await update_user_settings(user_id, "strategy", param_name, param_value)

async def reset_user_params(user_id: int) -> bool:
    """Reset strategy parameters to default"""
    return reset_user_settings(user_id, "strategy")

# === CM Settings Functions ===

def load_cm_settings(user_id: int) -> Dict[str, Any]:
    """Load CM indicator settings"""
    return get_settings_category(user_id, "cm")

async def update_cm_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """Update a CM indicator setting"""
    return await update_user_settings(user_id, "cm", param_name, param_value)

async def reset_cm_settings(user_id: int) -> bool:
    """Reset CM indicator settings to default"""
    return reset_user_settings(user_id, "cm")

# === Divergence Settings Functions ===

def load_divergence_settings(user_id: int) -> Dict[str, Any]:
    """Load divergence indicator settings"""
    return get_settings_category(user_id, "divergence")

async def update_divergence_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """Update a divergence indicator setting"""
    return await update_user_settings(user_id, "divergence", param_name, param_value)

async def reset_divergence_settings(user_id: int) -> bool:
    """Reset divergence indicator settings to default"""
    return reset_user_settings(user_id, "divergence")

# === RSI Settings Functions ===

def load_rsi_settings(user_id: int) -> Dict[str, Any]:
    """Load RSI indicator settings"""
    return get_settings_category(user_id, "rsi")

async def update_rsi_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """Update an RSI indicator setting"""
    return await update_user_settings(user_id, "rsi", param_name, param_value)

async def reset_rsi_settings(user_id: int) -> bool:
    """Reset RSI indicator settings to default"""
    return reset_user_settings(user_id, "rsi")

# === Pump/Dump Settings Functions ===

def load_pump_dump_settings(user_id: int) -> Dict[str, Any]:
    """Load pump/dump detector settings"""
    return get_settings_category(user_id, "pump_dump")

async def update_pump_dump_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """Update a pump/dump detector setting"""
    return await update_user_settings(user_id, "pump_dump", param_name, param_value)

async def reset_pump_dump_settings(user_id: int) -> bool:
    """Reset pump/dump detector settings to default"""
    return reset_user_settings(user_id, "pump_dump")

# === Trading Settings Functions ===

def load_trading_settings(user_id: int) -> Dict[str, Any]:
    """Load trading settings"""
    return get_settings_category(user_id, "trading")

async def update_trading_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """Update a trading setting"""
    return await update_user_settings(user_id, "trading", param_name, param_value)

async def reset_trading_settings(user_id: int) -> bool:
    """Reset trading settings to default"""
    return reset_user_settings(user_id, "trading")

# === Trading Type Settings Functions ===

def load_trading_type_settings(user_id: int) -> Dict[str, Any]:
    """Load trading type settings in expected format"""
    trading_settings = load_trading_settings(user_id)
    return {
        "TRADING_TYPE": trading_settings.get("trading_type", "spot").upper(),
        "LEVERAGE": trading_settings.get("leverage", 3)
    }

async def update_trading_type_setting(user_id: int, trading_type: str) -> bool:
    """Update trading type"""
    return await update_user_settings(user_id, "trading", "trading_type", trading_type.lower())

async def update_leverage_setting(user_id: int, leverage: int) -> bool:
    """Update leverage setting"""
    # First check if trading type is SPOT, if so, change it to FUTURES
    settings = load_user_settings(user_id)
    if settings["trading"]["trading_type"].lower() != "futures":
        print(f"Automatically changing trading type to FUTURES for user {user_id} when setting leverage")
        # Update trading type to FUTURES
        await update_user_settings(user_id, "trading", "trading_type", "futures")
    
    # Now set the leverage
    return await update_user_settings(user_id, "trading", "leverage", int(leverage))

# === User Settings Functions ===

async def get_user(user_id: int) -> Dict[str, Any]:
    """Get basic user settings"""
    return get_settings_category(user_id, "user")

async def update_user_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """Update a user setting"""
    return await update_user_settings(user_id, "user", param_name, param_value)

async def set_user(user_id: int, percent: float, balance: float, 
               trading_type: str = 'spot', leverage: int = 1, 
               exchanges: list = None) -> bool:
    """Создает или обновляет пользователя"""
    try:
        user = {
            'user_id': user_id,
            'percent': percent,
            'balance': balance,
            'trading_type': trading_type,
            'leverage': leverage
        }
        
        if exchanges is not None:
            user['exchanges'] = exchanges
        
        os.makedirs(f"data/users/{user_id}", exist_ok=True)
        
        # Загружаем существующие настройки, если они есть
        try:
            with open(f"data/users/{user_id}/settings.json", "r") as f:
                existing_settings = json.load(f)
                # Сохраняем все существующие ключи, кроме тех, которые обновляем
                for key in existing_settings:
                    if key not in ['user_id', 'percent', 'balance', 'trading_type', 'leverage'] and key not in user:
                        user[key] = existing_settings[key]
        except (FileNotFoundError, json.JSONDecodeError):
            pass
            
        with open(f"data/users/{user_id}/settings.json", "w") as f:
            json.dump(user, f, indent=4)
            
        return True
    except Exception as e:
        print(f"Error in set_user: {e}")
        return False

# === Crypto Pairs Functions ===

async def add_crypto_pair_to_db(user_id: int, pair: str) -> bool:
    """Add a pair to user's favorite list"""
    settings = load_user_settings(user_id)
    pairs = settings["user"].get("crypto_pairs", "").split(',') if settings["user"].get("crypto_pairs", "") else []
    
    if pair not in pairs:
        pairs.append(pair)
    
    settings["user"]["crypto_pairs"] = ','.join(filter(None, pairs))
    return save_user_settings(user_id, settings)

async def delete_crypto_pair_from_db(user_id: int, pair: str) -> bool:
    """Remove a pair from user's favorite list"""
    settings = load_user_settings(user_id)
    pairs = settings["user"].get("crypto_pairs", "").split(',') if settings["user"].get("crypto_pairs", "") else []
    
    if pair in pairs:
        pairs.remove(pair)
    
    settings["user"]["crypto_pairs"] = ','.join(filter(None, pairs))
    return save_user_settings(user_id, settings)

# === Monitor Pairs Functions ===

async def add_monitor_pair_to_db(user_id: int, pair: str) -> bool:
    """Add a pair to user's monitor list"""
    settings = load_user_settings(user_id)
    pairs = settings["user"].get("monitor_pairs", "").split(',') if settings["user"].get("monitor_pairs", "") else []
    
    if pair not in pairs:
        pairs.append(pair)
    
    settings["user"]["monitor_pairs"] = ','.join(filter(None, pairs))
    return save_user_settings(user_id, settings)

async def delete_monitor_pair_from_db(user_id: int, pair: str) -> bool:
    """Remove a pair from user's monitor list"""
    settings = load_user_settings(user_id)
    pairs = settings["user"].get("monitor_pairs", "").split(',') if settings["user"].get("monitor_pairs", "") else []
    
    if pair in pairs:
        pairs.remove(pair)
    
    settings["user"]["monitor_pairs"] = ','.join(filter(None, pairs))
    return save_user_settings(user_id, settings)

# === Subscription Functions ===

async def add_subscription(user_id: int, symbol: str, interval: str) -> bool:
    """Add a subscription to a pair and interval"""
    settings = load_user_settings(user_id)
    
    # Check if subscription already exists
    for sub in settings["subscriptions"]:
        if sub.get("symbol") == symbol and sub.get("interval") == interval:
            return True
    
    # Add new subscription
    settings["subscriptions"].append({
        "symbol": symbol,
        "interval": interval
    })
    
    return save_user_settings(user_id, settings)

async def remove_subscription(user_id: int, symbol: str, interval: str) -> bool:
    """Remove a subscription to a pair and interval"""
    settings = load_user_settings(user_id)
    
    for i, sub in enumerate(settings["subscriptions"]):
        if sub.get("symbol") == symbol and sub.get("interval") == interval:
            settings["subscriptions"].pop(i)
            return save_user_settings(user_id, settings)
    
    return True  # Subscription not found, nothing to remove

async def get_user_subscriptions(user_id: int) -> list:
    """Get user's subscriptions"""
    settings = load_user_settings(user_id)
    return settings.get("subscriptions", [])

# === Pump/Dump Subscriber Functions ===

async def add_subscriber(user_id: int) -> bool:
    """Subscribe user to pump/dump notifications"""
    settings = load_user_settings(user_id)
    settings["pump_dump_subscriber"] = True
    return save_user_settings(user_id, settings)

async def remove_subscriber(user_id: int) -> bool:
    """Unsubscribe user from pump/dump notifications"""
    settings = load_user_settings(user_id)
    settings["pump_dump_subscriber"] = False
    return save_user_settings(user_id, settings)

async def is_subscribed(user_id: int) -> bool:
    """Check if user is subscribed to pump/dump notifications"""
    settings = load_user_settings(user_id)
    return settings.get("pump_dump_subscriber", False)

# === Migration Function ===

def migrate_user_settings():
    """Migrate user settings from old formats to the new centralized format"""
    # Old settings directories and patterns
    old_settings = {
        "strategy": {
            "path": "data/users/{user_id}/strategy_params.json",
            "file_pattern": "user_strategy_params.json"
        },
        "cm": {
            "path": "user_settings/cm_settings_{user_id}.json",
        },
        "divergence": {
            "path": "user_settings/divergence_settings_{user_id}.json",
        },
        "rsi": {
            "path": "user_settings/rsi_settings_{user_id}.json",
        },
        "pump_dump": {
            "path": "user_settings/pump_dump_settings_{user_id}.json",
        },
        "trading": {
            "path": "data/users/{user_id}/trading_settings.json",
        },
        "trading_type": {
            "path": "data/users/{user_id}/trading_type_settings.json",
        }
    }
    
    # Find all user IDs from existing files
    user_ids = set()
    
    # Check data/users directory for user folders
    if os.path.exists("data/users"):
        for folder in os.listdir("data/users"):
            if folder.isdigit():
                user_ids.add(int(folder))
    
    # Check user_settings directory for user-specific files
    if os.path.exists("user_settings"):
        for filename in os.listdir("user_settings"):
            # Parse files like "cm_settings_123456.json" to get user ID
            parts = filename.split('_')
            if len(parts) >= 3 and parts[-1].endswith('.json'):
                user_id = parts[-1].split('.')[0]
                if user_id.isdigit():
                    user_ids.add(int(user_id))
    
    # Global settings file for strategy
    if os.path.exists("user_strategy_params.json"):
        try:
            with open("user_strategy_params.json", 'r') as f:
                strategy_params = json.load(f)
                for user_id_str in strategy_params:
                    if user_id_str.isdigit():
                        user_ids.add(int(user_id_str))
        except Exception as e:
            print(f"Error reading user_strategy_params.json: {e}")
    
    # Migrate settings for each user ID
    for user_id in user_ids:
        settings = load_user_settings(user_id)  # Start with default settings
        
        # Migrate strategy parameters
        strategy_file = f"data/users/{user_id}/strategy_params.json"
        global_strategy_file = "user_strategy_params.json"
        
        if os.path.exists(strategy_file):
            try:
                with open(strategy_file, 'r') as f:
                    strategy_params = json.load(f)
                    settings["strategy"].update(strategy_params)
            except Exception as e:
                print(f"Error migrating strategy settings from {strategy_file}: {e}")
        elif os.path.exists(global_strategy_file):
            try:
                with open(global_strategy_file, 'r') as f:
                    all_params = json.load(f)
                    user_id_str = str(user_id)
                    if user_id_str in all_params:
                        settings["strategy"].update(all_params[user_id_str])
            except Exception as e:
                print(f"Error migrating strategy settings from {global_strategy_file}: {e}")
        
        # Migrate CM settings
        cm_file = f"user_settings/cm_settings_{user_id}.json"
        if os.path.exists(cm_file):
            try:
                with open(cm_file, 'r') as f:
                    cm_settings = json.load(f)
                    settings["cm"].update(cm_settings)
            except Exception as e:
                print(f"Error migrating CM settings from {cm_file}: {e}")
        
        # Migrate divergence settings
        divergence_file = f"user_settings/divergence_settings_{user_id}.json"
        if os.path.exists(divergence_file):
            try:
                with open(divergence_file, 'r') as f:
                    divergence_settings = json.load(f)
                    settings["divergence"].update(divergence_settings)
            except Exception as e:
                print(f"Error migrating divergence settings from {divergence_file}: {e}")
        
        # Migrate RSI settings
        rsi_file = f"user_settings/rsi_settings_{user_id}.json"
        if os.path.exists(rsi_file):
            try:
                with open(rsi_file, 'r') as f:
                    rsi_settings = json.load(f)
                    settings["rsi"].update(rsi_settings)
            except Exception as e:
                print(f"Error migrating RSI settings from {rsi_file}: {e}")
        
        # Migrate pump/dump settings
        pump_dump_file = f"user_settings/pump_dump_settings_{user_id}.json"
        if os.path.exists(pump_dump_file):
            try:
                with open(pump_dump_file, 'r') as f:
                    pump_dump_settings = json.load(f)
                    settings["pump_dump"].update(pump_dump_settings)
            except Exception as e:
                print(f"Error migrating pump/dump settings from {pump_dump_file}: {e}")
        
        # Migrate trading settings
        trading_file = f"data/users/{user_id}/trading_settings.json"
        if os.path.exists(trading_file):
            try:
                with open(trading_file, 'r') as f:
                    trading_settings = json.load(f)
                    settings["trading"].update(trading_settings)
            except Exception as e:
                print(f"Error migrating trading settings from {trading_file}: {e}")
        
        # Migrate trading type settings
        trading_type_file = f"data/users/{user_id}/trading_type_settings.json"
        if os.path.exists(trading_type_file):
            try:
                with open(trading_type_file, 'r') as f:
                    trading_type_settings = json.load(f)
                    if "TRADING_TYPE" in trading_type_settings:
                        settings["trading"]["trading_type"] = trading_type_settings["TRADING_TYPE"].lower()
                    if "LEVERAGE" in trading_type_settings:
                        settings["trading"]["leverage"] = trading_type_settings["LEVERAGE"]
            except Exception as e:
                print(f"Error migrating trading type settings from {trading_type_file}: {e}")
        
        # Check for pump/dump subscription
        pump_dump_subscribers_file = "user_settings/pump_dump_subscribers.json"
        if os.path.exists(pump_dump_subscribers_file):
            try:
                with open(pump_dump_subscribers_file, 'r') as f:
                    subscribers = json.load(f)
                    settings["pump_dump_subscriber"] = user_id in subscribers
            except Exception as e:
                print(f"Error checking pump/dump subscription from {pump_dump_subscribers_file}: {e}")
        
        # Save the migrated settings
        save_user_settings(user_id, settings)
    
    print(f"Migration completed for {len(user_ids)} users")

# Добавляю функции для работы с выбором бирж

async def get_user_exchanges(user_id: int) -> list:
    """
    Получить список выбранных бирж пользователя
    """
    user = await get_user(user_id)
    # По умолчанию выбрана Binance
    return user.get('exchanges', ['Binance'])

async def update_user_exchanges(user_id: int, exchanges: list) -> bool:
    """
    Обновить список выбранных бирж пользователя
    """
    try:
        user = await get_user(user_id)
        user['exchanges'] = exchanges
        await set_user(user_id, user.get('percent', 5.0), user.get('balance', 50000.0), 
                     trading_type=user.get('trading_type', 'spot'), 
                     leverage=user.get('leverage', 1),
                     exchanges=exchanges)
        return True
    except Exception as e:
        print(f"Ошибка при обновлении списка бирж: {e}")
        return False

async def toggle_exchange(user_id: int, exchange: str) -> bool:
    """
    Переключить статус биржи (добавить если нет, удалить если есть)
    """
    exchanges = await get_user_exchanges(user_id)
    
    if exchange in exchanges:
        exchanges.remove(exchange)
    else:
        exchanges.append(exchange)
    
    return await update_user_exchanges(user_id, exchanges) 