from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from keyboard.inline import *
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from db import *
from db.xls import *
from strategy_logic.get_all_coins import get_usdt_pairs
import datetime
import asyncio

# Исправляем импорт datetime для корректного доступа к datetime.datetime
from datetime import datetime as dt

from basic.state import *
from config import config
from states import SubscriptionStates, EditPercent, StatPeriodStates, StrategyParamStates, CMParamStates
import re
from db.orders import (get_open_order, get_user_balance, create_order, close_order, 
                      get_user_open_orders, get_user_closed_orders, get_all_orders)
from db.select import (get_user, get_signal, get_active_order, get_user_orders, 
                     get_user_subscriptions, get_subscribed_users, get_order, 
                     get_all_user_id, get_all_orders, get_signals, 
                     get_statistics_for_period, get_stat_db, all_signals, count_signals, 
                     get_daily_statistics, all_signals_no_signal, 
                     get_all_intervals_for_pairs_with_status, fetch_signals, fetch_stat,
                     select_user_signals_stat, get_user_liked_coins, get_symbol_data,
                     get_signal_data_by_symbol_tf, select_count, get_tf_stat,
                     count_total_open, get_signal_data)
from db.insert import set_user
from strategy_logic.user_strategy_params import load_user_params, update_user_param, reset_user_params, get_param_names_and_types
from strategy_logic.cm_settings import load_cm_settings, update_cm_setting, reset_cm_settings, get_cm_param_names_and_types

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
    try:
        await bot.delete_message(message_id=data['last_msg'], chat_id=message.from_user.id)
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
    try:
        await bot.delete_message(message_id=data['last_msg'], chat_id=message.from_user.id)
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
    try:
        await bot.delete_message(chat_id=message.from_user.id, message_id=data['last_msg'])
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
    try:
        await bot.delete_message(chat_id=user_id, message_id=data['last_msg'])
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
        # Get daily statistics
        total_trades, profitable_trades, loss_trades, total_profit = await get_daily_statistics(callback.from_user.id)
        
        # Format profit/loss text
        if total_profit > 0:
            profit_text = f"Чистый профит: {round(total_profit, 2)}$ 💰🔋"
        else:
            profit_text = f"Чистый профит: {round(total_profit, 2)}$ 💰🔋"
        
        message = f"📊 Сделки, совершенные ботом за текущий день:\n\n" \
                 f"♻️ Общее количество сделок: {total_trades}\n\n" \
                 f"📗 В прибыль: {profitable_trades} {plural_form(profitable_trades, ['сделка', 'сделки', 'сделок'])} (<a href=\"tg://callback?data=stat profit_details 0\">Подробнее</a>)\n" \
                 f"📕 В убыток: {loss_trades} {plural_form(loss_trades, ['сделка', 'сделки', 'сделок'])} (<a href=\"tg://callback?data=stat loss_details 0\">Подробнее</a>)\n\n" \
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
        
        # Display multiple trades per page
        TRADES_PER_PAGE = 3
        total_pages = (len(closed_orders) + TRADES_PER_PAGE - 1) // TRADES_PER_PAGE
        start_idx = page * TRADES_PER_PAGE
        end_idx = min(start_idx + TRADES_PER_PAGE, len(closed_orders))
        
        message = f"📊 <b>Закрытые сделки (страница {page+1}/{total_pages}):</b>\n\n"
        
        for order in closed_orders[start_idx:end_idx]:
            # Access price data using correct keys
            buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
            sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
            
            # Calculate profit or loss
            if buy_price and sale_price:
                profit_percent = ((sale_price - buy_price) / buy_price) * 100
                profit_symbol = "✅" if profit_percent > 0 else "❌"
                
                time_str = dt.fromtimestamp(order['create_at']).strftime('%d.%m.%Y %H:%M:%S')
                invest_amount = order.get('invest_amount', order.get('investment_amount_usdt', 0))
                
                message += f"{profit_symbol} <b>{order['symbol']}:</b>\n" \
                          f"📅 {time_str}\n" \
                          f"💰 Инвестировано: ${round(invest_amount, 2)}\n" \
                          f"📈 Цена входа: ${round(buy_price, 8)}\n" \
                          f"📉 Цена выхода: ${round(sale_price, 8)}\n" \
                          f"🔄 P&L: {round(profit_percent, 2)}%\n\n"
        
        await callback.message.edit_text(
            text=message,
            reply_markup=stat_inline_n(page, total_pages, 'all'),
            parse_mode='HTML'
        )
    
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
                 f"📗 В прибыль: {profitable_trades} {plural_form(profitable_trades, ['сделка', 'сделки', 'сделок'])} (<a href=\"tg://callback?data=stat profit_details_{period_type} 0\">Подробнее</a>)\n" \
                 f"📕 В убыток: {loss_trades} {plural_form(loss_trades, ['сделка', 'сделки', 'сделок'])} (<a href=\"tg://callback?data=stat loss_details_{period_type} 0\">Подробнее</a>)\n\n" \
                 f"{profit_text}"
        
        # Create keyboard with options to view trades for this period
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
        
        # Display multiple trades per page
        TRADES_PER_PAGE = 3
        total_pages = (len(closed_orders) + TRADES_PER_PAGE - 1) // TRADES_PER_PAGE
        start_idx = page * TRADES_PER_PAGE
        end_idx = min(start_idx + TRADES_PER_PAGE, len(closed_orders))
        
        message = f"📊 <b>Закрытые сделки (страница {page+1}/{total_pages}):</b>\n\n"
        
        for order in closed_orders[start_idx:end_idx]:
            # Access price data using correct keys
            buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
            sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
            
            # Calculate profit or loss
            if buy_price and sale_price:
                profit_percent = ((sale_price - buy_price) / buy_price) * 100
                profit_symbol = "✅" if profit_percent > 0 else "❌"
                
                time_str = dt.fromtimestamp(order['create_at']).strftime('%d.%m.%Y %H:%M:%S')
                invest_amount = order.get('invest_amount', order.get('investment_amount_usdt', 0))
                
                message += f"{profit_symbol} <b>{order['symbol']}:</b>\n" \
                          f"📅 {time_str}\n" \
                          f"💰 Инвестировано: ${round(invest_amount, 2)}\n" \
                          f"📈 Цена входа: ${round(buy_price, 8)}\n" \
                          f"📉 Цена выхода: ${round(sale_price, 8)}\n" \
                          f"🔄 P&L: {round(profit_percent, 2)}%\n\n"
        
        # Create navigation keyboard with back button to period stats
        keyboard = []
        if total_pages > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton(text='◀️', callback_data=f'stat period_view_{period_type} {page-1}'))
            row.append(InlineKeyboardButton(text=f'{page+1}/{total_pages}', callback_data='none'))
            if page < total_pages - 1:
                row.append(InlineKeyboardButton(text='▶️', callback_data=f'stat period_view_{period_type} {page+1}'))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(text='Назад к статистике', callback_data=f'stat period_{period_type}')])
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(text=message, reply_markup=markup, parse_mode='HTML')
    
    elif action == 'profit_details' or action == 'loss_details':
        # Получаем дневную статистику
        today = dt.now()
        today_date = today.strftime('%Y-%m-%d')
        
        # Получаем все закрытые ордера за день
        closed_orders = await get_all_orders(callback.from_user.id, 'close')
        
        # Фильтруем только сегодняшние ордера
        today_orders = []
        for order in closed_orders:
            if isinstance(order.get('sale_time'), str):
                sale_date = order['sale_time'].split(' ')[0]  # Предполагаем формат "YYYY-MM-DD HH:MM:SS"
            else:
                # Если sale_time не строка, а datetime
                sale_date = dt.fromtimestamp(order['create_at']).strftime('%Y-%m-%d')
            
            if sale_date == today_date:
                today_orders.append(order)
        
        # Фильтруем по прибыльным или убыточным
        if action == 'profit_details':
            filtered_orders = []
            for order in today_orders:
                buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
                sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
                if sale_price > buy_price:
                    filtered_orders.append(order)
            title = "прибыльных"
        else:  # loss_details
            filtered_orders = []
            for order in today_orders:
                buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
                sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
                if sale_price < buy_price:
                    filtered_orders.append(order)
            title = "убыточных"
        
        if not filtered_orders:
            await callback.message.edit_text(
                text=f"У вас нет {title} сделок за сегодня.",
                reply_markup=stat_inline(profitable_trades, loss_trades)
            )
            return
        
        # Отображаем сделки
        TRADES_PER_PAGE = 3
        total_pages = (len(filtered_orders) + TRADES_PER_PAGE - 1) // TRADES_PER_PAGE
        start_idx = page * TRADES_PER_PAGE
        end_idx = min(start_idx + TRADES_PER_PAGE, len(filtered_orders))
        
        message = f"📊 <b>{title.capitalize()} сделки за сегодня (страница {page+1}/{total_pages}):</b>\n\n"
        
        for order in filtered_orders[start_idx:end_idx]:
            buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
            sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
            
            if buy_price and sale_price:
                profit_percent = ((sale_price - buy_price) / buy_price) * 100
                symbol = "✅" if profit_percent > 0 else "❌"
                
                time_str = ""
                if isinstance(order.get('sale_time'), str):
                    time_str = order['sale_time']
                else:
                    time_str = dt.fromtimestamp(order['create_at']).strftime('%d.%m.%Y %H:%M:%S')
                
                invest_amount = order.get('invest_amount', order.get('investment_amount_usdt', 0))
                
                message += f"{symbol} <b>{order['symbol']}:</b>\n" \
                          f"📅 {time_str}\n" \
                          f"💰 Инвестировано: ${round(invest_amount, 2)}\n" \
                          f"📈 Цена входа: ${round(buy_price, 8)}\n" \
                          f"📉 Цена выхода: ${round(sale_price, 8)}\n" \
                          f"🔄 P&L: {round(profit_percent, 2)}%\n\n"
        
        # Create navigation buttons
        keyboard = []
        if total_pages > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton(text='◀️', callback_data=f'stat {action} {page-1}'))
            row.append(InlineKeyboardButton(text=f'{page+1}/{total_pages}', callback_data='none'))
            if page < total_pages - 1:
                row.append(InlineKeyboardButton(text='▶️', callback_data=f'stat {action} {page+1}'))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(text='Назад к статистике', callback_data='stat start')])
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(text=message, reply_markup=markup, parse_mode='HTML')
    
    elif action.startswith('profit_details_') or action.startswith('loss_details_'):
        # Извлекаем тип периода из action
        period_type = action.split('_')[2]
        action_type = action.split('_')[0] + '_' + action.split('_')[1]  # profit_details или loss_details
        
        # Вычисляем начальную дату на основе типа периода
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
        
        # Получаем закрытые ордера за период
        closed_orders = await get_all_orders(callback.from_user.id, 'close', from_date=start_date)
        
        # Фильтруем по прибыльным или убыточным
        if action_type == 'profit_details':
            filtered_orders = []
            for order in closed_orders:
                buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
                sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
                if sale_price > buy_price:
                    filtered_orders.append(order)
            title = "прибыльных"
        else:  # loss_details
            filtered_orders = []
            for order in closed_orders:
                buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
                sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
                if sale_price < buy_price:
                    filtered_orders.append(order)
            title = "убыточных"
        
        if not filtered_orders:
            await callback.message.edit_text(
                text=f"У вас нет {title} сделок {period_text}.",
                reply_markup=stat_period_inline()
            )
            return
        
        # Отображаем сделки
        TRADES_PER_PAGE = 3
        total_pages = (len(filtered_orders) + TRADES_PER_PAGE - 1) // TRADES_PER_PAGE
        start_idx = page * TRADES_PER_PAGE
        end_idx = min(start_idx + TRADES_PER_PAGE, len(filtered_orders))
        
        message = f"📊 <b>{title.capitalize()} сделки {period_text} (страница {page+1}/{total_pages}):</b>\n\n"
        
        for order in filtered_orders[start_idx:end_idx]:
            buy_price = order.get('coin_buy_price', order.get('buy_price', 0))
            sale_price = order.get('coin_sale_price', order.get('sale_price', 0))
            
            if buy_price and sale_price:
                profit_percent = ((sale_price - buy_price) / buy_price) * 100
                symbol = "✅" if profit_percent > 0 else "❌"
                
                time_str = ""
                if isinstance(order.get('sale_time'), str):
                    time_str = order['sale_time']
                else:
                    time_str = dt.fromtimestamp(order['create_at']).strftime('%d.%m.%Y %H:%M:%S')
                
                invest_amount = order.get('invest_amount', order.get('investment_amount_usdt', 0))
                
                message += f"{symbol} <b>{order['symbol']}:</b>\n" \
                          f"📅 {time_str}\n" \
                          f"💰 Инвестировано: ${round(invest_amount, 2)}\n" \
                          f"📈 Цена входа: ${round(buy_price, 8)}\n" \
                          f"📉 Цена выхода: ${round(sale_price, 8)}\n" \
                          f"🔄 P&L: {round(profit_percent, 2)}%\n\n"
        
        # Create navigation buttons
        keyboard = []
        if total_pages > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton(text='◀️', callback_data=f'stat {action} {page-1}'))
            row.append(InlineKeyboardButton(text=f'{page+1}/{total_pages}', callback_data='none'))
            if page < total_pages - 1:
                row.append(InlineKeyboardButton(text='▶️', callback_data=f'stat {action} {page+1}'))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(text='Назад к статистике', callback_data=f'stat period_{period_type}')])
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(text=message, reply_markup=markup, parse_mode='HTML')
    
    else:
        await callback.message.edit_text(
            text="Неизвестная команда. Возврат к главному меню статистики.",
            reply_markup=stat_inline(0, 0)
        )

@router.message(Command("start"))
async def start_message(message: Message, bot: Bot):
    if not await get_user(message.from_user.id):
        await set_user(message.from_user.id, 5.0, 50000.0)
        # Initialize default strategy parameters for the new user
        reset_user_params(message.from_user.id)
    user = await get_user(message.from_user.id)
    await message.answer(
        f"Бот по обработке фильтра CM_Laguerre PPO PercentileRank Mkt Tops & Bottoms\nВаш баланс: {round(user['balance'])}$  💸",
        reply_markup=start_inline()
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
            
        # Create a list of all orders
        msg = "📋 Список всех ваших сделок:\n\n"
        
        for i, form in enumerate(all_forms, 1):
            status = "🟢 Открыта" if form.get('sale_price') is None else "🔴 Закрыта"
            profit_loss = ""
            if form.get('sale_price') is not None:
                if form['buy_price'] < form['sale_price']:
                    profit = form['sale_price'] - form['buy_price']
                    profit_loss = f"(+{round(profit, 2)}$💸)"
                else:
                    loss = form['buy_price'] - form['sale_price'] 
                    profit_loss = f"(-{round(loss, 2)}$🤕)"
                    
            msg += f"{i}. {form['symbol']} | {interval_conv(form['interval'])} | {status} {profit_loss}\n"
            
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
            forms = [form for form in forms if form.get('sale_price', 0) > form.get('buy_price', 0)]
            title = "прибыльных"
        else:
            forms = [form for form in forms if form.get('sale_price', 0) < form.get('buy_price', 0)]
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
            if action == 'profit':
                profit = form['sale_price'] - form['buy_price']
                profit_text = f"(+{round(profit, 2)}$💸)"
            else:
                loss = form['buy_price'] - form['sale_price']
                profit_text = f"(-{round(loss, 2)}$🤕)"
                
            msg += f"{i}. {form['symbol']} | {interval_conv(form['interval'])} | {profit_text} | {form['sale_time']}\n"
        
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
        forms = await get_all_orders(callback.from_user.id, action)
        
        if not forms:
            await callback.message.edit_text(
                text=f'У вас пока нет {"открытых" if action == "open" else "закрытых"} сделок',
                reply_markup=orders_inline(len(await get_all_orders(callback.from_user.id, 'open')), 
                                          len(await get_all_orders(callback.from_user.id, 'close')))
            )
            return
            
        # Create a list of all orders of this type
        msg = f"📋 Список {'открытых' if action == 'open' else 'закрытых'} сделок:\n\n"
        
        for i, form in enumerate(forms, 1):
            if action == 'open':
                msg += f"{i}. {form['symbol']} | {interval_conv(form['interval'])} | {round(form['buy_price'], 2)}$ | {form['buy_time']}\n"
            else:
                profit_loss = ""
                if form['buy_price'] < form['sale_price']:
                    profit = form['sale_price'] - form['buy_price']
                    profit_loss = f"(+{round(profit, 2)}$💸)"
                else:
                    loss = form['buy_price'] - form['sale_price']
                    profit_loss = f"(-{round(loss, 2)}$🤕)"
                
                msg += f"{i}. {form['symbol']} | {interval_conv(form['interval'])} | {profit_loss} | {form['sale_time']}\n"
        
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
    else:
        # For individual order view (deprecated but kept for compatibility)
        forms = await get_all_orders(callback.from_user.id, action)
        n = int(callback.data.split()[2])
        if n < 0:
            await callback.answer('Это начало')
            return
        if n >= len(forms):
            await callback.answer('Это конец списка')
            return

        form = forms[n]
        msg = f"Инструмент: {form['symbol']} | {interval_conv(form['interval'])}\n\n"
        msg += f"Цена открытия: {round(form['coin_buy_price'], 2)}$ 📈\n"

        if action == 'open':
            msg += f"Объем сделки: {round(form['buy_price'], 2)}$ 💵\n\n"
            msg += f"Дата и время открытия:\n⏱️{form['buy_time']}\n"
        else:
            msg += f"Цена закрытия: {round(form['coin_sale_price'], 2)}$ 📈\n"

            if form['buy_price'] < form['sale_price']:
                profit = form['sale_price'] - form['buy_price']
                msg += f"Прибыль: {round(profit, 2)}$💸🔋\n\n"
            else:
                profit = form['buy_price'] - form['sale_price']
                msg += f"Убыток: {round(profit, 2)}$🤕🪫\n\n"

            msg += f"Объем сделки: {round(form['buy_price'], 2)}$ 💵\n\n"
            msg += f"Дата и время закрытия:\n⏱️{form['sale_time']}\n\n"
            msg += f"Сделка была открыта:\n⏱️{form['buy_time']}\n"
        await callback.message.edit_text(
            text=msg,
            reply_markup=orders_inline_n(n, action, len(forms), "orders")
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

        file_name = create_xls(columns, data)

        # Отправка файла в Telegram
        xls_file = FSInputFile(file_name)  # Создаем FSInputFile с путем к файлу

        with open(file_name, 'rb') as file:
            await bot.send_document(chat_id=callback.from_user.id, document=xls_file, caption="Вот ваш файл 📄")

    elif action == 'stat':
        columns, data = await fetch_stat(callback.from_user.id)

        if not data:
            await callback.answer("Нет данных для отображения.")
            return

        # Создаем Excel файл
        file_name = create_xls(columns, data, file_name="orders_stat.xlsx")

        # Отправка файла в Telegram
        xls_file = FSInputFile(file_name)

        with open(file_name, 'rb') as file:
            await bot.send_document(chat_id=callback.from_user.id, document=xls_file, caption="Вот ваш файл с заказами 📄")


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


@router.callback_query(F.data.startswith('settings'))
async def settings(callback: CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split()[1]
    if action == 'start':
        await callback.message.edit_text(
            "Настройки\n\n"
            "Выберите раздел:",
            reply_markup=settings_inline()
        )
    elif action == 'percent':
        msg = await callback.message.edit_text(
            f"Изменение процента для показа новых сделок и сигналов\n"
            f"Введите новое значение:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Назад', callback_data='settings start')]
            ])
        )
        await state.set_state(EditPercent.new)
        await state.update_data(last_msg=msg.message_id)
    elif action == 'strategy':
        user_params = load_user_params(callback.from_user.id)
        text = "Настройки параметров торговой стратегии Moon Bot\n\n"
        
        # Display current parameters
        text += "📊 Текущие параметры:\n"
        text += f"💰 Объем ордера: {user_params['OrderSize']} USDT\n"
        text += f"📈 Take Profit: {user_params['TakeProfit']}%\n"
        text += f"📉 Stop Loss: {user_params['StopLoss']}%\n"
        text += f"📊 Мин. объем торгов: {user_params['MinVolume']}\n"
        text += f"📊 Макс. объем торгов: {user_params['MaxVolume']}\n"
        text += f"🕒 Макс. движение за 3ч: {user_params['Delta_3h_Max']}%\n"
        text += f"🕒 Макс. движение за 24ч: {user_params['Delta_24h_Max']}%\n"
        text += f"🕒 Макс. движение за 5м: {user_params['Delta2_Max']}%\n"
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
        
        text = "⚙️ Настройки индикатора CM (Congestion Measure)\n\n"
        
        # Отображаем текущие параметры CM
        text += "📊 Текущие параметры:\n"
        text += f"SHORT_GAMMA: {cm_settings['SHORT_GAMMA']:.2f}\n"
        text += f"LONG_GAMMA: {cm_settings['LONG_GAMMA']:.2f}\n"
        text += f"LOOKBACK_T: {cm_settings['LOOKBACK_T']}\n"
        text += f"LOOKBACK_B: {cm_settings['LOOKBACK_B']}\n"
        text += f"PCTILE: {cm_settings['PCTILE']}\n\n"
        
        text += "Выберите параметр для изменения:"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=cm_params_inline()
        )

@router.callback_query(F.data.startswith('strategy'))
async def strategy_params(callback: CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split()[1]
    if action == 'reset':
        reset_user_params(callback.from_user.id)
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
        text += f"📊 Мин. объем торгов: {default_params['MinVolume']}\n"
        text += f"📊 Макс. объем торгов: {default_params['MaxVolume']}\n"
        text += f"🕒 Макс. движение за 3ч: {default_params['Delta_3h_Max']}%\n"
        text += f"🕒 Макс. движение за 24ч: {default_params['Delta_24h_Max']}%\n"
        text += f"🕒 Макс. движение за 5м: {default_params['Delta2_Max']}%\n"
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
        
        # Convert input to proper type
        param_value = float(message.text.strip())
        
        # Update parameter
        success = update_user_param(message.from_user.id, param_name, param_value)
        
        if success:
            await message.answer(f"Параметр {param_name} успешно обновлен на {param_value}")
            
            # Get updated parameters
            user_params = load_user_params(message.from_user.id)
            
            text = "Настройки параметров торговой стратегии Moon Bot\n\n"
            
            # Display current parameters
            text += "📊 Текущие параметры:\n"
            text += f"💰 Объем ордера: {user_params['OrderSize']} USDT\n"
            text += f"📈 Take Profit: {user_params['TakeProfit']}%\n"
            text += f"📉 Stop Loss: {user_params['StopLoss']}%\n"
            text += f"📊 Мин. объем торгов: {user_params['MinVolume']}\n"
            text += f"📊 Макс. объем торгов: {user_params['MaxVolume']}\n"
            text += f"🕒 Макс. движение за 3ч: {user_params['Delta_3h_Max']}%\n"
            text += f"🕒 Макс. движение за 24ч: {user_params['Delta_24h_Max']}%\n"
            text += f"🕒 Макс. движение за 5м: {user_params['Delta2_Max']}%\n"
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
        
        # Process blacklist input
        blacklist_str = message.text.strip().upper()
        
        # Update parameter
        success = update_user_param(message.from_user.id, 'CoinsBlackList', blacklist_str)
        
        if success:
            await message.answer("Черный список монет успешно обновлен")
            
            # Get updated parameters
            user_params = load_user_params(message.from_user.id)
            
            text = "Настройки параметров торговой стратегии Moon Bot\n\n"
            
            # Display current parameters
            text += "📊 Текущие параметры:\n"
            text += f"💰 Объем ордера: {user_params['OrderSize']} USDT\n"
            text += f"📈 Take Profit: {user_params['TakeProfit']}%\n"
            text += f"📉 Stop Loss: {user_params['StopLoss']}%\n"
            text += f"📊 Мин. объем торгов: {user_params['MinVolume']}\n"
            text += f"📊 Макс. объем торгов: {user_params['MaxVolume']}\n"
            text += f"🕒 Макс. движение за 3ч: {user_params['Delta_3h_Max']}%\n"
            text += f"🕒 Макс. движение за 24ч: {user_params['Delta_24h_Max']}%\n"
            text += f"🕒 Макс. движение за 5м: {user_params['Delta2_Max']}%\n"
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
    user = await get_user(callback.from_user.id)
    await callback.message.edit_text(
        text=f"Бот по обработке фильтра CM_Laguerre PPO PercentileRank Mkt Tops & Bottoms\nВаш баланс: {round(user['balance'])}$  💸",
        reply_markup=start_inline()
    )

@router.callback_query(F.data.startswith('cm'))
async def cm_params(callback: CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split()[1]
    
    if action == 'reset':
        # Сброс настроек CM индикатора к стандартным
        reset_cm_settings(callback.from_user.id)
        await callback.answer("Настройки CM индикатора сброшены к стандартным значениям")
        
        # Получаем стандартные настройки
        cm_settings = load_cm_settings(callback.from_user.id)
        
        text = "⚙️ Настройки индикатора CM (Congestion Measure)\n\n"
        text += "Параметры сброшены к стандартным значениям.\n\n"
        
        # Отображаем текущие параметры
        text += "📊 Текущие параметры:\n"
        text += f"SHORT_GAMMA: {cm_settings['SHORT_GAMMA']:.2f}\n"
        text += f"LONG_GAMMA: {cm_settings['LONG_GAMMA']:.2f}\n"
        text += f"LOOKBACK_T: {cm_settings['LOOKBACK_T']}\n"
        text += f"LOOKBACK_B: {cm_settings['LOOKBACK_B']}\n"
        text += f"PCTILE: {cm_settings['PCTILE']}\n\n"
        
        text += "Выберите параметр для изменения:"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=cm_params_inline()
        )
    elif action in ['SHORT_GAMMA', 'LONG_GAMMA', 'LOOKBACK_T', 'LOOKBACK_B', 'PCTILE']:
        # Редактирование параметра CM
        cm_settings = load_cm_settings(callback.from_user.id)
        current_value = cm_settings.get(action, "не установлено")
        
        kb = [
            [InlineKeyboardButton(text='Назад', callback_data='settings cm')]
        ]
        
        msg = await callback.message.edit_text(
            f"Изменение параметра: {action}\n"
            f"Текущее значение: {current_value}\n\n"
            f"Введите новое значение:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
        
        await state.set_state(CMParamStates.edit_param)
        await state.update_data(param_name=action, last_msg=msg.message_id)

@router.message(CMParamStates.edit_param)
async def process_cm_param_edit(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    param_name = data.get('param_name')
    
    try:
        # Удаляем предыдущее сообщение
        try:
            await bot.delete_message(message_id=data.get('last_msg'), chat_id=message.from_user.id)
        except Exception:
            pass
        
        # Преобразуем входное значение в нужный тип
        param_value = float(message.text.strip())
        
        # Обновляем параметр
        success = update_cm_setting(message.from_user.id, param_name, param_value)
        
        if success:
            await message.answer(f"Параметр {param_name} успешно обновлен на {param_value}")
            
            # Получаем обновленные настройки
            cm_settings = load_cm_settings(message.from_user.id)
            
            text = "⚙️ Настройки индикатора CM (Congestion Measure)\n\n"
            
            # Отображаем текущие параметры
            text += "📊 Текущие параметры:\n"
            text += f"SHORT_GAMMA: {cm_settings['SHORT_GAMMA']:.2f}\n"
            text += f"LONG_GAMMA: {cm_settings['LONG_GAMMA']:.2f}\n"
            text += f"LOOKBACK_T: {cm_settings['LOOKBACK_T']}\n"
            text += f"LOOKBACK_B: {cm_settings['LOOKBACK_B']}\n"
            text += f"PCTILE: {cm_settings['PCTILE']}\n\n"
            
            text += "Выберите параметр для изменения:"
            
            # Показываем меню настроек CM с текущими параметрами
            await message.answer(
                text=text,
                reply_markup=cm_params_inline()
            )
        else:
            await message.answer(f"Не удалось обновить параметр {param_name}")
            await message.answer(
                "⚙️ Настройки индикатора CM (Congestion Measure)\n\n"
                "Выберите параметр для изменения:",
                reply_markup=cm_params_inline()
            )
    except ValueError:
        await message.answer(
            "Ошибка: значение должно быть числом.\n"
            "Попробуйте еще раз:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Назад', callback_data='settings cm')]
            ])
        )
    
    await state.clear()
