from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def start_inline():
    kb = [
        [InlineKeyboardButton(text='Сигналы 📌', callback_data='signals_0 start'),
        InlineKeyboardButton(text='Статистика 📈', callback_data='stat start')],
        [InlineKeyboardButton(text='Сделки 📄', callback_data='orders start')],
        [InlineKeyboardButton(text='Избранные пары ⭐️', callback_data='like start')],
        [InlineKeyboardButton(text='Мониторинг', callback_data='monitor start')],
        [InlineKeyboardButton(text='Уведомления', callback_data='sub start False')],
        [InlineKeyboardButton(text='Уведомления в группе', callback_data='sub start True')],
        [InlineKeyboardButton(text='Настройки ⚙️', callback_data='settings start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def subscription_management_inline(group):
    kb = [
        [
            InlineKeyboardButton(text='Добавить пару', callback_data=f'sub add {group}'),
            InlineKeyboardButton(text='Удалить пару', callback_data=f'sub del {group}')

         ],
        [InlineKeyboardButton(text='Назад', callback_data=f'start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def stat_inline(profit=0, lesion=0):
    kb = [
        [
            InlineKeyboardButton(text=f'Прибыльные ({profit})', callback_data='stat profit_list 0'),
            InlineKeyboardButton(text=f'Убыточные ({lesion})', callback_data='stat loss_list 0')
        ],
        [
            InlineKeyboardButton(text='Все сделки', callback_data='stat all 0')
        ],
        [InlineKeyboardButton(text='Скачать таблицу со сделками', callback_data='table stat')],
        [InlineKeyboardButton(text='Статистика за определенный период', callback_data='stat period')],
        [InlineKeyboardButton(text='Назад', callback_data='start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def like_inline():
    kb = [
        [
            InlineKeyboardButton(text='Добавить пару', callback_data='like add'),
            InlineKeyboardButton(text='Удалить пару', callback_data='like del')
         ],
         [InlineKeyboardButton(text='Назад', callback_data='start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def like_del_inline(user):
    kb = []
    if user['crypto_pairs']:
        pairs = user['crypto_pairs'].split(",")
        for pair in pairs:
            kb.append([
                InlineKeyboardButton(text=f"❌ {pair}", callback_data=f"like delete {pair}")
            ])
    kb.append([InlineKeyboardButton(text='Назад', callback_data='like start')])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def monitor_del_inline(user):
    kb = []
    if user['monitor_pairs']:
        pairs = user['monitor_pairs'].split(",")
        for pair in pairs:
            kb.append([
                InlineKeyboardButton(text=f"❌ {pair}", callback_data=f"monitor delete {pair}")
            ])
    kb.append([InlineKeyboardButton(text='Назад', callback_data='monitor start')])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def timeframe_inline():
    timeframes = [("1d", "1Д"), ("4h", "4h"), ("1h", "1h"), ("30m", "30m")]
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"tf_{value}")
        for value, label in timeframes
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons])  # Создаем клавиатуру
    return kb

def monitor_inline():
    kb = [
        [
            InlineKeyboardButton(text='Добавить пару', callback_data='monitor add'),
            InlineKeyboardButton(text='Удалить пару', callback_data='monitor del')
         ],
         [InlineKeyboardButton(text='Назад', callback_data='start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def orders_inline(open, close):
    kb = [
        [
            InlineKeyboardButton(text=f'Открытые ({open})', callback_data='orders open 0'),
            InlineKeyboardButton(text=f'Закрытые ({close})', callback_data='orders close 0')
        ],
        [
            InlineKeyboardButton(text='Все', callback_data='orders all 0'),
            InlineKeyboardButton(text='Прибыльные', callback_data='orders profit 0'),
            InlineKeyboardButton(text='Убыточные', callback_data='orders loss 0')
        ],
        [InlineKeyboardButton(text='Назад', callback_data='start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def orders_filter_inline(action, timeframes=None):
    """Создает клавиатуру с фильтрацией по таймфреймам для сделок"""
    kb = []
    
    # Кнопка "Все таймфреймы"
    kb.append([InlineKeyboardButton(text='📊 Все таймфреймы', callback_data=f'orders {action} all 0')])
    
    if timeframes:
        # Импортируем функцию для сортировки
        from basic.handlers import interval_weight
        
        # Сортируем таймфреймы по важности (от большего к меньшему)
        sorted_timeframes = sorted([tf for tf in timeframes if tf], 
                                 key=lambda x: interval_weight(x), reverse=True)
        
        # Группируем кнопки таймфреймов по 2 в ряд
        timeframe_buttons = []
        for tf in sorted_timeframes:
            # Конвертируем таймфрейм для отображения
            from basic.handlers import interval_conv
            tf_display = interval_conv(tf)
            timeframe_buttons.append(InlineKeyboardButton(
                text=f'⏱️ {tf_display}', 
                callback_data=f'orders {action} {tf} 0'
            ))
            
            # Добавляем ряд каждые 2 кнопки
            if len(timeframe_buttons) == 2:
                kb.append(timeframe_buttons)
                timeframe_buttons = []
        
        # Добавляем оставшиеся кнопки
        if timeframe_buttons:
            kb.append(timeframe_buttons)
    
    # Кнопка назад
    kb.append([InlineKeyboardButton(text='⬅️ Назад', callback_data='orders start')])
    
    return InlineKeyboardMarkup(inline_keyboard=kb)

def settings_inline():
    kb = [
        [InlineKeyboardButton(text='📊 Процент списания от депозита', callback_data='settings percent')],
        [InlineKeyboardButton(text='Типы торговли и плечо', callback_data='trading_settings')],
        [InlineKeyboardButton(text='Параметры торговой стратегии', callback_data='settings strategy')],
        [InlineKeyboardButton(text='Настройки CM индикатора', callback_data='settings cm')],
        [InlineKeyboardButton(text='Настройки индикатора дивергенции', callback_data='settings divergence')],
        [InlineKeyboardButton(text='Настройки RSI индикатора', callback_data='settings rsi')],
        [InlineKeyboardButton(text='Настройки Pump/Dump детектора', callback_data='settings pump_dump')],
        [InlineKeyboardButton(text='Настройки бирж', callback_data='settings exchanges')],
        [InlineKeyboardButton(text='Назад', callback_data='start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def strategy_params_inline():
    kb = [
        [InlineKeyboardButton(text='Объем ордера (USDT)', callback_data='strategy OrderSize')],
        [InlineKeyboardButton(text='Take Profit (%)', callback_data='strategy TakeProfit')],
        [InlineKeyboardButton(text='Stop Loss (%)', callback_data='strategy StopLoss')],
        [InlineKeyboardButton(text='Черный список монет', callback_data='strategy CoinsBlackList')],
        [InlineKeyboardButton(text='Мин. объем торгов', callback_data='strategy MinVolume')],
        [InlineKeyboardButton(text='Макс. объем торгов', callback_data='strategy MaxVolume')],
        [InlineKeyboardButton(text='Сбросить к стандартным', callback_data='strategy reset')],
        [InlineKeyboardButton(text='Назад', callback_data='settings start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def close_state():
    kb = [
        [InlineKeyboardButton(text='Отмена', callback_data='close_state')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def signals_inline(buy, sale):
    kb = [
        [InlineKeyboardButton(text=f'🔰 Покупка ({buy})', callback_data='signals_0 buy_s 0'), 
            InlineKeyboardButton(text=f'🔻 Продажа ({sale})', callback_data='signals_0 sale_s 0')
            ],
            [InlineKeyboardButton(text='Скачать таблицу с сигналами', callback_data='table signals')],
            [InlineKeyboardButton(text='Назад', callback_data='start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def signals_inline_n(status, len_n, n_back, interval, n):
    kb = [
        [InlineKeyboardButton(text=f"{n + 1} / {len_n}", callback_data='ignore')],
        [
            InlineKeyboardButton(text='<-', callback_data=f'signals_{n_back} {status}_{interval} {n - 1}'),
         InlineKeyboardButton(text='Назад', callback_data=f'signals_{n_back} {status}_s'),
         InlineKeyboardButton(text='->', callback_data=f'signals_{n_back} {status}_{interval} {n + 1}')
         ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def orders_inline_n(n,status, len_n, back):
    kb = [
        [InlineKeyboardButton(text=f"{n+1}/{len_n}", callback_data="ignore")],
        [InlineKeyboardButton(text='<-', callback_data=f'orders {status} {n - 1}'),
         InlineKeyboardButton(text='Назад', callback_data=f'{back} start'),
         InlineKeyboardButton(text='->', callback_data=f'orders {status} {n + 1}')
         ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def stat_inline_n(n,status, len_n, back):
    kb = [
        [InlineKeyboardButton(text=f"Страница {n+1}/{len_n}", callback_data="ignore")],
        [InlineKeyboardButton(text='<-', callback_data=f'stat {status} {n - 1}'),
         InlineKeyboardButton(text='Назад', callback_data=f'{back} start'),
         InlineKeyboardButton(text='->', callback_data=f'stat {status} {n + 1}')
         ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def interval_inline(status, n,len_n):
    kb = [
        [InlineKeyboardButton(text=f'{n+1} / {len_n}', callback_data=f'fffff_s')],
        [
            InlineKeyboardButton(text='<-', callback_data=f'signals_{n-1} {status}_s'),
            InlineKeyboardButton(text='->', callback_data=f'signals_{n+1} {status}_s'),

        ],
        [
            InlineKeyboardButton(text='ТФ - 1Д', callback_data=f'signals_{n} {status}_1d 0'),
        InlineKeyboardButton(text='ТФ - 4h', callback_data=f'signals_{n} {status}_h 0'),
        InlineKeyboardButton(text='ТФ - 1h', callback_data=f'signals_{n} {status}_1h 0'),
        InlineKeyboardButton(text='ТФ - 30m', callback_data=f'signals_{n} {status}_30m 0')
        ],
        [InlineKeyboardButton(text='Назад', callback_data=f'signals start 0')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def stat_period_inline():
    kb = [
        [
            InlineKeyboardButton(text='За неделю', callback_data='stat period_week'),
            InlineKeyboardButton(text='За месяц', callback_data='stat period_month')
        ],
        [
            InlineKeyboardButton(text='За год', callback_data='stat period_year'),
            InlineKeyboardButton(text='За всё время', callback_data='stat period_all')
        ],
        [InlineKeyboardButton(text='Выбрать даты', callback_data='stat data')],
        [InlineKeyboardButton(text='Назад', callback_data='stat start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def cm_params_inline():
    kb = [
        [InlineKeyboardButton(text='SHORT_GAMMA', callback_data='cm SHORT_GAMMA')],
        [InlineKeyboardButton(text='LONG_GAMMA', callback_data='cm LONG_GAMMA')],
        [InlineKeyboardButton(text='LOOKBACK_T', callback_data='cm LOOKBACK_T')],
        [InlineKeyboardButton(text='LOOKBACK_B', callback_data='cm LOOKBACK_B')],
        [InlineKeyboardButton(text='PCTILE', callback_data='cm PCTILE')],
        [InlineKeyboardButton(text='Сбросить к стандартным', callback_data='cm reset')],
        [InlineKeyboardButton(text='Назад', callback_data='settings start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def divergence_params_inline():
    kb = [
        [InlineKeyboardButton(text='RSI_LENGTH', callback_data='divergence RSI_LENGTH')],
        [InlineKeyboardButton(text='LB_RIGHT', callback_data='divergence LB_RIGHT')],
        [InlineKeyboardButton(text='LB_LEFT', callback_data='divergence LB_LEFT')],
        [InlineKeyboardButton(text='RANGE_UPPER', callback_data='divergence RANGE_UPPER')],
        [InlineKeyboardButton(text='RANGE_LOWER', callback_data='divergence RANGE_LOWER')],
        [InlineKeyboardButton(text='TAKE_PROFIT_RSI_LEVEL', callback_data='divergence TAKE_PROFIT_RSI_LEVEL')],
        [InlineKeyboardButton(text='STOP_LOSS_TYPE', callback_data='divergence STOP_LOSS_TYPE')],
        [InlineKeyboardButton(text='STOP_LOSS_PERC', callback_data='divergence STOP_LOSS_PERC')],
        [InlineKeyboardButton(text='ATR_LENGTH', callback_data='divergence ATR_LENGTH')],
        [InlineKeyboardButton(text='ATR_MULTIPLIER', callback_data='divergence ATR_MULTIPLIER')],
        [InlineKeyboardButton(text='Сбросить к стандартным', callback_data='divergence reset')],
        [InlineKeyboardButton(text='Назад', callback_data='settings start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def rsi_params_inline():
    kb = [
        [InlineKeyboardButton(text='RSI_PERIOD', callback_data='rsi RSI_PERIOD')],
        [InlineKeyboardButton(text='RSI_OVERBOUGHT', callback_data='rsi RSI_OVERBOUGHT')],
        [InlineKeyboardButton(text='RSI_OVERSOLD', callback_data='rsi RSI_OVERSOLD')],
        [InlineKeyboardButton(text='EMA_FAST', callback_data='rsi EMA_FAST')],
        [InlineKeyboardButton(text='EMA_SLOW', callback_data='rsi EMA_SLOW')],
        [InlineKeyboardButton(text='Сбросить к стандартным', callback_data='rsi reset')],
        [InlineKeyboardButton(text='Назад', callback_data='settings start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def stop_loss_type_inline():
    kb = [
        [InlineKeyboardButton(text='PERC (процент)', callback_data='divergence_sl_type PERC')],
        [InlineKeyboardButton(text='ATR (на основе ATR)', callback_data='divergence_sl_type ATR')],
        [InlineKeyboardButton(text='NONE (без стоп-лосса)', callback_data='divergence_sl_type NONE')],
        [InlineKeyboardButton(text='Назад', callback_data='settings divergence')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def pump_dump_params_inline():
    kb = [
        [InlineKeyboardButton(text='VOLUME_THRESHOLD', callback_data='pump_dump VOLUME_THRESHOLD')],
        [InlineKeyboardButton(text='PRICE_CHANGE_THRESHOLD', callback_data='pump_dump PRICE_CHANGE_THRESHOLD')],
        [InlineKeyboardButton(text='TIME_WINDOW', callback_data='pump_dump TIME_WINDOW')],
        [InlineKeyboardButton(text='MONITOR_INTERVALS', callback_data='pump_dump MONITOR_INTERVALS')],
        [InlineKeyboardButton(text='ENABLED', callback_data='pump_dump ENABLED')],
        [InlineKeyboardButton(text='Сбросить к стандартным', callback_data='pump_dump reset')],
        [InlineKeyboardButton(text='Назад', callback_data='settings start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def pump_dump_subscription_inline():
    kb = [
        [InlineKeyboardButton(text='Подписаться на уведомления', callback_data='pump_dump subscribe')],
        [InlineKeyboardButton(text='Отписаться от уведомлений', callback_data='pump_dump unsubscribe')],
        [InlineKeyboardButton(text='Назад к настройкам', callback_data='settings pump_dump')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def leverage_inline():
    """
    Create a keyboard for selecting leverage values
    Support both callback formats: 'set_leverage:10' and 'set_leverage 10'
    """
    # Common leverage values for futures trading
    leverage_values = [1, 2, 3, 5, 10, 20, 50, 100]
    
    # Split buttons into rows of 4
    buttons = []
    current_row = []
    
    for value in leverage_values:
        # Using the colon format to match admin_commands.py
        current_row.append(InlineKeyboardButton(text=f"x{value}", callback_data=f"set_leverage:{value}"))
        
        if len(current_row) == 4:
            buttons.append(current_row)
            current_row = []
    
    # Add any remaining buttons
    if current_row:
        buttons.append(current_row)
    
    # Add back button
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="back_to_trading_settings")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def trading_type_settings_inline(user_id=None):
    """
    Create a keyboard for selecting multiple trading types (SPOT and/or FUTURES)
    Shows checkmarks for selected types
    """
    # Import here to avoid circular imports
    from user_settings import load_trading_types
    
    # Get current trading types for the user
    current_types = []
    if user_id:
        try:
            current_types = load_trading_types(user_id)
        except:
            current_types = ["spot"]
    
    # Create buttons with checkmarks for selected types
    spot_text = "✅ SPOT" if "spot" in current_types else "❌ SPOT"
    futures_text = "✅ FUTURES" if "futures" in current_types else "❌ FUTURES"
    
    kb = [
        [
            InlineKeyboardButton(text=spot_text, callback_data="toggle_trading_type:spot"),
            InlineKeyboardButton(text=futures_text, callback_data="toggle_trading_type:futures")
        ],
        [InlineKeyboardButton(text="Настроить плечо", callback_data="show_leverage_options")],
        [InlineKeyboardButton(text="« Назад к настройкам", callback_data="settings start")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def orders_pairs_inline(action, pairs=None):
    """Создает клавиатуру с фильтрацией по торговым парам для сделок"""
    kb = []
    
    # Заголовок
    if action == 'open':
        title = "📋 Выберите торговую пару (открытые сделки):"
    else:
        title = "📋 Выберите торговую пару (закрытые сделки):"
    
    if pairs:
        # Группируем кнопки пар по 2 в ряд
        pair_buttons = []
        for pair in pairs:
            if pair:  # Проверяем, что пара не пустая
                pair_buttons.append(InlineKeyboardButton(
                    text=f'💱 {pair}', 
                    callback_data=f'orders {action} pair {pair} 0'
                ))
                
                # Добавляем ряд каждые 2 кнопки
                if len(pair_buttons) == 2:
                    kb.append(pair_buttons)
                    pair_buttons = []
        
        # Добавляем оставшиеся кнопки
        if pair_buttons:
            kb.append(pair_buttons)
    
    # Кнопка "Все пары"
    kb.append([InlineKeyboardButton(text='📊 Все пары', callback_data=f'orders {action} all_pairs 0')])
    
    # Кнопка назад
    kb.append([InlineKeyboardButton(text='⬅️ Назад', callback_data='orders start')])
    
    return InlineKeyboardMarkup(inline_keyboard=kb)

def orders_pair_timeframes_inline(action, pair, timeframes=None):
    """Создает клавиатуру с фильтрацией по таймфреймам для конкретной торговой пары"""
    kb = []
    
    # Кнопка "Все таймфреймы для этой пары"
    kb.append([InlineKeyboardButton(text=f'📊 Все ТФ для {pair}', callback_data=f'orders {action} pair {pair} all 0')])
    
    if timeframes:
        # Импортируем функцию для сортировки
        from basic.handlers import interval_weight
        
        # Сортируем таймфреймы по важности (от большего к меньшему)
        sorted_timeframes = sorted([tf for tf in timeframes if tf], 
                                 key=lambda x: interval_weight(x), reverse=True)
        
        # Группируем кнопки таймфреймов по 2 в ряд
        timeframe_buttons = []
        for tf in sorted_timeframes:
            # Конвертируем таймфрейм для отображения
            from basic.handlers import interval_conv
            tf_display = interval_conv(tf)
            timeframe_buttons.append(InlineKeyboardButton(
                text=f'⏱️ {tf_display}', 
                callback_data=f'orders {action} pair {pair} {tf} 0'
            ))
            
            # Добавляем ряд каждые 2 кнопки
            if len(timeframe_buttons) == 2:
                kb.append(timeframe_buttons)
                timeframe_buttons = []
        
        # Добавляем оставшиеся кнопки
        if timeframe_buttons:
            kb.append(timeframe_buttons)
    
    # Кнопки навигации
    kb.append([
        InlineKeyboardButton(text='🔄 Все пары', callback_data=f'orders {action}'),
        InlineKeyboardButton(text='⬅️ Назад', callback_data=f'orders {action}')
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=kb)