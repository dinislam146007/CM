async def get_pattern_price_action(candles: list, market_type) -> str:
    """
    Функция ищет паттерны на свечах.
    :param candles: [
        1499040000000,      // Open time
        "0.01634790",       // Open
        "0.80000000",       // High
        "0.01575800",       // Low
        "0.01577100",       // Close
    ]
    :param market_type: Тип торговли ('spot' или 'futures')
    :return: Название паттерна или None
    """

    def __get_ohlc(c: list) -> tuple[float, float, float, float]:
        return float(c[1]), float(c[2]), float(c[3]), float(c[4])


    def _pin_bar():
        candle = candles[-1]
        o, h, l, c = __get_ohlc(candle)

        if c > o:  # green candle
            upper_shadow: float = h - c
            lower_shadow: float = o - l
            body: float = c - o

        elif c < o:  # red candle
            upper_shadow: float = h - o
            lower_shadow: float = c - l
            body: float = o - c

        else:
            return

        max_shadow = max(upper_shadow, lower_shadow)
        min_shadow = min(upper_shadow, lower_shadow)

        if min_shadow == 0:
            # Обработка случая, когда min_shadow равен 0
            # Например, вы можете вернуть None, или использовать другое значение
            return None  # или просто пропустить этот паттерн
        else:
            # Ваш код
            if max_shadow / body > 2:
                if max_shadow == upper_shadow:  # Значит что большая тень сверху
                    if market_type == "spot":  # На споте шорт сигналы не нужны
                        return
                    return "Bear PinBar"  # Переименовано для единообразия
                else:  # Значит что большая тень снизу
                    return "Bull PinBar"  # Переименовано для единообразия

        return


    def _inside_bar():  # noqa
        prev_candle = candles[-2]
        curr_candle = candles[-1]

        o2, h2, l2, c2 = __get_ohlc(prev_candle)
        o1, h1, l1, c1 = __get_ohlc(curr_candle)

        # prev_candle_color = "RED" if c2 < o2 else "GREEN"
        # curr_candle_color = "RED" if c1 < o1 else "GREEN"

        # Contr-trend-bars
        # if prev_candle_color == curr_candle_color:
        #     return False

        # Trend bars
        # if prev_candle_color != curr_candle_color:
        #     return False

        if h2 > h1 and l1 > l2:
            return "Bull InsideBar"  # Переименовано для единообразия

        return


    def _fakey():
        prev_prev_candle = candles[-3]
        prev_candle = candles[-2]
        curr_candle = candles[-1]

        o3, h3, l3, c3 = __get_ohlc(prev_prev_candle)
        o2, h2, l2, c2 = __get_ohlc(prev_candle)
        o1, h1, l1, c1 = __get_ohlc(curr_candle)

        # Проверка на InsideBar
        if h3 > h2 and l2 > l3:
            # Проверка на закрытие свечи внутри "Внутреннего бара"
            if h2 > c1 > l2:
                stabbing_upper: bool = h1 > h3
                stabbing_lower: bool = l1 < l3

                # Проверка чтобы закол был только с одной стороны
                if all([stabbing_lower, stabbing_upper]):
                    return

                if stabbing_upper:
                    if market_type == "spot":
                        return
                    return "Bear Fakey"  # Переименовано для единообразия
                elif stabbing_lower:
                    return "Bull Fakey"  # Переименовано для единообразия

        return


    def _outside_bar():
        prev_candle = candles[-2]
        curr_candle = candles[-1]

        o2, h2, l2, c2 = __get_ohlc(prev_candle)
        o1, h1, l1, c1 = __get_ohlc(curr_candle)

        prev_candle_color = "RED" if c2 < o2 else "GREEN"
        curr_candle_color = "RED" if c1 < o1 else "GREEN"

        if prev_candle_color == curr_candle_color:
            return

        if not (h1 > h2 and l1 < l2):
            return

        if curr_candle_color == "RED":
            if market_type == "spot":
                return
            return "Bear OutsideBar"  # Переименовано для единообразия

        elif curr_candle_color == "GREEN":
            return "Bull OutsideBar"  # Переименовано для единообразия

        return


    def _ppr():
        """
        Поиск паттерна PPR:
        1. Паттерн PPR - паттерн состоящий всегда из двух контр трендовых свечей, где должен быть обязательно
        перекрыт максимум либо минимум предыдущей свечи именно телом второй свечи паттерна PPR.
        2. Вторая свеча паттерна не должна перебивать максимум либо минимум первой свечи паттерна иначе это будет
         уже паттерн OutsideBar.
        :return:
        """
        prev_candle = candles[-2]
        curr_candle = candles[-1]

        o2, h2, l2, c2 = __get_ohlc(prev_candle)
        o1, h1, l1, c1 = __get_ohlc(curr_candle)

        prev_candle_color = "RED" if c2 < o2 else "GREEN"
        curr_candle_color = "RED" if c1 < o1 else "GREEN"

        if prev_candle_color == curr_candle_color:
            return

        if curr_candle_color == "GREEN":
            if c1 > h2 and l1 > l2:
                return "Bull PPR"  # Переименовано для единообразия

        elif curr_candle_color == "RED":
            if market_type == "spot":
                return
            if c1 < l2 and h1 < h2:
                return "Bear PPR"  # Переименовано для единообразия

        return


    # ! Очередность логически важна
    for func in [
        _ppr,
        _fakey,
        _outside_bar,
        _pin_bar,
    ]:
        pattern = func()
        if pattern:
            return pattern
    return None
