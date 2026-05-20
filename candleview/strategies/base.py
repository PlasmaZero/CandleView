"""Strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from candleview.signals import Signal


@dataclass
class StrategyContext:
    symbol: str
    history: pd.DataFrame              # OHLCV + indicators
    options_chain: pd.DataFrame | None  # may be None for equity-only strategies


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, ctx: StrategyContext) -> list[Signal]:
        """Return zero or more signals for the given symbol."""
