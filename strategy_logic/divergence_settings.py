import json
import os
from typing import Dict, Any, Optional

# Создаем директорию для пользовательских настроек, если её нет
os.makedirs('user_settings', exist_ok=True)

# Стандартные настройки индикатора дивергенции
DEFAULT_DIVERGENCE_SETTINGS = {
    "RSI_LENGTH": 7,
    "LB_RIGHT": 3,
    "LB_LEFT": 3,
    "RANGE_UPPER": 60,
    "RANGE_LOWER": 5,
    "TAKE_PROFIT_RSI_LEVEL": 80,
    "STOP_LOSS_TYPE": "PERC",  # "ATR", "PERC", "NONE"
    "STOP_LOSS_PERC": 5.0,
    "ATR_LENGTH": 14,
    "ATR_MULTIPLIER": 3.5
}

def load_divergence_settings(user_id: int) -> Dict[str, Any]:
    """
    Загружает настройки индикатора дивергенции для конкретного пользователя.
    Если у пользователя нет индивидуальных настроек, возвращает стандартные.
    """
    try:
        file_path = f'user_settings/divergence_settings_{user_id}.json'
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Ошибка при загрузке настроек дивергенции для пользователя {user_id}: {e}")
    
    # Возвращаем стандартные настройки, если не удалось загрузить пользовательские
    return DEFAULT_DIVERGENCE_SETTINGS.copy()

def save_divergence_settings(user_id: int, settings: Dict[str, Any]) -> bool:
    """
    Сохраняет настройки индикатора дивергенции для конкретного пользователя.
    """
    try:
        file_path = f'user_settings/divergence_settings_{user_id}.json'
        with open(file_path, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении настроек дивергенции для пользователя {user_id}: {e}")
        return False

def reset_divergence_settings(user_id: int) -> bool:
    """
    Сбрасывает настройки индикатора дивергенции пользователя до стандартных значений.
    """
    return save_divergence_settings(user_id, DEFAULT_DIVERGENCE_SETTINGS.copy())

def update_divergence_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """
    Обновляет одну настройку индикатора дивергенции для пользователя.
    """
    try:
        settings = load_divergence_settings(user_id)
        
        # Проверка существования параметра
        if param_name not in DEFAULT_DIVERGENCE_SETTINGS:
            print(f"Параметр {param_name} не найден в стандартных настройках дивергенции")
            return False
        
        # Конвертация значения в правильный тип
        default_value = DEFAULT_DIVERGENCE_SETTINGS[param_name]
        try:
            if isinstance(default_value, int):
                param_value = int(param_value)
            elif isinstance(default_value, float):
                param_value = float(param_value)
            elif param_name == "STOP_LOSS_TYPE" and param_value in ["ATR", "PERC", "NONE"]:
                # Особая обработка для строкового перечисления
                pass
            # Остальные типы по необходимости
        except (ValueError, TypeError) as e:
            print(f"Ошибка преобразования типа для {param_name}: {e}")
            return False
        
        # Обновляем параметр
        settings[param_name] = param_value
        
        return save_divergence_settings(user_id, settings)
    except Exception as e:
        print(f"Ошибка при обновлении параметра {param_name}: {e}")
        return False

def get_divergence_param_names_and_types() -> Dict[str, str]:
    """
    Возвращает словарь с именами параметров индикатора дивергенции и их типами данных.
    """
    param_types = {}
    for key, value in DEFAULT_DIVERGENCE_SETTINGS.items():
        if isinstance(value, int):
            param_types[key] = "int"
        elif isinstance(value, float):
            param_types[key] = "float"
        elif key == "STOP_LOSS_TYPE":
            param_types[key] = "enum"  # Перечисление
        else:
            param_types[key] = type(value).__name__
    
    return param_types 