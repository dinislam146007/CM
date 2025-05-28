import asyncio
import queue
import threading
import time
import aiohttp
from pybit.unified_trading import WebSocket
from config import config
from aiogram import Bot, types
from strategy_logic.get_all_coins import get_usdt_pairs
from strategy_logic.pump_dump_settings import load_pump_dump_settings, load_subscribers
from aiogram.client.default import DefaultBotProperties
import logging
import numpy as np
import pandas as pd
import ccxt
from user_settings import is_subscribed

# Инициализируем бота
bot = Bot(token=config.tg_bot_token, default=DefaultBotProperties(parse_mode="HTML"))

# Определение классов данных для работы скринера
class Candle:
    def __init__(self, timestamp, close, high, low, open, volume):
        self.timestamp = timestamp
        self.close = close
        self.high = high
        self.low = low
        self.open = open
        self.volume = volume

class Changes:
    def __init__(self, growth, decay):
        self.growth = growth
        self.decay = decay

class Signal:
    def __init__(self, symbol, price_change, timeframe, user_id: int, preview: bool = False):
        self.symbol = symbol
        self.price_change = price_change
        self.timeframe = timeframe
        self.user_id = user_id
        self.preview = preview

class BybitPumpDumpScreener:
    def __init__(self, max_history_len=60):
        """
        :param max_history_len: Максимальная длина данных в минутах
        """
        self._max_history_len = max_history_len
        
        # Игнорируемые символы
        self._ignored_symbols = ["BTCUSDT3L", "BTCUSDT3S"]
        
        self._ws = None
        
        # ID канала для отправки сигналов (может использоваться для общих уведомлений, если потребуется)
        self.PUBLIC_CHANNEL_ID = config.public_channel_id
        
        # Главный словарь с данными
        self._data = {}
        
        # Словарь с задержками для каждой монеты каждого пользователя
        self._user_delays: dict[int, dict[str, list[float]]] = {}

        # Словарь с объемами за последние 24 часа
        self._volume_per_minute = {}

        # Реализация очереди для обработки сигналов
        self._queue = queue.Queue()

        # Таймштампы сообщений которые приходят с вебсокета
        self._runtime_data = {}

        self._loop = asyncio.get_event_loop()
        
        # Загружаем глобальные/дефолтные настройки, которые не зависят от пользователя
        # Например, все таймфреймы, для которых нужно считать изменения
        default_settings = load_pump_dump_settings(0)
        self.GLOBAL_TIMEFRAMES = []
        if "MONITOR_INTERVALS" in default_settings:
            for tf_str in default_settings["MONITOR_INTERVALS"]:
                if tf_str.endswith('m'):
                    self.GLOBAL_TIMEFRAMES.append(int(tf_str[:-1]))
                elif tf_str.endswith('h'):
                    self.GLOBAL_TIMEFRAMES.append(int(tf_str[:-1]) * 60)
        
        self.GLOBAL_VOLUME_THRESHOLD = default_settings.get("VOLUME_THRESHOLD", 0) # Default to 0 if not set

    def handle_ws_msg(self, msg: dict) -> None:
        """
        Функция получает и обрабатывает сообщение с вебсокета.
        """
        def _add_candle(s: str, c: Candle) -> None:
            try:
                self._data[s].append(c)
                self._data[s] = self._data[s][-self._max_history_len:]  # Убираем лишние данные
            except KeyError:
                self._data[s] = [c]

        def _update_candle(s: str, c: Candle) -> None:
            try:
                self._data[s][-1] = c
            except KeyError:
                self._data[s] = [c]

        try:
            if msg["topic"].startswith("tickers"):
                data = msg["data"]
                self._volume_per_minute[data["symbol"]] = float(data["volume24h"]) / 1440
            else:  # kline
                data = msg["data"][0]
                symbol = msg["topic"].split(".")[-1]

                candle = Candle(
                    timestamp=data["start"],
                    close=float(data["close"]),
                    high=float(data["high"]),
                    low=float(data["low"]),
                    open=float(data["open"]),
                    volume=float(data["volume"]))

                # Добавляем предыдушую свечу в словарь, если ее там еще нет
                try:
                    prev_candle = self._runtime_data[symbol]
                except KeyError:
                    self._runtime_data[symbol] = candle
                    return

                if candle.timestamp > prev_candle.timestamp:  # Проверяем закрылась ли предыдущая свеча.
                    self._runtime_data[symbol] = candle  # Обновляем предыдущую свечу
                    _add_candle(symbol, candle)
                else:
                    _update_candle(symbol, candle)
                self._queue.put(symbol)

        except Exception as e:
            print(f"Error in handle_ws_msg: {e}")

    def init_websocket(self) -> None:
        """
        Инициализирует вебсокет клиент.
        """
        # Используем testnet для тестирования
        self._ws = WebSocket(
            channel_type="linear", 
            testnet=True,  # Тестовая сеть для избежания лимитов
            ping_interval=20,
            ping_timeout=10,
            trace_logging=False,  # Отключаем трассировочное логирование
            restart_on_error=True
        )

    def start_streams(self, symbols: list[str]) -> None:
        """
        Запускает вебсокет стримы.
        """
        # Ограничиваем количество символов для тестирования
        test_symbols = symbols[:5] if len(symbols) > 5 else symbols
        print(f"Подписываемся на {len(test_symbols)} символов: {test_symbols}")
        
        try:
            self._ws.kline_stream(interval=1, symbol=test_symbols, callback=self.handle_ws_msg)
        except Exception as e:
            print(f"Ошибка при подписке на стримы: {e}")

    async def start_service(self) -> None:
        """Запуск сервиса по поиску объемов."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"Попытка подключения {attempt+1}/{max_retries}")
                # Инициализируем вебсокет
                self.init_websocket()
                
                # Получаем список тикеров и запускаем нужные стримы с ними
                symbols = await self._get_tickers()
                self.start_streams(symbols)
                
                # Запуск обработчиков для закрытых свечей
                for i in range(2):  # Уменьшаем количество потоков для тестирования
                    threading.Thread(target=self._worker, daemon=True).start()
                
                print("Подключение успешно установлено")
                break
                
            except Exception as e:
                print(f"Ошибка подключения: {e}")
                if attempt < max_retries - 1:
                    wait_time = 30 * (attempt + 1)
                    print(f"Повторная попытка через {wait_time} секунд")
                    await asyncio.sleep(wait_time)
                else:
                    print("Достигнуто максимальное количество попыток")
                    raise

    def _worker(self):
        while True:
            try:
                symbol = self._queue.get(timeout=1)
                self._process_symbol(symbol)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in worker: {e}")
                self._queue.task_done()

    def _process_symbol(self, symbol: str) -> None:
        """
        Обрабатывает данные для одного символа.
        """
        # Проверка на ENABLED теперь делается для каждого пользователя в _generate_signals
            
        try:
            # Проверяем объем
            if symbol in self._volume_per_minute:
                volume = self._volume_per_minute[symbol]
                # Пропускаем монеты с малым объемом (используем глобальный порог)
                if volume < self.GLOBAL_VOLUME_THRESHOLD:
                    return
                    
            if symbol in self._ignored_symbols:
                return
                
            if symbol not in self._data:
                return
                
            data = self._data[symbol]
            if len(data) < 5:  # Минимум 5 минут данных требуется
                return
                
            # Получаем изменения по всем таймфреймам
            changes_dict = self._get_changes(data)
            
            # Генерируем сигналы, если есть изменения
            signals = self._generate_signals(symbol, changes_dict)
            
            # Отправляем сигналы, если они есть
            if signals:
                asyncio.run_coroutine_threadsafe(self._send_signals(signals), self._loop)
        except Exception as e:
            print(f"Ошибка в обработке символа {symbol}: {e}")

    async def _send_signals(self, signals: list[Signal]) -> None:
        """
        Функция отправляет уведомления в Telegram пользователям.
        """
        if not signals:
            return
            
        try:
            for signal_obj in signals: # Переименовано во избежание конфликта имен
                # Настройки пользователя (включая ENABLED) проверяются в _generate_signals
                
                signal_type = "🟢 PUMP" if signal_obj.price_change > 0 else "🔴 DUMP"
                price_change_abs = abs(signal_obj.price_change) # Используем abs для отображения
                
                message_text = (
                    f"{signal_type} {signal_obj.symbol}\\n\\n"
                    f"💰 Изменение цены: {price_change_abs:.2f}%\\n"
                    f"⏱ Таймфрейм: {signal_obj.timeframe} минут\\n\\n"
                    f"📊 Биржа: Bybit"
                )
                
                # Отправляем сообщение конкретному пользователю
                try:
                    if signal_obj.preview:
                        # Логика для генерации и отправки графика (если включено)
                        # chart_data = self._data.get(signal_obj.symbol, [])
                        # relevant_klines = chart_data[-signal_obj.timeframe:] # Пример
                        # if relevant_klines and 'generate_chart_bytes' in globals():
                        #     klines_for_chart = [[c.timestamp, c.open, c.high, c.low, c.close, c.volume] for c in relevant_klines]
                        #     chart_bytes = generate_chart_bytes(klines_for_chart)
                        #     chart_bytes.seek(0)
                        #     await bot.send_photo(
                        #         chat_id=signal_obj.user_id,
                        #         caption=message_text,
                        #         photo=types.BufferedInputFile(chart_bytes.read(), f"Chart_{signal_obj.symbol}.png"),
                        #         parse_mode="HTML" # Убедитесь, что parse_mode поддерживается и настроен в bot
                        #     )
                        # else:
                        #     # Отправка текстового сообщения, если график не может быть сгенерирован
                        message_text_with_preview_note = message_text + "\\n\\n🖼️ (Предпросмотр графика включен, но функция генерации не реализована)"
                        await bot.send_message(chat_id=signal_obj.user_id, text=message_text_with_preview_note)
                    else:
                        await bot.send_message(chat_id=signal_obj.user_id, text=message_text)
                except Exception as e:
                    print(f"Ошибка при отправке пользователю {signal_obj.user_id}: {e}")
                    # Здесь можно добавить логику обработки блокировки бота пользователем,
                    # если у вас есть доступ к базе данных для обновления статуса пользователя,
                    # аналогично for_test.py.

        except Exception as e:
            print(f"Ошибка при отправке сигналов: {e}")

    def _generate_signals(self, symbol: str, changes_dict: dict[int, Changes]) -> list[Signal]:
        """
        Функция проверяет изменения цены для определения сигналов для каждого пользователя.
        """
        signals = []
        subscribers = load_subscribers() # Загружаем ID всех подписчиков

        for user_id in subscribers:
            user_settings = load_pump_dump_settings(user_id) # Загружаем настройки для конкретного пользователя

            if not user_settings.get("ENABLED", False): # Проверяем, включен ли детектор для этого пользователя
                continue

            # Пользовательские настройки
            user_monitor_intervals_str = user_settings.get("MONITOR_INTERVALS", [])
            user_timeframes_minutes = []
            for tf_str in user_monitor_intervals_str:
                if tf_str.endswith('m'):
                    user_timeframes_minutes.append(int(tf_str[:-1]))
                elif tf_str.endswith('h'):
                    user_timeframes_minutes.append(int(tf_str[:-1]) * 60)
            
            user_pump_size = user_settings.get("PRICE_CHANGE_THRESHOLD", 3.0)  # % роста для сигнала
            user_dump_size = user_settings.get("PRICE_CHANGE_THRESHOLD", 3.0)  # % падения для сигнала
            user_timeout_minutes = user_settings.get("TIME_WINDOW", 15) # Таймаут между сигналами
            user_long_direction = user_settings.get("LONG_DIRECTION", True)
            user_short_direction = user_settings.get("SHORT_DIRECTION", True)
            user_chart_preview = user_settings.get("CHART_PREVIEW", False) # Настройка для превью графика

            # Проверка на таймаут последнего сигнала для этого пользователя и символа
            user_symbol_signals_time = self._get_user_day_signals_time(user_id, symbol)
            if user_symbol_signals_time and \
               user_symbol_signals_time[-1] + user_timeout_minutes * 60 > time.time():
                continue
            
            for minutes in user_timeframes_minutes:
                if minutes not in changes_dict: # Если для этого ТФ нет рассчитанных изменений
                    continue
                
                change_data = changes_dict[minutes]
                
                # Проверка на процент изменения (Рост)
                if user_long_direction and change_data.growth > user_pump_size:
                    if user_id not in self._user_delays: self._user_delays[user_id] = {}
                    if symbol not in self._user_delays[user_id]: self._user_delays[user_id][symbol] = []
                    self._user_delays[user_id][symbol].append(time.time())
                    signals.append(
                        Signal(
                            symbol=symbol,
                            price_change=change_data.growth,
                            timeframe=minutes,
                            user_id=user_id,
                            preview=user_chart_preview
                        )
                    )
                        
                # Проверка на процент изменения (Падение)
                if user_short_direction and change_data.decay < -user_dump_size: # Падение - отрицательное значение
                    if user_id not in self._user_delays: self._user_delays[user_id] = {}
                    if symbol not in self._user_delays[user_id]: self._user_delays[user_id][symbol] = []
                    self._user_delays[user_id][symbol].append(time.time())
                    signals.append(
                        Signal(
                            symbol=symbol,
                            price_change=change_data.decay,
                            timeframe=minutes,
                            user_id=user_id,
                            preview=user_chart_preview
                        )
                    )
        return signals

    def _get_user_day_signals_time(self, user_id: int, symbol: str) -> list[float]:
        """
        Возвращает время последних сигналов по монете для конкретного пользователя.
        Очищает историю старше 24 часов.
        """
        current_time = time.time()
        threshold_time = current_time - (60 * 60 * 24)  # Время, старше которого данные не нужны

        if user_id not in self._user_delays:
            self._user_delays[user_id] = {}
        
        if symbol not in self._user_delays[user_id]:
            self._user_delays[user_id][symbol] = []
        else:
            # Очищаем ненужную историю
            self._user_delays[user_id][symbol] = [
                t for t in self._user_delays[user_id][symbol] if t > threshold_time
            ]
        return self._user_delays[user_id][symbol]

    def _get_changes(self, data: list[Candle]) -> dict[int, Changes]:
        """
        Считает изменения для каждого тикера за каждый таймфрейм из GLOBAL_TIMEFRAMES.
        """
        changes = {}

        for minutes in self.GLOBAL_TIMEFRAMES: # Используем GLOBAL_TIMEFRAMES
            if len(data) < minutes:
                continue
                
            relevant_data = data[-minutes:]

            # Определение изменения цены
            close_price = data[-1].close
            lowest_price = min([candle.low for candle in relevant_data])
            highest_price = max([candle.high for candle in relevant_data])

            growth_change = ((close_price - lowest_price) / lowest_price) * 100 if lowest_price else 0
            decay_change = ((close_price - highest_price) / highest_price) * 100 if highest_price else 0

            changes[minutes] = Changes(
                growth=round(growth_change, 2),
                decay=round(decay_change, 2),
            )

        return changes

    async def _get_tickers(self, category="linear") -> list[str]:
        """
        Получает и возвращает список тикеров с Bybit.
        """
        if self._ws and getattr(self._ws, 'testnet', False):
            print("Получаем список торговых пар через get_usdt_pairs для testnet")
            try:
                pairs = get_usdt_pairs()
                # Для тестовой сети ограничиваем количество пар до 5-10
                test_pairs = pairs[:10] if len(pairs) > 10 else pairs
                print(f"Получено {len(test_pairs)} пар: {test_pairs}")
                return test_pairs
            except Exception as e:
                print(f"Ошибка при получении списка пар: {e}")
                return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
            
        url = 'https://api.bybit.com/v5/market/tickers'
        params = {'category': category}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status != 200:
                        print(f"Ошибка API: статус {response.status}")
                        return get_usdt_pairs()[:20]  # Используем get_usdt_pairs с ограничением
                        
                    result = await response.json()
                    if 'result' not in result or 'list' not in result['result']:
                        print(f"Неверный формат ответа: {result}")
                        return get_usdt_pairs()[:20]  # Используем get_usdt_pairs с ограничением
                        
                    tickers = [s["symbol"] for s in result["result"]["list"] 
                              if s["symbol"] not in self._ignored_symbols and
                              s["symbol"].endswith("USDT")]
                    return tickers  # Ограничиваем количество тикеров для тестирования
        except Exception as e:
            print(f"Ошибка при получении тикеров: {e}")
            return get_usdt_pairs()  # Используем get_usdt_pairs с ограничением

async def pump_dump_main():
    try:
        screener = BybitPumpDumpScreener()
        
        await screener.start_service()
                
        while True:
            # Периодически перезагружаем настройки - теперь не нужно,
            # так как настройки пользователя загружаются в _generate_signals,
            # а список подписчиков - там же.
            # screener._load_settings() # Этот метод удален
            await asyncio.sleep(60) # Оставляем sleep для основного цикла
            
    except KeyboardInterrupt:
        print("\nПрограмма остановлена пользователем")
    except Exception as e:
        print(f"Ошибка при запуске: {e}")
    finally:
        print("Программа завершена")

