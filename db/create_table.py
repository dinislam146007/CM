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
                cm_val TEXT,
                ai_val TEXT,
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
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                symbol TEXT,
                interval TEXT,  
                side TEXT DEFAULT 'LONG',    -- Тип позиции: LONG или SHORT
                trading_type TEXT DEFAULT 'spot',  -- Тип торговли: spot или futures 
                leverage INTEGER DEFAULT 1,  -- Кредитное плечо, по умолчанию 1 (для spot)
                qty REAL,                    -- Количество монет
                coin_buy_price REAL,         -- Цена покупки монеты (BTC: 96k)
                coin_sale_price REAL,        -- Цена продажи монеты
                tp_price REAL,               -- Цена тейк-профита
                sl_price REAL,               -- Цена стоп-лосса
                buy_time TIMESTAMP,          -- Время покупки
                sale_time TIMESTAMP,         -- Время продажи
                status TEXT DEFAULT 'OPEN',  -- Статус ордера: OPEN или CLOSED
                pnl_percent NUMERIC,         -- Процент прибыли/убытка
                pnl_usdt REAL,               -- Прибыль/убыток в USDT
                investment_amount_usdt REAL, -- Сумма инвестиции в USDT
                return_amount_usdt REAL      -- Сумма возврата в USDT
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
