from scipy.signal import argrelextrema
import numpy as np


def calculate_rsi(df, period=14):
    """Вычисление RSI на основе закрытых цен без использования talib."""
    delta = df['close'].diff(1)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    avg_gain = np.zeros_like(delta)
    avg_loss = np.zeros_like(delta)

    avg_gain[period] = np.mean(gain[:period])
    avg_loss[period] = np.mean(loss[:period])

    for i in range(period + 1, len(df)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period

    rs = avg_gain / (avg_loss + 1e-10)  # Добавляем малое число для избежания деления на ноль
    df['rsi'] = 100 - (100 / (1 + rs))
    return df


def calculate_ema(df, period1=21, period2=49):
    """Вычисление EMA для двух периодов без использования talib."""

    def ema(series, period):
        alpha = 2 / (period + 1)
        ema_values = np.zeros_like(series)
        ema_values[0] = series[0]  # Начальное значение берем как первый элемент

        for i in range(1, len(series)):
            ema_values[i] = alpha * series[i] + (1 - alpha) * ema_values[i - 1]

        return ema_values

    df['ema21'] = ema(df['close'].values, period1)
    df['ema49'] = ema(df['close'].values, period2)
    return df

def generate_signals_rsi(df):
    """Генерация сигналов на основе пересечения EMA и уровней RSI."""
    if 'rsi' not in df.columns:
        raise ValueError("Column 'rsi' not found in DataFrame")
    if 'ema21' not in df.columns or 'ema49' not in df.columns:
        raise ValueError("Columns 'ema21' and/or 'ema49' not found in DataFrame")

    signals = []

    # Проверка условий на покупку или продажу
    for i in range(1, len(df)):

        if df['ema21'].iloc[i] > df['ema49'].iloc[i] and df['rsi'].iloc[i] < 30:
            signals.append("Buy")
        elif df['ema21'].iloc[i] < df['ema49'].iloc[i] and df['rsi'].iloc[i] > 70:
            signals.append("Sell")
        else:
            signals.append("Hold")
    # Добавляем сигналы в DataFrame
    df['signal_rsi'] = ['Hold'] + signals
    return df





def detect_divergence_convergence(df, indicator_col="rsi", price_col="close", order=30):
    """
    Обнаруживает дивергенции и конвергенции между ценой и индикатором (например, RSI).
    Возвращает:
        - "bullish_divergence" (бычья дивергенция)
        - "bearish_divergence" (медвежья дивергенция)
        - "bullish_convergence" (бычья конвергенция)
        - "bearish_convergence" (медвежья конвергенция)
        - None (если ничего не найдено)

    order - количество свечей, используемых для поиска экстремумов.
    """

    if len(df) < order + 2:  # Минимум данных для анализа
        return None

    price = df[price_col]
    indicator = df[indicator_col]

    # Определяем локальные минимумы и максимумы
    local_min_idx = argrelextrema(price.values, np.less, order=order)[0]
    local_max_idx = argrelextrema(price.values, np.greater, order=order)[0]

    indicator_min_idx = argrelextrema(indicator.values, np.less, order=order)[0]
    indicator_max_idx = argrelextrema(indicator.values, np.greater, order=order)[0]

    # Проверяем последние экстремумы для ДИВЕРГЕНЦИЙ
    if len(local_min_idx) > 1 and len(indicator_min_idx) > 1:
        price_min1, price_min2 = price.iloc[local_min_idx[-2]], price.iloc[local_min_idx[-1]]
        rsi_min1, rsi_min2 = indicator.iloc[indicator_min_idx[-2]], indicator.iloc[indicator_min_idx[-1]]

        # Бычья дивергенция: Цена делает новый минимум, а RSI – нет (растет)
        if price_min2 < price_min1 and rsi_min2 > rsi_min1:
            return "bullish_divergence"

    if len(local_max_idx) > 1 and len(indicator_max_idx) > 1:
        price_max1, price_max2 = price.iloc[local_max_idx[-2]], price.iloc[local_max_idx[-1]]
        rsi_max1, rsi_max2 = indicator.iloc[indicator_max_idx[-2]], indicator.iloc[indicator_max_idx[-1]]

        # Медвежья дивергенция: Цена делает новый максимум, а RSI – нет (падает)
        if price_max2 > price_max1 and rsi_max2 < rsi_max1:
            return "bearish_divergence"

    # Проверяем последние экстремумы для КОНВЕРГЕНЦИЙ
    if len(local_min_idx) > 1 and len(indicator_min_idx) > 1:
        price_min1, price_min2 = price.iloc[local_min_idx[-2]], price.iloc[local_min_idx[-1]]
        rsi_min1, rsi_min2 = indicator.iloc[indicator_min_idx[-2]], indicator.iloc[indicator_min_idx[-1]]

        # Бычья конвергенция: Цена делает более высокий минимум, а RSI – более низкий минимум
        if price_min2 > price_min1 and rsi_min2 < rsi_min1:
            return "bullish_convergence"

    if len(local_max_idx) > 1 and len(indicator_max_idx) > 1:
        price_max1, price_max2 = price.iloc[local_max_idx[-2]], price.iloc[local_max_idx[-1]]
        rsi_max1, rsi_max2 = indicator.iloc[indicator_max_idx[-2]], indicator.iloc[indicator_max_idx[-1]]

        # Медвежья конвергенция: Цена делает более низкий максимум, а RSI – более высокий максимум
        if price_max2 < price_max1 and rsi_max2 > rsi_max1:
            return "bearish_convergence"

    return None

