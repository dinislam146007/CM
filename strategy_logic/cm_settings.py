import json
import os
from typing import Dict, Any, Optional

# Создаем директорию для пользовательских настроек, если её нет
os.makedirs('user_settings', exist_ok=True)

# Стандартные настройки CM
DEFAULT_CM_SETTINGS = {
    "SHORT_GAMMA": 0.4,
    "LONG_GAMMA": 0.8,
    "LOOKBACK_T": 21,
    "LOOKBACK_B": 15,
    "PCTILE": 90
}

def load_cm_settings(user_id: int) -> Dict[str, Any]:
    """
    Загружает настройки CM для конкретного пользователя.
    Если у пользователя нет индивидуальных настроек, возвращает стандартные.
    """
    try:
        file_path = f'user_settings/cm_settings_{user_id}.json'
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Ошибка при загрузке настроек CM для пользователя {user_id}: {e}")
    
    # Возвращаем стандартные настройки, если не удалось загрузить пользовательские
    return DEFAULT_CM_SETTINGS.copy()

def save_cm_settings(user_id: int, settings: Dict[str, Any]) -> bool:
    """
    Сохраняет настройки CM для конкретного пользователя.
    """
    try:
        file_path = f'user_settings/cm_settings_{user_id}.json'
        with open(file_path, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении настроек CM для пользователя {user_id}: {e}")
        return False

def reset_cm_settings(user_id: int) -> bool:
    """
    Сбрасывает настройки CM пользователя до стандартных значений.
    """
    return save_cm_settings(user_id, DEFAULT_CM_SETTINGS.copy())

def update_cm_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """
    Обновляет одну настройку CM для пользователя.
    """
    try:
        settings = load_cm_settings(user_id)
        
        # Проверка существования параметра
        if param_name not in DEFAULT_CM_SETTINGS:
            print(f"Параметр {param_name} не найден в стандартных настройках CM")
            return False
        
        # Конвертация значения в правильный тип
        default_value = DEFAULT_CM_SETTINGS[param_name]
        try:
            if isinstance(default_value, int):
                param_value = int(param_value)
            elif isinstance(default_value, float):
                param_value = float(param_value)
            # Остальные типы по необходимости
        except (ValueError, TypeError) as e:
            print(f"Ошибка преобразования типа для {param_name}: {e}")
            return False
        
        # Обновляем параметр
        settings[param_name] = param_value
        
        return save_cm_settings(user_id, settings)
    except Exception as e:
        print(f"Ошибка при обновлении параметра {param_name}: {e}")
        return False

def get_cm_param_names_and_types() -> Dict[str, str]:
    """
    Возвращает словарь с именами параметров CM и их типами данных.
    """
    param_types = {}
    for key, value in DEFAULT_CM_SETTINGS.items():
        if isinstance(value, int):
            param_types[key] = "int"
        elif isinstance(value, float):
            param_types[key] = "float"
        else:
            param_types[key] = type(value).__name__
    
    return param_types 