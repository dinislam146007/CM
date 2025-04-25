import json
import os
from typing import Dict, Any, Optional, List, Union

# Создаем директорию для пользовательских настроек, если её нет
os.makedirs('user_settings', exist_ok=True)

# Стандартные настройки Pump/Dump детектора
DEFAULT_PUMP_DUMP_SETTINGS = {
    "VOLUME_THRESHOLD": 3.0,
    "PRICE_CHANGE_THRESHOLD": 3.0,
    "TIME_WINDOW": 15,
    "MONITOR_INTERVALS": ["5m", "15m", "1h", "4h"],
    "ENABLED": True
}

# Список подписчиков на уведомления
SUBSCRIBERS_FILE = 'user_settings/pump_dump_subscribers.json'

def load_pump_dump_settings(user_id: int) -> Dict[str, Any]:
    """
    Загружает настройки Pump/Dump детектора для конкретного пользователя.
    Если у пользователя нет индивидуальных настроек, возвращает стандартные.
    """
    try:
        file_path = f'user_settings/pump_dump_settings_{user_id}.json'
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Ошибка при загрузке настроек Pump/Dump для пользователя {user_id}: {e}")
    
    # Возвращаем стандартные настройки, если не удалось загрузить пользовательские
    return DEFAULT_PUMP_DUMP_SETTINGS.copy()

def save_pump_dump_settings(user_id: int, settings: Dict[str, Any]) -> bool:
    """
    Сохраняет настройки Pump/Dump детектора для конкретного пользователя.
    """
    try:
        file_path = f'user_settings/pump_dump_settings_{user_id}.json'
        with open(file_path, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении настроек Pump/Dump для пользователя {user_id}: {e}")
        return False

def reset_pump_dump_settings(user_id: int) -> bool:
    """
    Сбрасывает настройки Pump/Dump детектора пользователя до стандартных значений.
    """
    return save_pump_dump_settings(user_id, DEFAULT_PUMP_DUMP_SETTINGS.copy())

def update_pump_dump_setting(user_id: int, param_name: str, param_value: Any) -> bool:
    """
    Обновляет одну настройку Pump/Dump детектора для пользователя.
    """
    try:
        settings = load_pump_dump_settings(user_id)
        
        # Проверка существования параметра
        if param_name not in DEFAULT_PUMP_DUMP_SETTINGS:
            print(f"Параметр {param_name} не найден в стандартных настройках Pump/Dump")
            return False
        
        # Конвертация значения в правильный тип
        default_value = DEFAULT_PUMP_DUMP_SETTINGS[param_name]
        try:
            if isinstance(default_value, int):
                param_value = int(param_value)
            elif isinstance(default_value, float):
                param_value = float(param_value)
            elif isinstance(default_value, bool):
                if param_value.lower() == 'true':
                    param_value = True
                elif param_value.lower() == 'false':
                    param_value = False
                else:
                    print(f"Неверное значение для {param_name}: ожидается 'true' или 'false'")
                    return False
            elif isinstance(default_value, list) and param_name == "MONITOR_INTERVALS":
                # Обработка списка интервалов как строки через запятую
                param_value = [item.strip() for item in param_value.split(',')]
            # Остальные типы по необходимости
        except (ValueError, TypeError) as e:
            print(f"Ошибка преобразования типа для {param_name}: {e}")
            return False
        
        # Обновляем параметр
        settings[param_name] = param_value
        
        return save_pump_dump_settings(user_id, settings)
    except Exception as e:
        print(f"Ошибка при обновлении параметра {param_name}: {e}")
        return False

def get_pump_dump_param_names_and_types() -> Dict[str, str]:
    """
    Возвращает словарь с именами параметров Pump/Dump детектора и их типами данных.
    """
    param_types = {}
    for key, value in DEFAULT_PUMP_DUMP_SETTINGS.items():
        if isinstance(value, int):
            param_types[key] = "int"
        elif isinstance(value, float):
            param_types[key] = "float"
        elif isinstance(value, bool):
            param_types[key] = "bool"
        elif isinstance(value, list):
            param_types[key] = "list"
        else:
            param_types[key] = type(value).__name__
    
    return param_types

# Функции для работы с подписчиками
def load_subscribers() -> List[int]:
    """
    Загружает список подписчиков на уведомления Pump/Dump.
    """
    try:
        if os.path.exists(SUBSCRIBERS_FILE):
            with open(SUBSCRIBERS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Ошибка при загрузке списка подписчиков Pump/Dump: {e}")
    
    return []

def save_subscribers(subscribers: List[int]) -> bool:
    """
    Сохраняет список подписчиков на уведомления Pump/Dump.
    """
    try:
        with open(SUBSCRIBERS_FILE, 'w') as f:
            json.dump(subscribers, f, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении списка подписчиков Pump/Dump: {e}")
        return False

def add_subscriber(user_id: int) -> bool:
    """
    Добавляет пользователя в список подписчиков на уведомления Pump/Dump.
    """
    subscribers = load_subscribers()
    if user_id not in subscribers:
        subscribers.append(user_id)
        return save_subscribers(subscribers)
    return True  # Пользователь уже подписан

def remove_subscriber(user_id: int) -> bool:
    """
    Удаляет пользователя из списка подписчиков на уведомления Pump/Dump.
    """
    subscribers = load_subscribers()
    if user_id in subscribers:
        subscribers.remove(user_id)
        return save_subscribers(subscribers)
    return True  # Пользователь и так не подписан

def is_subscribed(user_id: int) -> bool:
    """
    Проверяет, подписан ли пользователь на уведомления Pump/Dump.
    """
    subscribers = load_subscribers()
    return user_id in subscribers 