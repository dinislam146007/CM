import asyncpg, datetime as dt
from db.connect import connect

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
        pnl_percent = ((sale_price - entry_price) / entry_price) * 100
        # Сумма к возврату: вложенные средства + прибыль (или - убыток)
        return_amount = qty * sale_price  # Текущая стоимость позиции
        
        # Обновляем баланс пользователя (возвращаем средства с учетом P&L)
        await conn.execute("""
            UPDATE users SET balance = balance + $2 WHERE user_id=$1
        """, user_id, return_amount)
        
        # Обновляем статус ордера
        result = await conn.fetchrow("""
            UPDATE orders
            SET coin_sale_price=$2,
                sale_time=$3,
                status='CLOSED',
                pnl_percent=$4,
                pnl_usdt=$5,
                return_amount_usdt=$6
            WHERE id=$1
            RETURNING id, user_id, qty, coin_buy_price, $2 as coin_sale_price, 
                      $4 as pnl_percent, $5 as pnl_usdt, $6 as return_amount_usdt
        """, order_id, sale_price, dt.datetime.utcnow(), 
            pnl_percent, (sale_price - entry_price) * qty, return_amount)
        
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


