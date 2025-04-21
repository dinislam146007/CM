import asyncpg, datetime as dt
from db.connect import connect

async def create_order(user_id, symbol, interval, side, qty,
                       buy_price, tp, sl):
    conn = await connect()
    await conn.execute("""
        INSERT INTO orders (user_id,symbol,interval,side,qty,
                            coin_buy_price,tp_price,sl_price,buy_time)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
    """, user_id, symbol, interval, side, qty,
         buy_price, tp, sl, dt.datetime.utcnow())
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
    conn = await connect()
    await conn.execute("""
        UPDATE orders
        SET coin_sale_price=$2,
            sale_time=$3,
            status='CLOSED',
            pnl_usdt = (sale_price - coin_buy_price) * qty
        FROM (
            SELECT qty, coin_buy_price
            FROM orders WHERE id=$1
        ) as o
        WHERE id=$1
    """, order_id, sale_price, dt.datetime.utcnow())
    await conn.close()


