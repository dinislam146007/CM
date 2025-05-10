import os
import json

# Default trading type settings
DEFAULT_TRADING_TYPE_SETTINGS = {
    "TRADING_TYPE": "SPOT",  # "SPOT" or "FUTURES"
    "LEVERAGE": 1,           # Only applicable for futures
}

def load_trading_type_settings(user_id=None):
    """
    Load trading type settings for a specific user or default if not found
    """
    # Default settings
    default_settings = DEFAULT_TRADING_TYPE_SETTINGS.copy()
    
    if user_id is None:
        return default_settings
        
    try:
        user_settings_file = f"user_settings/{user_id}.json"
        if os.path.exists(user_settings_file):
            with open(user_settings_file, 'r') as f:
                user_data = json.load(f)
                
                # Приоритет user.trading_type над trading.trading_type
                
                # Сначала загружаем из trading
                if "trading" in user_data and "trading_type" in user_data["trading"]:
                    trading_type = user_data["trading"]["trading_type"]
                    print(f"Найдены настройки типа торговли из trading: {trading_type}")
                    default_settings["trading_type"] = trading_type
                
                # Затем перезаписываем из user, если есть (имеет приоритет)
                if "user" in user_data and "trading_type" in user_data["user"]:
                    trading_type = user_data["user"]["trading_type"]
                    print(f"Найдены настройки типа торговли из user: {trading_type} (ПРИОРИТЕТ)")
                    default_settings["trading_type"] = trading_type
                
                return default_settings
        else:
            # If user directory doesn't exist, create it
            if user_id:
                os.makedirs(os.path.dirname(user_settings_file), exist_ok=True)
            
            # Save and return default settings
            save_trading_type_settings(DEFAULT_TRADING_TYPE_SETTINGS, user_id)
            return DEFAULT_TRADING_TYPE_SETTINGS
    except Exception as e:
        print(f"Error loading trading type settings: {e}")
        return DEFAULT_TRADING_TYPE_SETTINGS

def save_trading_type_settings(settings, user_id=None):
    """
    Save trading type settings for a specific user or as default
    """
    settings_file = f"data/users/{user_id}/trading_type_settings.json" if user_id else "data/default/trading_type_settings.json"
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving trading type settings: {e}")
        return False

def update_trading_type_setting(user_id, trading_type):
    """
    Update the trading type setting
    """
    current_settings = load_trading_type_settings(user_id)
    
    # Update trading type
    current_settings["TRADING_TYPE"] = trading_type.upper()
    
    # If changing to SPOT, reset leverage to 1
    if trading_type.upper() == "SPOT":
        current_settings["LEVERAGE"] = 1
    
    # Validate and save updated settings
    validate_trading_type_settings(current_settings)
    return save_trading_type_settings(current_settings, user_id)

def update_leverage_setting(user_id, leverage):
    """
    Update the leverage setting
    """
    current_settings = load_trading_type_settings(user_id)
    
    # Can only set leverage for FUTURES trading
    if current_settings["TRADING_TYPE"] != "FUTURES":
        print(f"Cannot set leverage for {current_settings['TRADING_TYPE']} trading")
        return False
    
    # Update leverage setting
    try:
        leverage = int(leverage)
        current_settings["LEVERAGE"] = leverage
        
        # Validate and save updated settings
        validate_trading_type_settings(current_settings)
        return save_trading_type_settings(current_settings, user_id)
    except ValueError:
        print(f"Invalid leverage value: {leverage}")
        return False

def validate_trading_type_settings(settings):
    """
    Validate trading type settings and make corrections if needed
    """
    # Ensure trading_type is valid
    if settings["TRADING_TYPE"] not in ["SPOT", "FUTURES"]:
        settings["TRADING_TYPE"] = "SPOT"
    
    # For spot trading, leverage must be 1
    if settings["TRADING_TYPE"] == "SPOT":
        settings["LEVERAGE"] = 1
    
    # For futures, ensure leverage is within reasonable range (1-100 is typical)
    if settings["TRADING_TYPE"] == "FUTURES":
        if settings["LEVERAGE"] < 1:
            settings["LEVERAGE"] = 1
        elif settings["LEVERAGE"] > 100:
            settings["LEVERAGE"] = 100
    
    return settings 