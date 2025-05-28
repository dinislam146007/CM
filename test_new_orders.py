#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой логики фильтрации сделок
"""

from keyboard.inline import orders_pairs_inline, orders_pair_timeframes_inline
from basic.handlers import interval_conv, interval_weight

def test_pairs_filter():
    """Тестируем фильтрацию по парам"""
    
    print("=== Тест фильтрации по торговым парам ===")
    
    # Тестовые пары
    test_pairs = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT']
    
    # Тест для открытых сделок
    print("\n1. Тест для открытых сделок:")
    keyboard_open = orders_pairs_inline('open', test_pairs)
    print(f"Создана клавиатура с {len(keyboard_open.inline_keyboard)} рядами кнопок")
    
    for i, row in enumerate(keyboard_open.inline_keyboard):
        print(f"  Ряд {i+1}: {[btn.text for btn in row]}")

def test_pair_timeframes():
    """Тестируем фильтрацию по таймфреймам для конкретной пары"""
    
    print("\n=== Тест фильтрации по таймфреймам для пары ===")
    
    # Тестовые таймфреймы
    test_timeframes = ['1D', '4H', '1H', '30']
    test_pair = 'BTCUSDT'
    
    print(f"\nТест для пары {test_pair}:")
    keyboard = orders_pair_timeframes_inline('open', test_pair, test_timeframes)
    print(f"Создана клавиатура с {len(keyboard.inline_keyboard)} рядами кнопок")
    
    for i, row in enumerate(keyboard.inline_keyboard):
        print(f"  Ряд {i+1}: {[btn.text for btn in row]}")

def test_timeframe_sorting():
    """Тестируем сортировку таймфреймов"""
    
    print("\n=== Тест сортировки таймфреймов ===")
    
    # Неупорядоченные таймфреймы
    unsorted_timeframes = ['30', '1H', '1D', '4H']
    
    print(f"Исходный порядок: {unsorted_timeframes}")
    
    # Сортируем по важности
    sorted_timeframes = sorted(unsorted_timeframes, 
                             key=lambda x: interval_weight(x), reverse=True)
    
    print(f"Отсортированный порядок: {sorted_timeframes}")
    
    # Показываем конвертированные названия
    converted = [interval_conv(tf) for tf in sorted_timeframes]
    print(f"Конвертированные названия: {converted}")

if __name__ == "__main__":
    test_pairs_filter()
    test_pair_timeframes()
    test_timeframe_sorting()
    print("\n✅ Все тесты завершены!") 