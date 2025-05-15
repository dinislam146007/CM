import asyncio
import queue
import threading
import time
import aiohttp
from pybit.unified_trading import WebSocket
from config import config
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from strategy_logic.get_all_coins import get_usdt_pairs  # Добавляем импорт функции

# Инициализация бота
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
    def __init__(self, symbol, price_change, timeframe):
        self.symbol = symbol
        self.price_change = price_change
        self.timeframe = timeframe

class BybitPumpDumpScreener:
    def __init__(self, max_history_len=60):
        """
        :param max_history_len: Максимальная длина данных в минутах
        """
        self._max_history_len = max_history_len
        
        # Игнорируемые символы
        self._ignored_symbols = ["BTCUSDT3L", "BTCUSDT3S"]
        
        self._ws = None
        
        # Таймфреймы для поиска памп/дамп сигналов
        self.TIMEFRAMES = [5, 10, 15, 30]
        
        # ID канала для отправки сигналов
        self.CHANNEL_ID = config.public_channel_id
        
        # Минимальные проценты изменения для сигнала
        self.PUMP_SIZE = 3.0  # % роста для сигнала
        self.DUMP_SIZE = 3.0  # % падения для сигнала
        
        # Таймаут между сигналами одной монеты в минутах
        self.TIMEOUT_MINUTES = 60
        
        # Направления торговли
        self.LONG_DIRECTION = True
        self.SHORT_DIRECTION = True

        # Главный словарь с данными
        self._data = {}
        
        # Словарь с задержками для каждой монеты
        self._delays = {}

        # Словарь с объемами за последние 24 часа
        self._volume_per_minute = {}

        # Реализация очереди для обработки сигналов
        self._queue = queue.Queue()

        # Таймштампы сообщений которые приходят с вебсокета
        self._runtime_data = {}

        self._loop = asyncio.get_event_loop()

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
        Функция обрабатывает сообщения с вебсокета.
        """
        try:
            # Проверяем, есть ли данные для этого символа
            if symbol not in self._data:
                return
                
            candles = self._data[symbol]
            
            # Проверка на достаточное количество свечей
            if len(candles) < max(self.TIMEFRAMES):
                return
                
            # Собираем словарь из данных
            changes = self._get_changes(candles)

            # Генерируем сигналы
            signals = self._generate_signals(symbol, changes)

            # Отправляем сигналы
            if signals:
                asyncio.run_coroutine_threadsafe(self._send_signals(signals), self._loop)
        except Exception as e:
            print(f"Error processing symbol {symbol}: {e}")

    async def _send_signals(self, signals: list[Signal]) -> None:
        """
        Функция готовит сообщение и отправляет его.
        """
        for signal in signals:
            try:
                if signal.price_change > 0:
                    signal_title = "🟢🔥 #Pump рост"
                else:
                    signal_title = "🔴🔥 #Dump падение"

                bybit_link = f"<a href='https://www.bybit.com/trade/usdt/{signal.symbol}'>Futures</a>"
                tw_link = f"<a href='https://www.tradingview.com/chart/?symbol=BYBIT:{signal.symbol}.P'>TradingView</a>"

                signal_text = (f"#{signal.symbol} (#{signal.timeframe}min) #Bybit #Futures\n"
                                f"{signal_title} {round(signal.price_change, 2)}%\n\n"
                                f"{bybit_link} {tw_link}")

                # Отправляем сообщение в публичный канал
                await bot.send_message(
                    chat_id=self.CHANNEL_ID,
                    text=signal_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                print(f"Signal sent: {signal.symbol} {signal.price_change}% to channel {self.CHANNEL_ID}")

            except Exception as e:
                print(f"Error sending signal: {e}")

    def _generate_signals(self, symbol: str, changes_dict: dict[int, Changes]) -> list[Signal]:
        """
        Функция проверяет изменения цены для определения сигналов.
        """
        signals = []
        
        # Проверка на таймаут последнего сигнала для этого символа
        symbol_signals_time = self._get_symbol_signals_time(symbol)
        if symbol_signals_time and symbol_signals_time[-1] + self.TIMEOUT_MINUTES * 60 > time.time():
            return signals
            
        # Перебираем все таймфреймы
        for minutes in self.TIMEFRAMES:
            try:
                # Проверка на процент изменения (Рост)
                if self.LONG_DIRECTION:
                    growth_changes = changes_dict[minutes]
                    growth_percent = growth_changes.growth
                    if growth_percent > self.PUMP_SIZE:
                        self._delays[symbol].append(time.time())
                        signals.append(
                            Signal(
                                symbol=symbol,
                                price_change=growth_percent,
                                timeframe=minutes
                            )
                        )
                        
                # Проверка на процент изменения (Падение)
                if self.SHORT_DIRECTION:
                    decay_changes = changes_dict[minutes]
                    decay_percent = decay_changes.decay
                    if decay_percent < -self.DUMP_SIZE:
                        self._delays[symbol].append(time.time())
                        signals.append(
                            Signal(
                                symbol=symbol,
                                price_change=decay_percent,
                                timeframe=minutes
                            )
                        )
            except KeyError:
                continue

        return signals

    def _get_symbol_signals_time(self, symbol: str) -> list[int]:
        """
        Возвращает время последних сигналов по монете.
        """
        current_time = time.time()
        threshold_time = current_time - (60 * 60 * 24)  # Время, старше которого данные не нужны

        # Если символа нет в словаре с задержками
        if symbol not in self._delays:
            self._delays[symbol] = []
        else:
            # Очищаем ненужную историю
            self._delays[symbol] = [t for t in self._delays[symbol] if t > threshold_time]

        return self._delays[symbol]

    def _get_changes(self, data: list[Candle]) -> dict[int, Changes]:
        """
        Считает изменения для каждого тикера за каждый таймфрейм.
        """
        changes = {}

        for minutes in self.TIMEFRAMES:
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
        # Для тестовой сети используем функцию get_usdt_pairs
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
            
        # Для основной сети используем API
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
                    return tickers[:10]  # Ограничиваем количество тикеров для тестирования
        except Exception as e:
            print(f"Ошибка при получении тикеров: {e}")
            return get_usdt_pairs()[:20]  # Используем get_usdt_pairs с ограничением

async def main():
    try:
        screener = BybitPumpDumpScreener()
        
        await screener.start_service()
        
        print("Скринер запущен и отслеживает изменения цен...")
        print("Нажмите Ctrl+C для остановки")
        
        # Держим программу запущенной
        while True:
            await asyncio.sleep(60)
            
    except KeyboardInterrupt:
        print("\nПрограмма остановлена пользователем")
    except Exception as e:
        print(f"Ошибка при запуске: {e}")
    finally:
        print("Программа завершена")

if __name__ == "__main__":
    asyncio.run(main())
