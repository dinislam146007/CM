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

def stat_inline(profit, lesion):
    kb = [
        [
            InlineKeyboardButton(text=f'Прибыльные ({profit})', callback_data='stat profit 0'),
            InlineKeyboardButton(text=f'Убыточные ({lesion})', callback_data='stat lesion 0')
        ],
        [InlineKeyboardButton(text='Скачать таблицу со статистикой', callback_data='table stat')],
        [InlineKeyboardButton(text='Статистика за определенный период', callback_data='stat data')],
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
         [InlineKeyboardButton(text='Назад', callback_data='start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def settings_inline():
    kb = [
        [InlineKeyboardButton(text='Изменить процент', callback_data='settings percent')],
        [InlineKeyboardButton(text='Назад', callback_data='start')]
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
        [InlineKeyboardButton(text=f"{n+1}/{len_n}", callback_data="ignore")],
        [InlineKeyboardButton(text='<-', callback_data=f'stat {status} {n - 1}'),
         InlineKeyboardButton(text='Назад', callback_data=f'{back} start'),
         InlineKeyboardButton(text='->', callback_data=f'stat {status} {n + 1}')
         ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def stat_inline_n(n,status, len_n):
    kb = [
        [InlineKeyboardButton(text=f"{n+1}/{len_n}", callback_data="ignore")],
        [InlineKeyboardButton(text='<-', callback_data=f'stat {status} {n - 1}'),
         InlineKeyboardButton(text='Назад', callback_data='stat start'),
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