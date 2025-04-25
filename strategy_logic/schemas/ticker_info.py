from dataclasses import dataclass


@dataclass
class TickerInfo:
    symbol: str
    is_high_fr: bool
    is_new_ticker: bool
