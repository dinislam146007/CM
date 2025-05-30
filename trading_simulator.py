"""
Trading Simulator for backtesting strategies
"""

import pandas as pd
from typing import Dict, Any, List

# Global balances dictionary for simulation
balances = {}

def init_balance(symbol: str, amount: float):
    """Initialize balance for a symbol"""
    balances[symbol] = amount

def create_order(symbol: str, side: str, qty: float, price: float, tp_price: float, sl_price: float, leverage: int, trading_type: str):
    """
    Create a new order in the simulator
    
    Args:
        symbol: Trading pair symbol
        side: "LONG" or "SHORT"
        qty: Quantity
        price: Entry price
        tp_price: Take profit price
        sl_price: Stop loss price
        leverage: Leverage multiplier
        trading_type: "spot" or "futures"
    """
    # расчёт инвестиции
    if trading_type == "futures":
        # на фьючерсах инвестируется только маржа = (qty*price)/leverage
        investment_amount = (qty * price) / leverage
    else:
        investment_amount = qty * price

    # снимем сумму с баланса
    balances[symbol] -= investment_amount

    order = {
        "symbol": symbol,
        "side": side.upper(),  # "LONG" или "SHORT"
        "qty": qty,
        "entry_price": price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "leverage": leverage,
        "investment": investment_amount,
        "trading_type": trading_type,
    }
    save_order(order)
    return order

def close_order(order: Dict[str, Any], last_candle: Dict[str, float], balances: Dict[str, float]):
    """
    Close an order based on the last candle data
    
    Args:
        order: Order dictionary
        last_candle: Dictionary with "open", "high", "low", "close" prices
        balances: Balances dictionary
    """
    # Определим направление
    side = order["side"].upper()
    # приводим к нашему формату
    is_long = (side == "LONG")

    # проверка TP/SL по high/low свечи
    high = last_candle["high"]
    low = last_candle["low"]
    tp = order["tp_price"]
    sl = order["sl_price"]

    if is_long:
        hit_tp = high >= tp
        hit_sl = low <= sl
    else:
        hit_tp = low <= tp
        hit_sl = high >= sl

    # если оба уровня пробиты — определяем по итоговой цене свечи
    exit_price = last_candle["close"]
    if hit_tp and hit_sl:
        hit_tp = (exit_price > order["entry_price"])
        hit_sl = not hit_tp

    # если ни один не сработал — остаёмся на close
    if not (hit_tp or hit_sl):
        exit_price = exit_price

    # расчёт PnL
    if is_long:
        pnl = (exit_price - order["entry_price"]) * order["qty"]
    else:
        pnl = (order["entry_price"] - exit_price) * order["qty"]

    # итоговый возврат
    ret = order["investment"] + pnl
    # для фьючерсов: если убыток больше маржи — симулируем ликвидацию
    if order["trading_type"] == "futures" and ret < 0:
        ret = 0

    # возвращаем на баланс
    balances[order["symbol"]] += ret

    order["exit_price"] = exit_price
    order["pnl"] = pnl
    order["closed"] = True

    update_order(order)
    return order

def save_order(order: Dict[str, Any]):
    """Save order to storage (placeholder)"""
    # This would save to database or file
    pass

def update_order(order: Dict[str, Any]):
    """Update order in storage (placeholder)"""
    # This would update in database or file
    pass

def get_balance(symbol: str) -> float:
    """Get current balance for symbol"""
    return balances.get(symbol, 0.0)

def run_backtest(data: pd.DataFrame, initial_balance: float = 10000.0):
    """
    Run a basic backtest on provided data
    
    Args:
        data: DataFrame with OHLCV data
        initial_balance: Starting balance in USDT
    """
    # Initialize balance
    init_balance("USDT", initial_balance)
    
    orders = []
    
    # Simulate trading logic here
    for i, row in data.iterrows():
        candle = {
            "open": row["open"],
            "high": row["high"], 
            "low": row["low"],
            "close": row["close"]
        }
        
        # Example: Close existing orders
        for order in orders:
            if not order.get("closed", False):
                close_order(order, candle, balances)
    
    return orders, balances 