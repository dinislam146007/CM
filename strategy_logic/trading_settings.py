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
    """
    settings_file = f"data/users/{user_id}/trading_settings.json" if user_id else "data/default/trading_settings.json"
    
    try:
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                return json.load(f)
        else:
            # If user directory doesn't exist, create it
            if user_id:
                os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            
            # Save and return default settings
            save_trading_settings(DEFAULT_TRADING_SETTINGS, user_id)
            return DEFAULT_TRADING_SETTINGS
    except Exception as e:
        print(f"Error loading trading settings: {e}")
        return DEFAULT_TRADING_SETTINGS

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