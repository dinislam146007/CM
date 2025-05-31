from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from keyboard.inline import *
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import FSInputFile
from db import *
from db.xls import *
from strategy_logic.get_all_coins import get_usdt_pairs
import datetime
import asyncio
import random

# Исправляем импорт datetime для корректного доступа к datetime.datetime
from datetime import datetime as dt

from basic.state import *
from config import config
from states import SubscriptionStates, EditDepositPercent, StatPeriodStates, StrategyParamStates, CMParamStates, DivergenceParamStates, RSIParamStates, PumpDumpParamStates
import re
from user_settings import get_user as get_user_db
from user_settings import set_user as set_user_db
from db.orders import ( 
                    get_all_orders,
                    set_user_balance
)
from db.db_select import (get_signal, 
                     get_statistics_for_period, all_signals, count_signals, 
                     get_daily_statistics, all_signals_no_signal, 
                     get_all_intervals_for_pairs_with_status, fetch_signals, fetch_stat,
                     get_signals)

# Replace old imports with new centralized user_settings module
from user_settings import (
    load_user_params, update_user_param, reset_user_params,
    load_cm_settings, reset_cm_settings, update_cm_setting,
    load_divergence_settings, reset_divergence_settings, update_divergence_setting,
    load_rsi_settings, reset_rsi_settings, update_rsi_setting,
    load_trading_settings, load_trading_type_settings, update_trading_type_setting, update_leverage_setting,
    load_pump_dump_settings, reset_pump_dump_settings, update_pump_dump_setting,
    add_subscriber, remove_subscriber, is_subscribed,
    get_user, set_user, update_user_setting,
    add_crypto_pair_to_db, delete_crypto_pair_from_db,
    add_monitor_pair_to_db, delete_monitor_pair_from_db,
    add_subscription, remove_subscription, get_user_subscriptions,
    migrate_user_settings,
    get_user_exchanges, update_user_exchanges, toggle_exchange
)

from strategy_logic.cm_settings import load_cm_settings, update_cm_setting
from strategy_logic.divergence_settings import load_divergence_settings, update_divergence_setting
from strategy_logic.rsi_settings import load_rsi_settings, update_rsi_setting
from strategy_logic.pump_dump_settings import load_pump_dump_settings, update_pump_dump_setting
from user_settings import reset_cm_settings, reset_divergence_settings, reset_rsi_settings, reset_pump_dump_settings
from user_settings import enable_cm_notifications, disable_cm_notifications, is_cm_notifications_enabled
from user_settings import enable_cm_group_notifications, disable_cm_group_notifications, is_cm_group_notifications_enabled

router = Router()


def interval_weight(interval):
    weights = {'1d': 4, '4h': 3, '1h': 2, '30m': 1}
    return weights.get(interval, 0)  # Возвращаем 0, если интервал неизвестен


def split_text_to_chunks(text, chunk_size=4096):
    chunks = []
    while text:
        if len(text) <= chunk_size:
            chunks.append(text)  # Если оставшийся текст меньше или равен chunk_size
            break
        # Попытка найти последнее разделение строки
        chunk = text[:chunk_size]
        if '\n' in chunk:
            chunk = chunk.rsplit('\n', 1)[0]
        chunks.append(chunk)
        text = text[len(chunk):]  # Оставшаяся часть текста
    return chunks


def interval_conv(interval):
    if interval == '1D':
        return '1Д'
    elif interval == '4H':
        return '4h'
    elif interval == '1H':
        return '1h'
    elif interval == '30':
        return '30m'
    
def buy_sale(status, interval):
    if status == 'buy':
        return f'🔰{interval} - B;'
    else:
        return f"🔻{interval} - S;"

def interval_conv(interval):
    if interval == '1D':
        return '1Д'
    elif interval == '4H':
        return '4h'
    elif interval == '1H':
        return '1h'
    elif interval == '30':
        return '30m'
    return interval

def interval_weight(interval):
    weights = {'1D': 4, '4H': 3, '1H': 2, '30': 1}
    return weights.get(interval, 0)

def buy_sale(status, interval):
    if status == 'buy':
        return f'🔰{interval} - B;'
    else:
        return f'🔻{interval} - S;'


async def format_monitor_signals(callback, user, mes=None):
    forms = await get_signals()
    monitor_pairs = user.get('monitor_pairs', '')  # Безопасно получаем значение, если его нет, используем пустую строку
    print(monitor_pairs)
    if not monitor_pairs:  # Если нет пар, возвращаем сообщение
        if mes is None:
            pass
            await callback.message.edit_text(
                text="У вас нет избранных пар для мониторинга.",
                reply_markup=monitor_inline()
            )

        return

    monitor_pairs = monitor_pairs.split(',')  # Разбиваем строку на список символов
    
    # Фильтруем сигналы по избранным парам
    filtered_signals = [form for form in forms if form['symbol'] in monitor_pairs]
    print(filtered_signals)
    # Группируем и сортируем сигналы
    grouped_signals = {}
    for form in filtered_signals:
        symbol = form['symbol']
        interval = form['interval']
        status = buy_sale(form['status'], interval_conv(interval))
        if symbol not in grouped_signals:
            grouped_signals[symbol] = []
        grouped_signals[symbol].append({'interval': interval, 'status': status})

    # Сортируем сигналы внутри каждой группы по убыванию интервалов
    for symbol in grouped_signals:
        grouped_signals[symbol].sort(key=lambda x: interval_weight(x['interval']), reverse=True)

    # Формируем сообщение
    msg_parts = []
    for symbol, signals in grouped_signals.items():
        msg_parts.append(f"{symbol} - {''.join(signal['status'] for signal in signals)}")
    
    if not msg_parts:  # Если отфильтрованных сигналов нет
        msg = "На ваших избранных парах нет активных сигналов."
    else:
        msg = "Сигналы на ваших избранных парах:\n\n" + "\n".join(msg_parts)
    
    # Отправляем сообщение
    if mes is None:
        await callback.message.edit_text(
            text=msg,
            reply_markup=monitor_inline()
        )
    else:
        await callback.answer(
            text=msg,
            reply_markup=monitor_inline()
        )

@router.callback_query(F.data.startswith('sub_remove'))
async def process_subscription_removal(callback: CallbackQuery):
    data = callback.data.split()[0].split('_')  # Например: "sub_remove_BTCUSDT_1D"
    symbol = data[2]
    interval = data[3]
    group = callback.data.split()[1]
    if group == 'True':
        user_id = config.trading_group_id
    else:
        user_id = callback.from_user.id

    await remove_subscription(user_id, symbol, interval)

    subscriptions = await get_user_subscriptions(user_id)

    if not subscriptions:
        kb = [
            [InlineKeyboardButton(text='Назад', callback_data='start')]
        ]
        await callback.message.edit_text("Вы не подписаны ни на одну пару.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # Формируем список списков кнопок
    buttons = []
    for sub in subscriptions:
        symbol = sub.get("symbol")  # Достаем по ключу
        interval = sub.get("interval")

        callback_data = f"sub_remove_{symbol}_{interval} {group}"
        button = InlineKeyboardButton(text=f"❌ {symbol} ({interval})", callback_data=callback_data)
        buttons.append([button])  # Каждая кнопка в отдельной строке

    buttons.append([InlineKeyboardButton(text='Назад', callback_data=f'sub start {group}')])
    # Создаём клавиатуру с переданными кнопками
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text("Выберите пару для удаления:", reply_markup=kb)

    # Отправляем сообщение с клавиатурой
    await callback.answer(f"Вы успешно отписались от {symbol} ({interval}).")

@router.message(lambda message: message.text and message.text.lower() == "id")
async def get_group_id_handler(message: Message):
    # Проверяем, что сообщение пришло из группы или супергруппы
    if message.chat.type in ["group", "supergroup"]:
        await message.reply(f"ID этой группы: `{message.chat.id}`", parse_mode="Markdown")
    else:
        await message.reply("Эта команда работает только в группе или супергруппе.")


@router.callback_query(F.data.startswith('sub'))
async def subscribe(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split()[1]
    if action == 'start':
        group = callback.data.split()[2]
        if group == 'True':
            user_id = config.trading_group_id
        else:
            user_id = callback.from_user.id
        subscriptions = await get_user_subscriptions(user_id)
        
        if not subscriptions:
            await callback.message.edit_text("Вы не подписаны ни на одну пару.", reply_markup=subscription_management_inline(group))
            return

        msg = "Вы подписаны на уведомления по следующим парам:\n\n"
        for sub in subscriptions:
            symbol = sub.get("symbol")  # Достаем по ключу
            interval = sub.get("interval")

            msg += f"🔹 {symbol} (ТФ - {interval_conv(interval)})\n"
        
        await callback.message.edit_text(
            text=msg,
            reply_markup=subscription_management_inline(group)
        )

    elif action == 'add':
        group = callback.data.split()[2]
        msg = await callback.message.edit_text("Введите название пары (например: BTCUSDT):", reply_markup=close_state())
        await state.set_state(SubscriptionStates.waiting_for_pair)
        await state.update_data(last_msg=msg.message_id, group=group)
    
    elif action == 'del':
        group = callback.data.split()[2]
        if group == 'True':
            user_id = config.trading_group_id
        else:
            user_id = callback.from_user.id

        
        subscriptions = await get_user_subscriptions(user_id)

        if not subscriptions:
            await callback.answer("Вы не подписаны ни на одну пару.")
            return

        # Формируем список списков кнопок
        buttons = []
        for sub in subscriptions:
            symbol = sub.get("symbol")  # Достаем по ключу
            interval = sub.get("interval")

            callback_data = f"sub_remove_{symbol}_{interval} {group}"
            button = InlineKeyboardButton(text=f"❌ {symbol} ({interval})", callback_data=callback_data)
            buttons.append([button])  # Каждая кнопка в отдельной строке

        buttons.append([InlineKeyboardButton(text='Назад', callback_data=f'sub start {group}')])
        # Создаём клавиатуру с переданными кнопками
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        # Отправляем сообщение с клавиатурой
        await callback.message.edit_text("Выберите пару для удаления:", reply_markup=kb)

@router.message(SubscriptionStates.waiting_for_pair)
async def process_pair_input(message: Message, state: FSMContext, bot: Bot):
    pair = message.text.strip().upper()
    data = await state.get_data()
    
    # Удаляем временное сообщение с запросом ввода
    try:
        await bot.delete_message(message_id=data['last_msg'], chat_id=message.from_user.id)
    except Exception:
        pass
    
    # Удаляем сообщение пользователя с введенной парой
    try:
        await bot.delete_message(message_id=message.message_id, chat_id=message.from_user.id)
    except Exception:
        pass
    
    if pair not in get_usdt_pairs():
        await message.answer("Такой пары нет в списке доступных. Попробуйте снова.")
        return

    await state.update_data(pair=pair)
    await message.answer(
        "Выберите таймфрейм:", 
        reply_markup=timeframe_inline()
    )
    await state.set_state(SubscriptionStates.waiting_for_timeframe)

@router.callback_query(SubscriptionStates.waiting_for_timeframe)
async def process_timeframe_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    timeframe = callback.data.split('_')[1]  # Например: "tf_1D"
    data = await state.get_data()
    await state.clear()
    if data['group'] == 'True':
        user_id = config.trading_group_id
    else:
        user_id = callback.from_user.id
    pair = data.get("pair")

    # Добавляем подписку в базу данных
    await add_subscription(user_id, pair, timeframe)
    signal = get_signal(pair, timeframe)
    await callback.message.delete()
    await callback.message.answer(f"Вы успешно подписались на уведомления по паре {pair} ТФ ({interval_conv(timeframe)}).")

    subscriptions = await get_user_subscriptions(user_id)
    if not subscriptions:
        await callback.message.edit_text("Вы не подписаны ни на одну пару.", reply_markup=subscription_management_inline(data['group']))
        return

    msg = "Вы подписаны на уведомления по следующим парам:\n\n"
    for sub in subscriptions:
        symbol = sub.get("symbol")  # Достаем по ключу
        interval = sub.get("interval")

        msg += f"🔹 {symbol} (ТФ - {interval_conv(interval)})\n"
    
    await callback.message.answer(
        text=msg,
        reply_markup=subscription_management_inline(data['group'])
    )
    await asyncio.sleep(10)
    if signal['symbol'] == 'DOGEUSDT':
        symbol = 'DOGEUSDT 🐕'
    else:
        symbol = signal['symbol']

    if signal['status'] == 'buy':
        message = f"Новый сигнал:\nИнструмент: {symbol}\nИнтервал: {interval_conv(signal['interval'])}\nСигнал: Long 🔰"
    else:
        message = f"Новый сигнал:\nИнструмент: {symbol}\nИнтервал: {interval_conv(signal['interval'])}\nСигнал: Short 🔻"

    await bot.send_message(chat_id=user_id, text=message)




@router.callback_query(F.data.startswith('like'))
async def like_symbol(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split()[1]
    user = await get_user(callback.from_user.id)
    if action == 'start':
        msg = 'Раздел избранные пары\n\n'
        if user['crypto_pairs']:
            pairs = user['crypto_pairs'].split(',')
            msg += f"Ваш список избранных пар:\n\n"
            for pair in pairs:
                msg += f"🔹 {pair}\n"
        else:
            msg += 'Список избранных пар пока пуст'
        await callback.message.edit_text(
            text=msg,
            reply_markup=like_inline()
        )
    elif action == 'add':
        msg = 'Введите одну пару или несколько пар через запятую\n\nПример: BTCUSDT,EGLDUSDT,XDCUSDT'
        await state.set_state(CryptoPairs.pairs)
        msg = await callback.message.edit_text(
            text=msg,
            reply_markup=close_state()
        )
        await state.update_data(action=action, last_msg=msg.message_id, call='like')

    elif action == 'del':
        await callback.message.edit_text(
            text='Введите пару для удаления',
            reply_markup=like_del_inline(user)
        )
    elif action == 'delete':
        pair_to_delete = callback.data.split()[2]
        user = await get_user(callback.from_user.id)
        
        # Удаляем пару из базы данных
        await delete_crypto_pair_from_db(callback.from_user.id, pair_to_delete)
        
        # Отправляем сообщение о том, что пара была удалена
        await callback.answer(f"Пара {pair_to_delete} была удалена из вашего списка избранных.")
        
        # Обновляем список избранных пар и показываем новую клавиатуру
        user = await get_user(callback.from_user.id)  # Обновляем данные пользователя после удаления
        await callback.message.edit_text(
            text='Введите пару для удаления',
            reply_markup=like_del_inline(user)
        )



@router.message(CryptoPairs.pairs)
async def add_del_pairs(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    
    # Удаляем временное сообщение с запросом ввода
    try:
        await bot.delete_message(message_id=data['last_msg'], chat_id=message.from_user.id)
    except Exception:
        pass
    
    # Удаляем сообщение пользователя с введенными парами
    try:
        await bot.delete_message(message_id=message.message_id, chat_id=message.from_user.id)
    except Exception:
        pass
    
    valid_pairs = get_usdt_pairs()

    # Получаем список пар из сообщения
    user_input = message.text
    pairs = [pair.strip().upper() for pair in user_input.split(',')]  # Разделяем, очищаем и приводим к верхнему регистру

    # Проверяем, что пользователь ввёл корректные пары
    invalid_pairs = [pair for pair in pairs if pair not in valid_pairs]
    if invalid_pairs:
        await message.answer(f"Некорректные пары: {', '.join(invalid_pairs)}.\n\nВведите корректные пары.")
        return

    if not pairs or any(not pair for pair in pairs):
        await message.answer("Некорректный ввод. Введите пары через запятую, например: BTCUSDT,ETHUSDT")
        return
    
    if data['action'] == 'add':
        if data['call'] == 'like':
            for pair in pairs:
                await add_crypto_pair_to_db(message.from_user.id, pair)  # Функция добавления пары в базу
        else:
            for pair in pairs:
                await add_monitor_pair_to_db(message.from_user.id, pair)  # Функция добавления пары в базу

        await message.answer(f"Добавлены пары: {', '.join(pairs)}")
    else:
        if data['call'] == 'like':
            for pair in pairs:
                await delete_crypto_pair_from_db(message.from_user.id, pair)  # Функция удаления пары из базы
        else:
            for pair in pairs:
                await delete_monitor_pair_from_db(message.from_user.id, pair)  # Функция удаления пары из базы
       
        await message.answer(f"Удалены пары: {', '.join(pairs)}")

    user = await get_user(message.from_user.id)
    if data['call'] == 'like':
        msg = 'Раздел избранные пары\n\n'
        if user['crypto_pairs']:
            pairs = user['crypto_pairs'].split(',')
            msg += f"Ваш список избранных пар:\n\n"
            for pair in pairs:
                msg += f"🔹 {pair}\n"
        else:
            msg += 'Список избранных пар пока пуст'
        reply_markup=like_inline()
        await message.answer(
        text=msg,
        reply_markup=reply_markup
    )

    else:
        await format_monitor_signals(message, user, True)

    await state.clear()

@router.callback_query(F.data == 'stat data')
async def stat_period_start(callback: CallbackQuery, state: FSMContext):
    kb = [
        [InlineKeyboardButton(text='Отмена', callback_data='stat start')]
    ]
    msg = await callback.message.edit_text("Введите начальную дату в формате ДД-ММ-ГГГГ:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(StatPeriodStates.waiting_for_start_date)
    await state.update_data(last_msg=msg.message_id)


@router.message(StatPeriodStates.waiting_for_start_date)
async def process_start_date(message: Message, state: FSMContext, bot: Bot):
    start_date = message.text
    data = await state.get_data()
    
    # Удаляем временное сообщение с запросом ввода
    try:
        await bot.delete_message(chat_id=message.from_user.id, message_id=data['last_msg'])
    except Exception:
        pass
    
    # Удаляем сообщение пользователя с введенной датой
    try:
        await bot.delete_message(chat_id=message.from_user.id, message_id=message.message_id)
    except Exception:
        pass
    
    try:
        # Проверяем правильность формата даты
        new = dt.strptime(start_date, '%d-%m-%Y')
    except ValueError:
        kb = [
        [InlineKeyboardButton(text='Отмена', callback_data='stat start')]
    ]

        await message.answer("Неверный формат даты. Введите дату в формате ДД-ММ-ГГГГ.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    await state.update_data(start_date=start_date)
    kb = [
        [InlineKeyboardButton(text='Отмена', callback_data='stat start')]
    ]

    msg = await message.answer("Введите конечную дату в формате ДД-ММ-ГГГГ:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(StatPeriodStates.waiting_for_end_date)
    await state.update_data(last_msg=msg.message_id)


def plural_form(number, forms):
    """
    Возвращает правильную форму слова в зависимости от числа.
    :param number: Число
    :param forms: Список из трёх форм слова: ['1 сделка', '2 сделки', '5 сделок']
    :return: Строка с правильной формой слова
    """
    number = abs(number) % 100
    if 11 <= number <= 19:
        return forms[2]
    number = number % 10
    if number == 1:
        return forms[0]
    if 2 <= number <= 4:
        return forms[1]
    return forms[2]

@router.message(StatPeriodStates.waiting_for_end_date)
async def process_end_date(message: Message, state: FSMContext, bot: Bot):
    end_date = message.text.strip()  # Убираем лишние пробелы
    data = await state.get_data()
    user_id = message.from_user.id
    
    # Удаляем временное сообщение с запросом ввода
    try:
        await bot.delete_message(chat_id=user_id, message_id=data['last_msg'])
    except Exception:
        pass
    
    # Удаляем сообщение пользователя с введенной датой
    try:
        await bot.delete_message(chat_id=user_id, message_id=message.message_id)
    except Exception:
        pass

    try:
        # Проверяем формат даты
        parsed_date = dt.strptime(end_date, '%d-%m-%Y')
    except ValueError:
        kb = [[InlineKeyboardButton(text='Отмена', callback_data='stat start')]]
        await message.answer("Неверный формат даты. Введите дату в формате ДД-ММ-ГГГГ.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # Получаем начальную дату из состояния
    start_date = data.get("start_date")
    if not start_date:
        kb = [[InlineKeyboardButton(text='Отмена', callback_data='stat start')]]
        await message.answer("Не найдена начальная дата. Попробуйте заново.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    try:
        # Проверяем начальную дату
        parsed_start_date = dt.strptime(start_date, '%d-%m-%Y')
        if parsed_start_date > parsed_date:
            await message.answer("Начальная дата не может быть позже конечной. Попробуйте заново.")
            return
    except ValueError:
        kb = [[InlineKeyboardButton(text='Отмена', callback_data='stat start')]]
        await message.answer("Неверный формат начальной даты. Введите дату в формате ДД-ММ-ГГГГ.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # Сохраняем конечную дату и продолжаем
    await state.update_data(end_date=end_date)

    # Преобразуем даты в строки для передачи в функцию
    start_date_str = parsed_start_date.strftime('%Y-%m-%d')  # Формат YYYY-MM-DD
    end_date_str = parsed_date.strftime('%Y-%m-%d')          # Формат YYYY-MM-DD

    # Вызываем функцию для получения статистики
    total_trades, profitable_trades, loss_trades, total_profit = await get_statistics_for_period(
        user_id, start_date_str, end_date_str
    )

    msg = (
            "📊 Сделки, совершенные ботом за указанный период:\n\n"
            f"♻️ Общее количество сделок: {total_trades}\n\n"
            f"📗 В прибыль: {profitable_trades} {plural_form(profitable_trades, ['сделка', 'сделки', 'сделок'])} (Подробнее)\n"
            f"📕 В убыток: {loss_trades} {plural_form(loss_trades, ['сделка', 'сделки', 'сделок'])} (Подробнее)\n\n"
            f"Чистый профит: {total_profit:.2f}$ 💰🔋"
        )
    await message.answer(msg)
    await state.clear()

@router.callback_query(F.data.startswith('stat'))
async def statistics(callback: CallbackQuery, state: FSMContext):
    # Parse callback data
    data = callback.data.split()
    action = data[1] if len(data) > 1 else 'start'
    page = int(data[2]) if len(data) > 2 and data[2].isdigit() else 0
    
    if action == 'start':
        # Get daily statistics with corrected profit calculation
        total_trades, profitable_trades, loss_trades, total_profit = await get_daily_statistics(callback.from_user.id)
        
        if total_profit > 0:
            profit_text = f"Чистый профит: {round(total_profit, 2)}$ 💰🔋"
        else:
            profit_text = f"Чистый профит: {round(total_profit, 2)}$ 💰🔋"
        
        message = f"📊 Сделки, совершенные ботом за текущий день:\n\n" \
                 f"♻️ Общее количество сделок: {total_trades}\n\n" \
                 f"📗 В прибыль: {profitable_trades} {plural_form(profitable_trades, ['сделка', 'сделки', 'сделок'])}\n" \
                 f"📕 В убыток: {loss_trades} {plural_form(loss_trades, ['сделка', 'сделки', 'сделок'])}\n\n" \
                 f"{profit_text}"
        
        await callback.message.edit_text(text=message, reply_markup=stat_inline(profitable_trades, loss_trades), parse_mode='HTML')
    
    elif action == 'all':
        # Pagination for all closed orders
        closed_orders = await get_all_orders(callback.from_user.id, 'close')
        if not closed_orders:
            await callback.message.edit_text(
                text="У вас пока нет закрытых сделок.",
                reply_markup=stat_inline()
            )
            return
        
        # Пагинация для отображения по одной сделке
        if page < 0:
            page = 0
        if page >= len(closed_orders):
            page = len(closed_orders) - 1
            
        order = closed_orders[page]
        
        # Получаем данные о сделке
        buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
        sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
        
        # Форматируем время
        time_str = ""
        if isinstance(order.get('sale_time'), str):
            time_str = order['sale_time']
        elif order.get('sale_time') is not None:
            time_str = order['sale_time'].strftime('%d-%m-%Y %H:%M')
        else:
            time_str = "Время не указано"
            
        buy_time_str = ""
        if isinstance(order.get('buy_time'), str):
            buy_time_str = order['buy_time']
        elif order.get('buy_time') is not None:
            buy_time_str = order['buy_time'].strftime('%d-%m-%Y %H:%M')
        else:
            buy_time_str = "Время не указано"
            
        # Расчет прибыли/убытка
        invest_amount = order.get('investment_amount_usdt', 0)
        pnl = order.get('pnl_usdt', sale_price - buy_price)
        is_profit = pnl > 0
        
        # Информация о торговле
        trading_type = order.get('trading_type', 'spot').upper()
        leverage = order.get('leverage', 1)
        exchange = order.get('exchange', 'Неизвестно')
        
        # Формируем сообщение по запрошенному шаблону
        message = f"<b>Инструмент:</b> {order['symbol']} | {interval_conv(order['interval'])}\n\n"
        message += f"<b>Цена открытия:</b> {round(buy_price, 8)}$ 📈\n"
        message += f"<b>Цена закрытия:</b> {round(sale_price, 8)}$ 📈\n"
        
        if is_profit:
            message += f"<b>Прибыль:</b> {abs(round(pnl, 2))}$💸🔋\n\n"
        else:
            message += f"<b>Убыток:</b> {abs(round(pnl, 2))}$🤕🪫\n\n"
            
        message += f"<b>Объем сделки:</b> {round(invest_amount, 2)}$ 💵\n\n"
        message += f"<b>Биржа:</b> {exchange}\n"
        message += f"<b>Тип торговли:</b> {trading_type}"
        
        if trading_type == 'FUTURES':
            message += f" (плечо: x{leverage})\n\n"
        else:
            message += "\n\n"
        
        message += f"<b>Дата и время закрытия:</b>\n⏱️{time_str}\n\n"
        message += f"<b>Сделка была открыта:</b>\n⏱️{buy_time_str}\n"
        
        # Create navigation buttons
        keyboard = []
        if len(closed_orders) > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton(text='◀️', callback_data=f'stat all {page-1}'))
            row.append(InlineKeyboardButton(text=f'{page+1}/{len(closed_orders)}', callback_data='none'))
            if page < len(closed_orders) - 1:
                row.append(InlineKeyboardButton(text='▶️', callback_data=f'stat all {page+1}'))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(text='Назад к статистике', callback_data='stat start')])
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(text=message, reply_markup=markup, parse_mode='HTML')
    
    elif action == 'period':
        await callback.message.edit_text(
            text="Выберите период для просмотра статистики:",
            reply_markup=stat_period_inline()
        )
    
    elif action.startswith('period_'):
        period_type = action.split('_')[1]
        
        # Calculate start date based on period type
        today = dt.now()
        if period_type == 'week':
            start_date = (today - datetime.timedelta(days=7)).timestamp()
            period_text = "за неделю"
        elif period_type == 'month':
            start_date = (today - datetime.timedelta(days=30)).timestamp()
            period_text = "за месяц"
        elif period_type == 'year':
            start_date = (today - datetime.timedelta(days=365)).timestamp()
            period_text = "за год"
        else:  # all time
            start_date = 0
            period_text = "за все время"
        
        # Get closed orders for the period
        closed_orders = await get_all_orders(callback.from_user.id, 'close', from_date=start_date)
        
        if not closed_orders:
            await callback.message.edit_text(
                text=f"У вас нет закрытых сделок {period_text}.",
                reply_markup=stat_period_inline()
            )
            return
        
        # Calculate statistics
        total_trades = len(closed_orders)
        profitable_trades = 0
        loss_trades = 0
        total_profit = 0
        
        for order in closed_orders:
            buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
            sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
            invest_amount = order.get('invest_amount', order.get('investment_amount_usdt', 0))
            
            if buy_price and sale_price:
                profit_percent = ((sale_price - buy_price) / buy_price) * 100
                profit_amount = invest_amount * (profit_percent / 100)
                total_profit += profit_amount
                
                if profit_percent > 0:
                    profitable_trades += 1
                else:
                    loss_trades += 1
        
        # Format profit/loss text
        if total_profit > 0:
            profit_text = f"Чистый профит: {round(total_profit, 2)}$ 💰🔋"
        else:
            profit_text = f"Чистый профит: {round(total_profit, 2)}$ 💰🔋"
        
        message = f"📊 Сделки, совершенные ботом {period_text}:\n\n" \
                 f"♻️ Общее количество сделок: {total_trades}\n\n" \
                 f"📗 В прибыль: {profitable_trades} {plural_form(profitable_trades, ['сделка', 'сделки', 'сделок'])}\n" \
                 f"📕 В убыток: {loss_trades} {plural_form(loss_trades, ['сделка', 'сделки', 'сделок'])}\n\n" \
                 f"{profit_text}"
        
        keyboard = [
            [InlineKeyboardButton(text='Просмотреть сделки за этот период', callback_data=f'stat period_view_{period_type} 0')],
            [InlineKeyboardButton(text='Назад', callback_data='stat period')]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(text=message, reply_markup=markup, parse_mode='HTML')
    
    elif action.startswith('period_view_'):
        period_type = action.split('_')[2]
        
        # Calculate start date based on period type
        today = dt.now()
        if period_type == 'week':
            start_date = (today - datetime.timedelta(days=7)).timestamp()
        elif period_type == 'month':
            start_date = (today - datetime.timedelta(days=30)).timestamp()
        elif period_type == 'year':
            start_date = (today - datetime.timedelta(days=365)).timestamp()
        else:  # all time
            start_date = 0
        
        # Get closed orders for the period
        closed_orders = await get_all_orders(callback.from_user.id, 'close', from_date=start_date)
        
        if not closed_orders:
            await callback.message.edit_text(
                text=f"У вас нет закрытых сделок за выбранный период.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Назад', callback_data=f'stat period_{period_type}')]])
            )
            return

        # Пагинация для отображения по одной сделке
        if page < 0:
            page = 0
        if page >= len(closed_orders):
            page = len(closed_orders) - 1
            
        order = closed_orders[page]
        
        # Получаем данные о сделке
        buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
        sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
        
        # Форматируем время
        time_str = ""
        if isinstance(order.get('sale_time'), str):
            time_str = order['sale_time']
        elif order.get('sale_time') is not None:
            time_str = order['sale_time'].strftime('%d-%m-%Y %H:%M')
        else:
            time_str = "Время не указано"
            
        buy_time_str = ""
        if isinstance(order.get('buy_time'), str):
            buy_time_str = order['buy_time']
        elif order.get('buy_time') is not None:
            buy_time_str = order['buy_time'].strftime('%d-%m-%Y %H:%M')
        else:
            buy_time_str = "Время не указано"
            
        # Расчет прибыли/убытка
        invest_amount = order.get('investment_amount_usdt', 0)
        pnl = order.get('pnl_usdt', sale_price - buy_price)
        is_profit = pnl > 0
        
        # Информация о торговле
        trading_type = order.get('trading_type', 'spot').upper()
        leverage = order.get('leverage', 1)
        exchange = order.get('exchange', 'Неизвестно')
        
        # Формируем сообщение по запрошенному шаблону
        message = f"<b>Инструмент:</b> {order['symbol']} | {interval_conv(order['interval'])}\n\n"
        message += f"<b>Цена открытия:</b> {round(buy_price, 8)}$ 📈\n"
        message += f"<b>Цена закрытия:</b> {round(sale_price, 8)}$ 📈\n"
        
        if is_profit:
            message += f"<b>Прибыль:</b> {abs(round(pnl, 2))}$💸🔋\n\n"
        else:
            message += f"<b>Убыток:</b> {abs(round(pnl, 2))}$🤕🪫\n\n"
            
        message += f"<b>Объем сделки:</b> {round(invest_amount, 2)}$ 💵\n\n"
        message += f"<b>Биржа:</b> {exchange}\n"
        message += f"<b>Тип торговли:</b> {trading_type}"
        
        if trading_type == 'FUTURES':
            message += f" (плечо: x{leverage})\n\n"
        else:
            message += "\n\n"
        
        message += f"<b>Дата и время закрытия:</b>\n⏱️{time_str}\n\n"
        message += f"<b>Сделка была открыта:</b>\n⏱️{buy_time_str}\n"
        
        # Create navigation keyboard with back button to period stats
        keyboard = []
        if len(closed_orders) > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton(text='◀️', callback_data=f'stat period_view_{period_type} {page-1}'))
            row.append(InlineKeyboardButton(text=f'{page+1}/{len(closed_orders)}', callback_data='none'))
            if page < len(closed_orders) - 1:
                row.append(InlineKeyboardButton(text='▶️', callback_data=f'stat period_view_{period_type} {page+1}'))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(text='Назад к статистике', callback_data=f'stat period_{period_type}')])
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(text=message, reply_markup=markup, parse_mode='HTML')
    
    elif action == 'profit_list' or action == 'loss_list':
        # Получаем все закрытые ордера
        closed_orders = await get_all_orders(callback.from_user.id, 'close')
        
        # Фильтруем по прибыльным или убыточным
        if action == 'profit_list':
            filtered_orders = []
            for order in closed_orders:
                buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
                sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
                if sale_price > buy_price:
                    filtered_orders.append(order)
            title = "прибыльных"
        else:  # loss_list
            filtered_orders = []
            for order in closed_orders:
                buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
                sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
                if sale_price < buy_price:
                    filtered_orders.append(order)
            title = "убыточных"
        
        if not filtered_orders:
            await callback.message.edit_text(
                text=f"У вас нет {title} сделок.",
                reply_markup=stat_inline()
            )
            return
        
        # Пагинация для отображения по одной сделке
        if page < 0:
            page = 0
        if page >= len(filtered_orders):
            page = len(filtered_orders) - 1
            
        order = filtered_orders[page]
        
        # Получаем данные о сделке
        buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
        sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
        
        # Форматируем время
        time_str = ""
        if isinstance(order.get('sale_time'), str):
            time_str = order['sale_time']
        elif order.get('sale_time') is not None:
            time_str = order['sale_time'].strftime('%d-%m-%Y %H:%M')
        else:
            time_str = "Время не указано"
            
        buy_time_str = ""
        if isinstance(order.get('buy_time'), str):
            buy_time_str = order['buy_time']
        elif order.get('buy_time') is not None:
            buy_time_str = order['buy_time'].strftime('%d-%m-%Y %H:%M')
        else:
            buy_time_str = "Время не указано"
            
        # Расчет прибыли/убытка
        invest_amount = order.get('investment_amount_usdt', 0)
        pnl = order.get('pnl_usdt', sale_price - buy_price)
        is_profit = pnl > 0
        
        # Информация о торговле
        trading_type = order.get('trading_type', 'spot').upper()
        leverage = order.get('leverage', 1)
        exchange = order.get('exchange', 'Неизвестно')
        
        # Формируем сообщение по запрошенному шаблону
        message = f"<b>Инструмент:</b> {order['symbol']} | {interval_conv(order['interval'])}\n\n"
        message += f"<b>Цена открытия:</b> {round(buy_price, 8)}$ 📈\n"
        message += f"<b>Цена закрытия:</b> {round(sale_price, 8)}$ 📈\n"
        
        if is_profit:
            message += f"<b>Прибыль:</b> {abs(round(pnl, 2))}$💸🔋\n\n"
        else:
            message += f"<b>Убыток:</b> {abs(round(pnl, 2))}$🤕🪫\n\n"
            
        message += f"<b>Объем сделки:</b> {round(invest_amount, 2)}$ 💵\n\n"
        message += f"<b>Биржа:</b> {exchange}\n"
        message += f"<b>Тип торговли:</b> {trading_type}"
        
        if trading_type == 'FUTURES':
            message += f" (плечо: x{leverage})\n\n"
        else:
            message += "\n\n"
        
        message += f"<b>Дата и время закрытия:</b>\n⏱️{time_str}\n\n"
        message += f"<b>Сделка была открыта:</b>\n⏱️{buy_time_str}\n"
        
        # Create navigation buttons
        keyboard = []
        if len(filtered_orders) > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton(text='◀️', callback_data=f'stat {action} {page-1}'))
            row.append(InlineKeyboardButton(text=f'{page+1}/{len(filtered_orders)}', callback_data='none'))
            if page < len(filtered_orders) - 1:
                row.append(InlineKeyboardButton(text='▶️', callback_data=f'stat {action} {page+1}'))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(text='Назад к статистике', callback_data='stat start')])
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(text=message, reply_markup=markup, parse_mode='HTML')
    
    else:
        await callback.message.edit_text(
            text="Неизвестная команда. Возврат к главному меню статистики.",
            reply_markup=stat_inline(0, 0)
        )

@router.message(Command("start"))
async def start_message(message: Message, bot: Bot):
    # Run migration at first start - don't await since it's not async
    from db.orders import migrate_strategy_fields
    try:
        await migrate_strategy_fields()
    except Exception as e:
        print(f"Ошибка при миграции полей стратегий: {e}")
    
    # Остальная логика старта
    user_id = message.from_user.id
    
    if not await get_user_db(message.from_user.id):
        await set_user_db(message.from_user.id, 5.0, 50000.0)
        await reset_user_params(message.from_user.id)
    user = await get_user_db(message.from_user.id)
    
    # Форматируем баланс с разделителями тысяч для лучшей читаемости
    formatted_balance = "{:,}".format(round(user['balance'])).replace(',', ' ')
    
    welcome_message = (
        "🚀 <b>Moon Bot | CM_Laguerre PPO</b> 🚀\n\n"
        "🤖 Ваш умный торговый бот на базе индикатора\n"
        "📊 <i>PercentileRank Mkt Tops & Bottoms</i>\n\n"
        f"💰 <b>Ваш баланс:</b> <code>{formatted_balance}$</code> 💸\n"
        "🔄 Автоматическая торговля SPOT и FUTURES\n"
        "📈 Поддержка Long и Short позиций\n"
    )
    
    await message.answer(
        welcome_message,
        reply_markup=start_inline(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == 'close_state')
async def close_state_cal(callback: CallbackQuery, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    
    user = await get_user_db(callback.from_user.id)
    formatted_balance = "{:,}".format(round(user['balance'])).replace(',', ' ')
    
    welcome_message = (
        "🚀 <b>Moon Bot | CM_Laguerre PPO</b> 🚀\n\n"
        "🤖 Ваш умный торговый бот на базе индикатора\n"
        "📊 <i>PercentileRank Mkt Tops & Bottoms</i>\n\n"
        f"💰 <b>Ваш баланс:</b> <code>{formatted_balance}$</code> 💸\n"
        "🔄 Автоматическая торговля SPOT и FUTURES\n"
        "📈 Поддержка Long и Short позиций\n"
    )
    
    await callback.message.edit_text(
        welcome_message,
        reply_markup=start_inline(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == 'start')
async def start_cal(callback: CallbackQuery, state: FSMContext):
    user = await get_user_db(callback.from_user.id)
    
    # Форматируем баланс с разделителями тысяч для лучшей читаемости
    formatted_balance = "{:,}".format(round(user['balance'])).replace(',', ' ')
    
    welcome_message = (
        "🚀 <b>Moon Bot | CM_Laguerre PPO</b> 🚀\n\n"
        "🤖 Ваш умный торговый бот на базе индикатора\n"
        "📊 <i>PercentileRank Mkt Tops & Bottoms</i>\n\n"
        f"💰 <b>Ваш баланс:</b> <code>{formatted_balance}$</code> 💸\n"
        "🔄 Автоматическая торговля SPOT и FUTURES\n"
        "📈 Поддержка Long и Short позиций\n"
    )
    
    await callback.message.edit_text(
        welcome_message,
        reply_markup=start_inline(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith('orders'))
async def orders(callback: CallbackQuery, bot: Bot):
    action = callback.data.split()[1]
    if action == 'start':
        open = len(await get_all_orders(callback.from_user.id, 'open'))
        close = len(await get_all_orders(callback.from_user.id, 'close'))
        await callback.message.edit_text(
            text='Ваши сделки', 
            reply_markup=orders_inline(open, close)
        )
    elif action == 'all':
        # Get all orders for the user
        open_forms = await get_all_orders(callback.from_user.id, 'open')
        close_forms = await get_all_orders(callback.from_user.id, 'close')
        all_forms = open_forms + close_forms
        
        if not all_forms:
            await callback.message.edit_text(
                text='У вас пока нет сделок',
                reply_markup=orders_inline(len(open_forms), len(close_forms))
            )
            return
        msg = "📋 Список всех ваших сделок:\n\n"
        for i, form in enumerate(all_forms, 1):
            status = "🟢 Открыта" if form.get('status') == 'OPEN' else "🔴 Закрыта"
            profit_loss = ""
            
            # Calculate profit/loss for closed orders
            if form.get('status') == 'CLOSED':
                side = form.get('side', 'LONG')
                buy_price = form.get('coin_buy_price', 0)
                sale_price = form.get('coin_sale_price', 0)
                
                # Different calculation based on position side
                if side == 'LONG':
                    is_profit = sale_price > buy_price
                else:  # SHORT
                    is_profit = sale_price < buy_price
                
                pnl_usdt = form.get('pnl_usdt')
                
                if pnl_usdt is not None and pnl_usdt != 0:
                    # Use pnl_usdt if available
                    if pnl_usdt > 0:
                        profit_loss = f"(+{round(pnl_usdt, 2)}$💸)"
                    else:
                        profit_loss = f"({round(pnl_usdt, 2)}$🤕)"
                else:
                    # Fallback calculation
                    pnl = abs(sale_price - buy_price)
                    if is_profit:
                        profit_loss = f"(+{round(pnl, 2)}$💸)"
                    else:
                        profit_loss = f"(-{round(pnl, 2)}$🤕)"
                    
            msg += f"{i}. {form['symbol']} | {interval_conv(form.get('interval', ''))} | {status} {profit_loss}\n"
        chunks = split_text_to_chunks(msg)
        n = int(callback.data.split()[2]) if len(callback.data.split()) > 2 else 0
        
        if n >= len(chunks):
            n = 0
        
        # Create pagination buttons if needed
        kb = []
        if len(chunks) > 1:
            pagination = []
            if n > 0:
                pagination.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"orders all {n-1}"))
            if n < len(chunks) - 1:
                pagination.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"orders all {n+1}"))
            kb.append(pagination)
            
        # Add back button
        kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="orders start")])
        
        await callback.message.edit_text(
            text=chunks[n],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
    elif action == 'profit' or action == 'loss':
        # Get closed orders
        forms = await get_all_orders(callback.from_user.id, 'close')
        
        # Filter for profit or loss
        if action == 'profit':
            filtered_forms = []
            for form in forms:
                side = form.get('side', 'LONG')
                buy_price = form.get('coin_buy_price', 0)
                sale_price = form.get('coin_sale_price', 0)
                
                # Check if profitable based on position side
                if side == 'LONG' and sale_price > buy_price:
                    filtered_forms.append(form)
                elif side == 'SHORT' and sale_price < buy_price:
                    filtered_forms.append(form)
                elif form.get('pnl_usdt', 0) > 0:
                    filtered_forms.append(form)
                    
            forms = filtered_forms
            title = "прибыльных"
        else:  # Loss
            filtered_forms = []
            for form in forms:
                side = form.get('side', 'LONG')
                buy_price = form.get('coin_buy_price', 0)
                sale_price = form.get('coin_sale_price', 0)
                
                # Check if loss based on position side
                if side == 'LONG' and sale_price < buy_price:
                    filtered_forms.append(form)
                elif side == 'SHORT' and sale_price > buy_price:
                    filtered_forms.append(form)
                elif form.get('pnl_usdt', 0) < 0:
                    filtered_forms.append(form)
                    
            forms = filtered_forms
            title = "убыточных"
        
        if not forms:
            await callback.message.edit_text(
                text=f'У вас пока нет {title} сделок',
                reply_markup=orders_inline(len(await get_all_orders(callback.from_user.id, 'open')), 
                                          len(await get_all_orders(callback.from_user.id, 'close')))
            )
            return
            
        # Create a list of filtered orders
        msg = f"📋 Список {title} сделок:\n\n"
        
        for i, form in enumerate(forms, 1):
            side = form.get('side', 'LONG')
            buy_price = form.get('coin_buy_price', 0)
            sale_price = form.get('coin_sale_price', 0)
            
            # Get profit/loss display
            pnl_usdt = form.get('pnl_usdt')
            if pnl_usdt is not None:
                if pnl_usdt > 0:
                    profit_text = f"(+{round(pnl_usdt, 2)}$💸)"
                else:
                    profit_text = f"({round(pnl_usdt, 2)}$🤕)"
            else:
                # Fallback calculation
                if (side == 'LONG' and sale_price > buy_price) or (side == 'SHORT' and sale_price < buy_price):
                    profit = abs(sale_price - buy_price)
                    profit_text = f"(+{round(profit, 2)}$💸)"
                else:
                    loss = abs(sale_price - buy_price)
                    profit_text = f"(-{round(loss, 2)}$🤕)"
            
            # Format sale time
            sale_time = ""
            if isinstance(form.get('sale_time'), str):
                sale_time = form['sale_time']
            elif form.get('sale_time') is not None:
                sale_time = form['sale_time'].strftime('%d-%m-%Y %H:%M')
            else:
                sale_time = "Время не указано"
                
            msg += f"{i}. {form['symbol']} | {interval_conv(form.get('interval', ''))} | {side} | {profit_text} | {sale_time}\n"
        
        # Split message if too long
        chunks = split_text_to_chunks(msg)
        n = int(callback.data.split()[2]) if len(callback.data.split()) > 2 else 0
        
        if n >= len(chunks):
            n = 0
        
        # Create pagination buttons if needed
        kb = []
        if len(chunks) > 1:
            pagination = []
            if n > 0:
                pagination.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"orders {action} {n-1}"))
            if n < len(chunks) - 1:
                pagination.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"orders {action} {n+1}"))
            kb.append(pagination)
            
        # Add back button
        kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="orders start")])
        
        await callback.message.edit_text(
            text=chunks[n],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
    elif action == 'open' or action == 'close':
        # Парсим callback данные для определения фильтров
        parts = callback.data.split()
        pair_filter = None
        timeframe_filter = None
        page = 0
        
        # Определяем тип фильтрации из callback данных
        if len(parts) >= 3:
            if parts[2] == 'pair':
                # Фильтрация по паре: orders open pair BTCUSDT [timeframe] [page]
                if len(parts) >= 4:
                    pair_filter = parts[3]
                    if len(parts) >= 5:
                        if parts[4] == 'all':
                            timeframe_filter = 'all'
                            if len(parts) >= 6 and parts[5].isdigit():
                                page = int(parts[5])
                        elif parts[4].isdigit():
                            page = int(parts[4])
                        else:
                            timeframe_filter = parts[4]
                            if len(parts) >= 6 and parts[5].isdigit():
                                page = int(parts[5])
            elif parts[2] == 'all_pairs':
                # Показать все пары без фильтрации
                timeframe_filter = 'all_pairs'
                if len(parts) >= 4 and parts[3].isdigit():
                    page = int(parts[3])
            elif parts[2].isdigit():
                # Старый формат: orders open 0
                page = int(parts[2])
            else:
                # Фильтрация по таймфрейму: orders open 1H 0
                timeframe_filter = parts[2]
                if len(parts) >= 4 and parts[3].isdigit():
                    page = int(parts[3])
        
        forms = await get_all_orders(callback.from_user.id, action)
        
        if not forms:
            await callback.message.edit_text(
                text=f'У вас пока нет {"открытых" if action == "open" else "закрытых"} сделок',
                reply_markup=orders_inline(len(await get_all_orders(callback.from_user.id, 'open')), 
                                          len(await get_all_orders(callback.from_user.id, 'close')))
            )
            return
        
        # Если нет фильтров, показываем список торговых пар
        if pair_filter is None and timeframe_filter is None:
            # Получаем уникальные торговые пары из сделок
            pairs = list(set(form.get('symbol', '') for form in forms if form.get('symbol')))
            pairs.sort()  # Сортируем пары по алфавиту
            
            msg = f"📋 {'Открытые' if action == 'open' else 'Закрытые'} сделки\n\n"
            msg += f"Всего сделок: {len(forms)}\n"
            msg += f"Торговых пар: {len(pairs)}\n\n"
            msg += "Выберите торговую пару для просмотра:"
            
            await callback.message.edit_text(
                text=msg,
                reply_markup=orders_pairs_inline(action, pairs)
            )
            return
        
        # Если выбрана конкретная пара, но не выбран таймфрейм
        if pair_filter and timeframe_filter is None:
            # Фильтруем сделки по выбранной паре
            pair_forms = [form for form in forms if form.get('symbol', '') == pair_filter]
            
            if not pair_forms:
                await callback.message.edit_text(
                    text=f'У вас нет {"открытых" if action == "open" else "закрытых"} сделок по паре {pair_filter}',
                    reply_markup=orders_pairs_inline(action, [pair_filter])
                )
                return
            
            # Получаем уникальные таймфреймы для этой пары
            timeframes = list(set(form.get('interval', '') for form in pair_forms if form.get('interval')))
            
            msg = f"📋 {'Открытые' if action == 'open' else 'Закрытые'} сделки | 💱 {pair_filter}\n\n"
            msg += f"Сделок по паре: {len(pair_forms)}\n"
            msg += f"Таймфреймов: {len(timeframes)}\n\n"
            msg += "Выберите таймфрейм для фильтрации:"
            
            await callback.message.edit_text(
                text=msg,
                reply_markup=orders_pair_timeframes_inline(action, pair_filter, timeframes)
            )
            return
        
        # Применяем фильтры
        filtered_forms = forms
        
        # Фильтр по паре
        if pair_filter:
            filtered_forms = [form for form in filtered_forms if form.get('symbol', '') == pair_filter]
        
        # Фильтр по таймфрейму
        if timeframe_filter and timeframe_filter not in ['all', 'all_pairs']:
            filtered_forms = [form for form in filtered_forms if form.get('interval', '') == timeframe_filter]
        
        if not filtered_forms:
            filter_text = ""
            if pair_filter:
                filter_text += f" по паре {pair_filter}"
            if timeframe_filter and timeframe_filter not in ['all', 'all_pairs']:
                filter_text += f" на таймфрейме {interval_conv(timeframe_filter)}"
            
            await callback.message.edit_text(
                text=f'У вас нет {"открытых" if action == "open" else "закрытых"} сделок{filter_text}',
                reply_markup=orders_pairs_inline(action, [pair_filter] if pair_filter else None)
            )
            return
            
        # Создаем список сделок с улучшенным форматированием
        msg = f"📋 {'Открытые' if action == 'open' else 'Закрытые'} сделки"
        if pair_filter:
            msg += f" | 💱 {pair_filter}"
        if timeframe_filter and timeframe_filter not in ['all', 'all_pairs']:
            msg += f" | ТФ: {interval_conv(timeframe_filter)}"
        msg += "\n\n"
        
        for i, form in enumerate(filtered_forms, 1):
            side = form.get('side', 'LONG')
            interval = form.get('interval', '')
            symbol = form.get('symbol', '')
            
            if action == 'open':
                # Отображение открытых позиций
                buy_price = form.get('coin_buy_price', 0)
                buy_time = form.get('buy_time', 'Неизвестно')
                leverage = form.get('leverage', 1)
                trading_type = form.get('trading_type', 'spot').upper()
                
                # Форматируем время (только дата и время без миллисекунд)
                if isinstance(buy_time, dt):
                    buy_time_str = buy_time.strftime('%d.%m.%Y %H:%M')
                elif isinstance(buy_time, str) and buy_time != 'Неизвестно':
                    try:
                        # Пытаемся распарсить строку времени
                        parsed_time = dt.fromisoformat(buy_time.replace('Z', '+00:00'))
                        buy_time_str = parsed_time.strftime('%d.%m.%Y %H:%M')
                    except:
                        buy_time_str = buy_time
                else:
                    buy_time_str = str(buy_time)
                
                # Форматируем отображение
                side_emoji = "🟢" if side == "LONG" else "🔴"
                lev_info = f" | x{leverage}" if trading_type == 'FUTURES' and leverage > 1 else ""
                
                # Если фильтруем по паре, не показываем символ в каждой строке
                symbol_display = "" if pair_filter else f"{symbol} | "
                
                msg += f"{i}. {side_emoji} {symbol_display}{interval_conv(interval)}{lev_info}\n"
                msg += f"   💰 {round(buy_price, 6)}$ | ⏰ {buy_time_str}\n\n"
            else:
                # Отображение закрытых позиций с прибылью/убытком
                buy_price = form.get('coin_buy_price', 0)
                sale_price = form.get('coin_sale_price', 0)
                sale_time = form.get('sale_time', 'Неизвестно')
                
                # Форматируем время закрытия
                if isinstance(sale_time, dt):
                    sale_time_str = sale_time.strftime('%d.%m.%Y %H:%M')
                elif isinstance(sale_time, str) and sale_time != 'Неизвестно':
                    try:
                        parsed_time = dt.fromisoformat(sale_time.replace('Z', '+00:00'))
                        sale_time_str = parsed_time.strftime('%d.%m.%Y %H:%M')
                    except:
                        sale_time_str = sale_time
                else:
                    sale_time_str = str(sale_time)
                
                # Получаем прибыль/убыток
                pnl_usdt = form.get('pnl_usdt')
                if pnl_usdt is not None:
                    if pnl_usdt > 0:
                        profit_loss = f"💚 +{round(pnl_usdt, 2)}$"
                    else:
                        profit_loss = f"❤️ {round(pnl_usdt, 2)}$"
                else:
                    # Fallback расчет
                    if (side == 'LONG' and sale_price > buy_price) or (side == 'SHORT' and sale_price < buy_price):
                        profit = abs(sale_price - buy_price)
                        profit_loss = f"💚 +{round(profit, 2)}$"
                    else:
                        loss = abs(sale_price - buy_price)
                        profit_loss = f"❤️ -{round(loss, 2)}$"
                
                side_emoji = "🟢" if side == "LONG" else "🔴"
                
                # Если фильтруем по паре, не показываем символ в каждой строке
                symbol_display = "" if pair_filter else f"{symbol} | "
                
                msg += f"{i}. {side_emoji} {symbol_display}{interval_conv(interval)}\n"
                msg += f"   {profit_loss} | ⏰ {sale_time_str}\n\n"
        
        # Разбиваем сообщение, если оно слишком длинное
        chunks = split_text_to_chunks(msg)
        
        if page >= len(chunks):
            page = 0
        
        # Создаем кнопки пагинации
        kb = []
        if len(chunks) > 1:
            pagination = []
            if page > 0:
                if pair_filter and timeframe_filter:
                    pagination.append(InlineKeyboardButton(text="◀️", callback_data=f"orders {action} pair {pair_filter} {timeframe_filter} {page-1}"))
                elif pair_filter:
                    pagination.append(InlineKeyboardButton(text="◀️", callback_data=f"orders {action} pair {pair_filter} {page-1}"))
                elif timeframe_filter:
                    pagination.append(InlineKeyboardButton(text="◀️", callback_data=f"orders {action} {timeframe_filter} {page-1}"))
                else:
                    pagination.append(InlineKeyboardButton(text="◀️", callback_data=f"orders {action} {page-1}"))
            
            pagination.append(InlineKeyboardButton(text=f"{page+1}/{len(chunks)}", callback_data="ignore"))
            
            if page < len(chunks) - 1:
                if pair_filter and timeframe_filter:
                    pagination.append(InlineKeyboardButton(text="▶️", callback_data=f"orders {action} pair {pair_filter} {timeframe_filter} {page+1}"))
                elif pair_filter:
                    pagination.append(InlineKeyboardButton(text="▶️", callback_data=f"orders {action} pair {pair_filter} {page+1}"))
                elif timeframe_filter:
                    pagination.append(InlineKeyboardButton(text="▶️", callback_data=f"orders {action} {timeframe_filter} {page+1}"))
                else:
                    pagination.append(InlineKeyboardButton(text="▶️", callback_data=f"orders {action} {page+1}"))
            kb.append(pagination)
        
        # Добавляем кнопки управления
        control_buttons = []
        if pair_filter:
            if timeframe_filter and timeframe_filter not in ['all', 'all_pairs']:
                # Показываем кнопку для всех ТФ этой пары
                control_buttons.append(InlineKeyboardButton(text="🔄 Все ТФ", callback_data=f"orders {action} pair {pair_filter} all 0"))
            # Показываем кнопку для всех пар
            control_buttons.append(InlineKeyboardButton(text="🔄 Все пары", callback_data=f"orders {action}"))
        else:
            if timeframe_filter and timeframe_filter not in ['all', 'all_pairs']:
                control_buttons.append(InlineKeyboardButton(text="🔄 Все ТФ", callback_data=f"orders {action} all_pairs 0"))
            control_buttons.append(InlineKeyboardButton(text="🔍 Фильтры", callback_data=f"orders {action}"))
        
        if control_buttons:
            kb.append(control_buttons)
        
        # Кнопка назад
        if pair_filter:
            kb.append([InlineKeyboardButton(text="⬅️ Назад к парам", callback_data=f"orders {action}")])
        else:
            kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="orders start")])
        
        await callback.message.edit_text(
            text=chunks[page],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
    else:
        # For individual order view
        forms = await get_all_orders(callback.from_user.id, action)
        n = int(callback.data.split()[2])
        if n < 0:
            await callback.answer('Это начало')
            return
        if n >= len(forms):
            await callback.answer('Это конец списка')
            return

        form = forms[n]
        side = form.get('side', 'LONG')
        symbol = form.get('symbol', '')
        interval = form.get('interval', '')
        trading_type = form.get('trading_type', 'spot').upper()
        leverage = form.get('leverage', 1)
        exchange = form.get('exchange', 'Неизвестно')
        
        # Prepare detailed order view message
        msg = f"<b>Инструмент:</b> {symbol} | {interval_conv(interval)}\n"
        msg += f"<b>Тип позиции:</b> {side}\n\n"
        msg += f"<b>Цена открытия:</b> {round(form.get('coin_buy_price', 0), 8)}$ 📈\n"

        if action == 'open':
            # Display open position details
            investment = form.get('investment_amount_usdt', 0)
            msg += f"<b>Объем сделки:</b> {round(investment, 2)}$ 💵\n\n"
            msg += f"<b>Биржа:</b> {exchange}\n"
            msg += f"<b>Тип торговли:</b> {trading_type}"
            if trading_type == 'FUTURES' and leverage > 1:
                msg += f" (плечо: x{leverage})\n\n"
            else:
                msg += "\n\n"
            
            # Форматируем время открытия
            buy_time = form.get('buy_time', 'Неизвестно')
            if isinstance(buy_time, dt):
                buy_time_str = buy_time.strftime('%d.%m.%Y %H:%M')
            elif isinstance(buy_time, str) and buy_time != 'Неизвестно':
                try:
                    parsed_time = dt.fromisoformat(buy_time.replace('Z', '+00:00'))
                    buy_time_str = parsed_time.strftime('%d.%m.%Y %H:%M')
                except:
                    buy_time_str = buy_time
            else:
                buy_time_str = str(buy_time)
            
            msg += f"<b>Дата и время открытия:</b>\n⏱️ {buy_time_str}\n"
            
            # Добавляем информацию о стратегиях для открытых сделок
            strategies_info = []
            
            # Проверяем каждую стратегию
            if form.get('price_action_active'):
                pattern = form.get('price_action_pattern', '')
                strategies_info.append(f"✅ Price Action {pattern}".strip())
            else:
                strategies_info.append("❌ Price Action")
                
            if form.get('cm_active'):
                strategies_info.append("✅ CM")
            else:
                strategies_info.append("❌ CM")
                
            if form.get('moonbot_active'):
                strategies_info.append("✅ MoonBot")
            else:
                strategies_info.append("❌ MoonBot")
                
            if form.get('rsi_active'):
                strategies_info.append("✅ RSI")
            else:
                strategies_info.append("❌ RSI")
                
            if form.get('divergence_active'):
                div_type = form.get('divergence_type', '')
                strategies_info.append(f"✅ Divergence {div_type}".strip())
            else:
                strategies_info.append("❌ Divergence")
            
            # Добавляем блок со стратегиями
            if any(strategies_info):
                msg += f"\n<b>⚠️ Сделка открыта по сигналам с:</b>\n"
                msg += "\n".join(strategies_info) + "\n"
        else:
            # Display closed position details
            sale_price = form.get('coin_sale_price', 0)
            msg += f"<b>Цена закрытия:</b> {round(sale_price, 8)}$ 📈\n"

            # Calculate and display PnL
            pnl = form.get('pnl_usdt')
            if pnl is not None:
                if pnl > 0:
                    msg += f"<b>Прибыль:</b> {round(abs(pnl), 2)}$ 💚\n\n"
                else:
                    msg += f"<b>Убыток:</b> {round(abs(pnl), 2)}$ ❤️\n\n"
            else:
                # Fallback calculation
                buy_price = form.get('coin_buy_price', 0)
                if (side == 'LONG' and sale_price > buy_price) or (side == 'SHORT' and sale_price < buy_price):
                    profit = abs(sale_price - buy_price)
                    msg += f"<b>Прибыль:</b> {round(profit, 2)}$ 💚\n\n"
                else:
                    loss = abs(sale_price - buy_price)
                    msg += f"<b>Убыток:</b> {round(loss, 2)}$ ❤️\n\n"

            # Add investment amount
            investment = form.get('investment_amount_usdt', 0)
            msg += f"<b>Объем сделки:</b> {round(investment, 2)}$ 💵\n\n"
            
            # Add trading details
            msg += f"<b>Биржа:</b> {exchange}\n"
            msg += f"<b>Тип торговли:</b> {trading_type}"
            if trading_type == 'FUTURES' and leverage > 1:
                msg += f" (плечо: x{leverage})\n\n"
            else:
                msg += "\n\n"
                
            # Форматируем время закрытия
            sale_time = form.get('sale_time', 'Неизвестно')
            if isinstance(sale_time, dt):
                sale_time_str = sale_time.strftime('%d.%m.%Y %H:%M')
            elif isinstance(sale_time, str) and sale_time != 'Неизвестно':
                try:
                    parsed_time = dt.fromisoformat(sale_time.replace('Z', '+00:00'))
                    sale_time_str = parsed_time.strftime('%d.%m.%Y %H:%M')
                except:
                    sale_time_str = sale_time
            else:
                sale_time_str = str(sale_time)
                
            # Форматируем время открытия
            buy_time = form.get('buy_time', 'Неизвестно')
            if isinstance(buy_time, dt):
                buy_time_str = buy_time.strftime('%d.%m.%Y %H:%M')
            elif isinstance(buy_time, str) and buy_time != 'Неизвестно':
                try:
                    parsed_time = dt.fromisoformat(buy_time.replace('Z', '+00:00'))
                    buy_time_str = parsed_time.strftime('%d.%m.%Y %H:%M')
                except:
                    buy_time_str = buy_time
            else:
                buy_time_str = str(buy_time)
                
            msg += f"<b>Дата и время закрытия:</b>\n⏱️ {sale_time_str}\n\n"
            msg += f"<b>Сделка была открыта:</b>\n⏱️ {buy_time_str}\n"
            
            # Добавляем информацию о стратегиях для закрытых сделок
            strategies_info = []
            
            # Проверяем каждую стратегию
            if form.get('price_action_active'):
                pattern = form.get('price_action_pattern', '')
                strategies_info.append(f"✅ Price Action {pattern}".strip())
            else:
                strategies_info.append("❌ Price Action")
                
            if form.get('cm_active'):
                strategies_info.append("✅ CM")
            else:
                strategies_info.append("❌ CM")
                
            if form.get('moonbot_active'):
                strategies_info.append("✅ MoonBot")
            else:
                strategies_info.append("❌ MoonBot")
                
            if form.get('rsi_active'):
                strategies_info.append("✅ RSI")
            else:
                strategies_info.append("❌ RSI")
                
            if form.get('divergence_active'):
                div_type = form.get('divergence_type', '')
                strategies_info.append(f"✅ Divergence {div_type}".strip())
            else:
                strategies_info.append("❌ Divergence")
            
            # Добавляем блок со стратегиями
            if any(strategies_info):
                msg += f"\n<b>⚠️ Сделка была открыта по сигналам с:</b>\n"
                msg += "\n".join(strategies_info) + "\n"

        await callback.message.edit_text(
            text=msg,
            reply_markup=orders_inline_n(n, action, len(forms), "orders"),
            parse_mode="HTML"
        )


async def split_message_and_edit(bot_message, text, reply_markup=None):
    while len(text) > 4096:
        chunk = text[:4096].rsplit('\n', 1)[0]  # Разбить по строкам
        await bot_message.edit_text(text=chunk)
        text = text[len(chunk):]
    await bot_message.edit_text(text=text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith('signals'))
async def signals(callback: CallbackQuery, bot: Bot):
    action = callback.data.split()[1]
    if action == 'start':
        sale = await count_signals('sale')
        buy = await count_signals('buy')
        # forms = all_signals_no_signal()
        # old_symbol = 'start'
        # msg_parts = []
        # for form in forms:
        #     if old_symbol != form['symbol']:
        #         if old_symbol == 'start':
        #             msg_parts.append(f"{form['symbol']} - {buy_sale(form['status'], interval_conv(form['interval']))}")
        #         else:
        #             msg_parts.append(f"\n{form['symbol']} - {buy_sale(form['status'], interval_conv(form['interval']))}")
        #         old_symbol = form['symbol']
        #     else:
        #         msg_parts.append(buy_sale(form['status'], interval_conv(form['interval'])))
        #         old_symbol = form['symbol']

        # msg = "".join(msg_parts)
        # await split_message_and_edit(callback.message, msg, signals_inline(buy, sale))
        await callback.message.edit_text(
            text='Сигналы', 
            reply_markup=signals_inline(buy, sale)
        )
    else:
        interval = action.split('_')[1]
        action = action.split('_')[0]
        if interval == 's':
            n = int(callback.data.split()[0].split('_')[1])
            if n < 0:
                await callback.answer('Это начало')
                return

            if action == 'buy':
                forms = await all_signals_no_signal()
            else:
                forms = await get_all_intervals_for_pairs_with_status(action)
            grouped_signals = {}

            # Группируем сигналы по символу
            INTERVAL_ORDER = {'1d': 1, '4h': 2, '1h': 3, '30m': 4}  # Приоритеты

            # Группируем сигналы по символу
            for form in forms:
                symbol = form['symbol']
                interval = form['interval']
                status = buy_sale(form['status'], interval_conv(interval))
                if symbol not in grouped_signals:
                    grouped_signals[symbol] = []
                grouped_signals[symbol].append({'interval': interval, 'status': status})

            # Сортируем сигналы по заданному порядку (1d → 4h → 1h → 30m)
            for symbol in grouped_signals:
                grouped_signals[symbol].sort(key=lambda x: INTERVAL_ORDER[x['interval']])

            # Формируем строки
            msg_parts = []
            for symbol, signals in grouped_signals.items():
                msg_parts.append(f"{symbol} - {''.join(signal['status'] for signal in signals)}")

            msg = "\n".join(msg_parts)
            chunks = split_text_to_chunks(msg)
            await callback.message.edit_text(
                text=chunks[n],
                reply_markup=interval_inline(action, n,len(chunks))
            )
            # await split_message_and_edit(callback.message, msg, interval_inline(action, 0))

            # await callback.message.edit_text(
            #     text=msg,
            #     reply_markup=interval_inline(action)
            # )
        else:
            n_back = int(callback.data.split()[0].split('_')[1])

            n = int(callback.data.split()[2])
            if n < 0:
                await callback.answer('Это начало')
                return

            forms = await all_signals(action, interval)
            # form = forms[n]
            if action == 'sale':
                signal = 'продажу'
            else:
                signal = 'покупку'
            msg = f"Сигнал на {signal}\n"
            # msg += f"Инструмент: {form['symbol']}\n"
            msg += f"ТФ: {interval_conv(interval)}\n"
            for form in forms:
                msg += f"{form['symbol']} - {buy_sale(action, interval)}\n"
            # msg += f"Цена за покупку: {form['buy_price']}\n"
            # msg += f"Цена за продажу {form['sale_price']}"
            chunks = split_text_to_chunks(msg)
            await callback.message.edit_text(
                text=chunks[n],
                reply_markup=signals_inline_n(action, len(chunks), n_back, interval, n )
            )
            # await split_message_and_edit(callback.message, msg, signals_inline_n(action))
    
            # await callback.message.edit_text(
            #     text=msg,
            #     reply_markup=signals_inline_n(action)
            # )

@router.callback_query(F.data.startswith("table"))
async def table(callback: CallbackQuery, bot: Bot):
    action = callback.data.split()[1]
    if action == 'signals':
        columns, data = await fetch_signals()

        # Создаем Excel файл с русскими названиями колонок
        file_name = create_xls(columns, data, file_name="signals.xlsx", translate_columns=True)

        # Отправка файла в Telegram
        xls_file = FSInputFile(file_name)  # Создаем FSInputFile с путем к файлу

        with open(file_name, 'rb') as file:
            await bot.send_document(chat_id=callback.from_user.id, document=xls_file, caption="Вот ваш файл с сигналами 📄")

    elif action == 'stat':
        columns, data = await fetch_stat(callback.from_user.id)

        if not data:
            await callback.answer("Нет данных для отображения.")
            return

        # Создаем Excel файл с русскими названиями колонок
        file_name = create_xls(columns, data, file_name="orders_stat.xlsx", translate_columns=True)

        # Отправка файла в Telegram
        xls_file = FSInputFile(file_name)

        with open(file_name, 'rb') as file:
            await bot.send_document(chat_id=callback.from_user.id, document=xls_file, caption="Вот ваш файл со сделками 📄")


@router.callback_query(F.data.startswith('monitor'))
async def monitoring(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split()[1]
    user = await get_user(callback.from_user.id)
    if action == 'start':
        await format_monitor_signals(callback, user)
    elif action == 'del':
        await callback.message.edit_text(
            text='Введите пару для удаления',
            reply_markup=monitor_del_inline(user)
        )
    elif action == 'delete':
        pair_to_delete = callback.data.split()[2]
        user = await get_user(callback.from_user.id)
        
        # Удаляем пару из базы данных
        await delete_monitor_pair_from_db(callback.from_user.id, pair_to_delete)
        
        # Отправляем сообщение о том, что пара была удалена
        await callback.answer(f"Пара {pair_to_delete} была удалена из вашего списка")
        
        # Обновляем список избранных пар и показываем новую клавиатуру
        user = await get_user(callback.from_user.id)  # Обновляем данные пользователя после удаления
        await callback.message.edit_text(
            text='Введите пару для удаления',
            reply_markup=monitor_del_inline(user)
        )

    else:
        msg = 'Введите одну пару или несколько пар через запятую\n\nПример: BTCUSDT,EGLDUSDT,XDCUSDT'
        await state.set_state(CryptoPairs.pairs)
        msg = await callback.message.edit_text(
            text=msg,
            reply_markup=close_state()
        )
        await state.update_data(action=action, last_msg=msg.message_id, call='monitor')


def settings_inline():
    kb = [
        [InlineKeyboardButton(text='💰 Изменить баланс', callback_data='settings set_balance')], # New button
        [InlineKeyboardButton(text='📊 Процент списания', callback_data='settings percent')],
        [InlineKeyboardButton(text='🧠 Стратегия Moon Bot', callback_data='settings strategy')],
        [InlineKeyboardButton(text='📈 Настройки индикатора CM', callback_data='settings cm')],
        [InlineKeyboardButton(text='📊 Настройки индикатора дивергенции', callback_data='settings divergence')],
        [InlineKeyboardButton(text='📉 Настройки индикатора RSI', callback_data='settings rsi')],
        [InlineKeyboardButton(text='🔄 Настройки P/D детектора', callback_data='settings pump_dump')],
        [InlineKeyboardButton(text='💱 Настройки типа торговли', callback_data='settings trading')],
        [InlineKeyboardButton(text='🏛️ Выбор бирж', callback_data='settings exchanges')],
        [InlineKeyboardButton(text='Назад', callback_data='start')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data.startswith('settings'))
async def settings(callback: CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split()[1] if len(callback.data.split()) > 1 else 'start'
    if action == 'start':
        await callback.message.edit_text(
            "Настройки\n\n"
            "Выберите раздел:",
            reply_markup=settings_inline()
        )
    elif action == 'set_balance': # New action handler
        msg = await callback.message.edit_text(
            "Пожалуйста, введите новое значение баланса (например, 1000.50):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Назад', callback_data='settings start')]
            ])
        )
        await state.set_state(SetBalanceStates.waiting_for_balance) # Use the existing state
        await state.update_data(last_msg=msg.message_id)
    elif action == 'percent':
        msg = await callback.message.edit_text(
            f"Настройка процента списания от депозита\n\n"
            f"Укажите процент от вашего депозита, который будет использоваться для каждой сделки.\n"
            f"Например: 5 означает, что на каждую сделку будет тратиться 5% от депозита.\n\n"
            f"Введите новое значение (от 0 до 100):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Назад', callback_data='settings start')]
            ])
        )
        await state.set_state(EditDepositPercent.new)
        await state.update_data(last_msg=msg.message_id)
    elif action == 'strategy':
        user_params = load_user_params(callback.from_user.id)
        text = "Настройки параметров торговой стратегии Moon Bot\n\n"
        
        # Display current parameters
        text += "📊 Текущие параметры:\n"
        text += f"💰 Объем ордера: {user_params['OrderSize']} USDT\n"
        text += f"📈 Take Profit: {user_params['TakeProfit']}%\n"
        text += f"📉 Stop Loss: {user_params['StopLoss']}%\n"
        text += f"📊 Мин. объем торгов (24ч): {user_params['MinVolume']}\n"
        text += f"📊 Макс. объем торгов (24ч): {user_params['MaxVolume']}\n"
        text += f"🕐 Мин. часовой объем: {user_params['MinHourlyVolume']}\n"
        text += f"🕐 Макс. часовой объем: {user_params['MaxHourlyVolume']}\n"
        text += f"📈 Макс. движение за 3ч: {user_params['Delta_3h_Max']}%\n"
        text += f"📈 Макс. движение за 24ч: {user_params['Delta_24h_Max']}%\n"
        text += f"⚡ Макс. движение за 5м: {user_params['Delta2_Max']}%\n"
        text += f"₿ BTC мин. движение: {user_params['Delta_BTC_Min']}%\n"
        text += f"₿ BTC макс. движение: {user_params['Delta_BTC_Max']}%\n"
        
        # Convert blacklist set to string
        blacklist = user_params.get('CoinsBlackList', set())
        blacklist_str = ", ".join(sorted(blacklist)) if blacklist else "пусто"
        text += f"⛔ Черный список: {blacklist_str}\n\n"
        
        text += "Выберите параметр для изменения:"
        await callback.message.edit_text(
            text=text,
            reply_markup=strategy_params_inline()
        )
    elif action == 'cm':
        # Загружаем настройки CM индикатора для пользователя
        cm_settings = load_cm_settings(callback.from_user.id)
        
        # Получаем статус уведомлений
        is_enabled = await is_cm_notifications_enabled(callback.from_user.id)
        is_group_enabled = await is_cm_group_notifications_enabled()
        
        text = "⚙️ Настройки индикатора CM (Congestion Measure)\n\n"
        
        # Отображаем текущие параметры CM
        text += "📊 Текущие параметры:\n"
        text += f"📈 Take Profit: {cm_settings.get('TakeProfit', 3.0)}%\n"
        text += f"📉 Stop Loss: {cm_settings.get('StopLoss', -1.5)}%\n"
        text += f"SHORT_GAMMA: {cm_settings['SHORT_GAMMA']:.2f}\n"
        text += f"LONG_GAMMA: {cm_settings['LONG_GAMMA']:.2f}\n"
        text += f"LOOKBACK_T: {cm_settings['LOOKBACK_T']}\n"
        text += f"LOOKBACK_B: {cm_settings['LOOKBACK_B']}\n"
        text += f"PCTILE: {cm_settings['PCTILE']}\n\n"
        
        # Статус уведомлений
        text += f"Уведомления CM индикатора: {'✅ Включены' if is_enabled else '❌ Отключены'}\n"
        text += f"Уведомления CM в группу: {'✅ Включены' if is_group_enabled else '❌ Отключены'}\n\n"
        
        text += "Выберите параметр для изменения:"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=cm_params_inline()
        )
    elif action == 'divergence':
        # Загружаем настройки индикатора дивергенции для пользователя
        divergence_settings = load_divergence_settings(callback.from_user.id)
        
        text = "⚙️ Настройки индикатора дивергенции (RSI)\n\n"
        
        # Отображаем текущие параметры
        text += "📊 Текущие параметры:\n"
        text += f"📈 Take Profit: {divergence_settings.get('TakeProfit', 3.0)}%\n"
        text += f"📉 Stop Loss: {divergence_settings.get('StopLoss', -1.5)}%\n"
        text += f"RSI_LENGTH: {divergence_settings['RSI_LENGTH']}\n"
        text += f"LB_RIGHT: {divergence_settings['LB_RIGHT']}\n"
        text += f"LB_LEFT: {divergence_settings['LB_LEFT']}\n"
        text += f"RANGE_UPPER: {divergence_settings['RANGE_UPPER']}\n"
        text += f"RANGE_LOWER: {divergence_settings['RANGE_LOWER']}\n"
        text += f"TAKE_PROFIT_RSI_LEVEL: {divergence_settings['TAKE_PROFIT_RSI_LEVEL']}\n"
        text += f"STOP_LOSS_TYPE: {divergence_settings['STOP_LOSS_TYPE']}\n"
        text += f"STOP_LOSS_PERC: {divergence_settings['STOP_LOSS_PERC']}\n"
        text += f"ATR_LENGTH: {divergence_settings['ATR_LENGTH']}\n"
        text += f"ATR_MULTIPLIER: {divergence_settings['ATR_MULTIPLIER']}\n\n"
        
        text += "Выберите параметр для изменения:"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=divergence_params_inline()
        )
    elif action == 'rsi':
        # Load RSI indicator settings for the user
        rsi_settings = load_rsi_settings(callback.from_user.id)
        
        text = "⚙️ Настройки индикатора RSI\n\n"
        
        # Display current parameters
        text += "📊 Текущие параметры:\n"
        text += f"📈 Take Profit: {rsi_settings.get('TakeProfit', 3.0)}%\n"
        text += f"📉 Stop Loss: {rsi_settings.get('StopLoss', -1.5)}%\n"
        text += f"RSI_PERIOD: {rsi_settings['RSI_PERIOD']}\n"
        text += f"RSI_OVERBOUGHT: {rsi_settings['RSI_OVERBOUGHT']}\n"
        text += f"RSI_OVERSOLD: {rsi_settings['RSI_OVERSOLD']}\n"
        text += f"EMA_FAST: {rsi_settings['EMA_FAST']}\n"
        text += f"EMA_SLOW: {rsi_settings['EMA_SLOW']}\n\n"
        
        text += "Выберите параметр для изменения:"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=rsi_params_inline()
        )
    elif action == 'pump_dump':
        # Load pump_dump detector settings for the user
        pump_dump_settings = load_pump_dump_settings(callback.from_user.id)
        
        text = "⚙️ Настройки Pump/Dump детектора\n\n"
        
        # Display current parameters
        text += "📊 Текущие параметры:\n"
        text += f"📈 Take Profit: {pump_dump_settings.get('TakeProfit', 3.0)}%\n"
        text += f"📉 Stop Loss: {pump_dump_settings.get('StopLoss', -1.5)}%\n"
        text += f"VOLUME_THRESHOLD: {pump_dump_settings['VOLUME_THRESHOLD']:.1f}x\n"
        text += f"PRICE_CHANGE_THRESHOLD: {pump_dump_settings['PRICE_CHANGE_THRESHOLD']:.1f}%\n"
        text += f"TIME_WINDOW: {pump_dump_settings['TIME_WINDOW']} минут\n"
        text += f"MONITOR_INTERVALS: {', '.join(pump_dump_settings['MONITOR_INTERVALS'])}\n"
        text += f"ENABLED: {'Включено' if pump_dump_settings['ENABLED'] else 'Выключено'}\n\n"
        
        # Show subscription status
        is_subbed = is_subscribed(callback.from_user.id)
        text += f"Статус подписки на уведомления: {'Подписаны ✅' if is_subbed else 'Не подписаны ❌'}\n\n"
        
        text += "Выберите параметр для изменения или управляйте подпиской:"
        
        # Create combined inline keyboard with settings and subscription options
        kb = [
            [InlineKeyboardButton(text='VOLUME_THRESHOLD', callback_data='pump_dump VOLUME_THRESHOLD')],
            [InlineKeyboardButton(text='PRICE_CHANGE_THRESHOLD', callback_data='pump_dump PRICE_CHANGE_THRESHOLD')],
            [InlineKeyboardButton(text='TIME_WINDOW', callback_data='pump_dump TIME_WINDOW')],
            [InlineKeyboardButton(text='MONITOR_INTERVALS', callback_data='pump_dump MONITOR_INTERVALS')],
            [InlineKeyboardButton(text='ENABLED', callback_data='pump_dump ENABLED')],
            [InlineKeyboardButton(text='Сбросить к стандартным', callback_data='pump_dump reset')],
            [InlineKeyboardButton(
                text='Отписаться от уведомлений' if is_subbed else 'Подписаться на уведомления', 
                callback_data='pump_dump unsubscribe' if is_subbed else 'pump_dump subscribe'
            )],
            [InlineKeyboardButton(text='Назад', callback_data='settings start')]
        ]
        
        await callback.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
    elif action == 'trading':
        # Перенаправляем на отдельный обработчик settings_trading
        await settings_trading(callback)
    elif action == 'exchanges':
        # Перенаправляем на отдельный обработчик show_exchanges_settings
        await show_exchanges_settings(callback)
    else:
        # Неизвестное действие - возвращаемся к началу настроек
        await callback.message.edit_text(
            "Настройки\n\n"
            "Выберите раздел:",
            reply_markup=settings_inline()
        )

@router.callback_query(F.data.startswith('strategy'))
async def strategy_params(callback: CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split()[1]
    if action == 'reset':
        await reset_user_params(callback.from_user.id)
        await callback.answer("Настройки стратегии сброшены к стандартным значениям")
        
        # Get the default parameters
        default_params = load_user_params(callback.from_user.id)
        
        text = "Настройки параметров торговой стратегии Moon Bot\n\n"
        text += "Параметры сброшены к стандартным значениям.\n\n"
        
        # Display current parameters
        text += "📊 Текущие параметры:\n"
        text += f"💰 Объем ордера: {default_params['OrderSize']} USDT\n"
        text += f"📈 Take Profit: {default_params['TakeProfit']}%\n"
        text += f"📉 Stop Loss: {default_params['StopLoss']}%\n"
        text += f"📊 Мин. объем торгов (24ч): {default_params['MinVolume']}\n"
        text += f"📊 Макс. объем торгов (24ч): {default_params['MaxVolume']}\n"
        text += f"🕐 Мин. часовой объем: {default_params['MinHourlyVolume']}\n"
        text += f"🕐 Макс. часовой объем: {default_params['MaxHourlyVolume']}\n"
        text += f"📈 Макс. движение за 3ч: {default_params['Delta_3h_Max']}%\n"
        text += f"📈 Макс. движение за 24ч: {default_params['Delta_24h_Max']}%\n"
        text += f"⚡ Макс. движение за 5м: {default_params['Delta2_Max']}%\n"
        text += f"₿ BTC мин. движение: {default_params['Delta_BTC_Min']}%\n"
        text += f"₿ BTC макс. движение: {default_params['Delta_BTC_Max']}%\n"
        
        # Convert blacklist set to string
        blacklist = default_params.get('CoinsBlackList', set())
        blacklist_str = ", ".join(sorted(blacklist)) if blacklist else "пусто"
        text += f"⛔ Черный список: {blacklist_str}\n\n"
        
        text += "Выберите параметр для изменения:"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=strategy_params_inline()
        )
    elif action in ['OrderSize', 'TakeProfit', 'StopLoss', 'MinVolume', 'MaxVolume', 'MinHourlyVolume', 'MaxHourlyVolume', 'Delta_3h_Max', 'Delta_24h_Max', 'Delta2_Max', 'Delta_BTC_Min', 'Delta_BTC_Max']:
        user_params = load_user_params(callback.from_user.id)
        current_value = user_params.get(action, "не установлено")
        kb = [
            [InlineKeyboardButton(text='Назад', callback_data='settings strategy')]
        ]
        msg = await callback.message.edit_text(
            f"Изменение параметра: {action}\n"
            f"Текущее значение: {current_value}\n\n"
            f"Введите новое значение:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
        await state.set_state(StrategyParamStates.edit_param)
        await state.update_data(param_name=action, last_msg=msg.message_id)
    elif action == 'CoinsBlackList':
        user_params = load_user_params(callback.from_user.id)
        blacklist = user_params.get('CoinsBlackList', set())
        blacklist_str = ", ".join(sorted(blacklist)) if blacklist else "пусто"
        kb = [
            [InlineKeyboardButton(text='Назад', callback_data='settings strategy')]
        ]
        msg = await callback.message.edit_text(
            f"Изменение черного списка монет\n"
            f"Текущий черный список: {blacklist_str}\n\n"
            f"Введите список монет через запятую (например: BTC,ETH,XRP):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
        await state.set_state(StrategyParamStates.edit_blacklist)
        await state.update_data(last_msg=msg.message_id)

@router.message(StrategyParamStates.edit_param)
async def process_param_edit(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    param_name = data.get('param_name')
    
    try:
        # Delete the previous message
        try:
            await bot.delete_message(message_id=data.get('last_msg'), chat_id=message.from_user.id)
        except Exception:
            pass
        
        # Удаляем сообщение пользователя с введенным значением
        try:
            await bot.delete_message(message_id=message.message_id, chat_id=message.from_user.id)
        except Exception:
            pass
        
        # Convert input to proper type
        param_value = float(message.text.strip())
        
        # Update parameter
        success = await update_user_param(message.from_user.id, param_name, param_value)
        
        if success:
            # Отправляем сообщение об успехе
            success_msg = await message.answer(f"Параметр {param_name} успешно обновлен на {param_value}")
            
            # Get updated parameters
            user_params = load_user_params(message.from_user.id)
            
            text = "Настройки параметров торговой стратегии Moon Bot\n\n"
            
            # Display current parameters
            text += "📊 Текущие параметры:\n"
            text += f"💰 Объем ордера: {user_params['OrderSize']} USDT\n"
            text += f"📈 Take Profit: {user_params['TakeProfit']}%\n"
            text += f"📉 Stop Loss: {user_params['StopLoss']}%\n"
            text += f"📊 Мин. объем торгов (24ч): {user_params['MinVolume']}\n"
            text += f"📊 Макс. объем торгов (24ч): {user_params['MaxVolume']}\n"
            text += f"🕐 Мин. часовой объем: {user_params['MinHourlyVolume']}\n"
            text += f"🕐 Макс. часовой объем: {user_params['MaxHourlyVolume']}\n"
            text += f"📈 Макс. движение за 3ч: {user_params['Delta_3h_Max']}%\n"
            text += f"📈 Макс. движение за 24ч: {user_params['Delta_24h_Max']}%\n"
            text += f"⚡ Макс. движение за 5м: {user_params['Delta2_Max']}%\n"
            text += f"₿ BTC мин. движение: {user_params['Delta_BTC_Min']}%\n"
            text += f"₿ BTC макс. движение: {user_params['Delta_BTC_Max']}%\n"
            
            # Convert blacklist set to string
            blacklist = user_params.get('CoinsBlackList', set())
            blacklist_str = ", ".join(sorted(blacklist)) if blacklist else "пусто"
            text += f"⛔ Черный список: {blacklist_str}\n\n"
            
            text += "Выберите параметр для изменения:"
            
            # Show settings menu again with current parameters
            await message.answer(
                text=text,
                reply_markup=strategy_params_inline()
            )
            
            # Удаляем сообщение об успехе через 5 секунд
            await asyncio.sleep(5)
            try:
                await bot.delete_message(message_id=success_msg.message_id, chat_id=message.from_user.id)
            except Exception:
                pass
        else:
            await message.answer(f"Не удалось обновить параметр {param_name}")
            await message.answer(
                "Настройки параметров торговой стратегии Moon Bot\n\n"
                "Выберите параметр для изменения:",
                reply_markup=strategy_params_inline()
            )
    except ValueError:
        await message.answer(
            "Ошибка: значение должно быть числом.\n"
            "Попробуйте еще раз:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Назад', callback_data='settings strategy')]
            ])
        )
    
    await state.clear()

@router.message(StrategyParamStates.edit_blacklist)
async def process_blacklist_edit(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    
    try:
        # Delete the previous message
        try:
            await bot.delete_message(message_id=data.get('last_msg'), chat_id=message.from_user.id)
        except Exception:
            pass
        
        # Удаляем сообщение пользователя с введенным значением
        try:
            await bot.delete_message(message_id=message.message_id, chat_id=message.from_user.id)
        except Exception:
            pass
        
        # Process blacklist input
        blacklist_str = message.text.strip().upper()
        
        # Update parameter
        success = await update_user_param(message.from_user.id, 'CoinsBlackList', blacklist_str)
        
        if success:
            success_msg = await message.answer("Черный список монет успешно обновлен")
            
            # Get updated parameters
            user_params = load_user_params(message.from_user.id)
            
            text = "Настройки параметров торговой стратегии Moon Bot\n\n"
            
            # Display current parameters
            text += "📊 Текущие параметры:\n"
            text += f"💰 Объем ордера: {user_params['OrderSize']} USDT\n"
            text += f"📈 Take Profit: {user_params['TakeProfit']}%\n"
            text += f"📉 Stop Loss: {user_params['StopLoss']}%\n"
            text += f"📊 Мин. объем торгов (24ч): {user_params['MinVolume']}\n"
            text += f"📊 Макс. объем торгов (24ч): {user_params['MaxVolume']}\n"
            text += f"🕐 Мин. часовой объем: {user_params['MinHourlyVolume']}\n"
            text += f"🕐 Макс. часовой объем: {user_params['MaxHourlyVolume']}\n"
            text += f"📈 Макс. движение за 3ч: {user_params['Delta_3h_Max']}%\n"
            text += f"📈 Макс. движение за 24ч: {user_params['Delta_24h_Max']}%\n"
            text += f"⚡ Макс. движение за 5м: {user_params['Delta2_Max']}%\n"
            text += f"₿ BTC мин. движение: {user_params['Delta_BTC_Min']}%\n"
            text += f"₿ BTC макс. движение: {user_params['Delta_BTC_Max']}%\n"
            
            # Convert blacklist set to string
            blacklist = user_params.get('CoinsBlackList', set())
            blacklist_str = ", ".join(sorted(blacklist)) if blacklist else "пусто"
            text += f"⛔ Черный список: {blacklist_str}\n\n"
            
            text += "Выберите параметр для изменения:"
            
            # Show settings menu again with current parameters
            await message.answer(
                text=text,
                reply_markup=strategy_params_inline()
            )
            
            # Удаляем сообщение об успехе через 5 секунд
            await asyncio.sleep(5)
            try:
                await bot.delete_message(message_id=success_msg.message_id, chat_id=message.from_user.id)
            except Exception:
                pass
        else:
            await message.answer("Не удалось обновить черный список монет")
            await message.answer(
                "Настройки параметров торговой стратегии Moon Bot\n\n"
                "Выберите параметр для изменения:",
                reply_markup=strategy_params_inline()
            )
    except Exception as e:
        await message.answer(
            f"Ошибка при обновлении черного списка: {e}\n"
            "Попробуйте еще раз:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Назад', callback_data='settings strategy')]
            ])
        )
    
    await state.clear()

@router.callback_query(F.data == 'close_state')
async def close_state_cal(callback: CallbackQuery, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    await callback.message.edit_text(
        'Бот по обработке фильтра CM_Laguerre PPO PercentileRank Mkt Tops & Bottoms',
        reply_markup=start_inline()
    )

        


@router.callback_query(F.data == 'start')
async def start_cal(callback: CallbackQuery, state: FSMContext):
    user = await get_user_db(callback.from_user.id)
    await callback.message.edit_text(
        text=f"Бот по обработке фильтра CM_Laguerre PPO PercentileRank Mkt Tops & Bottoms\nВаш баланс: {round(user['balance'])}$  💸",
        reply_markup=start_inline()
    )

@router.callback_query(F.data.startswith('cm'))
async def cm_params(callback: CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split()[1] if len(callback.data.split()) > 1 else None
    
    if action == 'reset':
        # Reset CM settings to default
        await reset_cm_settings(callback.from_user.id)
        await callback.answer("Настройки CM сброшены к стандартным значениям")
        
        # Get default settings
        cm_settings = load_cm_settings(callback.from_user.id)
        
        text = "⚙️ Настройки CM\\n\\n"
        text += "Параметры сброшены к стандартным значениям.\\n\\n"
        
        # Display current parameters
        text += "📊 Текущие параметры:\\n"
        text += f"📈 Take Profit: {cm_settings.get('TakeProfit', 3.0)}%\\n"
        text += f"📉 Stop Loss: {cm_settings.get('StopLoss', -1.5)}%\\n"
        text += f"SHORT_GAMMA: {cm_settings['SHORT_GAMMA']}\\n"
        text += f"LONG_GAMMA: {cm_settings['LONG_GAMMA']}\\n"
        text += f"LOOKBACK_T: {cm_settings['LOOKBACK_T']}\\n"
        text += f"LOOKBACK_B: {cm_settings['LOOKBACK_B']}\\n"
        text += f"PCTILE: {cm_settings['PCTILE']}"
        
        await callback.message.edit_text(text, reply_markup=cm_params_inline())
        return

    if action:
        # Save the parameter name to state
        await state.set_state(CMParamStates.edit_param)
        await state.update_data(param_name=action)
        
        text = f"Введите новое значение для параметра {action}:"
        if action in ['TakeProfit', 'StopLoss']:
            text = f"Введите новое значение для {'Take Profit' if action == 'TakeProfit' else 'Stop Loss'} в процентах:"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='Отмена', callback_data='close_state')
            ]])
        )
        return

    # Display current CM settings
    cm_settings = load_cm_settings(callback.from_user.id)
    
    text = "⚙️ Настройки CM\\n\\n"
    text += "📊 Текущие параметры:\\n"
    text += f"📈 Take Profit: {cm_settings.get('TakeProfit', 3.0)}%\\n"
    text += f"📉 Stop Loss: {cm_settings.get('StopLoss', -1.5)}%\\n"
    text += f"SHORT_GAMMA: {cm_settings['SHORT_GAMMA']}\\n"
    text += f"LONG_GAMMA: {cm_settings['LONG_GAMMA']}\\n"
    text += f"LOOKBACK_T: {cm_settings['LOOKBACK_T']}\\n"
    text += f"LOOKBACK_B: {cm_settings['LOOKBACK_B']}\\n"
    text += f"PCTILE: {cm_settings['PCTILE']}"
    
    await callback.message.edit_text(text, reply_markup=cm_params_inline())

@router.message(CMParamStates.edit_param)
async def process_cm_param_edit(message: Message, state: FSMContext, bot: Bot):
    # Get the parameter name from state
    data = await state.get_data()
    param_name = data.get('param_name')
    
    if not param_name:
        await message.answer("Ошибка: параметр не найден")
        await state.clear()
        return
    
    # Get the input value
    param_value = message.text.strip()
    
    try:
        # Convert value to float for numeric parameters
        if param_name in ['TakeProfit', 'StopLoss', 'SHORT_GAMMA', 'LONG_GAMMA', 'PCTILE']:
            param_value = float(param_value)
        else:
            param_value = int(param_value)
        
        # Validate TakeProfit and StopLoss
        if param_name == 'TakeProfit' and param_value <= 0:
            await message.answer("Take Profit должен быть больше 0")
            return
        if param_name == 'StopLoss' and param_value >= 0:
            await message.answer("Stop Loss должен быть меньше 0")
            return
        
        # Update the parameter
        await update_cm_setting(message.from_user.id, param_name, param_value)
        
        # Get updated settings
        cm_settings = load_cm_settings(message.from_user.id)
        
        # Format message with updated settings
        text = "⚙️ Настройки CM\\n\\n"
        text += "📊 Текущие параметры:\\n"
        text += f"📈 Take Profit: {cm_settings.get('TakeProfit', 3.0)}%\\n"
        text += f"📉 Stop Loss: {cm_settings.get('StopLoss', -1.5)}%\\n"
        text += f"SHORT_GAMMA: {cm_settings['SHORT_GAMMA']}\\n"
        text += f"LONG_GAMMA: {cm_settings['LONG_GAMMA']}\\n"
        text += f"LOOKBACK_T: {cm_settings['LOOKBACK_T']}\\n"
        text += f"LOOKBACK_B: {cm_settings['LOOKBACK_B']}\\n"
        text += f"PCTILE: {cm_settings['PCTILE']}"
        
        await message.answer(text, reply_markup=cm_params_inline())
        await state.clear()
        
    except ValueError:
        await message.answer(
            "Ошибка: введите числовое значение",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='Отмена', callback_data='close_state')
            ]])
        )

@router.callback_query(F.data.startswith('divergence'))
async def divergence_params(callback: CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split()[1] if len(callback.data.split()) > 1 else None
    
    if action == 'reset':
        # Reset divergence settings to default
        await reset_divergence_settings(callback.from_user.id)
        await callback.answer("Настройки дивергенции сброшены к стандартным значениям")
        
        # Get default settings
        divergence_settings = load_divergence_settings(callback.from_user.id)
        
        text = "⚙️ Настройки дивергенции\\n\\n"
        text += "Параметры сброшены к стандартным значениям.\\n\\n"
        
        # Display current parameters
        text += "📊 Текущие параметры:\\n"
        text += f"📈 Take Profit: {divergence_settings.get('TakeProfit', 3.0)}%\\n"
        text += f"📉 Stop Loss: {divergence_settings.get('StopLoss', -1.5)}%\\n"
        text += f"RSI_LENGTH: {divergence_settings['RSI_LENGTH']}\\n"
        text += f"LB_RIGHT: {divergence_settings['LB_RIGHT']}\\n"
        text += f"LB_LEFT: {divergence_settings['LB_LEFT']}\\n"
        text += f"RANGE_UPPER: {divergence_settings['RANGE_UPPER']}\\n"
        text += f"RANGE_LOWER: {divergence_settings['RANGE_LOWER']}\\n"
        text += f"TAKE_PROFIT_RSI_LEVEL: {divergence_settings['TAKE_PROFIT_RSI_LEVEL']}\\n"
        text += f"ATR_LENGTH: {divergence_settings['ATR_LENGTH']}\\n"
        text += f"ATR_MULTIPLIER: {divergence_settings['ATR_MULTIPLIER']}"
        
        await callback.message.edit_text(text, reply_markup=divergence_params_inline())
        return

    if action:
        # Save the parameter name to state
        await state.set_state(DivergenceParamStates.edit_param)
        await state.update_data(param_name=action)
        
        text = f"Введите новое значение для параметра {action}:"
        if action in ['TakeProfit', 'StopLoss']:
            text = f"Введите новое значение для {'Take Profit' if action == 'TakeProfit' else 'Stop Loss'} в процентах:"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='Отмена', callback_data='close_state')
            ]])
        )
        return

    # Display current divergence settings
    divergence_settings = load_divergence_settings(callback.from_user.id)
    
    text = "⚙️ Настройки дивергенции\\n\\n"
    text += "📊 Текущие параметры:\\n"
    text += f"📈 Take Profit: {divergence_settings.get('TakeProfit', 3.0)}%\\n"
    text += f"📉 Stop Loss: {divergence_settings.get('StopLoss', -1.5)}%\\n"
    text += f"RSI_LENGTH: {divergence_settings['RSI_LENGTH']}\\n"
    text += f"LB_RIGHT: {divergence_settings['LB_RIGHT']}\\n"
    text += f"LB_LEFT: {divergence_settings['LB_LEFT']}\\n"
    text += f"RANGE_UPPER: {divergence_settings['RANGE_UPPER']}\\n"
    text += f"RANGE_LOWER: {divergence_settings['RANGE_LOWER']}\\n"
    text += f"TAKE_PROFIT_RSI_LEVEL: {divergence_settings['TAKE_PROFIT_RSI_LEVEL']}\\n"
    text += f"ATR_LENGTH: {divergence_settings['ATR_LENGTH']}\\n"
    text += f"ATR_MULTIPLIER: {divergence_settings['ATR_MULTIPLIER']}"
    
    await callback.message.edit_text(text, reply_markup=divergence_params_inline())

@router.callback_query(F.data.startswith('divergence_sl_type'))
async def divergence_sl_type_select(callback: CallbackQuery, state: FSMContext):
    selected_type = callback.data.split()[1]  # PERC, ATR или NONE
    
    # Обновляем параметр STOP_LOSS_TYPE
    success = update_divergence_setting(callback.from_user.id, 'STOP_LOSS_TYPE', selected_type)
    
    if success:
        await callback.answer(f"Тип стоп-лосса установлен: {selected_type}")
        
        # Загружаем обновленные настройки и показываем их
        divergence_settings = load_divergence_settings(callback.from_user.id)
        
        text = "⚙️ Настройки индикатора дивергенции (RSI)\n\n"
        
        # Отображаем текущие параметры
        text += "📊 Текущие параметры:\n"
        text += f"RSI_LENGTH: {divergence_settings['RSI_LENGTH']}\n"
        text += f"LB_RIGHT: {divergence_settings['LB_RIGHT']}\n"
        text += f"LB_LEFT: {divergence_settings['LB_LEFT']}\n"
        text += f"RANGE_UPPER: {divergence_settings['RANGE_UPPER']}\n"
        text += f"RANGE_LOWER: {divergence_settings['RANGE_LOWER']}\n"
        text += f"TAKE_PROFIT_RSI_LEVEL: {divergence_settings['TAKE_PROFIT_RSI_LEVEL']}\n"
        text += f"STOP_LOSS_TYPE: {divergence_settings['STOP_LOSS_TYPE']}\n"
        text += f"STOP_LOSS_PERC: {divergence_settings['STOP_LOSS_PERC']}\n"
        text += f"ATR_LENGTH: {divergence_settings['ATR_LENGTH']}\n"
        text += f"ATR_MULTIPLIER: {divergence_settings['ATR_MULTIPLIER']}\n\n"
        
        text += "Выберите параметр для изменения:"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=divergence_params_inline()
        )
    else:
        await callback.answer("Ошибка при обновлении типа стоп-лосса")

@router.message(DivergenceParamStates.edit_param)
async def process_divergence_param_edit(message: Message, state: FSMContext, bot: Bot):
    # Get the parameter name from state
    data = await state.get_data()
    param_name = data.get('param_name')
    
    if not param_name:
        await message.answer("Ошибка: параметр не найден")
        await state.clear()
        return
    
    # Get the input value
    param_value = message.text.strip()
    
    try:
        # Convert value to float for numeric parameters
        if param_name in ['TakeProfit', 'StopLoss', 'ATR_MULTIPLIER', 'TAKE_PROFIT_RSI_LEVEL']:
            param_value = float(param_value)
        else:
            param_value = int(param_value)
        
        # Validate TakeProfit and StopLoss
        if param_name == 'TakeProfit' and param_value <= 0:
            await message.answer("Take Profit должен быть больше 0")
            return
        if param_name == 'StopLoss' and param_value >= 0:
            await message.answer("Stop Loss должен быть меньше 0")
            return
        
        # Update the parameter
        await update_divergence_setting(message.from_user.id, param_name, param_value)
        
        # Get updated settings
        divergence_settings = load_divergence_settings(message.from_user.id)
        
        # Format message with updated settings
        text = "⚙️ Настройки дивергенции\\n\\n"
        text += "📊 Текущие параметры:\\n"
        text += f"📈 Take Profit: {divergence_settings.get('TakeProfit', 3.0)}%\\n"
        text += f"📉 Stop Loss: {divergence_settings.get('StopLoss', -1.5)}%\\n"
        text += f"RSI_LENGTH: {divergence_settings['RSI_LENGTH']}\\n"
        text += f"LB_RIGHT: {divergence_settings['LB_RIGHT']}\\n"
        text += f"LB_LEFT: {divergence_settings['LB_LEFT']}\\n"
        text += f"RANGE_UPPER: {divergence_settings['RANGE_UPPER']}\\n"
        text += f"RANGE_LOWER: {divergence_settings['RANGE_LOWER']}\\n"
        text += f"TAKE_PROFIT_RSI_LEVEL: {divergence_settings['TAKE_PROFIT_RSI_LEVEL']}\\n"
        text += f"ATR_LENGTH: {divergence_settings['ATR_LENGTH']}\\n"
        text += f"ATR_MULTIPLIER: {divergence_settings['ATR_MULTIPLIER']}"
        
        await message.answer(text, reply_markup=divergence_params_inline())
        await state.clear()
        
    except ValueError:
        await message.answer(
            "Ошибка: введите числовое значение",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='Отмена', callback_data='close_state')
            ]])
        )

@router.message(DivergenceParamStates.edit_stop_loss_type)
async def process_divergence_stop_loss_type_edit(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    
    try:
        # Удаляем предыдущее сообщение
        try:
            await bot.delete_message(message_id=data.get('last_msg'), chat_id=message.from_user.id)
        except Exception:
            pass
        
        # Удаляем сообщение пользователя с введенным значением
        try:
            await bot.delete_message(message_id=message.message_id, chat_id=message.from_user.id)
        except Exception:
            pass
        
        # Обновляем тип стоп-лосса
        stop_loss_type = message.text.strip().upper()
        if stop_loss_type not in ['PERC', 'ATR']:
            await message.answer(
                "Некорректный тип стоп-лосса. Допустимые значения: PERC, ATR",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text='Отмена', callback_data='close_state')
                ]])
            )
            return
        
        # Обновляем настройку
        await update_divergence_setting(message.from_user.id, 'STOP_LOSS_TYPE', stop_loss_type)
        
        # Получаем обновленные настройки
        divergence_settings = load_divergence_settings(message.from_user.id)
        
        # Форматируем сообщение с обновленными настройками
        text = "⚙️ Настройки дивергенции\\n\\n"
        text += "📊 Текущие параметры:\\n"
        text += f"📈 Take Profit: {divergence_settings.get('TakeProfit', 3.0)}%\\n"
        text += f"📉 Stop Loss: {divergence_settings.get('StopLoss', -1.5)}%\\n"
        text += f"RSI_LENGTH: {divergence_settings['RSI_LENGTH']}\\n"
        text += f"LB_RIGHT: {divergence_settings['LB_RIGHT']}\\n"
        text += f"LB_LEFT: {divergence_settings['LB_LEFT']}\\n"
        text += f"RANGE_UPPER: {divergence_settings['RANGE_UPPER']}\\n"
        text += f"RANGE_LOWER: {divergence_settings['RANGE_LOWER']}\\n"
        text += f"TAKE_PROFIT_RSI_LEVEL: {divergence_settings['TAKE_PROFIT_RSI_LEVEL']}\\n"
        text += f"ATR_LENGTH: {divergence_settings['ATR_LENGTH']}\\n"
        text += f"ATR_MULTIPLIER: {divergence_settings['ATR_MULTIPLIER']}"
        
        await message.answer(text, reply_markup=divergence_params_inline())
        await state.clear()
        
    except Exception as e:
        await message.answer(
            f"Произошла ошибка при обновлении типа стоп-лосса: {e}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='Отмена', callback_data='close_state')
            ]])
        )
        await state.clear()

@router.message(EditDepositPercent.new)
async def process_deposit_percent_edit(message: Message, state: FSMContext, bot: Bot):
    from db.update import up_percent
    
    data = await state.get_data()
    
    # Удаляем временное сообщение с запросом ввода
    try:
        await bot.delete_message(message_id=data.get('last_msg'), chat_id=message.from_user.id)
    except Exception:
        pass
    
    
    try:
        # Преобразуем входное значение в число
        percent_value = float(message.text.strip())
        
        if percent_value < 0 or percent_value > 100:
            await message.answer("Процент должен быть от 0 до 100. Попробуйте еще раз.")
            return
        
        # Обновляем процент
        await up_percent(message.from_user.id, percent_value)
        
        # Отправляем сообщение об успехе
        success_msg = await message.answer(f"Процент списания от депозита успешно обновлен на {percent_value}%")
        
        # Сразу показываем меню настроек
        await message.answer(
            "Настройки\n\n"
            "Выберите раздел:",
            reply_markup=settings_inline()
        )
        
        # Удаляем сообщение об успехе через 5 секунд
        await asyncio.sleep(5)
        try:
            await bot.delete_message(message_id=success_msg.message_id, chat_id=message.from_user.id)
        except Exception:
            pass
        
    except ValueError:
        await message.answer(
            "Ошибка: значение должно быть числом.\n"
            "Попробуйте еще раз:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Назад', callback_data='settings start')]
            ])
        )
    except Exception as e:
        await message.answer(
            f"Ошибка при обновлении процента списания: {e}\n"
            "Попробуйте еще раз:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Назад', callback_data='settings start')]
            ])
        )
    
    await state.clear()

