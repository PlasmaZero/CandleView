"""Options chain access — yfinance by default, Tradier optional.

Returns a unified schema regardless of provider:
    symbol, expiry, strike, type, bid, ask, last, volume, open_interest,
    implied_volatility, delta, gamma, theta, vega, contract_symbol
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pandas as pd
import requests

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None  # type: ignore

log = logging.getLogger(__name__)

OPTIONS_COLUMNS = [
    "symbol",
    "expiry",
    "strike",
    "type",
    "bid",
    "ask",
    "last",
    "volume",
    "open_interest",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "contract_symbol",
]


@dataclass
class OptionsDataClient:
    provider: str = "yfinance"
    tradier_token: str | None = None
    tradier_base_url: str = "https://api.tradier.com/v1"

    def __post_init__(self) -> None:
        if self.tradier_token is None:
            self.tradier_token = os.getenv("TRADIER_TOKEN")

    def chain(
        self,
        symbol: str,
        expirations: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        if self.provider == "tradier" and self.tradier_token:
            return self._tradier_chain(symbol, expirations)
        return self._yfinance_chain(symbol, expirations)

    # ---------- yfinance ----------

    def _yfinance_chain(
        self, symbol: str, expirations: Iterable[str] | None
    ) -> pd.DataFrame:
        if yf is None:
            log.warning("yfinance not available; cannot fetch options chain for %s", symbol)
            return _empty_chain()

        try:
            ticker = yf.Ticker(symbol)
            available = list(ticker.options or [])
        except Exception as exc:
            log.error("failed to list expirations for %s: %s", symbol, exc)
            return _empty_chain()

        if not available:
            return _empty_chain()

        targets = list(expirations) if expirations else available
        frames: list[pd.DataFrame] = []
        for exp in targets:
            if exp not in available:
                continue
            try:
                chain = ticker.option_chain(exp)
            except Exception as exc:
                log.warning("option_chain %s %s failed: %s", symbol, exp, exc)
                continue
            frames.append(_normalize_yf(symbol, exp, chain.calls, "call"))
            frames.append(_normalize_yf(symbol, exp, chain.puts, "put"))

        if not frames:
            return _empty_chain()
        return pd.concat(frames, ignore_index=True)

    # ---------- Tradier ----------

    def _tradier_chain(
        self, symbol: str, expirations: Iterable[str] | None
    ) -> pd.DataFrame:
        headers = {
            "Authorization": f"Bearer {self.tradier_token}",
            "Accept": "application/json",
        }
        try:
            r = requests.get(
                f"{self.tradier_base_url}/markets/options/expirations",
                params={"symbol": symbol, "includeAllRoots": "true"},
                headers=headers,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json().get("expirations", {}) or {}
            available = data.get("date", []) if isinstance(data, dict) else []
            if isinstance(available, str):
                available = [available]
        except Exception as exc:
            log.error("Tradier expirations failed for %s: %s", symbol, exc)
            return _empty_chain()

        targets = list(expirations) if expirations else available
        frames: list[pd.DataFrame] = []
        for exp in targets:
            if exp not in available:
                continue
            try:
                r = requests.get(
                    f"{self.tradier_base_url}/markets/options/chains",
                    params={"symbol": symbol, "expiration": exp, "greeks": "true"},
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                body = r.json().get("options", {}) or {}
                rows = body.get("option", []) if isinstance(body, dict) else []
                if isinstance(rows, dict):
                    rows = [rows]
            except Exception as exc:
                log.warning("Tradier chain %s %s failed: %s", symbol, exp, exc)
                continue
            frames.append(_normalize_tradier(symbol, exp, rows))

        if not frames:
            return _empty_chain()
        return pd.concat(frames, ignore_index=True)

    # ---------- helpers ----------

    @staticmethod
    def iv_percentile(chain: pd.DataFrame) -> pd.Series:
        """Per-contract IV percentile relative to the symbol's full chain."""
        if chain.empty or "implied_volatility" not in chain:
            return pd.Series(dtype=float)
        ivs = chain["implied_volatility"].astype(float)
        return ivs.rank(pct=True) * 100.0

    @staticmethod
    def days_to_expiry(chain: pd.DataFrame, today: datetime | None = None) -> pd.Series:
        if chain.empty:
            return pd.Series(dtype=float)
        now = today or datetime.utcnow()
        exp_dt = pd.to_datetime(chain["expiry"])
        return (exp_dt - pd.Timestamp(now)).dt.days.clip(lower=0)


def _normalize_yf(symbol: str, expiry: str, df: pd.DataFrame, opt_type: str) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_chain()
    out = pd.DataFrame(
        {
            "symbol": symbol,
            "expiry": expiry,
            "strike": df.get("strike"),
            "type": opt_type,
            "bid": df.get("bid"),
            "ask": df.get("ask"),
            "last": df.get("lastPrice"),
            "volume": df.get("volume").fillna(0) if "volume" in df else 0,
            "open_interest": df.get("openInterest").fillna(0) if "openInterest" in df else 0,
            "implied_volatility": df.get("impliedVolatility"),
            "delta": pd.NA,
            "gamma": pd.NA,
            "theta": pd.NA,
            "vega": pd.NA,
            "contract_symbol": df.get("contractSymbol"),
        }
    )
    return out[OPTIONS_COLUMNS]


def _normalize_tradier(symbol: str, expiry: str, rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return _empty_chain()
    records = []
    for row in rows:
        greeks = row.get("greeks") or {}
        records.append(
            {
                "symbol": symbol,
                "expiry": expiry,
                "strike": row.get("strike"),
                "type": row.get("option_type"),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "last": row.get("last"),
                "volume": row.get("volume") or 0,
                "open_interest": row.get("open_interest") or 0,
                "implied_volatility": greeks.get("mid_iv") or greeks.get("smv_vol"),
                "delta": greeks.get("delta"),
                "gamma": greeks.get("gamma"),
                "theta": greeks.get("theta"),
                "vega": greeks.get("vega"),
                "contract_symbol": row.get("symbol"),
            }
        )
    return pd.DataFrame(records)[OPTIONS_COLUMNS]


def _empty_chain() -> pd.DataFrame:
    return pd.DataFrame(columns=OPTIONS_COLUMNS)
