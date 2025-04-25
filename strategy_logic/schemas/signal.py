from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Signal:
    type: Literal["rise", "volume", "fall", "pa"]
    is_high_fr: bool
    chart_preview: bool
    signal_value: float | str
    user_id: int

    def __str__(self):
        return f"{self.type} for {self.user_id} {self.is_high_fr} {self.signal_value} {self.chart_preview}"
