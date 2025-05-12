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

async def count_signals(signal: str) -> int:
    """Count the number of distinct symbols with the given signal status"""
    conn = await connect()
    try:
        count = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT symbol)
            FROM signals
            WHERE status = $1
            """,
            signal
        )
        return count if count is not None else 0
    finally:
        await conn.close()

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
            query += " AND coin_sale_price IS NULL"
        else:
            query += " AND coin_sale_price IS NOT NULL"

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
            WHERE coin_sale_price IS NOT NULL
              AND user_id = $1
              AND sale_time::DATE BETWEEN $2::DATE AND $3::DATE
            """,
            user_id, start_date, end_date
        )

        profitable_trades = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE coin_sale_price > coin_buy_price
              AND coin_sale_price IS NOT NULL
              AND user_id = $1
              AND sale_time::DATE BETWEEN $2::DATE AND $3::DATE
            """,
            user_id, start_date, end_date
        )

        loss_trades = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE coin_sale_price < coin_buy_price
              AND coin_sale_price IS NOT NULL
              AND user_id = $1
              AND sale_time::DATE BETWEEN $2::DATE AND $3::DATE
            """,
            user_id, start_date, end_date
        )

        # Получаем данные для расчета прибыли
        rows = await conn.fetch(
            """
            SELECT id, investment_amount_usdt, pnl_percent, pnl_usdt, coin_buy_price, coin_sale_price
            FROM orders
            WHERE coin_sale_price IS NOT NULL
              AND user_id = $1
              AND sale_time::DATE BETWEEN $2::DATE AND $3::DATE
            """,
            user_id, start_date, end_date
        )

        total_profit = 0
        for row in rows:
            # Если есть прямой PnL в USDT, используем его
            if row.get('pnl_usdt') is not None:
                total_profit += float(row['pnl_usdt'])
            # Иначе вычисляем из суммы инвестиций и процента
            elif row.get('investment_amount_usdt') is not None and row.get('pnl_percent') is not None:
                # Convert decimal.Decimal to float before calculations
                investment = row['investment_amount_usdt']
                if hasattr(investment, 'normalize'):  # It's a Decimal
                    investment = float(investment)
                
                pnl_percent = row['pnl_percent']
                if hasattr(pnl_percent, 'normalize'):  # It's a Decimal
                    pnl_percent = float(pnl_percent)
                
                profit = investment * (pnl_percent / 100)
                total_profit += profit
            # Если нет ни того ни другого, пробуем простой расчет
            elif row.get('coin_buy_price') is not None and row.get('coin_sale_price') is not None:
                buy_price = float(row['coin_buy_price'])
                sale_price = float(row['coin_sale_price'])
                profit = sale_price - buy_price
                total_profit += profit

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

async def all_signals(status: str, interval: str):
    """Get all signals with specified status and interval"""
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
            WHERE coin_sale_price IS NOT NULL AND user_id = $1
        """
        rows = await conn.fetch(query, user_id)
        if rows:
            columns = rows[0].keys()
            return list(columns), [tuple(row.values()) for row in rows]
        return [], []
    finally:
        await conn.close()

# Helper function in case it's needed elsewhere
async def count_total_open(user_id: int) -> int:
    """Count the total number of open orders for a user"""
    conn = await connect()
    try:
        count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE user_id = $1 AND coin_sale_price IS NULL
            """,
            user_id
        )
        return count if count is not None else 0
    finally:
        await conn.close()

# In case it's needed elsewhere
async def get_tf_stat(user_id: int, interval: str):
    """Get stats for a specific timeframe"""
    conn = await connect()
    try:
        rows = await conn.fetch(
            """
            SELECT * 
            FROM orders
            WHERE user_id = $1 AND interval = $2
            """,
            user_id, interval
        )
        return [dict(row) for row in rows] if rows else []
    finally:
        await conn.close()

# In case it's needed elsewhere
async def get_symbol_data(symbol: str):
    """Get all data for a specific symbol"""
    conn = await connect()
    try:
        rows = await conn.fetch(
            """
            SELECT * 
            FROM signals
            WHERE symbol = $1
            """,
            symbol
        )
        return [dict(row) for row in rows] if rows else []
    finally:
        await conn.close()

# In case it's needed elsewhere
async def get_signal_data_by_symbol_tf(symbol: str, interval: str):
    """Get signal data for a specific symbol and timeframe"""
    conn = await connect()
    try:
        row = await conn.fetchrow(
            """
            SELECT * 
            FROM signals
            WHERE symbol = $1 AND interval = $2
            """,
            symbol, interval
        )
        return dict(row) if row else None
    finally:
        await conn.close()

# In case it's needed elsewhere
async def get_signal_data(symbol: str, interval: str):
    """Alias for get_signal_data_by_symbol_tf"""
    return await get_signal_data_by_symbol_tf(symbol, interval)

# In case it's needed elsewhere
async def get_user_liked_coins(user_id: int):
    """Get list of liked coins for a user"""
    conn = await connect()
    try:
        row = await conn.fetchrow(
            """
            SELECT crypto_pairs
            FROM users
            WHERE user_id = $1
            """,
            user_id
        )
        if row and row['crypto_pairs']:
            return row['crypto_pairs'].split(',')
        return []
    finally:
        await conn.close()

# In case it's needed elsewhere
async def select_count(table: str, condition: str = None, params: list = None):
    """Count records in table with optional condition"""
    conn = await connect()
    try:
        query = f"SELECT COUNT(*) FROM {table}"
        if condition:
            query += f" WHERE {condition}"
        
        if params:
            count = await conn.fetchval(query, *params)
        else:
            count = await conn.fetchval(query)
            
        return count if count is not None else 0
    finally:
        await conn.close()

# This function might be renamed to select_user_signals_stat in some references
async def select_user_signals_stat(user_id: int):
    """Get signal statistics for a user"""
    conn = await connect()
    try:
        rows = await conn.fetch(
            """
            SELECT * 
            FROM orders
            WHERE user_id = $1 AND coin_sale_price IS NOT NULL
            """,
            user_id
        )
        return [dict(row) for row in rows] if rows else []
    finally:
        await conn.close()
