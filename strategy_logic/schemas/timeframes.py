from enum import Enum


class Timeframes(Enum):
    INTERVAL_1HOUR = '1h'
    INTERVAL_4HOUR = '4h'
    INTERVAL_1DAY = '1D'

    @classmethod
    def get_db_timeframe(cls, timeframe) -> str:
        return {
            cls.INTERVAL_1HOUR: "1h",
            cls.INTERVAL_4HOUR: "4h",
            cls.INTERVAL_1DAY: "1D",
        }[timeframe]
