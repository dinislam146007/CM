import json
import os
from typing import Dict, Any, Optional
from strategy_logic.moon_bot_strategy import DEFAULT_PARAMS

# Path to store user parameters
USER_PARAMS_FILE = 'user_strategy_params.json'

def load_user_params(user_id: int) -> Dict[str, Any]:
    """
    Load strategy parameters for a specific user.
    If user has no custom parameters, return default parameters.
    """
    try:
        if os.path.exists(USER_PARAMS_FILE):
            with open(USER_PARAMS_FILE, 'r') as f:
                all_user_params = json.load(f)
                user_id_str = str(user_id)  # Convert to string for JSON dictionary keys
                if user_id_str in all_user_params:
                    return all_user_params[user_id_str]
    except Exception as e:
        print(f"Error loading user parameters: {e}")
    
    # Return default parameters if no custom ones exist
    return DEFAULT_PARAMS.copy()

def save_user_params(user_id: int, params: Dict[str, Any]) -> bool:
    """
    Save strategy parameters for a specific user.
    """
    try:
        # Load existing parameters for all users
        all_user_params = {}
        if os.path.exists(USER_PARAMS_FILE):
            with open(USER_PARAMS_FILE, 'r') as f:
                all_user_params = json.load(f)
        
        # Update parameters for this user
        user_id_str = str(user_id)  # Convert to string for JSON dictionary keys
        all_user_params[user_id_str] = params
        
        # Save updated parameters
        with open(USER_PARAMS_FILE, 'w') as f:
            json.dump(all_user_params, f, indent=2)
        
        return True
    except Exception as e:
        print(f"Error saving user parameters: {e}")
        return False

def reset_user_params(user_id: int) -> bool:
    """
    Reset user parameters to default values.
    """
    return save_user_params(user_id, DEFAULT_PARAMS.copy())

def update_user_param(user_id: int, param_name: str, param_value: Any) -> bool:
    """
    Update a single parameter for a user.
    """
    params = load_user_params(user_id)
    
    # Handle special case for blacklist which is a set
    if param_name == "CoinsBlackList":
        if isinstance(param_value, str):
            # If it's comma-separated string, convert to set
            param_value = {coin.strip() for coin in param_value.split(',')}
        params[param_name] = set(param_value)
    else:
        # For other parameters, just update the value
        params[param_name] = param_value
    
    return save_user_params(user_id, params)

def get_param_names_and_types() -> Dict[str, str]:
    """
    Return a dictionary of parameter names and their data types.
    This is useful for validating user input.
    """
    param_types = {}
    for key, value in DEFAULT_PARAMS.items():
        if isinstance(value, set):
            param_types[key] = "set"
        elif isinstance(value, (int, float)):
            param_types[key] = "number"
        else:
            param_types[key] = type(value).__name__
    
    return param_types
