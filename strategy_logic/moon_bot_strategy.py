"""
Moon Bot \"0.3‑0.5 long\" strategy — Python translation
========================================================

This module transplants the parameters and logic of your Moon Bot strategy
(see the block between ##Begin_Strategy / ##End_Strategy) into pure Python so
it can be imported by your existing async trading framework.

Usage example (inside *process_timeframe*):

```python
from strategy_logic.moon_bot_strategy import StrategyMoonBot, load_strategy_params

# create once, outside the loop
moon_params = load_strategy_params()
moon = StrategyMoonBot(moon_params)

...

btc_df_5m = await fetch_ohlcv("BTCUSDT", "5m", limit=300)  # ≈ 24 h of 5‑min bars
sym_ticker = await exchange.fetch_ticker(symbol)

if moon.check_coin(symbol, sym_ticker, df_5m, btc_df_5m):
    if moon.should_place_order(df_5m):
        order = moon.build_order(df_5m)
        try:
            await exchange.create_order(symbol, order["type"], order["side"],
                                        order["amount"], order["price"])
        except Exception as e:
            logging.error(f"order error {symbol}: {e}")
```

The helper returns a **dict** ready for `exchange.create_order()` and embeds the
main risk‑management fields (TP/SL) for downstream handling.  Fine‑tune the
rule‑set in *StrategyMoonBot.should_place_order* or extend the dataclass if you
need the full MoonBot feature set (MShot, trailing, etc.).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Dict, Any, Optional, Set

import numpy as np
import pandas as pd

__all__ = [
    "load_strategy_params",
    "StrategyMoonBot",
]

###############################################################################
# ↑ Public interface only – everything below can be edited safely.            #
###############################################################################

# ---------------------------------------------------------------------------
# 1. MoonBot config ⇒ Python dict                                             
# ---------------------------------------------------------------------------

DEFAULT_PARAMS: Dict[str, Any] = {
    # -------- general --------
    "Active": 0,
    "CoinsBlackList": {
        "LUNA", "AVAX", "1INCH", "REN", "SRM", "UFI", "BZRX", "NEAR", "XTZ", "ANKR",
    },
    # -------- volumes (USDT) --------
    "MinVolume": 5_000_000,        # 5000k
    "MaxVolume": 100_000_000_000,  # 100000M
    "MinHourlyVolume": 1_000_000,  # 1000k
    "MaxHourlyVolume": 10_000_000_000,  # 10000M
    # -------- deltas (%) --------
    "Delta_3h_Max": 100.0,
    "Delta_24h_Max": 700.0,
    "Delta2_Max": 100.0,           # 5‑minute delta
    "Delta_BTC_Min": -50.0,
    "Delta_BTC_Max": 50.0,
    # (one can add Delta_Market* here if you calculate a market index)
    # -------- order sizing / exits --------
    "OrderSize": 2_500.0,          # fixed USDT per order
    "SellPrice": 0.4,              # legacy field – not used directly here
    "TakeProfit": 2.0,             # +2 % TP
    "StopLoss": -0.4,              # –0.4 % SL
    # second/third stop blocks skipped for brevity – extend if needed
}


def load_strategy_params(user_id: Optional[int] = None) -> Dict[str, Any]:
    """Return strategy parameters for a specific user or default parameters.
    
    If user_id is provided and user has custom parameters, return those.
    Otherwise, return a copy of the default parameters.
    """
    if user_id is not None:
        try:
            # Use relative import to avoid circular import issues
            from strategy_logic.user_strategy_params import load_user_params
            return load_user_params(user_id)
        except Exception as e:
            print(f"Error loading user parameters: {e}")

    return DEFAULT_PARAMS.copy()


# ---------------------------------------------------------------------------
# 2. Strategy engine                                                          
# ---------------------------------------------------------------------------

@dataclass
class Context:
    """Reusable market context passed to filters (keeps your signature tidy)."""

    ticker_24h: Dict[str, Any]      # result of exchange.fetch_ticker(symbol)
    hourly_volume: float            # sum(df["volume"].iloc[-12:]) assuming 5‑min bars
    btc_df: pd.DataFrame            # 5‑min BTCUSDT OHLCV


class StrategyMoonBot:
    """Lightweight clone of Moon Bot \"0.3‑0.5 long\" (core subset).

    The goal is **not** a 1‑to‑1 re‑implementation of every feature – MoonBot
    has plenty of micro‑behaviours – but a pragmatic subset that fits your
    async CCXT pipeline.  Add more guards / actions where marked *TODO*.
    """

    def __init__(self, params: Dict[str, Any]):
        self.p = params

    # ==============================
    # Filters                        
    # ==============================

    # ----- helpers -----
    @staticmethod
    def _delta(series: pd.Series, bars: int) -> float:
        """Return percentage move between *now* and *bars* ago."""
        if bars >= len(series):
            return 0.0
        prev = series.iloc[-bars]
        if prev == 0:
            return 0.0
        return (series.iloc[-1] - prev) / prev * 100.0

    def _allowed_coin(self, symbol: str) -> bool:
        base = symbol.replace("USDT", "")
        return base not in self.p["CoinsBlackList"]

    def _volume_ok(self, ctx: Context) -> bool:
        return (
            self.p["MinVolume"] <= ctx.ticker_24h.get("quoteVolume", 0) <= self.p["MaxVolume"]
            and self.p["MinHourlyVolume"] <= ctx.hourly_volume <= self.p["MaxHourlyVolume"]
        )

    def _delta_ok(self, df: pd.DataFrame) -> bool:
        d_3h = self._delta(df["close"], 36)    # 36×5‑min ≈ 3 h
        d_24h = self._delta(df["close"], 288)  # 288×5‑min ≈ 24 h
        d_5m = self._delta(df["close"], 1)
        return (
            d_3h <= self.p["Delta_3h_Max"]
            and d_24h <= self.p["Delta_24h_Max"]
            and d_5m <= self.p["Delta2_Max"]
        )

    def _btc_ok(self, ctx: Context) -> bool:
        btc_24h = self._delta(ctx.btc_df["close"], 288)
        return self.p["Delta_BTC_Min"] <= btc_24h <= self.p["Delta_BTC_Max"]

    # ----- public -----
    def check_coin(
        self,
        symbol: str,
        df_5m: pd.DataFrame,
        ctx: Context,
    ) -> bool:
        """Return **True** if *symbol* passes every MoonBot filter."""

        return (
            self._allowed_coin(symbol)
            and self._volume_ok(ctx)
            and self._delta_ok(df_5m)
            and self._btc_ok(ctx)
            # TODO – add market deltas / price‑step / MarkPrice filters 
        )

    # ==============================
    # Entry / exit rules             
    # ==============================

    def should_place_order(self, df_5m: pd.DataFrame) -> bool:
        """Basic long condition: last candle closed green **and**
        previous candle was red (simple momentum flip).  Replace with your
        preferred signal (RSI, PPO, etc.) if stricter logic is needed."""

        if len(df_5m) < 2:
            return False
        last = df_5m.iloc[-1]
        prev = df_5m.iloc[-2]
        return last["close"] > last["open"] and prev["close"] < prev["open"]

    def build_order(self, df_5m: pd.DataFrame) -> Dict[str, Any]:
        price = df_5m["close"].iloc[-1]
        qty = round(self.p["OrderSize"] / price, 8)

        tp = price * (1 + self.p["TakeProfit"] / 100.0)
        sl = price * (1 + self.p["StopLoss"] / 100.0)

        # exchange.create_order doesn't support TP/SL natively on spot, so we
        # return them as annotations for your risk manager.
        return {
            "side": "buy",
            "type": "limit",
            "price": price,
            "amount": qty,
            "take_profit": tp,
            "stop_loss": sl,
            "meta": {
                "strategy": "moon_0.3‑0.5_long",
            },
        }
    
    
