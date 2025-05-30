import asyncpg, datetime as dt
from db.connect import connect
import aiosqlite
from strategy_logic.trading_settings import load_trading_settings

COMMISSION_RATE_SPOT = 0.001      # 0.10% для спота
COMMISSION_RATE_FUTURES = 0.00075  # 0.075% для фьючерсов

async def get_user_balance(user_id):
    """Получение баланса пользователя из таблицы users"""
    conn = await connect()
    row = await conn.fetchrow("""
        SELECT balance FROM users WHERE user_id=$1
    """, user_id)
    
    if row:
        await conn.close()
        return row['balance']
    
    # Если пользователь не найден, создаем его с начальным балансом
    try:
        await conn.execute("""
            INSERT INTO users (user_id, balance) VALUES ($1, $2)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, 1000.0)
        print(f"[DB] Создан новый пользователь {user_id} с начальным балансом 1000.0 USDT")
        await conn.close()
        return 1000.0
    except Exception as e:
        print(f"[DB_ERROR] Ошибка при создании пользователя {user_id}: {e}")
        await conn.close()
        return 0.0  # Возвращаем 0 если создание не удалось




async def update_user_balance(user_id, amount):
    """Обновление баланса пользователя"""
    conn = await connect()
    
    try:
        # Используем транзакцию для атомарности операции
        tr = conn.transaction()
        await tr.start()
        
        # Получаем текущий баланс с блокировкой строки
        current_balance = await conn.fetchval("""
            SELECT balance FROM users WHERE user_id=$1 FOR UPDATE
        """, user_id)
        
        if current_balance is None:
            # Пользователь не существует, создаем его
            await conn.execute("""
                INSERT INTO users (user_id, balance) VALUES ($1, $2)
            """, user_id, max(1000.0 + amount, 0))
            await tr.commit()
            return max(1000.0 + amount, 0)
        
        # Проверяем, что операция не приведет к отрицательному балансу
        new_balance = current_balance + amount
        if new_balance < 0:
            await tr.rollback()
            print(f"[BALANCE_ERROR] Попытка создать отрицательный баланс для user_id={user_id}: {current_balance} + {amount} = {new_balance}")
            raise ValueError(f"Операция приведет к отрицательному балансу: {current_balance} + {amount} = {new_balance}")
        
        # Обновляем баланс
        await conn.execute("""
            UPDATE users SET balance = $2 WHERE user_id=$1
        """, user_id, new_balance)
        
        await tr.commit()
        return new_balance
        
    except Exception as e:
        await tr.rollback()
        print(f"[BALANCE_ERROR] Ошибка при обновлении баланса пользователя {user_id}: {e}")
        raise
    finally:
        await conn.close()

async def set_user_balance(user_id: int, new_balance: float):
    """Устанавливает новое значение баланса для пользователя."""
    conn = await connect()
    try:
        await conn.execute("""
            UPDATE users SET balance = $2 WHERE user_id = $1
        """, user_id, new_balance)
        print(f"[DB] Баланс пользователя {user_id} обновлен на {new_balance}")
    except Exception as e:
        print(f"[DB_ERROR] Ошибка при обновлении баланса пользователя {user_id}: {e}")
        raise  # Перевыбрасываем исключение для обработки выше
    finally:
        await conn.close()
    # Возвращаем новый баланс для подтверждения или дальнейшего использования
    # Можно также вернуть просто True/False в зависимости от успеха операции
    return new_balance

async def create_order(user_id, exchange, symbol, interval, side, qty,
                       buy_price, tp, sl, trading_type=None, leverage=None, 
                       strategy_signals=None):
    """Создание ордера и списание средств с баланса пользователя"""
    
    # Проверяем, что все обязательные параметры переданы
    if not all([user_id, exchange, symbol, interval, side, qty, buy_price, tp, sl]):
        raise ValueError("Все обязательные параметры должны быть переданы")
    
    # Устанавливаем значения по умолчанию
    if trading_type is None:
        trading_type = "spot"
    if leverage is None:
        leverage = 1
    if strategy_signals is None:
        strategy_signals = {}
    
    # Проверяем корректность значений
    if qty <= 0:
        raise ValueError(f"Количество должно быть больше 0: {qty}")
    if buy_price <= 0:
        raise ValueError(f"Цена покупки должна быть больше 0: {buy_price}")
    if leverage < 1:
        raise ValueError(f"Плечо должно быть >= 1: {leverage}")
    
    # Рассчитываем сумму инвестиции с учетом плеча
    if trading_type == "futures":
        investment_amount = (qty * buy_price) / leverage
        print(f"Расчет futures: qty={qty}, price={buy_price}, leverage={leverage}, investment={investment_amount}")
    else:
        investment_amount = qty * buy_price
        print(f"Расчет spot: qty={qty}, price={buy_price}, investment={investment_amount}")
    
    # Списываем средства с баланса (update_user_balance проверит достаточность средств)
    try:
        commission_rate = COMMISSION_RATE_FUTURES if trading_type == "futures" else COMMISSION_RATE_SPOT
        open_fee = qty * buy_price * commission_rate
        await update_user_balance(user_id, -(investment_amount + open_fee))
    except ValueError as e:
        print(f"ОШИБКА: Недостаточно средств для user_id={user_id}: {e}")
        raise
    
    # Извлекаем информацию о стратегиях
    price_action_active = strategy_signals.get('price_action_active', False)
    price_action_pattern = strategy_signals.get('price_action_pattern', '')
    cm_active = strategy_signals.get('cm_active', False)
    moonbot_active = strategy_signals.get('moonbot_active', False)
    rsi_active = strategy_signals.get('rsi_active', False)
    divergence_active = strategy_signals.get('divergence_active', False)
    divergence_type = strategy_signals.get('divergence_type', '')
    
    # Преобразуем numpy booleans в Python booleans для избежания ошибок БД
    price_action_active = bool(price_action_active)
    cm_active = bool(cm_active)
    moonbot_active = bool(moonbot_active)
    rsi_active = bool(rsi_active)
    divergence_active = bool(divergence_active)
    
    # Создаем запись о сделке с учетом типа торговли, плеча и стратегий
    conn = await connect()
    try:
        order_id = await conn.fetchval("""
            INSERT INTO orders (user_id, exchange, symbol, interval, side, qty,
                               coin_buy_price, tp_price, sl_price, buy_time,
                               investment_amount_usdt, trading_type, leverage,
                               price_action_active, price_action_pattern,
                               cm_active, moonbot_active, rsi_active,
                               divergence_active, divergence_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15, $16, $17, $18, $19, $20)
            RETURNING id
        """, user_id, exchange, symbol, interval, side.upper(), qty,
            buy_price, tp, sl, dt.datetime.utcnow(), investment_amount,
            trading_type, leverage, price_action_active, price_action_pattern,
            cm_active, moonbot_active, rsi_active, divergence_active, divergence_type)
        
        print(f"УСПЕХ: Создан ордер id={order_id} для user_id={user_id}, exchange={exchange}, symbol={symbol}, side={side}, leverage={leverage}")
        print(f"Стратегии: PA={price_action_active}, CM={cm_active}, Moon={moonbot_active}, RSI={rsi_active}, Div={divergence_active}")
        return order_id
    finally:
        await conn.close()

async def get_open_order(user_id, exchange, symbol, interval):
    conn = await connect()
    row = await conn.fetchrow("""
        SELECT * FROM orders
        WHERE user_id=$1 AND exchange=$2 AND symbol=$3 AND interval=$4 AND status='OPEN'
        ORDER BY buy_time DESC LIMIT 1
    """, user_id, exchange, symbol, interval)
    await conn.close()
    return row

async def close_order(
    order_id: int,
    sale_price: float,
    close_reason: str | None = None,
):
    """
    Закрывает ордер, рассчитывает PnL с учётом комиссий и возвращает средства на баланс.
    Работает для SPOT и FUTURES, LONG и SHORT.
    """

    # убеждаемся, что sale_price – число
    sale_price = float(sale_price)

    # --- значения по умолчанию, чтобы переменные существовали в любой ветке ---
    gross_pnl: float = 0.0
    total_fee: float = 0.0
    pnl_usdt: float = 0.0
    pnl_percent: float = 0.0
    return_amount: float = 0.0

    conn = await connect()
    tr = conn.transaction()
    await tr.start()
    try:
        # берём ордер под FOR UPDATE
        order = await conn.fetchrow(
            """
            SELECT id, user_id, qty, coin_buy_price, investment_amount_usdt,
                   side, trading_type, leverage, status
              FROM orders
             WHERE id = $1
            FOR UPDATE
            """,
            order_id,
        )
        if not order:
            raise ValueError(f"Ордер {order_id} не найден")
        if order["status"] == "CLOSED":
            print(f"[WARN] Ордер {order_id} уже закрыт — пропуск")
            await tr.rollback()
            return None

        # --- поля ордера ---
        user_id: int = order["user_id"]
        qty: float = float(order["qty"])
        entry_price: float = float(order["coin_buy_price"])
        invested: float = float(order["investment_amount_usdt"])
        side: str = order["side"]         # LONG / SHORT
        trading_type: str = order["trading_type"]  # spot / futures

        # --- комиссия ---
        commission_rate = (
            COMMISSION_RATE_FUTURES if trading_type == "futures" else COMMISSION_RATE_SPOT
        )
        open_fee = entry_price * qty * commission_rate
        close_fee = sale_price * qty * commission_rate
        total_fee = open_fee + close_fee

        # --- расчёт PnL до комиссии (gross) ---
        if side == "LONG":
            gross_pnl = (sale_price - entry_price) * qty
        elif side == "SHORT":
            gross_pnl = (entry_price - sale_price) * qty
        else:
            raise ValueError(f"Неизвестный side='{side}' у ордера {order_id}")

        # --- net-PnL и проценты ---
        pnl_usdt = gross_pnl - total_fee
        pnl_percent = (pnl_usdt / (entry_price * qty)) * 100

        print(
            f"[PNL_DEBUG] {side}: gross={gross_pnl:.4f} USDT, "
            f"fee={total_fee:.4f} USDT, net={pnl_usdt:.4f} USDT "
            f"({pnl_percent:.4f} %)"
        )

        # --- сумма к возврату на баланс ---
        return_amount = invested + pnl_usdt

        # ликвидация, если убыток > маржи
        if return_amount < 0:
            print(
                f"[LIQUIDATION] Убыток превысил маржу по ордеру {order_id} "
                f"({return_amount:.4f} USDT). Возврат 0."
            )
            pnl_usdt = -invested
            pnl_percent = -100.0
            return_amount = 0.0
            close_reason = "LIQUIDATION"

        # --- обновляем баланс пользователя ---
        await conn.execute(
            "UPDATE users SET balance = balance + $2 WHERE user_id = $1",
            user_id,
            return_amount,
        )

        # --- сохраняем закрытие ордера ---
        if close_reason is None:
            close_reason = "MANUAL"
        close_trigger = (
            "price"
            if close_reason in ("TP", "SL")
            else ("liquidation" if close_reason == "LIQUIDATION" else "manual")
        )

        result = await conn.fetchrow(
            """
            UPDATE orders
               SET coin_sale_price     = $2,
                   sale_time          = $3,
                   status             = 'CLOSED',
                   pnl_percent        = $4,
                   pnl_usdt           = $5,
                   return_amount_usdt = $6,
                   close_reason       = $7,
                   close_trigger      = $8
             WHERE id = $1
               AND status = 'OPEN'
         RETURNING *
            """,
            order_id,
            sale_price,
            dt.datetime.utcnow(),
            pnl_percent,
            pnl_usdt,
            return_amount,
            close_reason,
            close_trigger,
        )

        if not result:
            print(f"[WARN] Ордер {order_id} не был обновлён — откат")
            await tr.rollback()
            return None

        await tr.commit()

        new_balance = await get_user_balance(user_id)
        print(
            f"[BALANCE] user={user_id}: +{return_amount:.4f} USDT → "
            f"{new_balance:.4f} USDT"
        )

        return result

    except Exception as exc:
        await tr.rollback()
        print(f"[ERROR] close_order({order_id}): {exc}")
        raise

    finally:
        await conn.close()
# Add the missing functions
async def get_user_open_orders(user_id):
    """Получение списка открытых ордеров пользователя"""
    return await get_all_orders(user_id, 'open')

async def get_user_closed_orders(user_id):
    """Получение списка закрытых ордеров пользователя"""
    return await get_all_orders(user_id, 'close')

# Helper function to get all orders of a specific type (open/closed)
async def get_all_orders(user_id, order_type, from_date=None):
    """Получение всех ордеров определенного типа для пользователя"""
    conn = await connect()
    try:
        if order_type == 'open':
            rows = await conn.fetch("""
                SELECT * FROM orders
                WHERE user_id=$1 AND status='OPEN'
                ORDER BY buy_time DESC
            """, user_id)
        elif order_type == 'close':
            # If from_date is provided, filter by sale_time
            if from_date is not None:
                rows = await conn.fetch("""
                    SELECT * FROM orders
                    WHERE user_id=$1 AND status='CLOSED'
                    AND EXTRACT(EPOCH FROM sale_time) >= $2
                    ORDER BY sale_time DESC
                """, user_id, from_date)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM orders
                    WHERE user_id=$1 AND status='CLOSED'
                    ORDER BY sale_time DESC
                """, user_id)
        else:
            # Default to returning all orders
            rows = await conn.fetch("""
                SELECT * FROM orders
                WHERE user_id=$1
                ORDER BY buy_time DESC
            """, user_id)
        
        return [dict(row) for row in rows]
    finally:
        await conn.close()

async def get_daily_profit(user_id, date):
    """
    Получить суммарный профит пользователя за указанный день
    :param user_id: ID пользователя
    :param date: Дата (объект datetime.date или строка в формате YYYY-MM-DD)
    :return: Суммарный профит в USDT
    """
    conn = await connect()
    try:
        # Конвертируем дату в строку для логирования
        date_for_log = str(date)
        
        # Преобразуем все входные данные в datetime.date объект
        if isinstance(date, str):
            try:
                # Проверяем формат YYYY-MM-DD
                date_obj = dt.datetime.strptime(date, '%Y-%m-%d').date()
            except ValueError:
                try:
                    # Проверяем формат DD.MM.YYYY
                    date_obj = dt.datetime.strptime(date, '%d.%m.%Y').date()
                except ValueError:
                    # Если не удалось распознать формат, используем текущую дату
                    print(f"Невалидный формат даты: {date}, используем текущую дату")
                    date_obj = dt.date.today()
        elif isinstance(date, dt.datetime):
            # Если передан datetime, преобразуем в date
            date_obj = date.date()
        elif isinstance(date, dt.date):
            # Если уже date, используем как есть
            date_obj = date
        else:
            # Если неизвестный тип, используем текущую дату
            print(f"Неизвестный тип даты: {type(date)}, используем текущую дату")
            date_obj = dt.date.today()
        
        # Преобразуем date_obj в строку YYYY-MM-DD для SQL запроса
        date_str = date_obj.strftime('%Y-%m-%d')
        
        print(f"Получение профита для пользователя {user_id} на дату: {date_for_log} (преобразовано в {date_str})")
        
        # Запрос на получение суммы прибыли за день с использованием текстового сравнения дат
        row = await conn.fetchrow("""
            SELECT SUM(pnl_usdt) as daily_profit
            FROM orders 
            WHERE user_id = $1 
            AND status = 'CLOSED'
            AND TO_CHAR(sale_time, 'YYYY-MM-DD') = $2
        """, user_id, date_str)
        
        # Если нет закрытых ордеров или сумма NULL, возвращаем 0
        return row['daily_profit'] if row and row['daily_profit'] is not None else 0.0
    except Exception as e:
        print(f"Ошибка при получении дневного профита: {e}")
        return 0.0
    finally:
        await conn.close()

async def get_order_by_id(order_id):
    """Получение информации о конкретном ордере по его ID"""
    conn = await connect()
    row = await conn.fetchrow("""
        SELECT * FROM orders
        WHERE id=$1
    """, order_id)
    await conn.close()
    return dict(row) if row else None

# Aliases and additional functions needed by main_strategy.py
async def get_open_orders(user_id):
    """Алиас для get_user_open_orders для совместимости"""
    return await get_user_open_orders(user_id)
    
async def save_order(user_id, exchange, symbol, interval, side, qty, entry_price, tp_price, sl_price, trading_type=None, leverage=None):
    """Сохранение нового ордера (алиас для create_order для совместимости)"""
    return await create_order(user_id, exchange, symbol, interval, side, qty, entry_price, tp_price, sl_price, trading_type, leverage)

async def get_active_positions(user_id, exchange=None):
    """Получение всех активных позиций пользователя"""
    conn = await connect()
    try:
        if exchange:
            rows = await conn.fetch("""
                SELECT * FROM orders
                WHERE user_id=$1 AND exchange=$2 AND status='OPEN'
                ORDER BY buy_time DESC
            """, user_id, exchange)
        else:
            rows = await conn.fetch("""
                SELECT * FROM orders
                WHERE user_id=$1 AND status='OPEN'
                ORDER BY buy_time DESC
            """, user_id)
        
        return [dict(row) for row in rows]
    finally:
        await conn.close()
    
async def get_active_btc_position_size(user_id, exchange=None):
    """Получение активной BTC позиции пользователя"""
    conn = await connect()
    try:
        if exchange:
            row = await conn.fetchrow("""
                SELECT SUM(qty * coin_buy_price) as position_size
                FROM orders
                WHERE user_id=$1 AND exchange=$2 AND symbol='BTCUSDT' AND status='OPEN'
            """, user_id, exchange)
        else:
            row = await conn.fetchrow("""
                SELECT SUM(qty * coin_buy_price) as position_size
                FROM orders
                WHERE user_id=$1 AND symbol='BTCUSDT' AND status='OPEN'
            """, user_id)
        
        await conn.close()
        return row['position_size'] if row and row['position_size'] is not None else 0.0
    finally:
        await conn.close()

async def init_db():
    """Инициализирует базу данных, проверяет и добавляет необходимые колонки."""
    conn = await connect()
    try:
        # Создаем таблицу users, если она еще не существует
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    balance REAL DEFAULT 1000.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except asyncpg.exceptions.InsufficientPrivilegeError:
            print("Недостаточно прав для создания таблицы users. Продолжаем работу с существующей.")
        
        # Создаем таблицу orders, если она еще не существует
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    exchange TEXT,
                    symbol TEXT,
                    interval TEXT,
                    side TEXT,
                    qty REAL,
                    coin_buy_price REAL,
                    coin_sale_price REAL,
                    buy_time TIMESTAMP,
                    sale_time TIMESTAMP,
                    tp_price REAL,
                    sl_price REAL,
                    status TEXT DEFAULT 'OPEN',
                    pnl_percent NUMERIC,
                    pnl_usdt REAL,
                    return_amount_usdt REAL,
                    investment_amount_usdt REAL,
                    trading_type TEXT DEFAULT 'spot',
                    leverage INTEGER DEFAULT 1,
                    price_action_active BOOLEAN,
                    price_action_pattern TEXT,
                    cm_active BOOLEAN,
                    moonbot_active BOOLEAN,
                    rsi_active BOOLEAN,
                    divergence_active BOOLEAN,
                    divergence_type TEXT
                )
            """)
        except asyncpg.exceptions.InsufficientPrivilegeError:
            print("Недостаточно прав для создания таблицы orders. Продолжаем работу с существующей.")
        
        print("База данных инициализирована успешно")
    except Exception as e:
        print(f"Ошибка при инициализации базы данных: {e}")
        # Продолжаем работу даже при ошибках
    finally:
        await conn.close()

async def migrate_strategy_fields():
    """Добавляет поля стратегий в существующую таблицу orders"""
    conn = await connect()
    try:
        # Проверяем, существуют ли уже поля стратегий
        try:
            await conn.fetchval("SELECT price_action_active FROM orders LIMIT 1")
            print("Поля стратегий уже существуют в таблице orders")
            return
        except:
            print("Добавляем поля стратегий в таблицу orders...")
        
        # Добавляем новые поля
        strategy_fields = [
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS price_action_active BOOLEAN DEFAULT FALSE",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS price_action_pattern TEXT DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS cm_active BOOLEAN DEFAULT FALSE", 
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS moonbot_active BOOLEAN DEFAULT FALSE",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS rsi_active BOOLEAN DEFAULT FALSE",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS divergence_active BOOLEAN DEFAULT FALSE",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS divergence_type TEXT DEFAULT ''"
        ]
        
        for field_sql in strategy_fields:
            try:
                await conn.execute(field_sql)
                print(f"Добавлено поле: {field_sql.split('ADD COLUMN IF NOT EXISTS')[1].split()[0]}")
            except Exception as e:
                print(f"Ошибка при добавлении поля: {e}")
        
        print("Миграция полей стратегий завершена успешно")
    except Exception as e:
        print(f"Ошибка при миграции полей стратегий: {e}")
    finally:
        await conn.close()

async def calculate_max_position_size(user_id, symbol, leverage=1):
    """
    Расчет максимального размера позиции с учетом плеча
    :param user_id: ID пользователя
    :param symbol: Торговая пара
    :param leverage: Плечо (по умолчанию 1 для spot)
    :return: Максимальный размер позиции в единицах базовой валюты
    """
    # Получаем баланс пользователя
    balance = await get_user_balance(user_id)
    
    # Получаем текущую цену актива
    # Здесь предполагается, что у вас есть функция для получения текущей цены
    # Например:
    # current_price = await get_current_price(symbol)
    # Для примера предположим, что цена BTC - 50000 USDT
    current_price = 50000  # Замените на реальное получение цены
    
    # Рассчитываем максимальное количество с учетом плеча
    # Обычно используется не весь баланс, а часть (например, 80%)
    safe_balance = balance * 0.8  # Используем 80% от доступного баланса
    
    # С учетом плеча
    max_position_value = safe_balance * leverage
    
    # Конвертируем в количество базовой валютыа
    max_qty = max_position_value / current_price
    
    return max_qty


