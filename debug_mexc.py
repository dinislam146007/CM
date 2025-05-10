#!/usr/bin/env python3
"""
Скрипт для отладки проблем с MEXC.
Запуск: python debug_mexc.py
"""

import asyncio
import json
import sys
import traceback
import pandas as pd
import numpy as np
import ccxt.async_support as ccxt
from pathlib import Path
from datetime import datetime

# MEXC интервалы для фьючерсов
MEXC_INTERVAL_MAP = {
    "1m": "Min1", "3m": "Min3", "5m": "Min5", "15m": "Min15", "30m": "Min30",
    "1h": "Min60", "4h": "Hour4", "8h": "Hour8", "1d": "Day1", "1w": "Week1", "1M": "Month1"
}

# MEXC интервалы для спота
MEXC_SPOT_INTERVALS = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w", "1M": "1M"
}

# Тест #1: Проверка создания экземпляра MEXC API
async def test_create_mexc_instances():
    print("\n[TEST 1] Создание экземпляров MEXC API")
    
    try:
        # Spot экземпляр
        mexc_spot = ccxt.mexc({"enableRateLimit": True})
        print(f"✅ MEXC Spot создан успешно: {mexc_spot.id}")
        await mexc_spot.close()
    except Exception as e:
        print(f"❌ Ошибка создания MEXC Spot: {e}")
        traceback.print_exc()
    
    try:
        # Futures экземпляр
        mexc_futures = ccxt.mexc3({"enableRateLimit": True})
        print(f"✅ MEXC Futures создан успешно: {mexc_futures.id}")
        await mexc_futures.close()
    except Exception as e:
        print(f"❌ Ошибка создания MEXC Futures: {e}")
        traceback.print_exc()

# Тест #2: Получение OHLCV данных
async def test_ohlcv_fetch():
    print("\n[TEST 2] Получение OHLCV данных")
    symbols = ["BTCUSDT", "ETHUSDT"]
    timeframes = ["1m", "5m", "1h"]
    
    # Spot тест
    mexc_spot = ccxt.mexc({"enableRateLimit": True})
    print("\n--- MEXC Spot ---")
    
    try:
        for symbol in symbols:
            for tf in timeframes:
                try:
                    if tf not in MEXC_SPOT_INTERVALS:
                        print(f"⚠️ Таймфрейм {tf} не поддерживается MEXC Spot API, пропускаем")
                        continue
                        
                    print(f"Получение {symbol} {tf}...")
                    ohlcv = await mexc_spot.fetch_ohlcv(symbol, tf, limit=10)
                    if ohlcv and len(ohlcv) > 0:
                        print(f"✅ Успешно: {symbol} {tf} - получено {len(ohlcv)} свечей")
                        # Преобразуем время в человекочитаемый формат
                        first_candle_time = datetime.fromtimestamp(ohlcv[0][0]/1000).strftime('%Y-%m-%d %H:%M:%S')
                        print(f"   Первая свеча: {first_candle_time}")
                    else:
                        print(f"❌ Нет данных для {symbol} {tf}")
                except Exception as e:
                    print(f"❌ Ошибка при получении {symbol} {tf}: {e}")
    except Exception as e:
        print(f"❌ Общая ошибка MEXC Spot: {e}")
    finally:
        await mexc_spot.close()
    
    # Futures тест
    mexc_futures = ccxt.mexc3({"enableRateLimit": True})
    print("\n--- MEXC Futures ---")
    
    try:
        for symbol in symbols:
            for tf in timeframes:
                try:
                    if tf not in MEXC_INTERVAL_MAP:
                        print(f"⚠️ Таймфрейм {tf} не поддерживается MEXC Futures API, пропускаем")
                        continue
                        
                    print(f"Получение {symbol} {tf}...")
                    ohlcv = await mexc_futures.fetch_ohlcv(symbol, tf, limit=10)
                    if ohlcv and len(ohlcv) > 0:
                        print(f"✅ Успешно: {symbol} {tf} - получено {len(ohlcv)} свечей")
                        # Преобразуем время в человекочитаемый формат
                        first_candle_time = datetime.fromtimestamp(ohlcv[0][0]/1000).strftime('%Y-%m-%d %H:%M:%S')
                        print(f"   Первая свеча: {first_candle_time}")
                    else:
                        print(f"❌ Нет данных для {symbol} {tf}")
                except Exception as e:
                    print(f"❌ Ошибка при получении {symbol} {tf}: {e}")
    except Exception as e:
        print(f"❌ Общая ошибка MEXC Futures: {e}")
    finally:
        await mexc_futures.close()

# Тест #3: Проверка рыночных данных
async def test_market_data():
    print("\n[TEST 3] Проверка рыночных данных")
    
    exchanges = [
        ("MEXC Spot", ccxt.mexc({"enableRateLimit": True})),
        ("MEXC Futures", ccxt.mexc3({"enableRateLimit": True})),
        ("Binance", ccxt.binance({"enableRateLimit": True}))  # Для сравнения
    ]
    
    symbol = "BTCUSDT"
    
    for name, exchange in exchanges:
        try:
            print(f"\n--- {name} ---")
            
            # Проверка получения тикера
            print(f"Получение тикера для {symbol}...")
            ticker = await exchange.fetch_ticker(symbol)
            print(f"✅ Тикер: Цена = {ticker['last']}, Объем 24ч = {ticker['quoteVolume']}")
            
            # Проверка получения книги ордеров
            print(f"Получение книги ордеров для {symbol}...")
            orderbook = await exchange.fetch_order_book(symbol)
            print(f"✅ Книга ордеров: {len(orderbook['bids'])} ставок на покупку, {len(orderbook['asks'])} ставок на продажу")
            
            # Проверка получения списка доступных символов
            print("Получение списка символов...")
            markets = await exchange.load_markets()
            total_markets = len(markets)
            print(f"✅ Доступно {total_markets} торговых пар")
            
            usdt_pairs = [m for m in markets.keys() if 'USDT' in m]
            print(f"  USDT пары: {len(usdt_pairs)} ({usdt_pairs[:5]}...)")
            
        except Exception as e:
            print(f"❌ Ошибка при работе с {name}: {e}")
        finally:
            await exchange.close()

# Главная функция
async def main():
    print("===== MEXC DEBUG SCRIPT =====")
    print(f"Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"CCXT версия: {ccxt.__version__}")
    
    try:
        # Тест #1: Создание экземпляров API
        await test_create_mexc_instances()
        
        # Тест #2: Получение OHLCV данных
        await test_ohlcv_fetch()
        
        # Тест #3: Проверка рыночных данных
        await test_market_data()
        
        print("\n===== ТЕСТЫ ЗАВЕРШЕНЫ =====")
        
    except Exception as e:
        print(f"⛔ Критическая ошибка: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 