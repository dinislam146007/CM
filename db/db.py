import sqlite3
import datetime as dt

# Подключение к SQLite
conn = sqlite3.connect("trading_data.db")
cursor = conn.cursor()

# Создание таблицы
# Создание таблицы signals
cursor.execute("""
CREATE TABLE IF NOT EXISTS signals (
    symbol TEXT,
    interval TEXT,
    status TEXT,
    buy_price REAL,
    sale_price REAL,
    PRIMARY KEY (symbol, interval)  -- Уникальность по symbol и interval
)
""")

# Создание таблицы users
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,  -- Уникальный идентификатор пользователя
    percent REAL,
    balance REAL,
    crypto_pairs TEXT,
    monitor_pairs TEXT
)
""")

# cursor.execute("""
# ALTER TABLE orders ADD COLUMN coin_sale_price REAL
# """)


# Создание таблицы orders
cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    user_id INTEGER,
    symbol TEXT,
    interval TEXT,  
    coin_buy_price REAL,
    coin_sale_price REAL,
    buy_price REAL,
    sale_price REAL,
    buy_time TEXT,
    sale_time TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- Уникальный идентификатор подписки
    user_id INTEGER NOT NULL,             -- Идентификатор пользователя (связывается с Telegram ID)
    symbol TEXT NOT NULL,                 -- Символ (например, BTCUSDT)
    interval TEXT NOT NULL,               -- Таймфрейм (например, 1D, 4H, 1H, 30)
    UNIQUE(user_id, symbol, interval)     -- Уникальная подписка на пару символ-таймфрейм для пользователя
);
""")

conn.commit()



def get_statistics_for_period(user_id, start_date, end_date):
    # Подключение к базе данных
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()

        # Преобразуем формат даты в запросах
        # Подсчет общего количества закрытых сделок за период
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE sale_price IS NOT NULL
              AND user_id = ?
              AND date(substr(sale_time, 7, 4) || '-' || substr(sale_time, 4, 2) || '-' || substr(sale_time, 1, 2)) 
                  BETWEEN date(?) AND date(?)
            """,
            (user_id, start_date, end_date)
        )
        total_trades = cursor.fetchone()[0]

        # Подсчет количества прибыльных сделок
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE sale_price > buy_price
              AND sale_price IS NOT NULL
              AND user_id = ?
              AND date(substr(sale_time, 7, 4) || '-' || substr(sale_time, 4, 2) || '-' || substr(sale_time, 1, 2)) 
                  BETWEEN date(?) AND date(?)
            """,
            (user_id, start_date, end_date)
        )
        profitable_trades = cursor.fetchone()[0]

        # Подсчет количества убыточных сделок
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE sale_price < buy_price
              AND sale_price IS NOT NULL
              AND user_id = ?
              AND date(substr(sale_time, 7, 4) || '-' || substr(sale_time, 4, 2) || '-' || substr(sale_time, 1, 2)) 
                  BETWEEN date(?) AND date(?)
            """,
            (user_id, start_date, end_date)
        )
        loss_trades = cursor.fetchone()[0]

        # Подсчет общего профита за период
        cursor.execute(
            """
            SELECT SUM(sale_price - buy_price)
            FROM orders
            WHERE sale_price IS NOT NULL
              AND user_id = ?
              AND date(substr(sale_time, 7, 4) || '-' || substr(sale_time, 4, 2) || '-' || substr(sale_time, 1, 2)) 
                  BETWEEN date(?) AND date(?)
            """,
            (user_id, start_date, end_date)
        )
        total_profit = cursor.fetchone()[0]
        total_profit = total_profit if total_profit is not None else 0

        return total_trades, profitable_trades, loss_trades, total_profit
    

def get_daily_statistics(user_id):
    # Подключение к базе данных
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()

        # Получение текущей даты
        today = dt.datetime.now().strftime('%d-%m-%Y')

        # Подсчет общего количества закрытых сделок за текущий день
        cursor.execute("""
        SELECT COUNT(*)
        FROM orders
        WHERE sale_price IS NOT NULL AND sale_time LIKE ?
        AND user_id = ?
        """, (f'{today}%', user_id))
        total_trades = cursor.fetchone()[0]

        # Подсчет количества прибыльных сделок
        cursor.execute("""
        SELECT COUNT(*)
        FROM orders
        WHERE sale_price > buy_price AND sale_time LIKE ?
        AND user_id = ?
        """, (f'{today}%',user_id, ))
        profitable_trades = cursor.fetchone()[0]

        # Подсчет количества убыточных сделок
        cursor.execute("""
        SELECT COUNT(*)
        FROM orders
        WHERE sale_price < buy_price AND sale_time LIKE ?
        AND user_id = ?
        """, (f'{today}%', user_id, ))
        loss_trades = cursor.fetchone()[0]

        # Подсчет общего профита
        cursor.execute("""
        SELECT SUM(sale_price - buy_price)
        FROM orders
        WHERE sale_price IS NOT NULL AND sale_time LIKE ?
        AND user_id = ?
        """, (f'{today}%', user_id))
        total_profit = cursor.fetchone()[0]
        total_profit = total_profit if total_profit is not None else 0

        return total_trades, profitable_trades, loss_trades, total_profit

def update_signal(symbol, interval, status, buy_price, sale_price):
    with sqlite3.connect("trading_data.db") as conn:  # Открываем новое соединение
        cursor = conn.cursor()  # Создаем новый курсор
        # Проверяем, есть ли запись с таким символом и интервалом
        cursor.execute("""
        SELECT status FROM signals WHERE symbol=? AND interval=?
        """, (symbol, interval))
        row = cursor.fetchone()

        # print(f"Проверяем базу данных для {symbol} с интервалом {interval}: {row}")  # Отладочный вывод

        if row is None:
            # Если записи нет, вставляем новую
            # print("Вставляем новую запись.")  # Отладочный вывод
            cursor.execute("""
            INSERT INTO signals (symbol, interval, status, buy_price, sale_price)
            VALUES (?, ?, ?, ?, ?)
            """, (symbol, interval, status, buy_price, sale_price))
        else:
            # Если запись есть, обновляем данные
            # print("Обновляем существующую запись.")  # Отладочный вывод
            cursor.execute("""
            UPDATE signals
            SET status=?, buy_price=?, sale_price=?
            WHERE symbol=? AND interval=?
            """, (status, buy_price, sale_price, symbol, interval))

        conn.commit()  # Фиксируем изменения
        # print("Данные успешно обновлены.")  # Отладочный вывод

def get_user_subscriptions(user_id):
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT symbol, interval FROM subscriptions
        WHERE user_id = ?
        """, (user_id,))
        return cursor.fetchall()  # Возвращает список кортежей (symbol, interval)


def get_subscribed_users(symbol, interval):
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id FROM subscriptions
            WHERE symbol = ? AND interval = ?
        """, (symbol, interval))
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    

def add_subscription(user_id, symbol, interval):
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
            INSERT INTO subscriptions (user_id, symbol, interval)
            VALUES (?, ?, ?)
            """, (user_id, symbol, interval))
            conn.commit()
            return True  # Успешное добавление
        except sqlite3.IntegrityError:
            return False  # Подписка уже существует
        

def remove_subscription(user_id, symbol, interval):
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
        DELETE FROM subscriptions
        WHERE user_id = ? AND symbol = ? AND interval = ?
        """, (user_id, symbol, interval))
        conn.commit()


def set_user(user_id, percent, balance):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, percent, balance)
        VALUES (?, ?, ?)
        """, (user_id, percent, balance))
        conn.commit()
        return True

def get_user(user_id):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM users WHERE user_id=?
        """, (user_id,))
        row = cursor.fetchone()
        if row is not None:
            # Создаем словарь с именами полей из запроса
            columns = [desc[0] for desc in cursor.description]  # Получаем названия колонок
            client_data = dict(zip(columns, row))  # Соединяем названия колонок и данные
            return client_data
        return None  # Если ничего не найдено, возвращаем None


def get_signals():
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM signals
        """)
        rows = cursor.fetchall()
        return rows
    
def get_stat_db(user_id, action):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        if action == 'profit':
            cursor.execute("""
            SELECT * FROM orders
            WHERE user_id=?
            AND sale_price>buy_price
            """, (user_id, ))
        else:
            cursor.execute("""
            SELECT * FROM orders
            WHERE user_id=?
            AND sale_price<buy_price
            """, (user_id, ))
        rows = cursor.fetchall()
        if rows:
            columns = [desc[0] for desc in cursor.description]
            # Создаем список словарей, где каждое поле строки сопоставлено названию колонки
            customer_data_list = [dict(zip(columns, row)) for row in rows]
            return customer_data_list  # Возвращаем список словарей
        return []  # Если ничего не найдено, возвращаем пустой список

    
def get_order(interval, symbol, user_id):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM orders
        WHERE symbol=? AND interval=? 
        AND sale_price IS NULL
        AND user_id =?
        """, (symbol, interval, user_id))
        row = cursor.fetchone()
        if row is not None:
            # Создаем словарь с именами полей из запроса
            columns = [desc[0] for desc in cursor.description]  # Получаем названия колонок
            client_data = dict(zip(columns, row))  # Соединяем названия колонок и данные
            return client_data
        return None  # Если ничего не найдено, возвращаем None


def buy_order(user_id, interval, symbol, buy_price, buy_time, coin_buy_price):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO orders (user_id, symbol, interval, buy_price, buy_time, coin_buy_price)
        VALUES (?, ?, ?, ?, ?, ?)""", (user_id, symbol, interval, buy_price, buy_time, coin_buy_price))
        conn.commit()    



def sale_order(user_id, sale_price, sale_time, coin_sale_price, symbol, interval):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE orders SET sale_price=?, sale_time=?, coin_sale_price=?
        WHERE user_id=? AND symbol=? AND interval=? AND sale_price IS NULL AND sale_time IS NULL
        """, (sale_price, sale_time, coin_sale_price, user_id, symbol, interval))
        conn.commit()

def up_percent(user_id, percent):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE users SET percent=?
        WHERE user_id=? 
        """, (percent, user_id, ))
        conn.commit()


async def add_crypto_pair_to_db(user_id: int, pair: str):
    # Здесь пишем логику для добавления пары в базу данных
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT crypto_pairs FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if row and row[0]:  # Если есть данные
            existing_pairs = row[0].split(',')
            if pair not in existing_pairs:
                existing_pairs.append(pair)
        else:  # Если данных нет
            existing_pairs = [pair]

        pairs_str = ','.join(existing_pairs)
        cursor.execute("UPDATE users SET crypto_pairs = ? WHERE user_id = ?", (pairs_str, user_id))
        conn.commit()

async def add_monitor_pair_to_db(user_id: int, pair: str):
    # Здесь пишем логику для добавления пары в базу данных
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT monitor_pairs FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if row and row[0]:  # Если есть данные
            existing_pairs = row[0].split(',')
            if pair not in existing_pairs:
                existing_pairs.append(pair)
        else:  # Если данных нет
            existing_pairs = [pair]

        pairs_str = ','.join(existing_pairs)
        cursor.execute("UPDATE users SET monitor_pairs = ? WHERE user_id = ?", (pairs_str, user_id))
        conn.commit()

async def delete_crypto_pair_from_db(user_id: int, pair: str):
    # Здесь пишем логику для удаления пары из базы данных
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT crypto_pairs FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if row and row[0]:
            existing_pairs = row[0].split(',')
            if pair in existing_pairs:
                existing_pairs.remove(pair)

            pairs_str = ','.join(existing_pairs)
            cursor.execute("UPDATE users SET crypto_pairs = ? WHERE user_id = ?", (pairs_str, user_id))
            conn.commit()

async def delete_monitor_pair_from_db(user_id: int, pair: str):
    # Здесь пишем логику для удаления пары из базы данных
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT monitor_pairs FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if row and row[0]:
            existing_pairs = row[0].split(',')
            if pair in existing_pairs:
                existing_pairs.remove(pair)

            pairs_str = ','.join(existing_pairs)
            cursor.execute("UPDATE users SET monitor_pairs = ? WHERE user_id = ?", (pairs_str, user_id))
            conn.commit()

        
def minus_plus_user(price, user_id):
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE users
        SET balance = balance + ? 
        WHERE user_id=?
        """, (price, user_id, ))
        conn.commit()



def get_all_user_id():
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM users
        """)
        rows = cursor.fetchall()
        if rows:
            columns = [desc[0] for desc in cursor.description]
            # Создаем список словарей, где каждое поле строки сопоставлено названию колонки
            customer_data_list = [dict(zip(columns, row)) for row in rows]
            return customer_data_list  # Возвращаем список словарей
        return []  # Если ничего не найдено, возвращаем пустой список

    
def get_signal(symbol, interval):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM signals
        WHERE symbol=? AND interval=?
        """, (symbol, interval))
        row = cursor.fetchone()
        if row is not None:
            # Создаем словарь с именами полей из запроса
            columns = [desc[0] for desc in cursor.description]  # Получаем названия колонок
            client_data = dict(zip(columns, row))  # Соединяем названия колонок и данные
            return client_data
        return None  # Если ничего не найдено, возвращаем None


def count_signals(signal):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT COUNT(DISTINCT symbol)
        FROM signals
        WHERE status = ?
        """, (signal,))
        row = cursor.fetchone()
        return row[0] if row else 0
    
def get_all_intervals_for_pairs_with_status(status):
    with sqlite3.connect("trading_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT symbol, interval, status, buy_price, sale_price
        FROM signals
        WHERE symbol IN (
            SELECT DISTINCT symbol
            FROM signals
            WHERE status = ?
        )
        ORDER BY symbol, interval
        """, (status,))
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]  # Заголовки колонок
        return [dict(zip(columns, row)) for row in rows]  # Преобразуем в список словарей


def all_signals(status, interval):
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM signals
        WHERE status=? AND interval=?
        """, (status, interval))  # Добавлена запятая для формирования кортежа
        rows = cursor.fetchall()
        if rows:
            columns = [desc[0] for desc in cursor.description]
            # Создаем список словарей, где каждое поле строки сопоставлено названию колонки
            customer_data_list = [dict(zip(columns, row)) for row in rows]
            return customer_data_list  # Возвращаем список словарей
        return []  # Если ничего не найдено, возвращаем пустой список

def all_signals_no_signal():
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM signals
        """)  # Добавлена запятая для формирования кортежа
        rows = cursor.fetchall()
        if rows:
            columns = [desc[0] for desc in cursor.description]
            # Создаем список словарей, где каждое поле строки сопоставлено названию колонки
            customer_data_list = [dict(zip(columns, row)) for row in rows]
            return customer_data_list  # Возвращаем список словарей
        return []  # Если ничего не найдено, возвращаем пустой список

def fetch_signals():
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals")
        rows = cursor.fetchall()
        if rows:
            columns = [desc[0] for desc in cursor.description]
            return columns, rows
        return [], []

def fetch_stat(user_id):
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM orders
            WHERE coin_sale_price IS NOT NULL AND user_id = ?
        """, (user_id,))
        rows = cursor.fetchall()
        if rows:
            columns = [desc[0] for desc in cursor.description]
            return columns, rows
        return [], []

def get_all_orders(user_id, order_type):
    with sqlite3.connect('trading_data.db') as conn:
        cursor = conn.cursor()
        if order_type == 'open':
            cursor.execute("""
            SELECT * FROM orders
            WHERE user_id=? 
            AND coin_sale_price IS NULL
            """, (user_id, ))
        else:
            cursor.execute("""
            SELECT * FROM orders
            WHERE user_id=? 
            AND coin_sale_price IS NOT NULL
            """, (user_id, ))

        rows = cursor.fetchall()
        if rows:
            columns = [desc[0] for desc in cursor.description]
            # Создаем список словарей, где каждое поле строки сопоставлено названию колонки
            customer_data_list = [dict(zip(columns, row)) for row in rows]
            return customer_data_list  # Возвращаем список словарей
        return []  # Если ничего не найдено, возвращаем пустой список

def connect():
    """Connect to the database."""
    conn = sqlite3.connect('trading_data.db')
    return conn

