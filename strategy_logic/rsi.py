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
            signals.append("long")
        elif df['ema21'].iloc[i] < df['ema49'].iloc[i] and df['rsi'].iloc[i] > 70:
            signals.append("short")
        else:
            signals.append("Hold")
    # Добавляем сигналы в DataFrame
    df['signal_rsi'] = ['Hold'] + signals
    return df





# def detect_divergence_convergence(df, indicator_col="rsi", price_col="close", order=30):
#     """
#     Обнаруживает дивергенции и конвергенции между ценой и индикатором (например, RSI).
#     Возвращает:
#         - "bullish_divergence" (бычья дивергенция)
#         - "bearish_divergence" (медвежья дивергенция)
#         - "bullish_convergence" (бычья конвергенция)
#         - "bearish_convergence" (медвежья конвергенция)
#         - None (если ничего не найдено)
#
#     order - количество свечей, используемых для поиска экстремумов.
#     """
#
#     if len(df) < order + 2:  # Минимум данных для анализа
#         return None
#
#     price = df[price_col]
#     indicator = df[indicator_col]
#
#     # Определяем локальные минимумы и максимумы
#     local_min_idx = argrelextrema(price.values, np.less, order=order)[0]
#     local_max_idx = argrelextrema(price.values, np.greater, order=order)[0]
#
#     indicator_min_idx = argrelextrema(indicator.values, np.less, order=order)[0]
#     indicator_max_idx = argrelextrema(indicator.values, np.greater, order=order)[0]
#
#     # Проверяем последние экстремумы для ДИВЕРГЕНЦИЙ
#     if len(local_min_idx) > 1 and len(indicator_min_idx) > 1:
#         price_min1, price_min2 = price.iloc[local_min_idx[-2]], price.iloc[local_min_idx[-1]]
#         rsi_min1, rsi_min2 = indicator.iloc[indicator_min_idx[-2]], indicator.iloc[indicator_min_idx[-1]]
#
#         # Бычья дивергенция: Цена делает новый минимум, а RSI – нет (растет)
#         if price_min2 < price_min1 and rsi_min2 > rsi_min1:
#             return "bullish_divergence"
#
#     if len(local_max_idx) > 1 and len(indicator_max_idx) > 1:
#         price_max1, price_max2 = price.iloc[local_max_idx[-2]], price.iloc[local_max_idx[-1]]
#         rsi_max1, rsi_max2 = indicator.iloc[indicator_max_idx[-2]], indicator.iloc[indicator_max_idx[-1]]
#
#         # Медвежья дивергенция: Цена делает новый максимум, а RSI – нет (падает)
#         if price_max2 > price_max1 and rsi_max2 < rsi_max1:
#             return "bearish_divergence"
#
#     # Проверяем последние экстремумы для КОНВЕРГЕНЦИЙ
#     if len(local_min_idx) > 1 and len(indicator_min_idx) > 1:
#         price_min1, price_min2 = price.iloc[local_min_idx[-2]], price.iloc[local_min_idx[-1]]
#         rsi_min1, rsi_min2 = indicator.iloc[indicator_min_idx[-2]], indicator.iloc[indicator_min_idx[-1]]
#
#         # Бычья конвергенция: Цена делает более высокий минимум, а RSI – более низкий минимум
#         if price_min2 > price_min1 and rsi_min2 < rsi_min1:
#             return "bullish_convergence"
#
#     if len(local_max_idx) > 1 and len(indicator_max_idx) > 1:
#         price_max1, price_max2 = price.iloc[local_max_idx[-2]], price.iloc[local_max_idx[-1]]
#         rsi_max1, rsi_max2 = indicator.iloc[indicator_max_idx[-2]], indicator.iloc[indicator_max_idx[-1]]
#
#         # Медвежья конвергенция: Цена делает более низкий максимум, а RSI – более высокий максимум
#         if price_max2 < price_max1 and rsi_max2 > rsi_max1:
#             return "bearish_convergence"
#
#     return None

def detect_divergence_convergence(df):
    signals = {'RSI': None, 'CM': None}

    # RSI divergence/convergence
    if df['close'].iloc[-1] < df['close'].iloc[-2] and df['rsi'].iloc[-1] > df['rsi'].iloc[-2]:
        signals['RSI'] = 'Bullish Divergence'
    elif df['close'].iloc[-1] > df['close'].iloc[-2] and df['rsi'].iloc[-1] < df['rsi'].iloc[-2]:
        signals['RSI'] = 'Bearish Divergence'

    # PPO divergence/convergence
    if df['close'].iloc[-1] < df['close'].iloc[-2] and df['ppoT'].iloc[-1] > df['ppoT'].iloc[-2]:
        signals['PPO'] = 'Bullish Divergence'
    elif df['close'].iloc[-1] > df['close'].iloc[-2] and df['ppoT'].iloc[-1] < df['ppoT'].iloc[-2]:
        signals['PPO'] = 'Bearish Divergence'

    return signals

import numpy as np
import pandas as pd
import ta

def detect_rsi_divergence(df, rsi_period=14):
    df['rsi'] = ta.momentum.rsi(df['close'], window=rsi_period)

    # находим локальные экстремумы цены и RSI
    df['price_high'] = df['close'][(df['close'].shift(1) < df['close']) & (df['close'].shift(-1) < df['close'])]
    df['price_low'] = df['close'][(df['close'].shift(1) > df['close']) & (df['close'].shift(-1) > df['close'])]

    df['rsi_high'] = df['rsi'][(df['rsi'].shift(1) < df['rsi']) & (df['rsi'].shift(-1) < df['rsi'])]
    df['rsi_low'] = df['rsi'][(df['rsi'].shift(1) > df['rsi']) & (df['rsi'].shift(-1) > df['rsi'])]

    # последние два экстремума
    price_lows = df['price_low'].dropna().iloc[-2:]
    rsi_lows = df['rsi_low'].dropna().iloc[-2:]

    price_highs = df['price_high'].dropna().iloc[-2:]
    rsi_highs = df['rsi_high'].dropna().iloc[-2:]

    divergence = None

    # проверка бычьей дивергенции (по минимумам)
    if len(price_lows) == 2 and len(rsi_lows) == 2:
        if price_lows.iloc[-1] < price_lows.iloc[-2] and rsi_lows.iloc[-1] > rsi_lows.iloc[-2]:
            divergence = 'Bullish Divergence'

    # проверка медвежьей дивергенции (по максимумам)
    if len(price_highs) == 2 and len(rsi_highs) == 2:
        if price_highs.iloc[-1] > price_highs.iloc[-2] and rsi_highs.iloc[-1] < rsi_highs.iloc[-2]:
            divergence = 'Bearish Divergence'

    return divergence

def detect_cm_ppo_divergence(df):
    # используем уже рассчитанные значения df['ppoT'] или df['ppoB']
    df['price_high'] = df['close'][(df['close'].shift(1) < df['close']) & (df['close'].shift(-1) < df['close'])]
    df['price_low'] = df['close'][(df['close'].shift(1) > df['close']) & (df['close'].shift(-1) > df['close'])]

    df['ppo_high'] = df['ppoT'][(df['ppoT'].shift(1) < df['ppoT']) & (df['ppoT'].shift(-1) < df['ppoT'])]
    df['ppo_low'] = df['ppoB'][(df['ppoB'].shift(1) > df['ppoB']) & (df['ppoB'].shift(-1) > df['ppoB'])]

    # последние два экстремума
    price_lows = df['price_low'].dropna().iloc[-2:]
    ppo_lows = df['ppo_low'].dropna().iloc[-2:]

    price_highs = df['price_high'].dropna().iloc[-2:]
    ppo_highs = df['ppo_high'].dropna().iloc[-2:]

    divergence = None

    # проверка бычьей дивергенции
    if len(price_lows) == 2 and len(ppo_lows) == 2:
        if price_lows.iloc[-1] < price_lows.iloc[-2] and ppo_lows.iloc[-1] > ppo_lows.iloc[-2]:
            divergence = 'Bullish Divergence'

    # проверка медвежьей дивергенции
    if len(price_highs) == 2 and len(ppo_highs) == 2:
        if price_highs.iloc[-1] > price_highs.iloc[-2] and ppo_highs.iloc[-1] < ppo_highs.iloc[-2]:
            divergence = 'Bearish Divergence'

    return divergence

def detect_divergence_convergence_advanced(df, rsi_length=9, lbR=3, lbL=1, range_upper=60, range_lower=5):
    """
    Advanced divergence and convergence detection based on TradingView PineScript implementation.
    
    Parameters:
    -----------
    df : pandas DataFrame
        DataFrame with ohlc data and RSI values
    rsi_length : int
        RSI period for calculation
    lbR : int
        Pivot Lookback Right
    lbL : int
        Pivot Lookback Left
    range_upper : int
        Max of Lookback Range
    range_lower : int
        Min of Lookback Range
        
    Returns:
    --------
    dict
        Contains detected signals: regular_bullish, hidden_bullish, regular_bearish, hidden_bearish
    """
    # Ensure RSI is calculated
    if 'rsi' not in df.columns:
        df = calculate_rsi(df, rsi_length)
    
    osc = df['rsi'].values
    result = {
        'regular_bullish': False,
        'hidden_bullish': False,
        'regular_bearish': False,
        'hidden_bearish': False
    }
    
    # Find pivot lows and highs
    pivot_lows = []
    pivot_highs = []
    
    for i in range(lbL, len(df) - lbR):
        # Check for pivot low
        is_pivot_low = True
        for j in range(1, lbL + 1):
            if osc[i] >= osc[i-j]:
                is_pivot_low = False
                break
        for j in range(1, lbR + 1):
            if osc[i] >= osc[i+j]:
                is_pivot_low = False
                break
        if is_pivot_low:
            pivot_lows.append(i)
        
        # Check for pivot high
        is_pivot_high = True
        for j in range(1, lbL + 1):
            if osc[i] <= osc[i-j]:
                is_pivot_high = False
                break
        for j in range(1, lbR + 1):
            if osc[i] <= osc[i+j]:
                is_pivot_high = False
                break
        if is_pivot_high:
            pivot_highs.append(i)
    
    # Helper function for _inRange
    def _in_range(idx1, idx2):
        bars = idx1 - idx2
        return range_lower <= bars <= range_upper
    
    # Check last two pivot lows for bullish divergence
    if len(pivot_lows) >= 2:
        i = pivot_lows[-1]
        prev_i = pivot_lows[-2]
        
        if _in_range(i, prev_i):
            # Regular Bullish: Price makes lower low but RSI makes higher low
            if df['low'].iloc[i] < df['low'].iloc[prev_i] and osc[i] > osc[prev_i]:
                result['regular_bullish'] = True
            
            # Hidden Bullish: Price makes higher low but RSI makes lower low
            if df['low'].iloc[i] > df['low'].iloc[prev_i] and osc[i] < osc[prev_i]:
                result['hidden_bullish'] = True
    
    # Check last two pivot highs for bearish divergence
    if len(pivot_highs) >= 2:
        i = pivot_highs[-1]
        prev_i = pivot_highs[-2]
        
        if _in_range(i, prev_i):
            # Regular Bearish: Price makes higher high but RSI makes lower high
            if df['high'].iloc[i] > df['high'].iloc[prev_i] and osc[i] < osc[prev_i]:
                result['regular_bearish'] = True
            
            # Hidden Bearish: Price makes lower high but RSI makes higher high
            if df['high'].iloc[i] < df['high'].iloc[prev_i] and osc[i] > osc[prev_i]:
                result['hidden_bearish'] = True
    
    return result

def detect_take_profit_condition(df, rsi_level=80):
    """
    Detects if RSI has crossed above a specified take profit level.
    Similar to the TradingView script's take profit implementation.
    
    Parameters:
    -----------
    df : pandas DataFrame
        DataFrame with OHLC data and RSI values
    rsi_level : int
        The RSI level that triggers profit taking (default: 80)
        
    Returns:
    --------
    bool
        True if profit taking condition is met, False otherwise
    """
    if 'rsi' not in df.columns:
        return False
    
    # Check if RSI has crossed above the specified level
    if len(df) < 2:
        return False
    
    # Detect crossover (RSI was below the level and is now above it)
    rsi_crossover = df['rsi'].iloc[-2] < rsi_level and df['rsi'].iloc[-1] >= rsi_level
    
    return rsi_crossover

def calculate_atr(df, length=14):
    """
    Calculate the Average True Range (ATR) for use in stop loss calculations.
    
    Parameters:
    -----------
    df : pandas DataFrame
        DataFrame with OHLC data
    length : int
        Period for ATR calculation
        
    Returns:
    --------
    DataFrame
        Input DataFrame with added 'atr' column
    """
    if len(df) < length + 1:
        df['atr'] = 0
        return df
        
    # Calculate True Range
    true_range = np.zeros(len(df))
    
    for i in range(1, len(df)):
        high_low = df['high'].iloc[i] - df['low'].iloc[i]
        high_close_prev = abs(df['high'].iloc[i] - df['close'].iloc[i-1])
        low_close_prev = abs(df['low'].iloc[i] - df['close'].iloc[i-1])
        
        true_range[i] = max(high_low, high_close_prev, low_close_prev)
    
    # Calculate ATR using exponential moving average
    atr = np.zeros(len(df))
    atr[length] = np.mean(true_range[1:length+1])
    
    for i in range(length+1, len(df)):
        atr[i] = (atr[i-1] * (length-1) + true_range[i]) / length
    
    df['atr'] = atr
    return df

def calculate_stop_loss(df, position_type='long', stop_loss_type='PERC', stop_loss_perc=5, atr_length=14, atr_multiplier=3.5):
    """
    Calculate stop loss levels using either percentage-based or ATR-based methods.
    
    Parameters:
    -----------
    df : pandas DataFrame
        DataFrame with OHLC data
    position_type : str
        'long' or 'short' - the type of position
    stop_loss_type : str
        'ATR', 'PERC', or 'NONE' - method for calculating stop loss
    stop_loss_perc : float
        Percentage for stop loss (if using 'PERC' method)
    atr_length : int
        Period for ATR calculation (if using 'ATR' method)
    atr_multiplier : float
        Multiplier for ATR (if using 'ATR' method)
        
    Returns:
    --------
    float
        The calculated stop loss level, or None if stop_loss_type is 'NONE'
    """
    if stop_loss_type == 'NONE':
        return None
    
    if 'atr' not in df.columns and stop_loss_type == 'ATR':
        df = calculate_atr(df, atr_length)
    
    current_price = df['close'].iloc[-1]
    
    if stop_loss_type == 'PERC':
        if position_type == 'long':
            stop_level = current_price * (1 - stop_loss_perc / 100)
        else:  # short position
            stop_level = current_price * (1 + stop_loss_perc / 100)
    
    elif stop_loss_type == 'ATR':
        atr_value = df['atr'].iloc[-1]
        if position_type == 'long':
            stop_level = current_price - (atr_value * atr_multiplier)
        else:  # short position
            stop_level = current_price + (atr_value * atr_multiplier)
    
    return stop_level

def check_stop_loss_hit(df, stop_level, position_type='long'):
    """
    Check if the stop loss level has been hit.
    
    Parameters:
    -----------
    df : pandas DataFrame
        DataFrame with OHLC data (needs at least 2 rows)
    stop_level : float
        The stop loss price level
    position_type : str
        'long' or 'short' - the type of position
        
    Returns:
    --------
    bool
        True if stop loss was hit, False otherwise
    """
    if stop_level is None or len(df) < 2:
        return False
    
    if position_type == 'long':
        # For long positions, check if price went below stop level
        return df['close'].iloc[-1] < stop_level
    else:
        # For short positions, check if price went above stop level
        return df['close'].iloc[-1] > stop_level

def generate_trading_signals(df, rsi_length=9, lbR=3, lbL=1, take_profit_level=80, 
                           stop_loss_type='PERC', stop_loss_perc=5, atr_length=14, atr_multiplier=3.5):
    """
    Generates comprehensive trading signals based on RSI divergence with take profit and stop loss levels.
    
    Parameters:
    -----------
    df : pandas DataFrame
        DataFrame with OHLC data
    rsi_length : int
        RSI period for calculation
    lbR : int
        Pivot Lookback Right
    lbL : int
        Pivot Lookback Left
    take_profit_level : int
        RSI level for taking profit
    stop_loss_type : str
        'ATR', 'PERC', or 'NONE' - method for calculating stop loss
    stop_loss_perc : float
        Percentage for stop loss (if using 'PERC' method)
    atr_length : int
        Period for ATR calculation (if using 'ATR' method)
    atr_multiplier : float
        Multiplier for ATR (if using 'ATR' method)
        
    Returns:
    --------
    dict
        Contains all detected signals, recommendations, and risk management levels
    """
    # Ensure RSI is calculated
    if 'rsi' not in df.columns:
        df = calculate_rsi(df, rsi_length)
    
    # Get divergence signals
    divergence_signals = detect_divergence_convergence_advanced(
        df, 
        rsi_length=rsi_length,
        lbR=lbR,
        lbL=lbL
    )
    
    # Check for take profit condition
    take_profit = detect_take_profit_condition(df, take_profit_level)
    
    # Generate final signals
    entry_signal = False
    exit_signal = False
    signal_type = "None"
    position_type = "none"
    
    # Entry signals (based on bullish divergences)
    if divergence_signals['regular_bullish'] or divergence_signals['hidden_bullish']:
        entry_signal = True
        signal_type = "Long" if divergence_signals['regular_bullish'] else "Hidden Long"
        position_type = "long"
    
    # Exit signals (based on bearish divergences or take profit)
    if divergence_signals['regular_bearish'] or divergence_signals['hidden_bearish'] or take_profit:
        exit_signal = True
        if take_profit:
            signal_type = "Take Profit"
        else:
            signal_type = "Exit - Bearish" if divergence_signals['regular_bearish'] else "Exit - Hidden Bearish"
    
    # Calculate stop loss level if we have an entry signal
    stop_loss_level = None
    if entry_signal and stop_loss_type != 'NONE':
        stop_loss_level = calculate_stop_loss(
            df, 
            position_type=position_type, 
            stop_loss_type=stop_loss_type,
            stop_loss_perc=stop_loss_perc,
            atr_length=atr_length,
            atr_multiplier=atr_multiplier
        )
    
    # Check if stop loss was hit (for existing positions)
    stop_loss_hit = False
    if stop_loss_level is not None and not entry_signal:
        stop_loss_hit = check_stop_loss_hit(df, stop_loss_level, position_type)
        if stop_loss_hit:
            exit_signal = True
            signal_type = "Stop Loss Hit"
    
    # Calculate target profit level
    target_price = None
    if entry_signal and position_type == 'long':
        # Simple target calculation - can be enhanced
        current_price = df['close'].iloc[-1]
        if stop_loss_level:
            # Risk:Reward of 1:2
            risk = current_price - stop_loss_level
            target_price = current_price + (risk * 2)
    
    return {
        'entry_signal': entry_signal,
        'exit_signal': exit_signal,
        'signal_type': signal_type,
        'position_type': position_type,
        'divergence': divergence_signals,
        'take_profit_triggered': take_profit,
        'current_rsi': df['rsi'].iloc[-1],
        'stop_loss_level': stop_loss_level,
        'stop_loss_hit': stop_loss_hit,
        'target_price': target_price,
        'current_price': df['close'].iloc[-1]
    }