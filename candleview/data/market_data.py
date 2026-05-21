"""Real-time and historical OHLCV via yfinance."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None  # type: ignore

log = logging.getLogger(__name__)


class MarketDataClient:
    """Thin wrapper over yfinance with caching and rate limiting."""

    def __init__(self, rate_limit_per_minute: int = 60, cache_ttl_seconds: int = 30):
        self.rate_limit = rate_limit_per_minute
        self.cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, pd.DataFrame]] = {}
        self._last_calls: list[float] = []

    def _throttle(self) -> None:
        now = time.time()
        self._last_calls = [t for t in self._last_calls if now - t < 60.0]
        if len(self._last_calls) >= self.rate_limit:
            sleep_for = 60.0 - (now - self._last_calls[0])
            if sleep_for > 0:
                log.debug("Rate limit reached; sleeping %.2fs", sleep_for)
                time.sleep(sleep_for)
        self._last_calls.append(time.time())

    def _cached(self, key: str) -> pd.DataFrame | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, df = entry
        if time.time() - ts > self.cache_ttl:
            return None
        return df.copy()

    def _set_cache(self, key: str, df: pd.DataFrame) -> None:
        self._cache[key] = (time.time(), df.copy())

    def history(
        self,
        symbol: str,
        interval: str = "5m",
        lookback_days: int = 5,
    ) -> pd.DataFrame:
        """Return OHLCV history for `symbol`.

        Columns: Open, High, Low, Close, Volume. Index is a tz-aware
        DatetimeIndex in US/Eastern.
        """
        key = f"{symbol}:{interval}:{lookback_days}"
        cached = self._cached(key)
        if cached is not None:
            return cached

        if yf is None:
            log.warning("yfinance not installed — returning empty frame for %s", symbol)
            return _empty_ohlcv()

        self._throttle()
        end = datetime.utcnow()
        start = end - timedelta(days=lookback_days)
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start,
                end=end,
                interval=interval,
                auto_adjust=False,
                prepost=False,
            )
        except Exception as exc:  # network / parsing errors
            log.error("history failed for %s: %s", symbol, exc)
            return _empty_ohlcv()

        if df is None or df.empty:
            return _empty_ohlcv()

        # Normalize timezone to ET for consistent session math downstream.
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert("US/Eastern")
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        self._set_cache(key, df)
        return df

    def last_price(self, symbol: str) -> float | None:
        df = self.history(symbol, interval="1m", lookback_days=1)
        if df.empty:
            return None
        return float(df["Close"].iloc[-1])

    def info(self, symbol: str) -> dict[str, Any]:
        if yf is None:
            return {}
        self._throttle()
        try:
            return dict(yf.Ticker(symbol).info or {})
        except Exception as exc:
            log.error("info failed for %s: %s", symbol, exc)
            return {}

    def next_earnings_date(self, symbol: str) -> datetime | None:
        if yf is None:
            return None
        try:
            self._throttle()
            cal = yf.Ticker(symbol).calendar
        except Exception:
            return None
        if cal is None:
            return None
        # Calendar may be a DataFrame or dict depending on yfinance version
        try:
            if hasattr(cal, "loc") and "Earnings Date" in cal.index:
                value = cal.loc["Earnings Date"].iloc[0]
            elif isinstance(cal, dict) and "Earnings Date" in cal:
                value = cal["Earnings Date"]
                if isinstance(value, (list, tuple)) and value:
                    value = value[0]
            else:
                return None
        except Exception:
            return None
        if value is None:
            return None
        try:
            return pd.to_datetime(value).to_pydatetime()
        except Exception:
            return None


def _empty_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
