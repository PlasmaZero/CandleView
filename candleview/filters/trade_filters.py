"""Filters applied before a signal becomes an actionable trade."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

import pandas as pd
import pytz

from candleview.config import FiltersConfig
from candleview.data.market_data import MarketDataClient

log = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")


class TradeFilter:
    def __init__(self, cfg: FiltersConfig, market_data: MarketDataClient):
        self.cfg = cfg
        self.market_data = market_data
        self._earnings_cache: dict[str, datetime | None] = {}

    def is_market_open(self, now: datetime | None = None) -> bool:
        if not self.cfg.market_hours_only:
            return True
        now = now or datetime.now(tz=ET)
        if now.tzinfo is None:
            now = ET.localize(now)
        else:
            now = now.astimezone(ET)
        if now.weekday() >= 5:
            return False
        open_t = _parse_hhmm(self.cfg.market_open_et)
        close_t = _parse_hhmm(self.cfg.market_close_et)
        current = now.time()
        return open_t <= current <= close_t

    def passes_volume(self, history: pd.DataFrame) -> bool:
        if history.empty or "Volume" not in history.columns:
            return False
        # Daily-equivalent: sum the most recent ~390 minutes (one session) of bars
        avg_volume = history["Volume"].tail(78).sum()  # 78 5-min bars = full session
        return avg_volume >= self.cfg.min_avg_volume

    def near_earnings(self, symbol: str, now: datetime | None = None) -> bool:
        if self.cfg.skip_earnings_window_days <= 0:
            return False
        if symbol not in self._earnings_cache:
            self._earnings_cache[symbol] = self.market_data.next_earnings_date(symbol)
        next_e = self._earnings_cache[symbol]
        if next_e is None:
            return False
        now = now or datetime.utcnow()
        if next_e.tzinfo is not None:
            next_e = next_e.replace(tzinfo=None)
        window = timedelta(days=self.cfg.skip_earnings_window_days)
        return abs((next_e - now)) <= window

    def accept(self, symbol: str, history: pd.DataFrame) -> tuple[bool, str]:
        if not self.is_market_open():
            return False, "market_closed"
        if not self.passes_volume(history):
            return False, "low_volume"
        if self.near_earnings(symbol):
            return False, "earnings_window"
        return True, "ok"


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))
