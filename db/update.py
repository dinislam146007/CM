from db.connect import connect


async def update_user_balance(user_id: int, amount: float) -> None:
    """
    :param user_id:
    :param amount:
    :return:
    """
    conn = await connect()
    await conn.execute(
        """
        UPDATE users SET balance = balance + $1 WHERE user_id = $2
        """,
        amount, user_id
    )
    await conn.close()

async def update_order_sale(user_id: int, symbol: str, interval: str, coin_sale_price: float,
                          sale_price: float, sale_time: str) -> None:
    conn = await connect()
    await conn.execute(
        """
        UPDATE orders 
        SET coin_sale_price = $1, sale_price = $2, sale_time = $3
        WHERE user_id = $4 AND symbol = $5 AND interval = $6 AND sale_time IS NULL
        """,
        coin_sale_price, sale_price, sale_time, user_id, symbol, interval
    )
    await conn.close()


async def sale_order(user_id, sale_price, sale_time, coin_sale_price, symbol, interval):
    conn = await connect()
    await conn.execute("""
    UPDATE orders SET sale_price=$1, sale_time=$2, coin_sale_price=$3
    WHERE user_id=$4 AND symbol=$5 AND interval=$6 AND sale_price IS NULL AND sale_time IS NULL
    """, sale_price, sale_time, coin_sale_price, user_id, symbol, interval)
    await conn.close()

async def update_signal(symbol, interval, status, buy_price, sale_price):
    conn = await connect()

    row = await conn.fetchrow("""
        SELECT status FROM signals WHERE symbol=$1 AND interval=$2
        """, symbol, interval)

    if row is None:
        # Если записи нет, вставляем новую
        # print("Вставляем новую запись.")  # Отладочный вывод
        await conn.execute("""
            INSERT INTO signals (symbol, interval, status, buy_price, sale_price)
            VALUES ($1, $2, $3, $4, $5)
            """, symbol, interval, status, buy_price, sale_price)

    else:
        # Если запись есть, обновляем данные
        # print("Обновляем существующую запись.")  # Отладочный вывод
        await conn.execute("""
            UPDATE signals
            SET status=$1, buy_price=$2, sale_price=$3
            WHERE symbol=$4 AND interval=$5
            """, status, buy_price, sale_price, symbol, interval)

    await conn.close()

async def minus_plus_user(price, user_id):
    conn = await connect()
    try:
        await conn.execute("""
        UPDATE users
        SET balance = balance + $1
        WHERE user_id=$2
        """, price, user_id)
    finally:
        await conn.close()


async def delete_crypto_pair_from_db(user_id: int, pair: str):
    conn = await connect()
    try:
        row = await conn.fetchrow("SELECT crypto_pairs FROM users WHERE user_id = $1", user_id)

        if row and row["crypto_pairs"]:
            existing_pairs = row["crypto_pairs"].split(',')
            if pair in existing_pairs:
                existing_pairs.remove(pair)

            pairs_str = ','.join(existing_pairs)
            await conn.execute("UPDATE users SET crypto_pairs = $1 WHERE user_id = $2", pairs_str, user_id)
    finally:
        await conn.close()


async def delete_monitor_pair_from_db(user_id: int, pair: str):
    conn = await connect()
    try:
        row = await conn.fetchrow("SELECT monitor_pairs FROM users WHERE user_id = $1", user_id)

        if row and row["monitor_pairs"]:
            existing_pairs = row["monitor_pairs"].split(',')
            if pair in existing_pairs:
                existing_pairs.remove(pair)

            pairs_str = ','.join(existing_pairs)
            await conn.execute("UPDATE users SET monitor_pairs = $1 WHERE user_id = $2", pairs_str, user_id)
    finally:
        await conn.close()


async def add_crypto_pair_to_db(user_id: int, pair: str):
    conn = await connect()
    try:
        row = await conn.fetchrow("SELECT crypto_pairs FROM users WHERE user_id = $1", user_id)

        if row and row["crypto_pairs"]:
            existing_pairs = row["crypto_pairs"].split(',')
            if pair not in existing_pairs:
                existing_pairs.append(pair)
        else:
            existing_pairs = [pair]

        pairs_str = ','.join(existing_pairs)
        await conn.execute("UPDATE users SET crypto_pairs = $1 WHERE user_id = $2", pairs_str, user_id)
    finally:
        await conn.close()


async def add_monitor_pair_to_db(user_id: int, pair: str):
    conn = await connect()
    try:
        row = await conn.fetchrow("SELECT monitor_pairs FROM users WHERE user_id = $1", user_id)

        if row and row["monitor_pairs"]:
            existing_pairs = row["monitor_pairs"].split(',')
            if pair not in existing_pairs:
                existing_pairs.append(pair)
        else:
            existing_pairs = [pair]

        pairs_str = ','.join(existing_pairs)
        await conn.execute("UPDATE users SET monitor_pairs = $1 WHERE user_id = $2", pairs_str, user_id)
    finally:
        await conn.close()

async def up_percent(user_id: int, percent: float):
    conn = await connect()
    try:
        await conn.execute("""
        UPDATE users SET percent = $1
        WHERE user_id = $2
        """, percent, user_id)
    finally:
        await conn.close()
