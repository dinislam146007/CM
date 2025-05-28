#!/usr/bin/env python3
"""
Тестовый скрипт для проверки настроек MoonBot
"""

import asyncio
from user_settings import load_user_params, update_user_param, reset_user_params

async def test_moonbot_settings():
    """Тестируем настройки MoonBot"""
    
    test_user_id = 12345
    
    print("=== Тест настроек MoonBot ===\n")
    
    # 1. Загружаем настройки по умолчанию
    print("1. Загружаем настройки по умолчанию:")
    params = load_user_params(test_user_id)
    
    print(f"   💰 OrderSize: {params['OrderSize']}")
    print(f"   📈 TakeProfit: {params['TakeProfit']}%")
    print(f"   📉 StopLoss: {params['StopLoss']}%")
    print(f"   📊 MinVolume: {params['MinVolume']}")
    print(f"   📊 MaxVolume: {params['MaxVolume']}")
    print(f"   🕐 MinHourlyVolume: {params['MinHourlyVolume']}")
    print(f"   🕐 MaxHourlyVolume: {params['MaxHourlyVolume']}")
    print(f"   📈 Delta_3h_Max: {params['Delta_3h_Max']}%")
    print(f"   📈 Delta_24h_Max: {params['Delta_24h_Max']}%")
    print(f"   ⚡ Delta2_Max: {params['Delta2_Max']}%")
    print(f"   ₿ Delta_BTC_Min: {params['Delta_BTC_Min']}%")
    print(f"   ₿ Delta_BTC_Max: {params['Delta_BTC_Max']}%")
    print(f"   ⛔ CoinsBlackList: {params['CoinsBlackList']}")
    
    # 2. Тестируем изменение Take Profit
    print("\n2. Тестируем изменение Take Profit:")
    old_tp = params['TakeProfit']
    new_tp = 5.0
    
    success = await update_user_param(test_user_id, 'TakeProfit', new_tp)
    print(f"   Изменение TakeProfit с {old_tp}% на {new_tp}%: {'✅ Успешно' if success else '❌ Ошибка'}")
    
    # Проверяем, что изменение сохранилось
    updated_params = load_user_params(test_user_id)
    actual_tp = updated_params['TakeProfit']
    print(f"   Проверка: TakeProfit = {actual_tp}% {'✅ Корректно' if actual_tp == new_tp else '❌ Ошибка'}")
    
    # 3. Тестируем изменение других параметров
    print("\n3. Тестируем изменение других параметров:")
    
    test_params = {
        'OrderSize': 100.0,
        'StopLoss': 2.0,
        'MinHourlyVolume': 2000000,
        'Delta_BTC_Max': 1.0
    }
    
    for param_name, new_value in test_params.items():
        old_value = updated_params[param_name]
        success = await update_user_param(test_user_id, param_name, new_value)
        print(f"   {param_name}: {old_value} → {new_value} {'✅' if success else '❌'}")
    
    # 4. Проверяем все изменения
    print("\n4. Проверяем все изменения:")
    final_params = load_user_params(test_user_id)
    
    for param_name, expected_value in test_params.items():
        actual_value = final_params[param_name]
        status = "✅" if actual_value == expected_value else "❌"
        print(f"   {param_name}: {actual_value} (ожидалось {expected_value}) {status}")
    
    # 5. Тестируем сброс настроек
    print("\n5. Тестируем сброс настроек:")
    reset_success = await reset_user_params(test_user_id)
    print(f"   Сброс настроек: {'✅ Успешно' if reset_success else '❌ Ошибка'}")
    
    # Проверяем, что настройки сброшены
    reset_params = load_user_params(test_user_id)
    tp_after_reset = reset_params['TakeProfit']
    print(f"   TakeProfit после сброса: {tp_after_reset}% (ожидалось 3.0%) {'✅' if tp_after_reset == 3.0 else '❌'}")
    
    print("\n=== Тест завершен ===")

if __name__ == "__main__":
    asyncio.run(test_moonbot_settings()) 