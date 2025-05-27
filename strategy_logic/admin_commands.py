from aiogram import Bot, types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from strategy_logic.trading_settings import load_trading_settings, update_trading_settings
from config import config
from strategy_logic.cm_notification_processor import test_send_notification

# Создаем роутер для обработчиков настроек торговли
trading_router = Router()

@trading_router.message(Command("trading"))
async def cmd_trading_settings(message: types.Message):
    """Показывает текущие настройки торговли и предлагает изменить их"""
    # Получаем user_id из message
    user_id = message.from_user.id
    await show_trading_settings(message, user_id)

@trading_router.message(Command("cm_test"))
async def cmd_cm_test(message: Message):
    """Test CM notification system"""
    # Check if the user is admin
    if message.from_user.id != config.admin_id:
        await message.answer("❌ This command is only available to admins.")
        return
    
    await message.answer("🧪 Starting CM notification system test...")
    
    # Run the test
    await test_send_notification()
    
    await message.answer("✅ CM notification test completed. Check logs for results.")

# Вспомогательная функция для отображения настроек
async def show_trading_settings(message: types.Message, user_id: int):
    """Отображает настройки торговли и клавиатуру для их изменения"""
    from user_settings import load_trading_types
    
    settings = load_trading_settings(user_id)
    trading_types = load_trading_types(user_id)
    
    # Создаем сообщение с текущими настройками
    text = f"📊 <b>Настройки торговли</b>\n\n"
    text += f"🔹 Активные типы торговли: <b>{', '.join([t.upper() for t in trading_types])}</b>\n"
    text += f"🔹 Кредитное плечо: <b>x{settings['leverage']}</b>\n\n"
    text += "Выберите параметр для изменения:"
    
    # Создаем клавиатуру с кнопками для изменения настроек
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Изменить типы торговли", callback_data="change_trading_type")],
        [InlineKeyboardButton(text="📈 Изменить кредитное плечо", callback_data="change_leverage")]
    ])
    
    await message.answer(text=text, reply_markup=keyboard)

@trading_router.callback_query(F.data == "change_trading_type")
async def process_callback_trading_type(callback_query: types.CallbackQuery):
    """Обрабатывает выбор типов торговли (множественный выбор)"""
    from user_settings import load_trading_types
    from keyboard.inline import trading_type_settings_inline
    
    user_id = callback_query.from_user.id
    
    # Получаем текущие типы торговли
    current_types = load_trading_types(user_id)
    
    # Формируем текст
    text = "📊 Настройки типов торговли\n\n"
    text += f"🔹 Активные типы: {', '.join([t.upper() for t in current_types])}\n\n"
    text += "Выберите типы торговли (можно выбрать несколько):\n\n"
    text += "SPOT - обычная спотовая торговля без плеча\n"
    text += "FUTURES - фьючерсная торговля с возможностью кредитного плеча и SHORT позиций"
    
    # Используем новую клавиатуру с множественным выбором
    keyboard = trading_type_settings_inline(user_id)
    
    await callback_query.message.edit_text(text=text, reply_markup=keyboard)
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
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="« Назад", callback_data="back_to_trading_settings")]
            ])
        )
        await callback_query.answer()
        return
    
    # Создаем клавиатуру для выбора кредитного плеча
    leverage_options = [1, 2, 3, 5, 10, 20, 50, 100]
    buttons = [InlineKeyboardButton(text=f"x{lev}", callback_data=f"set_leverage:{lev}") for lev in leverage_options]
    
    # Разбиваем кнопки на ряды по 5 кнопок
    keyboard_buttons = []
    for i in range(0, len(buttons), 4):
        keyboard_buttons.append(buttons[i:i+4])
    
    # Добавляем кнопку назад
    keyboard_buttons.append([InlineKeyboardButton(text="« Назад", callback_data="back_to_trading_settings")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback_query.message.edit_text(
        text=f"Выберите кредитное плечо для FUTURES торговли:\n"
        f"Текущее плечо: x{settings['leverage']}\n\n"
        f"⚠️ Помните, что высокое плечо увеличивает как потенциальную прибыль, так и риск ликвидации.",
        reply_markup=keyboard
    )
    
    await callback_query.answer()

@trading_router.callback_query(F.data.startswith("set_trading_type:"))
async def process_callback_set_trading_type(callback_query: types.CallbackQuery):
    """Устанавливает выбранный тип торговли (старый обработчик для совместимости)"""
    user_id = callback_query.from_user.id
    trading_type = callback_query.data.split(':')[1]
    
    # Обновляем настройки
    update_trading_settings({"trading_type": trading_type}, user_id)
    
    # Если тип торговли изменился на SPOT, сбрасываем плечо на 1
    if trading_type == "spot":
        update_trading_settings({"leverage": 1}, user_id)
    
    # Отображаем обновленные настройки
    settings = load_trading_settings(user_id)
    
    # Получаем множественные типы торговли
    from user_settings import load_trading_types
    current_types = load_trading_types(user_id)
    
    text = f"✅ Настройки обновлены!\n\n"
    text += f"🔹 Активные типы торговли: <b>{', '.join([t.upper() for t in current_types])}</b>\n"
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Изменить тип торговли", callback_data="change_trading_type")],
        [InlineKeyboardButton(text="📈 Изменить кредитное плечо", callback_data="change_leverage")]
    ])
    
    await callback_query.message.edit_text(text=text, reply_markup=keyboard)
    await callback_query.answer()

@trading_router.callback_query(F.data.startswith("toggle_trading_type:"))
async def process_callback_toggle_trading_type(callback_query: types.CallbackQuery):
    """Переключает тип торговли (добавляет/убирает из списка)"""
    from user_settings import toggle_trading_type, load_trading_types
    from keyboard.inline import trading_type_settings_inline
    
    user_id = callback_query.from_user.id
    trading_type = callback_query.data.split(':')[1]
    
    # Переключаем тип торговли
    success = await toggle_trading_type(user_id, trading_type)
    
    if not success:
        await callback_query.answer("❌ Нельзя убрать единственный тип торговли!", show_alert=True)
        return
    
    # Получаем обновленные типы торговли
    current_types = load_trading_types(user_id)
    
    # Формируем текст с обновленными настройками
    text = "📊 Настройки типов торговли\n\n"
    text += f"🔹 Активные типы: {', '.join([t.upper() for t in current_types])}\n\n"
    text += "Выберите типы торговли (можно выбрать несколько):\n\n"
    text += "SPOT - обычная спотовая торговля без плеча\n"
    text += "FUTURES - фьючерсная торговля с возможностью кредитного плеча и SHORT позиций"
    
    # Обновляем клавиатуру с новыми состояниями
    keyboard = trading_type_settings_inline(user_id)
    
    # Обновляем сообщение
    await callback_query.message.edit_text(text=text, reply_markup=keyboard)
    
    # Показываем уведомление
    if trading_type in current_types:
        await callback_query.answer(f"✅ {trading_type.upper()} добавлен")
    else:
        await callback_query.answer(f"❌ {trading_type.upper()} убран")

@trading_router.callback_query(F.data.startswith("set_leverage:"))
async def process_callback_set_leverage(callback_query: types.CallbackQuery):
    """Устанавливает выбранное кредитное плечо"""
    user_id = callback_query.from_user.id
    leverage = int(callback_query.data.split(':')[1])
    
    # Обновляем настройки
    update_trading_settings({"leverage": leverage}, user_id)
    
    # Отображаем обновленные настройки
    settings = load_trading_settings(user_id)
    
    # Получаем множественные типы торговли
    from user_settings import load_trading_types
    current_types = load_trading_types(user_id)
    
    text = f"✅ Настройки обновлены!\n\n"
    text += f"🔹 Активные типы торговли: <b>{', '.join([t.upper() for t in current_types])}</b>\n"
    text += f"🔹 Кредитное плечо: <b>x{settings['leverage']}</b>\n\n"
    
    if leverage > 1:
        text += f"⚠️ Обратите внимание:\n"
        text += f"- При плече x{leverage} ваша прибыль/убыток умножается на {leverage}\n"
        text += f"- Если убыток достигнет 100% от суммы депозита, позиция будет ликвидирована\n\n"
    
    text += "Выберите параметр для изменения:"
    
    # Создаем клавиатуру с кнопками для изменения настроек
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Изменить тип торговли", callback_data="change_trading_type")],
        [InlineKeyboardButton(text="📈 Изменить кредитное плечо", callback_data="change_leverage")]
    ])
    
    await callback_query.message.edit_text(text=text, reply_markup=keyboard)
    await callback_query.answer()

@trading_router.callback_query(F.data == "back_to_trading_settings")
async def process_callback_back_to_settings(callback_query: types.CallbackQuery):
    """Возвращает к главному меню настроек"""
    user_id = callback_query.from_user.id
    settings = load_trading_settings(user_id)
    
    # Создаем сообщение с текущими настройками
    # Получаем множественные типы торговли
    from user_settings import load_trading_types
    current_types = load_trading_types(user_id)
    
    text = f"📊 <b>Настройки торговли</b>\n\n"
    text += f"🔹 Активные типы торговли: <b>{', '.join([t.upper() for t in current_types])}</b>\n"
    text += f"🔹 Кредитное плечо: <b>x{settings['leverage']}</b>\n\n"
    text += "Выберите параметр для изменения:"
    
    # Создаем клавиатуру с кнопками для изменения настроек
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Изменить тип торговли", callback_data="change_trading_type")],
        [InlineKeyboardButton(text="📈 Изменить кредитное плечо", callback_data="change_leverage")]
    ])
    
    await callback_query.message.edit_text(text=text, reply_markup=keyboard)
    await callback_query.answer()

# Функция для регистрации обработчиков в диспетчере
def register_trading_settings_handlers(dp):
    dp.include_router(trading_router)
