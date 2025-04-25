from dataclasses import dataclass

from .pattern import Pattern


@dataclass
class RFVPChanges:  # RiseFallVolumePattern changes
    ticker: str
    rise: float
    fall: float
    volume: float
    pattern: Pattern
