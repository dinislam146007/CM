from aiogram import Bot, types
from aiogram import Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from strategy_logic.trading_settings import load_trading_settings, update_trading_settings

# Обработчики команд для настройки торговли

async def cmd_trading_settings(message: types.Message):
    """Показывает текущие настройки торговли и предлагает изменить их"""
    user_id = message.from_user.id
    settings = load_trading_settings(user_id)
    
    # Создаем сообщение с текущими настройками
    text = f"📊 <b>Настройки торговли</b>\n\n"
    text += f"🔹 Тип торговли: <b>{settings['trading_type'].upper()}</b>\n"
    text += f"🔹 Кредитное плечо: <b>x{settings['leverage']}</b>\n\n"
    text += "Выберите параметр для изменения:"
    
    # Создаем клавиатуру с кнопками для изменения настроек
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🔄 Изменить тип торговли", callback_data="change_trading_type"),
        InlineKeyboardButton("📈 Изменить кредитное плечо", callback_data="change_leverage")
    )
    
    await message.answer(text, reply_markup=keyboard)

async def process_callback_trading_type(callback_query: types.CallbackQuery):
    """Обрабатывает выбор типа торговли"""
    user_id = callback_query.from_user.id
    
    # Создаем клавиатуру для выбора типа торговли
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("SPOT", callback_data="set_trading_type:spot"),
        InlineKeyboardButton("FUTURES", callback_data="set_trading_type:futures")
    )
    
    await callback_query.message.edit_text(
        "Выберите тип торговли:\n\n"
        "SPOT - обычная спотовая торговля без плеча\n"
        "FUTURES - фьючерсная торговля с возможностью кредитного плеча и SHORT позиций",
        reply_markup=keyboard
    )
    
    await callback_query.answer()

async def process_callback_leverage(callback_query: types.CallbackQuery):
    """Обрабатывает выбор кредитного плеча"""
    user_id = callback_query.from_user.id
    settings = load_trading_settings(user_id)
    
    # Если выбран тип SPOT, информируем пользователя, что плечо недоступно
    if settings["trading_type"] == "spot":
        await callback_query.message.edit_text(
            "⚠️ Кредитное плечо доступно только для FUTURES торговли.\n\n"
            "Сначала измените тип торговли на FUTURES.",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("« Назад", callback_data="back_to_trading_settings")
            )
        )
        await callback_query.answer()
        return
    
    # Создаем клавиатуру для выбора кредитного плеча
    keyboard = InlineKeyboardMarkup(row_width=5)
    # Добавляем кнопки с разными значениями плеча
    leverage_options = [1, 2, 3, 5, 10, 20, 50, 100]
    buttons = [InlineKeyboardButton(f"x{lev}", callback_data=f"set_leverage:{lev}") for lev in leverage_options]
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton("« Назад", callback_data="back_to_trading_settings"))
    
    await callback_query.message.edit_text(
        f"Выберите кредитное плечо для FUTURES торговли:\n"
        f"Текущее плечо: x{settings['leverage']}\n\n"
        f"⚠️ Помните, что высокое плечо увеличивает как потенциальную прибыль, так и риск ликвидации.",
        reply_markup=keyboard
    )
    
    await callback_query.answer()

async def process_callback_set_trading_type(callback_query: types.CallbackQuery, trading_type: str):
    """Устанавливает выбранный тип торговли"""
    user_id = callback_query.from_user.id
    
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
        InlineKeyboardButton("🔄 Изменить тип торговли", callback_data="change_trading_type"),
        InlineKeyboardButton("📈 Изменить кредитное плечо", callback_data="change_leverage")
    )
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

async def process_callback_set_leverage(callback_query: types.CallbackQuery, leverage: int):
    """Устанавливает выбранное кредитное плечо"""
    user_id = callback_query.from_user.id
    
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
        InlineKeyboardButton("🔄 Изменить тип торговли", callback_data="change_trading_type"),
        InlineKeyboardButton("📈 Изменить кредитное плечо", callback_data="change_leverage")
    )
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

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
        InlineKeyboardButton("🔄 Изменить тип торговли", callback_data="change_trading_type"),
        InlineKeyboardButton("📈 Изменить кредитное плечо", callback_data="change_leverage")
    )
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

# Функция для регистрации обработчиков в диспетчере
def register_trading_settings_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_trading_settings, commands=["trading"])
    
    dp.register_callback_query_handler(process_callback_trading_type, 
                                     lambda c: c.data == "change_trading_type")
    
    dp.register_callback_query_handler(process_callback_leverage, 
                                     lambda c: c.data == "change_leverage")
    
    dp.register_callback_query_handler(lambda c: process_callback_set_trading_type(c, c.data.split(':')[1]), 
                                     lambda c: c.data.startswith("set_trading_type:"))
    
    dp.register_callback_query_handler(lambda c: process_callback_set_leverage(c, int(c.data.split(':')[1])), 
                                     lambda c: c.data.startswith("set_leverage:"))
    
    dp.register_callback_query_handler(process_callback_back_to_settings, 
                                     lambda c: c.data == "back_to_trading_settings") 