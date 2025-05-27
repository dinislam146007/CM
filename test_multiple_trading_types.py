#!/usr/bin/env python3
"""
Тестовый файл для проверки функциональности множественных типов торговли
"""

import asyncio
import sys
import os

# Добавляем текущую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from user_settings import (
    load_trading_types,
    update_trading_types,
    add_trading_type,
    remove_trading_type,
    toggle_trading_type,
    load_user_settings,
    save_user_settings
)

async def test_multiple_trading_types():
    """Тестирование функций множественных типов торговли"""
    test_user_id = 999999  # Тестовый пользователь
    
    print("🧪 Тестирование функций множественных типов торговли")
    print("=" * 60)
    
    # Тест 1: Загрузка по умолчанию
    print("\n1. Тест загрузки по умолчанию:")
    types = load_trading_types(test_user_id)
    print(f"   Типы торговли по умолчанию: {types}")
    assert types == ["spot"], f"Ожидался ['spot'], получен {types}"
    print("   ✅ Тест пройден")
    
    # Тест 2: Добавление типа торговли
    print("\n2. Тест добавления типа торговли:")
    success = await add_trading_type(test_user_id, "futures")
    print(f"   Добавление futures: {success}")
    types = load_trading_types(test_user_id)
    print(f"   Текущие типы: {types}")
    assert "futures" in types, f"futures должен быть в списке: {types}"
    print("   ✅ Тест пройден")
    
    # Тест 3: Переключение типа торговли
    print("\n3. Тест переключения типа торговли:")
    success = await toggle_trading_type(test_user_id, "spot")
    print(f"   Переключение spot (убрать): {success}")
    types = load_trading_types(test_user_id)
    print(f"   Текущие типы: {types}")
    assert types == ["futures"], f"Ожидался ['futures'], получен {types}"
    
    success = await toggle_trading_type(test_user_id, "spot")
    print(f"   Переключение spot (добавить): {success}")
    types = load_trading_types(test_user_id)
    print(f"   Текущие типы: {types}")
    assert "spot" in types and "futures" in types, f"Оба типа должны быть в списке: {types}"
    print("   ✅ Тест пройден")
    
    # Тест 4: Попытка убрать единственный тип
    print("\n4. Тест защиты от удаления единственного типа:")
    await update_trading_types(test_user_id, ["spot"])  # Оставляем только spot
    success = await toggle_trading_type(test_user_id, "spot")
    print(f"   Попытка убрать единственный тип: {success}")
    types = load_trading_types(test_user_id)
    print(f"   Текущие типы: {types}")
    assert not success, "Не должно быть возможности убрать единственный тип"
    assert types == ["spot"], f"Должен остаться ['spot'], получен {types}"
    print("   ✅ Тест пройден")
    
    # Тест 5: Обновление множественных типов
    print("\n5. Тест обновления множественных типов:")
    success = await update_trading_types(test_user_id, ["spot", "futures"])
    print(f"   Установка обоих типов: {success}")
    types = load_trading_types(test_user_id)
    print(f"   Текущие типы: {types}")
    assert set(types) == {"spot", "futures"}, f"Ожидались оба типа, получен {types}"
    print("   ✅ Тест пройден")
    
    # Тест 6: Проверка обратной совместимости
    print("\n6. Тест обратной совместимости:")
    settings = load_user_settings(test_user_id)
    print(f"   trading_type (для совместимости): {settings['trading']['trading_type']}")
    print(f"   trading_types (новый формат): {settings['trading']['trading_types']}")
    assert settings['trading']['trading_type'] in settings['trading']['trading_types'], \
        "trading_type должен быть в списке trading_types"
    print("   ✅ Тест пройден")
    
    # Очистка тестовых данных
    print("\n🧹 Очистка тестовых данных...")
    settings_file = f"user_settings/{test_user_id}.json"
    if os.path.exists(settings_file):
        os.remove(settings_file)
        print(f"   Удален файл: {settings_file}")
    
    print("\n🎉 Все тесты пройдены успешно!")

def test_keyboard_functionality():
    """Тестирование клавиатуры"""
    print("\n🎹 Тестирование клавиатуры:")
    
    try:
        from keyboard.inline import trading_type_settings_inline
        
        # Тест с пользователем
        keyboard = trading_type_settings_inline(999999)
        print("   ✅ Клавиатура создана успешно")
        
        # Проверяем структуру клавиатуры
        assert keyboard.inline_keyboard is not None, "Клавиатура должна содержать кнопки"
        print(f"   Количество рядов кнопок: {len(keyboard.inline_keyboard)}")
        
        # Проверяем наличие кнопок toggle
        found_toggle = False
        for row in keyboard.inline_keyboard:
            for button in row:
                if "toggle_trading_type:" in button.callback_data:
                    found_toggle = True
                    break
        
        assert found_toggle, "Должны быть кнопки с toggle_trading_type:"
        print("   ✅ Найдены кнопки переключения типов торговли")
        
    except ImportError as e:
        print(f"   ⚠️ Не удалось импортировать клавиатуру: {e}")

if __name__ == "__main__":
    print("🚀 Запуск тестов множественных типов торговли")
    
    # Запускаем асинхронные тесты
    asyncio.run(test_multiple_trading_types())
    
    # Запускаем тесты клавиатуры
    test_keyboard_functionality()
    
    print("\n✨ Тестирование завершено!") 