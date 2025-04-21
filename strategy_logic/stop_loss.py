import numpy as np
import pandas as pd
from strategy_logic.price_action import get_pattern_price_action

def find_support_resistance(df, timeframe='1h', window=10, threshold=0.02, min_touches=3):
    """
    Find support and resistance levels from price data with multiple touches
    
    Parameters:
    -----------
    df : pandas DataFrame
        DataFrame with OHLC data
    timeframe : str
        Current timeframe (affects the sensitivity of level detection)
    window : int
        Window size for detecting peaks and valleys
    threshold : float
        Percentage threshold for grouping similar price levels
    min_touches : int
        Minimum number of price touches to consider a valid level
        
    Returns:
    --------
    list
        List of dictionaries with level type, price, strength and range
    """
    # Адаптируем параметры под таймфрейм
    timeframe_multipliers = {
        '30m': 0.7,   # Более чувствительный для малых таймфреймов
        '1h': 1.0,    # Базовый уровень чувствительности
        '4h': 1.5,    # Менее чувствительный для 4h
        '1d': 2.0     # Еще менее чувствительный для дневного таймфрейма
    }
    
    # Получаем множитель для текущего таймфрейма (или используем 1.0 если таймфрейм неизвестен)
    tf_multiplier = timeframe_multipliers.get(timeframe, 1.0)
    
    # Адаптируем окно и порог под таймфрейм
    adapted_window = int(window * tf_multiplier)
    adapted_threshold = threshold * tf_multiplier
    
    # Инициализируем структуры для хранения потенциальных уровней
    price_clusters = []  # Кластеры цен для объединения близких уровней
    touches = {}  # Словарь для отслеживания количества касаний каждого уровня
    
    # Находим локальные минимумы (поддержки) и максимумы (сопротивления)
    support_levels = []
    resistance_levels = []
    
    # Для поиска локальных минимумов (поддержек)
    for i in range(adapted_window, len(df) - adapted_window):
        # Проверка на локальный минимум
        if all(df['low'].iloc[i] <= df['low'].iloc[i-adapted_window:i]) and \
           all(df['low'].iloc[i] <= df['low'].iloc[i+1:i+adapted_window+1]):
            support_levels.append((i, df['low'].iloc[i]))
    
    # Для поиска локальных максимумов (сопротивлений)
    for i in range(adapted_window, len(df) - adapted_window):
        # Проверка на локальный максимум
        if all(df['high'].iloc[i] >= df['high'].iloc[i-adapted_window:i]) and \
           all(df['high'].iloc[i] >= df['high'].iloc[i+1:i+adapted_window+1]):
            resistance_levels.append((i, df['high'].iloc[i]))
    
    # Функция для объединения близких уровней в кластеры
    def find_or_create_cluster(level_price, level_type):
        for cluster in price_clusters:
            # Проверяем, близок ли уровень к существующему кластеру
            avg_price = sum(p for _, p, _ in cluster['points']) / len(cluster['points']) if cluster['points'] else 0
            if abs(level_price - avg_price) / avg_price < adapted_threshold and cluster['type'] == level_type:
                return cluster
        
        # Если не нашли подходящий кластер, создаем новый
        new_cluster = {
            'type': level_type,
            'points': [],
            'touches': 0
        }
        price_clusters.append(new_cluster)
        return new_cluster
    
    # Обрабатываем уровни поддержки
    for idx, price in support_levels:
        cluster = find_or_create_cluster(price, 'support')
        cluster['points'].append((idx, price, 'support'))
        cluster['touches'] += 1
    
    # Обрабатываем уровни сопротивления
    for idx, price in resistance_levels:
        cluster = find_or_create_cluster(price, 'resistance')
        cluster['points'].append((idx, price, 'resistance'))
        cluster['touches'] += 1
    
    # Формируем итоговый список уровней
    final_levels = []
    for cluster in price_clusters:
        if cluster['touches'] >= min_touches:  # Фильтруем по минимальному количеству касаний
            points = cluster['points']
            avg_price = sum(p for _, p, _ in points) / len(points)
            # Вычисляем диапазон (мин. и макс. цены в кластере)
            min_price = min(p for _, p, _ in points)
            max_price = max(p for _, p, _ in points)
            range_width = max_price - min_price
            
            final_levels.append({
                'level_type': cluster['type'],
                'level_price': avg_price,
                'range_min': min_price,
                'range_max': max_price,
                'range_width': range_width,
                'strength': cluster['touches'],
                'points': points  # Сохраняем точки для возможного использования в дальнейшем
            })
    
    # Сортируем по силе (количеству касаний) по убыванию
    final_levels = sorted(final_levels, key=lambda x: x['strength'], reverse=True)
    
    return final_levels

def calculate_stop_loss(level, position_type, stop_loss_perc):
    """
    Calculate stop loss level based on support/resistance level range
    
    Parameters:
    -----------
    level : dict
        Level dict containing range_min, range_max, level_price
    position_type : str
        'long' or 'short'
    stop_loss_perc : float
        Percentage for stop loss
        
    Returns:
    --------
    float
        The calculated stop loss level
    """
    level_price = level['level_price']
    range_min = level['range_min']
    range_max = level['range_max']
    
    if position_type == 'long':
        # Для длинных позиций стоп-лосс выставляется ниже зоны поддержки
        base_stop = range_min
        # Добавляем еще немного места для уверенности (% от уровня)
        additional_buffer = base_stop * (stop_loss_perc / 100)
        return base_stop - additional_buffer
    else:
        # Для коротких позиций стоп-лосс выставляется выше зоны сопротивления
        base_stop = range_max
        # Добавляем еще немного места для уверенности (% от уровня)
        additional_buffer = base_stop * (stop_loss_perc / 100)
        return base_stop + additional_buffer

async def check_signals_near_level(df, levels, timeframe='1h', proximity_threshold=0.03):
    """
    Check for trading signals near support/resistance levels
    
    Parameters:
    -----------
    df : pandas DataFrame
        DataFrame with OHLC data and indicators
    levels : list
        List of support/resistance levels from find_support_resistance()
    timeframe : str
        Current timeframe (for reference)
    proximity_threshold : float
        How close price needs to be to the level (as percentage)
        
    Returns:
    --------
    list
        List of dictionaries with signals near levels
    """
    current_price = df['close'].iloc[-1]
    signals_near_level = []
    
    # Адаптируем порог под таймфрейм
    timeframe_thresholds = {
        '30m': proximity_threshold * 0.7,
        '1h': proximity_threshold,
        '4h': proximity_threshold * 1.5,
        '1d': proximity_threshold * 2.0
    }
    adapted_threshold = timeframe_thresholds.get(timeframe, proximity_threshold)
    
    # Подготовка данных для price_action в формате, который ожидает функция
    last_candles = []
    for i in range(-3, 0):
        try:
            # Формат свечи: [timestamp, open, high, low, close, volume]
            candle = [
                0,  # Timestamp (не используется в price_action)
                str(df['open'].iloc[i]),
                str(df['high'].iloc[i]),
                str(df['low'].iloc[i]),
                str(df['close'].iloc[i]),
                str(df['volume'].iloc[i]) if 'volume' in df.columns else "0"
            ]
            last_candles.append(candle)
        except (IndexError, KeyError) as e:
            print(f"Ошибка при доступе к данным: {e}")
            # Если нет достаточно данных, пропускаем
            continue
    
    # Получение сигнала price_action если достаточно данных
    pa_signal = None
    if len(last_candles) >= 3:
        try:
            pa_signal = await get_pattern_price_action(last_candles, "spot")
        except Exception as e:
            print(f"Ошибка при анализе паттернов Price Action: {e}")
            pa_signal = None
    
    for level in levels:
        # Проверяем, находится ли цена рядом с диапазоном уровня
        level_price = level['level_price']
        level_min = level['range_min']
        level_max = level['range_max']
        
        # Проверяем, находится ли цена в диапазоне уровня или близко к нему
        in_range = level_min <= current_price <= level_max
        near_range = abs(current_price - level_min) / level_min <= adapted_threshold or \
                     abs(current_price - level_max) / level_max <= adapted_threshold
        
        if in_range or near_range:
            # Рассчитываем процент расстояния
            if in_range:
                distance_percent = 0  # Цена внутри диапазона
            else:
                # Расстояние до ближайшей границы диапазона
                distance_to_min = abs(current_price - level_min) / level_min * 100
                distance_to_max = abs(current_price - level_max) / level_max * 100
                distance_percent = min(distance_to_min, distance_to_max)
            
            # Check for signals
            rsi_signal = "None"
            cm_signal = "None"
            price_action_signal = "None" if pa_signal is None else pa_signal
            
            # RSI signals
            if 'rsi' in df.columns:
                if df['rsi'].iloc[-1] < 30 and level['level_type'] == 'support':
                    rsi_signal = "Oversold near support - Bullish"
                elif df['rsi'].iloc[-1] > 70 and level['level_type'] == 'resistance':
                    rsi_signal = "Overbought near resistance - Bearish"
            
            # CM (PPO) signals - if present
            if 'ppoT' in df.columns:
                if df['ppoT'].iloc[-1] < -0.5 and level['level_type'] == 'support':
                    cm_signal = "PPO negative near support - Bullish reversal potential"
                elif df['ppoT'].iloc[-1] > 0.5 and level['level_type'] == 'resistance':
                    cm_signal = "PPO positive near resistance - Bearish reversal potential"
            
            # Проверяем соответствие сигнала price_action и типа уровня
            signal_is_valid = False
            if price_action_signal != "None":
                if (level['level_type'] == 'support' and 'Long' in price_action_signal) or \
                   (level['level_type'] == 'resistance' and 'Short' in price_action_signal):
                    signal_is_valid = True
            
            # Only add signals where at least one indicator is triggering
            if rsi_signal != "None" or cm_signal != "None" or (price_action_signal != "None" and signal_is_valid):
                signals_near_level.append({
                    'level_type': level['level_type'],
                    'level_price': level_price,
                    'range_min': level_min,
                    'range_max': level_max,
                    'range_width': level['range_width'],
                    'distance_percent': distance_percent,
                    'strength': level['strength'],  # Количество касаний
                    'rsi_signal': rsi_signal,
                    'cm_signal': cm_signal,
                    'price_action_signal': price_action_signal
                })
    
    return signals_near_level
