import asyncpg, datetime as dt
from db.connect import connect
import aiosqlite

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

async def create_order(user_id, symbol, interval, side, qty,
                       buy_price, tp, sl):
    """Создание ордера и списание средств с баланса пользователя"""
    # Рассчитываем сумму инвестиции
    investment_amount = qty * buy_price
    
    # Списываем средства с баланса
    conn = await connect()
    try:
        # Начинаем транзакцию
        tr = conn.transaction()
        await tr.start()
        
        # Обновляем баланс пользователя (списываем средства)
        await conn.execute("""
            UPDATE users SET balance = balance - $2 WHERE user_id=$1
        """, user_id, investment_amount)
        
        # Создаем запись о сделке
        await conn.execute("""
            INSERT INTO orders (user_id, symbol, interval, side, qty,
                               coin_buy_price, tp_price, sl_price, buy_time,
                               investment_amount_usdt)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, user_id, symbol, interval, side, qty,
            buy_price, tp, sl, dt.datetime.utcnow(), investment_amount)
        
        # Завершаем транзакцию
        await tr.commit()
    except Exception as e:
        # В случае ошибки отменяем все изменения
        await tr.rollback()
        print(f"Ошибка при создании ордера: {e}")
        raise
    finally:
        await conn.close()

async def get_open_order(user_id, symbol, interval):
    conn = await connect()
    row = await conn.fetchrow("""
        SELECT * FROM orders
        WHERE user_id=$1 AND symbol=$2 AND interval=$3 AND status='OPEN'
        ORDER BY buy_time DESC LIMIT 1
    """, user_id, symbol, interval)
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
            SELECT user_id, qty, coin_buy_price, investment_amount_usdt
            FROM orders WHERE id=$1
        """, order_id)
        
        if not order_data:
            raise Exception(f"Ордер с ID {order_id} не найден")
        
        user_id = order_data['user_id']
        qty = order_data['qty']
        entry_price = order_data['coin_buy_price']
        
        # Рассчитываем прибыль/убыток
        pnl_percent = float(((sale_price - entry_price) / entry_price) * 100)
        # Сумма к возврату: вложенные средства + прибыль (или - убыток)
        return_amount = float(qty * sale_price)  # Текущая стоимость позиции
        pnl_usdt = float((sale_price - entry_price) * qty)
        
        # Обновляем баланс пользователя (возвращаем средства с учетом P&L)
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
            WHERE id=$1
            RETURNING id, user_id, qty, coin_buy_price, CAST($2 AS real) as coin_sale_price, 
                      CAST($4 AS numeric) as pnl_percent, CAST($5 AS real) as pnl_usdt, CAST($6 AS real) as return_amount_usdt
        """, order_id, sale_price, dt.datetime.utcnow(), 
            pnl_percent, pnl_usdt, return_amount)
        
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
    conn = await connect()
    rows = await conn.fetch("""
        SELECT * FROM orders
        WHERE user_id=$1 AND status='OPEN'
        ORDER BY buy_time DESC
    """, user_id)
    await conn.close()
    return [dict(row) for row in rows]

async def get_user_closed_orders(user_id):
    """Получение списка закрытых ордеров пользователя"""
    conn = await connect()
    rows = await conn.fetch("""
        SELECT * FROM orders
        WHERE user_id=$1 AND status='CLOSED'
        ORDER BY sale_time DESC
    """, user_id)
    await conn.close()
    return [dict(row) for row in rows]

# Helper function to get all orders of a specific type (open/closed)
async def get_all_orders(user_id, order_type):
    """Получение всех ордеров определенного типа для пользователя"""
    if order_type == 'open':
        return await get_user_open_orders(user_id)
    elif order_type == 'close':
        return await get_user_closed_orders(user_id)
    else:
        # Default to returning all orders
        conn = await connect()
        rows = await conn.fetch("""
            SELECT * FROM orders
            WHERE user_id=$1
            ORDER BY buy_time DESC
        """, user_id)
        await conn.close()
        return [dict(row) for row in rows]

async def get_daily_profit(user_id, date):
    """
    Получить суммарный профит пользователя за указанный день
    :param user_id: ID пользователя
    :param date: Дата (объект datetime.date)
    :return: Суммарный профит в USDT
    """
    async with aiosqlite.connect('db/tg_bot.db') as db:
        # Конвертируем дату в строку формата YYYY-MM-DD для сравнения
        date_str = date.strftime('%Y-%m-%d')
        
        # Ищем все закрытые ордера пользователя за указанный день
        cursor = await db.execute(
            """
            SELECT SUM(pnl_usdt) FROM orders 
            WHERE user_id = ? AND status = 'closed' 
            AND strftime('%Y-%m-%d', datetime(close_time, 'unixepoch')) = ?
            """, 
            (user_id, date_str)
        )
        result = await cursor.fetchone()
        
        # Если нет закрытых ордеров или сумма NULL, возвращаем 0
        return result[0] if result and result[0] is not None else 0.0

async def get_order_by_id(order_id):
    """Получение информации о конкретном ордере по его ID"""
    conn = await connect()
    row = await conn.fetchrow("""
        SELECT * FROM orders
        WHERE id=$1
    """, order_id)
    await conn.close()
    return dict(row) if row else None


