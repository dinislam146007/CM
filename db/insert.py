from db.connect import connect

async def set_user(user_id: int, percent: float, balance: float) -> None:
    """
    :param user_id:
    :param percent:
    :param balance:
    :return: None
    """
    conn = await connect()
    await conn.execute(
        """
        INSERT INTO users (user_id, percent, balance)
        VALUES ($1, $2, $3)
        """,
        user_id, percent, balance
    )
    await conn.close()


async def set_signal(symbol: str, interval: str, status: str, buy_price: float = None,
                    sale_price: float = None) -> None:
    conn = await connect()
    await conn.execute(
        """
        INSERT INTO signals (symbol, interval, status, buy_price, sale_price)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (symbol, interval) DO UPDATE
        SET status = $3, buy_price = $4, sale_price = $5
        """,
        symbol, interval, status, buy_price, sale_price
    )
    await conn.close()


async def create_order(user_id: int, symbol: str, interval: str, coin_buy_price: float,
                      buy_price: float, buy_time: str) -> None:
    conn = await connect()
    await conn.execute(
        """
        INSERT INTO orders (user_id, symbol, interval, coin_buy_price, buy_price, buy_time)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        user_id, symbol, interval, coin_buy_price, buy_price, buy_time
    )
    await conn.close()


async def add_subscription(user_id: int, symbol: str, interval: str) -> None:
    conn = await connect()
    await conn.execute(
        """
        INSERT INTO subscriptions (user_id, symbol, interval)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, symbol, interval) DO NOTHING
        """,
        user_id, symbol, interval
    )
    await conn.close()

async def remove_subscription(user_id: int, symbol: str, interval: str) -> None:
    conn = await connect()
    await conn.execute(
        """
        DELETE FROM subscriptions 
        WHERE user_id = $1 AND symbol = $2 AND interval = $3
        """,
        user_id, symbol, interval
    )
    await conn.close()


async def buy_order(user_id:int, interval: str,
                    symbol: str, buy_price:float,
                    buy_time:str, coin_buy_price: float):
    conn = await connect()
    try:
        await conn.execute(
            """
            INSERT INTO orders (user_id, symbol, interval, buy_price, buy_time, coin_buy_price)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            user_id, symbol, interval, buy_price, buy_time, coin_buy_price
        )
    finally:
        await conn.close()