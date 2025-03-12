from db.connect import connect


async def create_tables():
    conn = await connect()
    try:
        # Создание таблицы signals
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                symbol TEXT, 
                interval TEXT,
                status TEXT,
                buy_price REAL,
                sale_price REAL,
                PRIMARY KEY (symbol, interval)  -- Уникальность по symbol и interval
            );
        """)

        # Создание таблицы users
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT,  -- Уникальный идентификатор пользователя
                percent REAL,                 -- процент от баланса, на который покупается монета
                balance REAL, 
                crypto_pairs TEXT DEFAULT NULL,  -- монеты, которыми торгуют
                monitor_pairs TEXT DEFAULT NULL -- монеты, за которыми уведомления приходят
            );
        """)

        # Создание таблицы orders
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                user_id BIGINT,
                symbol TEXT,
                interval TEXT,  
                coin_buy_price REAL, -- цена покупки монеты (BTC: 96k)
                coin_sale_price REAL, -- цена продажи монеты
                buy_price REAL,  -- цена, за которую пользователь купил (5 процентов от баланса)
                sale_price REAL, 
                buy_time TEXT,
                sale_time TEXT,
                PRIMARY KEY (user_id, symbol, interval)
            );
        """)

        # Создание таблицы subscriptions
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,  -- Уникальный идентификатор подписки (автоинкремент)
                user_id BIGINT, -- Идентификатор пользователя (связывается с Telegram ID)
                symbol TEXT NOT NULL, -- Символ (например, BTCUSDT)
                interval TEXT NOT NULL, -- Таймфрейм (например, 1D, 4H, 1H, 30)
                UNIQUE(user_id, symbol, interval) -- Уникальная подписка на пару символ-таймфрейм для пользователя
            );
        """)

    finally:
        await conn.close()
