"""Pure-pandas technical indicators.

Implemented from scratch so the engine has no hard dependency on TA-Lib.
All functions take/return pandas Series or DataFrames; OHLCV columns are
the standard yfinance casing: Open, High, Low, Close, Volume.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(50.0)


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP — resets each trading day."""
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv = typical * df["Volume"]
    # Group by date to reset VWAP each session
    if isinstance(df.index, pd.DatetimeIndex):
        session = df.index.tz_convert("US/Eastern").date if df.index.tz else df.index.date
    else:
        session = pd.Series(range(len(df))).values
    cum_pv = pd.Series(pv.values, index=df.index).groupby(session).cumsum()
    cum_vol = df["Volume"].groupby(session).cumsum().replace(0.0, np.nan)
    return cum_pv / cum_vol


def bollinger_bands(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(window=period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return pd.DataFrame({"bb_mid": mid, "bb_upper": upper, "bb_lower": lower})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist}
    )


def volume_profile(df: pd.DataFrame, bins: int = 24) -> pd.DataFrame:
    """Volume-by-price profile over the window in `df`.

    Returns a DataFrame with `price_low`, `price_high`, `volume` rows. The
    most-traded bin is the Point of Control (POC); the highest-volume
    contiguous band covering 70% of volume is the Value Area.
    """
    if df.empty:
        return pd.DataFrame(columns=["price_low", "price_high", "volume"])
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    lo, hi = float(typical.min()), float(typical.max())
    if hi == lo:
        hi = lo + 1e-6
    edges = np.linspace(lo, hi, bins + 1)
    idx = np.clip(np.digitize(typical.values, edges) - 1, 0, bins - 1)
    vol_by_bin = np.zeros(bins)
    np.add.at(vol_by_bin, idx, df["Volume"].values)
    rows = [
        {"price_low": float(edges[i]), "price_high": float(edges[i + 1]), "volume": float(vol_by_bin[i])}
        for i in range(bins)
    ]
    return pd.DataFrame(rows)


def point_of_control(profile: pd.DataFrame) -> float | None:
    if profile.empty:
        return None
    row = profile.loc[profile["volume"].idxmax()]
    return float((row["price_low"] + row["price_high"]) / 2.0)


def add_all_indicators(
    df: pd.DataFrame,
    ema_periods: tuple[int, int, int] = (9, 21, 50),
    rsi_period: int = 14,
    bb_period: int = 20,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Append all standard indicators to an OHLCV frame.

    The frame must have columns: Open, High, Low, Close, Volume.
    Returns a new DataFrame; the original is not mutated.
    """
    out = df.copy()
    if out.empty:
        return out
    fast, slow, trend = ema_periods
    out[f"ema_{fast}"] = ema(out["Close"], fast)
    out[f"ema_{slow}"] = ema(out["Close"], slow)
    out[f"ema_{trend}"] = ema(out["Close"], trend)
    out["rsi"] = rsi(out["Close"], rsi_period)
    out["vwap"] = vwap(out)
    bb = bollinger_bands(out["Close"], bb_period)
    out = pd.concat([out, bb], axis=1)
    out["atr"] = atr(out, atr_period)
    out = pd.concat([out, macd(out["Close"])], axis=1)
    return out
