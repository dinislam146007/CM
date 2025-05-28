import asyncio
import queue
import threading
import time

import aiohttp
from aiogram import Bot, types
from pybit.unified_trading import WebSocket

from src.configuration import config, logger
from src.db import Database, PumpDumpSettings
from src.screeners.schemas import TickerInfo
from src.screeners.tasks import ExchangesInfo
from .schemas import Candle, Changes, Signal
from ...utils import generate_chart_bytes


class BybitPumpDumpScreener:

    def __init__(self,
                 bot: Bot,
                 database: Database,
                 exchanges_info: ExchangesInfo,
                 max_history_len: int = config.PD_MAX_HISTORY_LEN,
                 ) -> None:
        """

        :param bot: Обьект телеграм бота.
        :param database: Обьект для работы с базой данных.
        :param max_history_len: Максимальная длинная данных в минутах, которые бот должен помнить.
        """
        self._bot = bot
        self._database = database
        self._max_history_len = max_history_len
        self._ignored_symbols = config.BYBIT_IGNORED_SYMBOLS

        self._ws: WebSocket | None = None

        '''Тут хранится информация из базы данных по настройкам юзеров.'''
        self._active_users_id: list[int] = []
        self._settings: list[PumpDumpSettings] = []

        '''Главный словарь с данными. Имеет формат:
        {ticker: [[time, volume], [time, volume], [time, volume] ...]}
        Данные по oi хранятся только за последние 60 минут.'''
        self._data: dict[str, list[Candle]] = {}  # Главный словарь со всеми собранными данными.

        '''Словарь с задержками для каждого юзера'''
        self._user_delays: dict[int, dict[str, list]] = {}

        '''Словарь с обьемами за последние 24 часа'''
        self._volume_per_minute: dict[str, float] = {}

        '''Реализация очереди, потому что сервер не успевает быстро обрабатывать сообщения с вебсокета, из-за
        чего возникает ошибка: Queue overflow. Message not filled'''
        self._queue = queue.Queue()

        '''Таймштампы сообщений которые приходят с вебсокета. Байбит не информирует о том, что свеча закрылась
        в сообщении, поэтому приходится хранить свечи в словаре, и когда свеча приходит с новым таймштампом - 
        мы добавим ее в словарь с данными'''
        self._runtime_data: dict[str, Candle] = {}

        self._loop = asyncio.get_event_loop()

        self._exchanges_info = exchanges_info

    def handle_ws_msg(self, msg: dict) -> None:
        """
        Функция получает и обрабатывает сообщение с вебсокета.
        :param msg:
        :return:
        """

        # e = {'topic': 'kline.1.10000LADYSUSDT', 'data': [
        #     {'start': 1708538580000, 'end': 1708538639999, 'interval': '1', 'open': '0.0006523', 'close': '0.0006523',
        #      'high': '0.0006523', 'low': '0.0006523', 'volume': '0', 'turnover': '0', 'confirm': False,
        #      'timestamp': 1708538584618}], 'ts': 1708538584618, 'type': 'snapshot'}
        def _add_candle(s: str, c: Candle) -> None:
            try:
                self._data[s].append(c)
                self._data[s] = self._data[symbol][-self._max_history_len:]  # Убираем лишние данные
            except KeyError:
                self._data[s] = [c]

        def _update_candle(s: str, c: Candle) -> None:
            try:
                self._data[s][-1] = c
            except KeyError:
                self._data[s] = [candle]

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
                    prev_candle: Candle = self._runtime_data[symbol]
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
            logger.exception(e)

    def init_websocket(self) -> None:
        """
        Инициализирует вебсокет клиент.
        :return:
        """
        self._ws = WebSocket(channel_type="linear", testnet=False)

    def start_streams(self, symbols: list[str]) -> None:
        """
        Запускает вебсокет стримы.
        :param symbols:
        :return:
        """
        self._ws.kline_stream(interval=1, symbol=symbols, callback=self.handle_ws_msg)

    async def start_service(self) -> None:
        """Запуск сервиса по поиску обьемов."""
        logger.success("Start binance pd screener")

        # Инициалдизируем вебсокет клиент
        self.init_websocket()

        # Получаем список тикеров и запускаем нужные стримы с ними
        symbols: list[str] = await self._get_tickers()
        self.start_streams(symbols)

        # Запускаем сбор информации из базы данных в потоке
        asyncio.create_task(self._update_settings_cycle())

        # Запуск воркеров для обработки закрытых свечей
        for i in range(4):
            threading.Thread(target=self._worker).start()

    def _worker(self):
        while True:
            try:
                symbol = self._queue.get(timeout=1)
                self._process_symbol(symbol)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.exception(e)
                self._queue.task_done()

    def _process_symbol(self, symbol: str) -> None:
        """
        Функция обрабатывает сообщения с вебсокета, которые берет из очереди.
        :return:
        """
        # Единожды получаем данные для формирования сигнала
        candles: list[Candle] = self._data[symbol]

        # Собираем словарь из данных
        changes: dict[int, Changes] = self._get_changes(candles)

        # Генерируем сигналы
        signals: list[Signal] = self._generate_signals(symbol, changes)

        # Отправляем сигналы
        asyncio.run_coroutine_threadsafe(self._send_signals(signals, candles), self._loop)

    async def _send_signals(self, signals: list[Signal], candles: list[Candle]) -> None:
        """
        Функция готовит сообщение и отправляет его.
        :param signals:
        :return:
        """
        for signal in signals:
            logger.info(f"Detected bybit signal for {signal.user_id}: {signal}")
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

                if not signal.preview:
                    await self._bot.send_message(
                        chat_id=signal.user_id,
                        text=signal_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                else:
                    klines = [[c.timestamp, c.open, c.high, c.low, c.close, c.volume] for c in candles]
                    chart = generate_chart_bytes(klines)
                    chart.seek(0)
                    await self._bot.send_photo(
                        chat_id=signal.user_id,
                        caption=signal_text,
                        parse_mode="HTML",
                        photo=types.BufferedInputFile(chart.read(), f"Chart")
                    )

            except Exception as e:
                logger.error(f"Error while send message for {signal.user_id}: {e}")
                if "bot was blocked" in str(e):
                    try:
                        await self._database.user_repo.update(signal.user_id, {"status": False})
                        logger.debug(f"Turn off bot for user {signal.user_id}")
                    except Exception as e:
                        logger.error(f"Cant turn off bot for user {signal.user_id}: {e}")

    def _make_humanreadable_volume(self, volume: float) -> str:
        """
        Функция превращает большое числа в человеческий вид.
        :param volume:
        :return:
        """
        suffixes = {
            1_000: "тыс.",
            1_000_000: "млн.",
            1_000_000_000: "млрд.",
            1_000_000_000_000: "трлн.",
            1_000_000_000_000_000: "квдрлн.",
            1_000_000_000_000_000_000: "квнтлн."
            # Добавлять сюда дополнительные суффиксы по мере необходимости
        }
        for divisor in sorted(suffixes.keys(), reverse=True):
            if volume >= divisor:
                return f"{volume / divisor:.2f} {suffixes[divisor]}"
        return str(volume)

    def _generate_signals(self, symbol: str, changes_dict: dict[int, Changes]) -> list[Signal]:
        """
        Функция собирает данные из базы данных, и сравнивает значения для определения, нужно ли
        высылать пользователю сигнал.
        :return:
        """
        signals = []

        symbol_info: TickerInfo = self._exchanges_info.get_ticker_info(
            exchange="bybit", market_type="futures", symbol=symbol)

        for user_settings in self._settings:
            # Проверка на состояние настроек юзера
            if not user_settings.status:
                continue

            if not user_settings.is_bybit:
                continue

            # Проверка на подписку пользователя
            user_id = user_settings.user_id
            if user_id not in self._active_users_id:
                continue

            if user_settings.funding_restrict and symbol_info.is_high_fr:
                continue

            if user_settings.futures_ignore_new_symbols and symbol_info.is_new_ticker:
                continue

            # Проверка на таймаут последнего сигнала
            user_signals_time: list[int] = self._get_user_day_signals_time(user_id, symbol)
            if user_signals_time and \
                    user_signals_time[-1] + config.PD_TIMEOUT_MINUTES * 60 > time.time():
                continue

            # Проверка на процент изменения (Рост)
            try:
                growth_changes: Changes = changes_dict[user_settings.pump_interval]
                growth_percent: float = growth_changes.growth
                if growth_percent > user_settings.pump_size and user_settings.long_direction:
                    self._user_delays[user_id][symbol].append(time.time())
                    signals.append(
                        Signal(
                            user_id=user_id,
                            symbol=symbol,
                            price_change=growth_percent,
                            timeframe=user_settings.pump_interval,
                            preview=user_settings.chart_preview
                        )
                    )
            except KeyError:
                pass

            # Проверка на процент изменения (Падение)
            try:
                decay_changes: Changes = changes_dict[user_settings.dump_interval]
                decay_percent: float = decay_changes.decay
                if decay_percent < -user_settings.dump_size and user_settings.short_direction:
                    self._user_delays[user_id][symbol].append(time.time())
                    signals.append(
                        Signal(
                            user_id=user_id,
                            symbol=symbol,
                            price_change=decay_percent,
                            timeframe=user_settings.dump_interval,
                            preview=user_settings.chart_preview
                        )
                    )
            except KeyError:
                pass

        return signals

    def _get_user_day_signals_time(self, user_id: int, symbol: str) -> list[int]:
        """
        Функция возвращает количество сигналов отосланных пользователю по конкретной монете за последние
        сутки.
        :param user_id:
        :param symbol:
        :return:
        """
        current_time = time.time()  # Текущее время в миллисекундах
        threshold_time = current_time - (60 * 60 * 24)  # Время, старше которого данные не нужны

        # Если пользователя нет в словаре с задержками
        if user_id not in self._user_delays:
            self._user_delays[user_id] = {}
            self._user_delays[user_id][symbol] = []

        else:
            # Если тикера нет в словаре с тикерами
            if symbol not in self._user_delays[user_id]:
                self._user_delays[user_id][symbol] = []
            # Очищаем ненужную историю
            else:
                self._user_delays[user_id][symbol] = [
                    t for t in self._user_delays[user_id][symbol] if t > threshold_time]

        return self._user_delays[user_id][symbol]

    def _get_changes(self, data: list[Candle]) -> dict[int, Changes]:
        """
        Функция считает изменения для каждого тикера за каждый промежуток времени до self._max_history_len минут.
        :return:
        """
        changes = {}

        # for minutes in SequentialValues.PUMP_DUMP_TIMEFRAMES:
        for minutes in config.PD_TIMEFRAMES:
            relevant_data = data[-minutes:]
            relevant_data_len = len(relevant_data)

            if relevant_data_len != minutes:
                continue

            # Определение изменения price
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
        Функция получает и возвращает список тикеров.
        :param category:
        :return:
        """
        url = 'https://api.bybit.com/v5/market/tickers'
        params = {'category': category}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                result = await response.json()
                return [s["symbol"] for s in result["result"]["list"] if s["symbol"] not in self._ignored_symbols and
                        s["symbol"].endswith("USDT")]

    async def _update_settings_cycle(self, timeout: float = 5) -> None:
        """
        В бесконечном цикле обновляет информацию из базы данных.
        :param timeout:
        :return:
        """
        while True:
            try:
                self._active_users_id = await self._database.user_repo.get_subscribers_id()
                self._settings = await self._database.pd_repo.get_all()
            except Exception as e:
                logger.exception(e)
            finally:
                await asyncio.sleep(timeout)
