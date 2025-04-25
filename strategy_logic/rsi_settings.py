import json
import os
from typing import Dict, Any, Optional

# Create user settings directory if it doesn't exist
os.makedirs('user_settings', exist_ok=True)

# Default RSI settings
DEFAULT_RSI_SETTINGS = {
    "RSI_PERIOD": 14,
    "RSI_OVERBOUGHT": 70,
    "RSI_OVERSOLD": 30,
    "EMA_FAST": 9,
    "EMA_SLOW": 21
}

def load_rsi_settings(user_id: int) -> Dict[str, Any]:
    """
    Loads RSI indicator settings for a specific user.
    If the user doesn't have custom settings, returns default settings.
    """
    try:
        file_path = f'user_settings/rsi_settings_{user_id}.json'
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading RSI settings for user {user_id}: {e}")
    
    # Return default settings if custom settings couldn't be loaded
    return DEFAULT_RSI_SETTINGS.copy()

def save_rsi_settings(user_id: int, settings: Dict[str, Any]) -> bool:
    """
    Saves RSI indicator settings for a specific user.
    """
    try:
        file_path = f'user_settings/rsi_settings_{user_id}.json'
        with open(file_path, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving RSI settings for user {user_id}: {e}")
        return False

def reset_rsi_settings(user_id: int) -> bool:
    """
    Resets RSI indicator settings for a user to default values.
    """
    return save_rsi_settings(user_id, DEFAULT_RSI_SETTINGS.copy())

def update_rsi_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """
    Updates a single RSI indicator setting for a user.
    """
    try:
        settings = load_rsi_settings(user_id)
        
        # Check if parameter exists
        if param_name not in DEFAULT_RSI_SETTINGS:
            print(f"Parameter {param_name} not found in default RSI settings")
            return False
        
        # Convert value to the correct type
        default_value = DEFAULT_RSI_SETTINGS[param_name]
        try:
            if isinstance(default_value, int):
                param_value = int(param_value)
            elif isinstance(default_value, float):
                param_value = float(param_value)
            # Other types as needed
        except (ValueError, TypeError) as e:
            print(f"Type conversion error for {param_name}: {e}")
            return False
        
        # Update parameter
        settings[param_name] = param_value
        
        return save_rsi_settings(user_id, settings)
    except Exception as e:
        print(f"Error updating parameter {param_name}: {e}")
        return False

def get_rsi_param_names_and_types() -> Dict[str, str]:
    """
    Returns a dictionary with RSI parameter names and their data types.
    """
    param_types = {}
    for key, value in DEFAULT_RSI_SETTINGS.items():
        if isinstance(value, int):
            param_types[key] = "int"
        elif isinstance(value, float):
            param_types[key] = "float"
        else:
            param_types[key] = type(value).__name__
    
    return param_types 