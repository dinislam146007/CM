#!/usr/bin/env python3
import asyncio
import sys
import os
import sqlite3

sys.path.append('.')

async def check_db():
    from db.connect import connect
    
    print("=== Проверка структуры базы данных ===\n")
    
    # Проверяем SQLite файл напрямую
    db_path = 'data/trading_data.db'
    if os.path.exists(db_path):
        print(f"✅ SQLite файл найден: {db_path}")
        
        sqlite_conn = sqlite3.connect(db_path)
        cursor = sqlite_conn.cursor()
        
        # Получаем структуру таблицы
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'")
        result = cursor.fetchone()
        if result:
            print("\n📋 Структура таблицы orders:")
            print(result[0])
        
        # Получаем список колонок
        cursor.execute('PRAGMA table_info(orders)')
        columns = cursor.fetchall()
        print(f"\n📊 Колонки в таблице orders ({len(columns)} всего):")
        
        strategy_columns = []
        for col in columns:
            col_name = col[1]
            col_type = col[2]
            print(f"  • {col_name} ({col_type})")
            
            if col_name in ['price_action_active', 'price_action_pattern', 'cm_active', 
                           'moonbot_active', 'rsi_active', 'divergence_active', 'divergence_type']:
                strategy_columns.append(col_name)
        
        print(f"\n🎯 Найдено колонок стратегий: {len(strategy_columns)}")
        for col in strategy_columns:
            print(f"  ✅ {col}")
        
        missing_strategy_columns = []
        expected_columns = ['price_action_active', 'price_action_pattern', 'cm_active', 
                           'moonbot_active', 'rsi_active', 'divergence_active', 'divergence_type']
        
        for expected in expected_columns:
            if expected not in strategy_columns:
                missing_strategy_columns.append(expected)
        
        if missing_strategy_columns:
            print(f"\n❌ Отсутствующие колонки стратегий: {missing_strategy_columns}")
        else:
            print("\n✅ Все колонки стратегий присутствуют")
        
        sqlite_conn.close()
    else:
        print(f"❌ SQLite файл не найден: {db_path}")
    
    # Проверяем через wrapper
    print("\n=== Проверка через database wrapper ===")
    try:
        conn = await connect()
        print("✅ Подключение через wrapper успешно")
        
        # Тестируем доступ к колонкам стратегий
        for col in expected_columns:
            try:
                await conn.fetchval(f"SELECT {col} FROM orders LIMIT 1")
                print(f"✅ Колонка {col} доступна через wrapper")
            except Exception as e:
                print(f"❌ Ошибка доступа к колонке {col}: {e}")
        
        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения через wrapper: {e}")

if __name__ == "__main__":
    asyncio.run(check_db()) 