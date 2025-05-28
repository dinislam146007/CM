#!/usr/bin/env python3
"""
Скрипт для проверки и выполнения миграции базы данных
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def check_and_migrate():
    """Проверяем состояние базы данных и выполняем миграцию"""
    
    try:
        from db.orders import migrate_strategy_fields, get_order_by_id
        from db.connect import connect
        
        print("=== Проверка состояния базы данных ===\n")
        
        # Проверяем подключение к базе данных
        try:
            conn = await connect()
            print("✅ Подключение к базе данных успешно")
            
            # Проверяем, существует ли таблица orders
            try:
                result = await conn.fetchval("SELECT COUNT(*) FROM orders LIMIT 1")
                print(f"✅ Таблица orders существует, записей: {result}")
            except Exception as e:
                print(f"❌ Ошибка при проверке таблицы orders: {e}")
                await conn.close()
                return
            
            # Проверяем, существуют ли новые поля
            try:
                await conn.fetchval("SELECT price_action_active FROM orders LIMIT 1")
                print("✅ Поля стратегий уже существуют")
                
                # Проверяем, есть ли записи с информацией о стратегиях
                strategy_records = await conn.fetchval("""
                    SELECT COUNT(*) FROM orders 
                    WHERE price_action_active IS NOT NULL 
                    OR cm_active IS NOT NULL 
                    OR moonbot_active IS NOT NULL
                """)
                print(f"📊 Записей с информацией о стратегиях: {strategy_records}")
                
            except Exception as e:
                print(f"❌ Поля стратегий отсутствуют: {e}")
                print("🔄 Выполняем миграцию...")
                
                # Выполняем миграцию
                await migrate_strategy_fields()
                print("✅ Миграция завершена")
            
            await conn.close()
            
        except Exception as e:
            print(f"❌ Ошибка подключения к базе данных: {e}")
            print("💡 Возможно, используется SQLite или база данных недоступна")
            return
        
        print("\n=== Рекомендации ===")
        print("1. Перезапустите бота для применения изменений")
        print("2. Новые сделки будут содержать информацию о стратегиях")
        print("3. Существующие сделки будут показывать '❌' для всех стратегий")
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        print("💡 Убедитесь, что вы находитесь в корневой директории проекта")
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(check_and_migrate()) 