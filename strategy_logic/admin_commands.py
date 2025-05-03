from aiogram import Bot, types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from strategy_logic.trading_settings import load_trading_settings, update_trading_settings

# Создаем роутер для обработчиков настроек торговли
trading_router = Router()

@trading_router.message(Command("trading"))
async def cmd_trading_settings(message: types.Message):
    """Показывает текущие настройки торговли и предлагает изменить их"""
    # Получаем user_id из message
    user_id = message.from_user.id
    await show_trading_settings(message, user_id)

# Вспомогательная функция для отображения настроек
async def show_trading_settings(message: types.Message, user_id: int):
    """Отображает настройки торговли и клавиатуру для их изменения"""
    settings = load_trading_settings(user_id)
    
    # Создаем сообщение с текущими настройками
    text = f"📊 <b>Настройки торговли</b>\n\n"
    text += f"🔹 Тип торговли: <b>{settings['trading_type'].upper()}</b>\n"
    text += f"🔹 Кредитное плечо: <b>x{settings['leverage']}</b>\n\n"
    text += "Выберите параметр для изменения:"
    
    # Создаем клавиатуру с кнопками для изменения настроек
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="🔄 Изменить тип торговли", callback_data="change_trading_type"),
        InlineKeyboardButton(text="📈 Изменить кредитное плечо", callback_data="change_leverage")
    )
    
    await message.answer(text=text, reply_markup=keyboard)

@trading_router.callback_query(F.data == "change_trading_type")
async def process_callback_trading_type(callback_query: types.CallbackQuery):
    """Обрабатывает выбор типа торговли"""
    user_id = callback_query.from_user.id
    
    # Создаем клавиатуру для выбора типа торговли
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="SPOT", callback_data="set_trading_type:spot"),
        InlineKeyboardButton(text="FUTURES", callback_data="set_trading_type:futures")
    )
    
    await callback_query.message.edit_text(
        text="Выберите тип торговли:\n\n"
        "SPOT - обычная спотовая торговля без плеча\n"
        "FUTURES - фьючерсная торговля с возможностью кредитного плеча и SHORT позиций",
        reply_markup=keyboard
    )
    
    await callback_query.answer()

@trading_router.callback_query(F.data == "change_leverage")
async def process_callback_leverage(callback_query: types.CallbackQuery):
    """Обрабатывает выбор кредитного плеча"""
    user_id = callback_query.from_user.id
    settings = load_trading_settings(user_id)
    
    # Если выбран тип SPOT, информируем пользователя, что плечо недоступно
    if settings["trading_type"] == "spot":
        await callback_query.message.edit_text(
            text="⚠️ Кредитное плечо доступно только для FUTURES торговли.\n\n"
            "Сначала измените тип торговли на FUTURES.",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton(text="« Назад", callback_data="back_to_trading_settings")
            )
        )
        await callback_query.answer()
        return
    
    # Создаем клавиатуру для выбора кредитного плеча
    keyboard = InlineKeyboardMarkup(row_width=5)
    # Добавляем кнопки с разными значениями плеча
    leverage_options = [1, 2, 3, 5, 10, 20, 50, 100]
    buttons = [InlineKeyboardButton(text=f"x{lev}", callback_data=f"set_leverage:{lev}") for lev in leverage_options]
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton(text="« Назад", callback_data="back_to_trading_settings"))
    
    await callback_query.message.edit_text(
        text=f"Выберите кредитное плечо для FUTURES торговли:\n"
        f"Текущее плечо: x{settings['leverage']}\n\n"
        f"⚠️ Помните, что высокое плечо увеличивает как потенциальную прибыль, так и риск ликвидации.",
        reply_markup=keyboard
    )
    
    await callback_query.answer()

@trading_router.callback_query(F.data.startswith("set_trading_type:"))
async def process_callback_set_trading_type(callback_query: types.CallbackQuery):
    """Устанавливает выбранный тип торговли"""
    user_id = callback_query.from_user.id
    trading_type = callback_query.data.split(':')[1]
    
    # Обновляем настройки
    update_trading_settings({"trading_type": trading_type}, user_id)
    
    # Если тип торговли изменился на SPOT, сбрасываем плечо на 1
    if trading_type == "spot":
        update_trading_settings({"leverage": 1}, user_id)
    
    # Отображаем обновленные настройки
    settings = load_trading_settings(user_id)
    
    text = f"✅ Настройки обновлены!\n\n"
    text += f"🔹 Тип торговли: <b>{settings['trading_type'].upper()}</b>\n"
    text += f"🔹 Кредитное плечо: <b>x{settings['leverage']}</b>\n\n"
    
    if trading_type == "futures":
        text += "📊 Теперь вы можете:\n"
        text += "- Использовать кредитное плечо\n"
        text += "- Открывать SHORT позиции\n\n"
    else:
        text += "📊 Режим SPOT:\n"
        text += "- Без кредитного плеча\n"
        text += "- Только LONG позиции\n\n"
    
    text += "Выберите параметр для изменения:"
    
    # Создаем клавиатуру с кнопками для изменения настроек
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="🔄 Изменить тип торговли", callback_data="change_trading_type"),
        InlineKeyboardButton(text="📈 Изменить кредитное плечо", callback_data="change_leverage")
    )
    
    await callback_query.message.edit_text(text=text, reply_markup=keyboard)
    await callback_query.answer()

@trading_router.callback_query(F.data.startswith("set_leverage:"))
async def process_callback_set_leverage(callback_query: types.CallbackQuery):
    """Устанавливает выбранное кредитное плечо"""
    user_id = callback_query.from_user.id
    leverage = int(callback_query.data.split(':')[1])
    
    # Обновляем настройки
    update_trading_settings({"leverage": leverage}, user_id)
    
    # Отображаем обновленные настройки
    settings = load_trading_settings(user_id)
    
    text = f"✅ Настройки обновлены!\n\n"
    text += f"🔹 Тип торговли: <b>{settings['trading_type'].upper()}</b>\n"
    text += f"🔹 Кредитное плечо: <b>x{settings['leverage']}</b>\n\n"
    
    if leverage > 1:
        text += f"⚠️ Обратите внимание:\n"
        text += f"- При плече x{leverage} ваша прибыль/убыток умножается на {leverage}\n"
        text += f"- Если убыток достигнет 100% от суммы депозита, позиция будет ликвидирована\n\n"
    
    text += "Выберите параметр для изменения:"
    
    # Создаем клавиатуру с кнопками для изменения настроек
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="🔄 Изменить тип торговли", callback_data="change_trading_type"),
        InlineKeyboardButton(text="📈 Изменить кредитное плечо", callback_data="change_leverage")
    )
    
    await callback_query.message.edit_text(text=text, reply_markup=keyboard)
    await callback_query.answer()

@trading_router.callback_query(F.data == "back_to_trading_settings")
async def process_callback_back_to_settings(callback_query: types.CallbackQuery):
    """Возвращает к главному меню настроек"""
    user_id = callback_query.from_user.id
    settings = load_trading_settings(user_id)
    
    # Создаем сообщение с текущими настройками
    text = f"📊 <b>Настройки торговли</b>\n\n"
    text += f"🔹 Тип торговли: <b>{settings['trading_type'].upper()}</b>\n"
    text += f"🔹 Кредитное плечо: <b>x{settings['leverage']}</b>\n\n"
    text += "Выберите параметр для изменения:"
    
    # Создаем клавиатуру с кнопками для изменения настроек
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="🔄 Изменить тип торговли", callback_data="change_trading_type"),
        InlineKeyboardButton(text="📈 Изменить кредитное плечо", callback_data="change_leverage")
    )
    
    await callback_query.message.edit_text(text=text, reply_markup=keyboard)
    await callback_query.answer()

# Функция для регистрации обработчиков в диспетчере
