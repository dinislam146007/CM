from aiogram.types import (
    KeyboardButton, 
    ReplyKeyboardMarkup, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardRemove
)

def cm_params_inline():
    keyboard = [
        [
            InlineKeyboardButton(text="SHORT_GAMMA", callback_data="cm SHORT_GAMMA"),
            InlineKeyboardButton(text="LONG_GAMMA", callback_data="cm LONG_GAMMA")
        ],
        [
            InlineKeyboardButton(text="LOOKBACK_T", callback_data="cm LOOKBACK_T"),
            InlineKeyboardButton(text="LOOKBACK_B", callback_data="cm LOOKBACK_B")
        ],
        [
            InlineKeyboardButton(text="PCTILE", callback_data="cm PCTILE")
        ],
        [
            InlineKeyboardButton(text="Сбросить настройки", callback_data="cm reset")
        ],
        [
            InlineKeyboardButton(text="CM Уведомления", callback_data="cm notifications")
        ],
        [
            InlineKeyboardButton(text="CM Уведомления в группе", callback_data="cm group_notifications")
        ],
        [
            InlineKeyboardButton(text="« Назад", callback_data="settings start")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard) 