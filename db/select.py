from db.connect import connect
from typing import Optional, List
import datetime


async def get_user(user_id: int) -> Optional[dict]:
    conn = await connect()
    row = await conn.fetchrow(
        """
        SELECT * FROM users WHERE user_id = $1
        """,
        user_id
    )
    await conn.close()
    return dict(row) if row else None


# Функции для таблицы signals
async def get_signal(symbol: str, interval: str) -> Optional[dict]:
    conn = await connect()
    row = await conn.fetchrow(
        """
        SELECT * FROM signals WHERE symbol = $1 AND interval = $2
        """,
        symbol, interval
    )
    await conn.close()
    return dict(row) if row else None

# Функции для таблицы orders


async def get_active_order(user_id: int, symbol: str, interval: str) -> Optional[dict]:
    conn = await connect()
    row = await conn.fetchrow(
        """
        SELECT * FROM orders 
        WHERE user_id = $1 AND symbol = $2 AND interval = $3 AND sale_time IS NULL
        """,
        user_id, symbol, interval
    )
    await conn.close()
    return dict(row) if row else None

async def get_user_orders(user_id: int) -> List[dict]:
    conn = await connect()
    rows = await conn.fetch(
        """
        SELECT * FROM orders WHERE user_id = $1
        """,
        user_id
    )
    await conn.close()
    return [dict(row) for row in rows]

# Функции для таблицы subscriptions


async def get_user_subscriptions(user_id: int) -> List[dict]:
    conn = await connect()
    rows = await conn.fetch(
        """
        SELECT * FROM subscriptions WHERE user_id = $1
        """,
        user_id
    )
    await conn.close()
    return [dict(row) for row in rows]

async def get_subscribed_users(symbol: str, interval: str) -> List[dict]:
    conn = await connect()
    rows = await conn.fetch(
        """
        SELECT * FROM subscriptions WHERE symbol = $1 AND interval = $2
        """,
        symbol, interval
    )
    await conn.close()
    return [dict(row) for row in rows]

async def get_order(interval, symbol, user_id):
    conn = await connect()
    row = await conn.fetchrow("""
    SELECT * FROM orders
    WHERE symbol=$1 AND interval=$2 
    AND sale_price IS NULL
    AND user_id = $3
    """, symbol, interval, user_id)
    if row is not None:
        return dict(row)
    return None

async def get_all_user_id():
    conn = await connect()
    rows = await conn.fetch("SELECT * FROM users")
    await conn.close()

    return [dict(row) for row in rows] if rows else []


async def get_all_orders(user_id: int, order_type: str):
    conn = await connect()
    try:
        query = """
        SELECT * FROM orders
        WHERE user_id = $1
        """
        if order_type == 'open':
            query += " AND sale_price IS NULL"
        else:
            query += " AND sale_price IS NOT NULL"

        rows = await conn.fetch(query, user_id)
        return [dict(row) for row in rows] if rows else []
    finally:
        await conn.close()

async def get_signals():
    conn = await connect()
    try:
        query = "SELECT * FROM signals"
        rows = await conn.fetch(query)
        return [dict(row) for row in rows] if rows else []
    finally:
        await conn.close()

async def get_statistics_for_period(user_id: int, start_date: str, end_date: str):
    conn = await connect()
    try:
        total_trades = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE sale_price IS NOT NULL
              AND user_id = $1
              AND sale_time::DATE BETWEEN $2::DATE AND $3::DATE
            """,
            user_id, start_date, end_date
        )

        profitable_trades = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE sale_price > buy_price
              AND sale_price IS NOT NULL
              AND user_id = $1
              AND sale_time::DATE BETWEEN $2::DATE AND $3::DATE
            """,
            user_id, start_date, end_date
        )

        loss_trades = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE sale_price < buy_price
              AND sale_price IS NOT NULL
              AND user_id = $1
              AND sale_time::DATE BETWEEN $2::DATE AND $3::DATE
            """,
            user_id, start_date, end_date
        )

        total_profit = await conn.fetchval(
            """
            SELECT COALESCE(SUM(sale_price - buy_price), 0)
            FROM orders
            WHERE sale_price IS NOT NULL
              AND user_id = $1
              AND sale_time::DATE BETWEEN $2::DATE AND $3::DATE
            """,
            user_id, start_date, end_date
        )

        return total_trades, profitable_trades, loss_trades, total_profit
    finally:
        await conn.close()

async def get_stat_db(user_id: int, action: str):
    conn = await connect()
    try:
        query = """
        SELECT * FROM orders
        WHERE user_id = $1
        """
        if action == 'profit':
            query += " AND sale_price > buy_price"
        else:
            query += " AND sale_price < buy_price"

        rows = await conn.fetch(query, user_id)
        return [dict(row) for row in rows] if rows else []
    finally:
        await conn.close()

async def all_signals(status: str, interval: str):
    conn = await connect()
    try:
        query = """
        SELECT * FROM signals
        WHERE status = $1 AND interval = $2
        """
        rows = await conn.fetch(query, status, interval)
        return [dict(row) for row in rows] if rows else []
    finally:
        await conn.close()

async def count_signals(signal: str):
    conn = await connect()
    try:
        query = """
        SELECT COUNT(DISTINCT symbol)
        FROM signals
        WHERE status = $1
        """
        count = await conn.fetchval(query, signal)
        return count if count is not None else 0
    finally:
        await conn.close()



async def get_daily_statistics(user_id: int):
    conn = await connect()
    try:
        today = datetime.date.today()  # Преобразуем в date

        total_trades = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE sale_price IS NOT NULL
              AND sale_time::DATE = $1
              AND user_id = $2
            """,
            today, user_id  # Передаём объект date вместо строки
        )

        profitable_trades = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE sale_price > buy_price
              AND sale_time::DATE = $1
              AND user_id = $2
            """,
            today, user_id
        )

        loss_trades = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE sale_price < buy_price
              AND sale_time::DATE = $1
              AND user_id = $2
            """,
            today, user_id
        )

        total_profit = await conn.fetchval(
            """
            SELECT COALESCE(SUM(sale_price - buy_price), 0)
            FROM orders
            WHERE sale_price IS NOT NULL
              AND sale_time::DATE = $1
              AND user_id = $2
            """,
            today, user_id
        )

        return total_trades, profitable_trades, loss_trades, total_profit
    finally:
        await conn.close()

async def all_signals_no_signal():
    conn = await connect()
    try:
        query = "SELECT * FROM signals"
        rows = await conn.fetch(query)
        return [dict(row) for row in rows] if rows else []
    finally:
        await conn.close()

async def get_all_intervals_for_pairs_with_status(status: str):
    conn = await connect()
    try:
        query = """
        SELECT symbol, interval, status, buy_price, sale_price
        FROM signals
        WHERE symbol IN (
            SELECT DISTINCT symbol
            FROM signals
            WHERE status = $1
        )
        ORDER BY symbol, interval
        """
        rows = await conn.fetch(query, status)
        return [dict(row) for row in rows] if rows else []
    finally:
        await conn.close()

async def fetch_signals():
    conn = await connect()
    try:
        query = "SELECT * FROM signals"
        rows = await conn.fetch(query)
        if rows:
            columns = rows[0].keys()
            return list(columns), [tuple(row.values()) for row in rows]
        return [], []
    finally:
        await conn.close()

async def fetch_stat(user_id: int):
    conn = await connect()
    try:
        query = """
            SELECT * FROM orders
            WHERE sale_price IS NOT NULL AND user_id = $1
        """
        rows = await conn.fetch(query, user_id)
        if rows:
            columns = rows[0].keys()
            return list(columns), [tuple(row.values()) for row in rows]
        return [], []
    finally:
        await conn.close()
