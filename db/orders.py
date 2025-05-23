import asyncpg, datetime as dt
from db.connect import connect
import aiosqlite
from strategy_logic.trading_settings import load_trading_settings

async def get_user_balance(user_id):
    """Получение баланса пользователя из таблицы users"""
    conn = await connect()
    row = await conn.fetchrow("""
        SELECT balance FROM users WHERE user_id=$1
    """, user_id)
    await conn.close()
    
    if row:
        return row['balance']
    return 0.0  # Если пользователь не найден, возвращаем 0




async def update_user_balance(user_id, amount):
    """Обновление баланса пользователя"""
    conn = await connect()
    await conn.execute("""
        UPDATE users SET balance = balance + $2 WHERE user_id=$1
    """, user_id, amount)
    await conn.close()
    
    # Возвращаем новый баланс
    return await get_user_balance(user_id)

async def create_order(user_id, exchange, symbol, interval, side, qty,
                       buy_price, tp, sl, trading_type=None, leverage=None):
    """Создание ордера и списание средств с баланса пользователя"""
    # Если trading_type и leverage не указаны, загружаем из настроек пользователя
    if trading_type is None or leverage is None:
        trading_settings = load_trading_settings(user_id)
        trading_type = trading_settings["trading_type"] if trading_type is None else trading_type
        leverage = trading_settings["leverage"] if leverage is None else leverage
    
    print(f"DEBUG [create_order]: user_id={user_id}, exchange={exchange}, symbol={symbol}, trading_type={trading_type}, leverage={leverage}")
    
    # Валидация параметров
    if trading_type == "spot" and side.upper() == "SHORT":
        print(f"ОШИБКА: SHORT позиции недоступны для spot торговли user_id={user_id}")
        raise ValueError("SHORT позиции недоступны для spot торговли")
    
    if trading_type == "spot" and leverage != 1:
        print(f"ПРЕДУПРЕЖДЕНИЕ: Для spot торговли плечо всегда 1, исправлено с {leverage} для user_id={user_id}")
        leverage = 1  # Для spot торговли плечо всегда 1
    
    # Проверка валидности плеча
    if trading_type == "futures" and (leverage < 1 or leverage > 125):
        original_leverage = leverage
        leverage = max(1, min(125, leverage))
        print(f"ПРЕДУПРЕЖДЕНИЕ: Некорректное плечо {original_leverage}, исправлено на {leverage} для user_id={user_id}")
    
    # Рассчитываем сумму инвестиции с учетом плеча
    if trading_type == "futures":
        investment_amount = (qty * buy_price) / leverage
        print(f"Расчет futures: qty={qty}, price={buy_price}, leverage={leverage}, investment={investment_amount}")
    else:
        investment_amount = qty * buy_price
        print(f"Расчет spot: qty={qty}, price={buy_price}, investment={investment_amount}")
    
    # Проверяем, достаточно ли средств у пользователя
    user_balance = await get_user_balance(user_id)
    if user_balance < investment_amount:
        print(f"ОШИБКА: Недостаточно средств: баланс={user_balance}, требуется={investment_amount} для user_id={user_id}")
        raise ValueError(f"Недостаточно средств: {user_balance} < {investment_amount}")
    
    # Списываем средства с баланса
    await update_user_balance(user_id, -investment_amount)
    
    # Создаем запись о сделке с учетом типа торговли и плеча
    conn = await connect()
    try:
        order_id = await conn.fetchval("""
            INSERT INTO orders (user_id, exchange, symbol, interval, side, qty,
                               coin_buy_price, tp_price, sl_price, buy_time,
                               investment_amount_usdt, trading_type, leverage)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id
        """, user_id, exchange, symbol, interval, side.upper(), qty,
            buy_price, tp, sl, dt.datetime.utcnow(), investment_amount,
            trading_type, leverage)
        
        print(f"УСПЕХ: Создан ордер id={order_id} для user_id={user_id}, exchange={exchange}, symbol={symbol}, side={side}, leverage={leverage}")
        return order_id
    finally:
        await conn.close()

async def get_open_order(user_id, exchange, symbol, interval):
    conn = await connect()
    row = await conn.fetchrow("""
        SELECT * FROM orders
        WHERE user_id=$1 AND exchange=$2 AND symbol=$3 AND interval=$4 AND status='OPEN'
        ORDER BY buy_time DESC LIMIT 1
    """, user_id, exchange, symbol, interval)
    await conn.close()
    return row

async def close_order(order_id, sale_price):
    """Закрытие ордера с расчетом прибыли/убытка и возвратом средств на баланс"""
    # Убедимся, что sale_price - число
    sale_price = float(sale_price)
    
    conn = await connect()
    try:
        # Начинаем транзакцию
        tr = conn.transaction()
        await tr.start()
        
        # Получаем данные ордера перед закрытием
        order_data = await conn.fetchrow("""
            SELECT user_id, qty, coin_buy_price, investment_amount_usdt, side, trading_type, leverage, status
            FROM orders WHERE id=$1
        """, order_id)
        
        if not order_data:
            raise Exception(f"Ордер с ID {order_id} не найден")
            
        # Проверка на статус ордера
        if order_data['status'] == 'CLOSED':
            print(f"Предупреждение: Ордер {order_id} уже закрыт. Пропускаем закрытие.")
            await tr.rollback()
            return None
        
        user_id = order_data['user_id']
        qty = float(order_data['qty'])
        entry_price = float(order_data['coin_buy_price'])
        side = order_data['side']
        trading_type = order_data['trading_type']
        leverage = int(order_data['leverage'])
        
        # Рассчитываем прибыль/убыток с учетом типа позиции и плеча
        if side == 'LONG':
            # Базовый PnL в USDT (без учета плеча)
            base_pnl_usdt = (sale_price - entry_price) * qty
            price_change_percent = ((sale_price - entry_price) / entry_price) * 100
            
            # Применяем плечо для futures
            if trading_type == 'futures':
                pnl_percent = price_change_percent * leverage
                pnl_usdt = base_pnl_usdt * leverage
                print(f"[PNL_DEBUG] LONG: base_pnl={base_pnl_usdt:.2f}USDT (base: {price_change_percent:.2f}%), with leverage {leverage}x: {pnl_usdt:.2f}USDT ({pnl_percent:.2f}%)")
            else:
                pnl_percent = price_change_percent
                pnl_usdt = base_pnl_usdt
                print(f"[PNL_DEBUG] LONG SPOT: pnl={base_pnl_usdt:.2f}USDT ({price_change_percent:.2f}%)")
        else:  # SHORT
            # Базовый PnL в USDT (без учета плеча)
            base_pnl_usdt = (entry_price - sale_price) * qty
            price_change_percent = ((entry_price - sale_price) / entry_price) * 100
            
            # Применяем плечо для конечного PnL в USDT (SHORT доступен только в futures)
            pnl_percent = price_change_percent * leverage
            pnl_usdt = base_pnl_usdt * leverage
            print(f"[PNL_DEBUG] SHORT: base_pnl={base_pnl_usdt:.2f}USDT (base: {price_change_percent:.2f}%), with leverage {leverage}x: {pnl_usdt:.2f}USDT ({pnl_percent:.2f}%)")
        
        # Сумма к возврату: вложенные средства + прибыль (или - убыток)
        # Преобразуем Decimal в float
        invested = float(order_data['investment_amount_usdt'])
        pnl_usdt = float(pnl_usdt)
        return_amount = invested + pnl_usdt
        
        # Проверка на ликвидацию (для futures с плечом)
        # Если потери превышают вложенную сумму, возвращаем 0
        if trading_type == 'futures' and return_amount < 0:
            return_amount = 0
            pnl_percent = -100
            pnl_usdt = -invested
          
          
        # Обновляем баланс пользователя (в озвращаем средства с учетом P&L)
        await conn.execute("""
            UPDATE users SET balance = balance + $2 WHERE user_id=$1
        """, user_id, return_amount)
        
        # Обновляем статус ордера
        result = await conn.fetchrow("""
            UPDATE orders
            SET coin_sale_price=$2::real,
                sale_time=$3,
                status='CLOSED',
                pnl_percent=$4::numeric,
                pnl_usdt=$5::real,
                return_amount_usdt=$6::real
            WHERE id=$1 AND status='OPEN'
            RETURNING id, user_id, qty, coin_buy_price, CAST($2 AS real) as coin_sale_price, 
                      CAST($4 AS numeric) as pnl_percent, CAST($5 AS real) as pnl_usdt, 
                      CAST($6 AS real) as return_amount_usdt, side, trading_type, leverage
        """, order_id, sale_price, dt.datetime.utcnow(), 
            pnl_percent, pnl_usdt, return_amount)
        
        # Проверяем, был ли обновлен ордер (если ордер уже был закрыт, result будет None)
        if not result:
            print(f"Предупреждение: Ордер {order_id} не был обновлен (возможно уже закрыт). Отменяем транзакцию.")
            await tr.rollback()
            return None
            
        # Получаем новый баланс пользователя для логирования
        new_balance = await get_user_balance(user_id)
        print(f"Новый баланс пользователя {user_id} после закрытия ордера: {new_balance} (+{return_amount})")
        
        # Завершаем транзакцию
        await tr.commit()
        
        return result
    except Exception as e:
        # В случае ошибки отменяем все изменения
        await tr.rollback()
        print(f"Ошибка при закрытии ордера: {e}")
        raise
    finally:
        await conn.close()

# Add the missing functions
async def get_user_open_orders(user_id):
    """Получение списка открытых ордеров пользователя"""
    return await get_all_orders(user_id, 'open')

async def get_user_closed_orders(user_id):
    """Получение списка закрытых ордеров пользователя"""
    return await get_all_orders(user_id, 'close')

# Helper function to get all orders of a specific type (open/closed)
async def get_all_orders(user_id, order_type, from_date=None):
    """Получение всех ордеров определенного типа для пользователя"""
    conn = await connect()
    try:
        if order_type == 'open':
            rows = await conn.fetch("""
                SELECT * FROM orders
                WHERE user_id=$1 AND status='OPEN'
                ORDER BY buy_time DESC
            """, user_id)
        elif order_type == 'close':
            # If from_date is provided, filter by sale_time
            if from_date is not None:
                rows = await conn.fetch("""
                    SELECT * FROM orders
                    WHERE user_id=$1 AND status='CLOSED'
                    AND EXTRACT(EPOCH FROM sale_time) >= $2
                    ORDER BY sale_time DESC
                """, user_id, from_date)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM orders
                    WHERE user_id=$1 AND status='CLOSED'
                    ORDER BY sale_time DESC
                """, user_id)
        else:
            # Default to returning all orders
            rows = await conn.fetch("""
                SELECT * FROM orders
                WHERE user_id=$1
                ORDER BY buy_time DESC
            """, user_id)
        
        return [dict(row) for row in rows]
    finally:
        await conn.close()

async def get_daily_profit(user_id, date):
    """
    Получить суммарный профит пользователя за указанный день
    :param user_id: ID пользователя
    :param date: Дата (объект datetime.date или строка в формате YYYY-MM-DD)
    :return: Суммарный профит в USDT
    """
    conn = await connect()
    try:
        # Конвертируем дату в строку для логирования
        date_for_log = str(date)
        
        # Преобразуем все входные данные в datetime.date объект
        if isinstance(date, str):
            try:
                # Проверяем формат YYYY-MM-DD
                date_obj = dt.datetime.strptime(date, '%Y-%m-%d').date()
            except ValueError:
                try:
                    # Проверяем формат DD.MM.YYYY
                    date_obj = dt.datetime.strptime(date, '%d.%m.%Y').date()
                except ValueError:
                    # Если не удалось распознать формат, используем текущую дату
                    print(f"Невалидный формат даты: {date}, используем текущую дату")
                    date_obj = dt.date.today()
        elif isinstance(date, dt.datetime):
            # Если передан datetime, преобразуем в date
            date_obj = date.date()
        elif isinstance(date, dt.date):
            # Если уже date, используем как есть
            date_obj = date
        else:
            # Если неизвестный тип, используем текущую дату
            print(f"Неизвестный тип даты: {type(date)}, используем текущую дату")
            date_obj = dt.date.today()
        
        # Преобразуем date_obj в строку YYYY-MM-DD для SQL запроса
        date_str = date_obj.strftime('%Y-%m-%d')
        
        print(f"Получение профита для пользователя {user_id} на дату: {date_for_log} (преобразовано в {date_str})")
        
        # Запрос на получение суммы прибыли за день с использованием текстового сравнения дат
        row = await conn.fetchrow("""
            SELECT SUM(pnl_usdt) as daily_profit
            FROM orders 
            WHERE user_id = $1 
            AND status = 'CLOSED'
            AND TO_CHAR(sale_time, 'YYYY-MM-DD') = $2
        """, user_id, date_str)
        
        # Если нет закрытых ордеров или сумма NULL, возвращаем 0
        return row['daily_profit'] if row and row['daily_profit'] is not None else 0.0
    except Exception as e:
        print(f"Ошибка при получении дневного профита: {e}")
        return 0.0
    finally:
        await conn.close()

async def get_order_by_id(order_id):
    """Получение информации о конкретном ордере по его ID"""
    conn = await connect()
    row = await conn.fetchrow("""
        SELECT * FROM orders
        WHERE id=$1
    """, order_id)
    await conn.close()
    return dict(row) if row else None

# Aliases and additional functions needed by main_strategy.py
async def get_open_orders(user_id):
    """Алиас для get_user_open_orders для совместимости"""
    return await get_user_open_orders(user_id)
    
async def save_order(user_id, exchange, symbol, interval, side, qty, entry_price, tp_price, sl_price, trading_type=None, leverage=None):
    """Сохранение нового ордера (алиас для create_order для совместимости)"""
    return await create_order(user_id, exchange, symbol, interval, side, qty, entry_price, tp_price, sl_price, trading_type, leverage)

async def get_active_positions(user_id, exchange=None):
    """Получение всех активных позиций пользователя"""
    conn = await connect()
    try:
        if exchange:
            rows = await conn.fetch("""
                SELECT * FROM orders
                WHERE user_id=$1 AND exchange=$2 AND status='OPEN'
                ORDER BY buy_time DESC
            """, user_id, exchange)
        else:
            rows = await conn.fetch("""
                SELECT * FROM orders
                WHERE user_id=$1 AND status='OPEN'
                ORDER BY buy_time DESC
            """, user_id)
        
        return [dict(row) for row in rows]
    finally:
        await conn.close()
    
async def get_active_btc_position_size(user_id, exchange=None):
    """Получение активной BTC позиции пользователя"""
    conn = await connect()
    try:
        if exchange:
            row = await conn.fetchrow("""
                SELECT SUM(qty * coin_buy_price) as position_size
                FROM orders
                WHERE user_id=$1 AND exchange=$2 AND symbol='BTCUSDT' AND status='OPEN'
            """, user_id, exchange)
        else:
            row = await conn.fetchrow("""
                SELECT SUM(qty * coin_buy_price) as position_size
                FROM orders
                WHERE user_id=$1 AND symbol='BTCUSDT' AND status='OPEN'
            """, user_id)
        
        await conn.close()
        return row['position_size'] if row and row['position_size'] is not None else 0.0
    finally:
        await conn.close()

async def init_db():
    """Инициализирует базу данных, проверяет и добавляет необходимые колонки."""
    conn = await connect()
    try:
        # Создаем таблицу users, если она еще не существует
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    balance REAL DEFAULT 1000.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except asyncpg.exceptions.InsufficientPrivilegeError:
            print("Недостаточно прав для создания таблицы users. Продолжаем работу с существующей.")
        
        # Создаем таблицу orders, если она еще не существует
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    exchange TEXT,
                    symbol TEXT,
                    interval TEXT,
                    side TEXT,
                    qty REAL,
                    coin_buy_price REAL,
                    coin_sale_price REAL,
                    buy_time TIMESTAMP,
                    sale_time TIMESTAMP,
                    tp_price REAL,
                    sl_price REAL,
                    status TEXT DEFAULT 'OPEN',
                    pnl_percent NUMERIC,
                    pnl_usdt REAL,
                    return_amount_usdt REAL,
                    investment_amount_usdt REAL,
                    trading_type TEXT DEFAULT 'spot',
                    leverage INTEGER DEFAULT 1
                )
            """)
        except asyncpg.exceptions.InsufficientPrivilegeError:
            print("Недостаточно прав для создания таблицы orders. Продолжаем работу с существующей.")
        
        print("База данных инициализирована успешно")
    except Exception as e:
        print(f"Ошибка при инициализации базы данных: {e}")
        # Продолжаем работу даже при ошибках
    finally:
        await conn.close()

async def calculate_max_position_size(user_id, symbol, leverage=1):
    """
    Расчет максимального размера позиции с учетом плеча
    :param user_id: ID пользователя
    :param symbol: Торговая пара
    :param leverage: Плечо (по умолчанию 1 для spot)
    :return: Максимальный размер позиции в единицах базовой валюты
    """
    # Получаем баланс пользователя
    balance = await get_user_balance(user_id)
    
    # Получаем текущую цену актива
    # Здесь предполагается, что у вас есть функция для получения текущей цены
    # Например:
    # current_price = await get_current_price(symbol)
    # Для примера предположим, что цена BTC - 50000 USDT
    current_price = 50000  # Замените на реальное получение цены
    
    # Рассчитываем максимальное количество с учетом плеча
    # Обычно используется не весь баланс, а часть (например, 80%)
    safe_balance = balance * 0.8  # Используем 80% от доступного баланса
    
    # С учетом плеча
    max_position_value = safe_balance * leverage
    
    # Конвертируем в количество базовой валюты
    max_qty = max_position_value / current_price
    
    return max_qty


