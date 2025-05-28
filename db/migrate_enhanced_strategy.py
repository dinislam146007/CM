#!/usr/bin/env python3
"""
Миграция для добавления расширенных полей статистики стратегий
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connect import connect

async def migrate_enhanced_strategy_fields():
    """Добавляет расширенные поля для статистики стратегий в таблицу orders"""
    conn = await connect()
    try:
        print("🔄 Начинаем миграцию расширенных полей статистики...")
        
        # Группы полей для миграции
        field_groups = {
            "Детализация сигналов": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS signal_strength REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS signal_confidence REAL", 
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS strategy_combination TEXT"
            ],
            "Рыночные условия": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS market_condition TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS volatility_level TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS volume_profile TEXT"
            ],
            "Технические индикаторы": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS rsi_value REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS cm_ppo_value REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ema_fast REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ema_slow REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS atr_value REAL"
            ],
            "Статистика выполнения": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS time_to_tp_minutes INTEGER",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS time_to_sl_minutes INTEGER",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS max_profit_percent REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS max_drawdown_percent REAL"
            ],
            "Причина закрытия": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS close_reason TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS close_trigger TEXT"
            ],
            "Дополнительные метрики": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS risk_reward_ratio REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS position_size_percent REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS slippage_percent REAL"
            ],
            "Контекстная информация": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS btc_price_entry REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS btc_correlation REAL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS session_type TEXT"
            ],
            "Pump/Dump детекция": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS pump_dump_detected BOOLEAN",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS pump_dump_type TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS unusual_volume BOOLEAN"
            ],
            "Стратегии выхода": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS exit_strategy_used TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS trailing_stop_used BOOLEAN",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS partial_close_count INTEGER"
            ],
            "Метаданные": [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS trade_session_id TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS strategy_version TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS notes TEXT"
            ]
        }
        
        # Добавляем поля по группам
        total_added = 0
        for group_name, fields in field_groups.items():
            print(f"\n📊 Добавляем группу: {group_name}")
            for field_sql in fields:
                try:
                    await conn.execute(field_sql)
                    field_name = field_sql.split('ADD COLUMN IF NOT EXISTS')[1].split()[0]
                    print(f"  ✅ {field_name}")
                    total_added += 1
                except Exception as e:
                    field_name = field_sql.split('ADD COLUMN IF NOT EXISTS')[1].split()[0]
                    print(f"  ❌ {field_name}: {e}")
        
        # Создаем индексы для быстрого поиска
        print(f"\n🔍 Создаем индексы для оптимизации...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_orders_strategy_combination ON orders(strategy_combination)",
            "CREATE INDEX IF NOT EXISTS idx_orders_market_condition ON orders(market_condition)",
            "CREATE INDEX IF NOT EXISTS idx_orders_close_reason ON orders(close_reason)",
            "CREATE INDEX IF NOT EXISTS idx_orders_signal_strength ON orders(signal_strength)",
            "CREATE INDEX IF NOT EXISTS idx_orders_pnl_percent ON orders(pnl_percent)",
            "CREATE INDEX IF NOT EXISTS idx_orders_buy_time ON orders(buy_time)",
            "CREATE INDEX IF NOT EXISTS idx_orders_user_strategy ON orders(user_id, strategy_combination)"
        ]
        
        indexes_created = 0
        for index_sql in indexes:
            try:
                await conn.execute(index_sql)
                index_name = index_sql.split('IF NOT EXISTS')[1].split()[0]
                print(f"  ✅ {index_name}")
                indexes_created += 1
            except Exception as e:
                index_name = index_sql.split('IF NOT EXISTS')[1].split()[0]
                print(f"  ❌ {index_name}: {e}")
        
        print(f"\n✅ Миграция завершена!")
        print(f"📊 Добавлено полей: {total_added}")
        print(f"🔍 Создано индексов: {indexes_created}")
        
        # Проверяем результат
        print(f"\n🔍 Проверяем результат миграции...")
        try:
            # Проверяем несколько ключевых полей
            test_fields = ['signal_strength', 'strategy_combination', 'market_condition', 'close_reason']
            for field in test_fields:
                await conn.fetchval(f"SELECT {field} FROM orders LIMIT 1")
                print(f"  ✅ {field} - доступно")
        except Exception as e:
            print(f"  ❌ Ошибка проверки: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при миграции: {e}")
        return False
    finally:
        await conn.close()

async def main():
    """Основная функция для запуска миграции"""
    print("=== Миграция расширенных полей статистики стратегий ===\n")
    
    success = await migrate_enhanced_strategy_fields()
    
    if success:
        print("\n🎉 Миграция успешно завершена!")
        print("\n📋 Теперь доступны следующие возможности:")
        print("  • Детальная статистика по каждой стратегии")
        print("  • Анализ рыночных условий на момент входа")
        print("  • Отслеживание причин закрытия сделок")
        print("  • Метрики риск/прибыль")
        print("  • Корреляция с BTC")
        print("  • Детекция pump/dump")
        print("\n💡 Рекомендации:")
        print("  1. Обновите функции create_order() и close_order()")
        print("  2. Добавьте сбор новых метрик в торговую логику")
        print("  3. Создайте отчеты для анализа эффективности стратегий")
    else:
        print("\n❌ Миграция не удалась. Проверьте подключение к базе данных.")

if __name__ == "__main__":
    asyncio.run(main()) 