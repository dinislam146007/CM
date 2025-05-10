import os
import json

# Default trading settings
DEFAULT_TRADING_SETTINGS = {
    "trading_type": "spot",  # "spot" or "futures"
    "leverage": 1,           # Only applicable for futures
}

def load_trading_settings(user_id=None):
    """
    Load trading settings for a specific user or default if not found
    
    Now supports reading from both:
    1. user_settings/{user_id}.json (primary source)
    2. data/users/{user_id}/trading_settings.json (legacy source)
    """
    # Default settings
    default_settings = DEFAULT_TRADING_SETTINGS.copy()
    
    if user_id is None:
        return default_settings
        
    # First try to load from user_settings/{user_id}.json (new format)
    try:
        user_settings_file = f"user_settings/{user_id}.json"
        if os.path.exists(user_settings_file):
            with open(user_settings_file, 'r') as f:
                user_data = json.load(f)
                
                print(f"DEBUG: Загружены настройки для {user_id} из {user_settings_file}")
                
                # Сначала проверим секцию trading (с низшим приоритетом)
                if "trading" in user_data and isinstance(user_data["trading"], dict):
                    if "trading_type" in user_data["trading"]:
                        default_settings["trading_type"] = user_data["trading"]["trading_type"]
                        print(f"DEBUG: Найден trading_type в trading: {user_data['trading']['trading_type']}")
                    
                    if "leverage" in user_data["trading"]:
                        default_settings["leverage"] = int(user_data["trading"]["leverage"])
                        print(f"DEBUG: Найден leverage в trading: {user_data['trading']['leverage']}")
                
                # Затем проверим секцию user (с высшим приоритетом) - перезапишет настройки из trading
                if "user" in user_data and isinstance(user_data["user"], dict):
                    # Load trading_type
                    if "trading_type" in user_data["user"]:
                        default_settings["trading_type"] = user_data["user"]["trading_type"]
                        print(f"DEBUG: Найден trading_type в user: {user_data['user']['trading_type']} - ПРИОРИТЕТ!")
                    
                    # Load leverage
                    if "leverage" in user_data["user"]:
                        default_settings["leverage"] = int(user_data["user"]["leverage"])
                        print(f"DEBUG: Найден leverage в user: {user_data['user']['leverage']} - ПРИОРИТЕТ!")
                
                # Validate settings
                result = validate_trading_settings(default_settings)
                print(f"DEBUG: Финальные настройки: {result}")
                return result
    except Exception as e:
        print(f"Error loading from user_settings/{user_id}.json: {e}")
        
    # Fallback: try legacy settings file
    settings_file = f"data/users/{user_id}/trading_settings.json"
    
    try:
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                settings = json.load(f)
                print(f"DEBUG: Загружены legacy настройки для {user_id}: {settings}")
                return validate_trading_settings(settings)
        else:
            # If user directory doesn't exist, create it
            os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            
            # Save and return default settings
            save_trading_settings(default_settings, user_id)
            print(f"DEBUG: Созданы дефолтные настройки для {user_id}: {default_settings}")
            return default_settings
    except Exception as e:
        print(f"Error loading trading settings: {e}")
        return default_settings

def save_trading_settings(settings, user_id=None):
    """
    Save trading settings for a specific user or as default
    """
    settings_file = f"data/users/{user_id}/trading_settings.json" if user_id else "data/default/trading_settings.json"
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving trading settings: {e}")
        return False

def update_trading_settings(updates, user_id=None):
    """
    Update specific fields in the trading settings
    """
    current_settings = load_trading_settings(user_id)
    
    # Update settings
    for key, value in updates.items():
        current_settings[key] = value
    
    # Ensure the settings are valid
    validate_trading_settings(current_settings)
    
    # Save updated settings
    return save_trading_settings(current_settings, user_id)

def validate_trading_settings(settings):
    """
    Validate trading settings and make corrections if needed
    """
    # Ensure trading_type is valid
    if settings["trading_type"] not in ["spot", "futures"]:
        settings["trading_type"] = "spot"
    
    # For spot trading, leverage must be 1
    if settings["trading_type"] == "spot":
        settings["leverage"] = 1
    
    # For futures, ensure leverage is within reasonable range (1-125 is typical for Bybit)
    if settings["trading_type"] == "futures":
        if settings["leverage"] < 1:
            settings["leverage"] = 1
        elif settings["leverage"] > 125:
            settings["leverage"] = 125
    
    return settings 