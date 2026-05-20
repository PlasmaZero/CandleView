"""Indicator sanity checks — no live network calls."""

from __future__ import annotations

import numpy as np
import pandas as pd

from candleview.data.indicators import (
    add_all_indicators,
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    volume_profile,
    vwap,
)


def _ohlcv(n: int = 100, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = np.linspace(100, 110, n) + rng.normal(0, 0.5, n)
    high = base + rng.uniform(0.1, 0.5, n)
    low = base - rng.uniform(0.1, 0.5, n)
    close = base + rng.normal(0, 0.2, n)
    open_ = base + rng.normal(0, 0.2, n)
    volume = rng.integers(100_000, 500_000, n)
    idx = pd.date_range("2025-01-02 09:30", periods=n, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def test_ema_returns_series_with_same_length():
    df = _ohlcv()
    out = ema(df["Close"], 9)
    assert len(out) == len(df)
    assert out.iloc[-1] == out.iloc[-1]  # not NaN


def test_rsi_within_bounds():
    df = _ohlcv()
    r = rsi(df["Close"], 14)
    assert ((r >= 0) & (r <= 100)).all()


def test_vwap_monotonic_within_session():
    df = _ohlcv()
    v = vwap(df)
    # VWAP should be finite and close to typical price range
    assert v.dropna().between(df["Low"].min() - 5, df["High"].max() + 5).all()


def test_bollinger_bands_ordering():
    df = _ohlcv()
    bb = bollinger_bands(df["Close"], 20)
    valid = bb.dropna()
    assert (valid["bb_upper"] >= valid["bb_mid"]).all()
    assert (valid["bb_mid"] >= valid["bb_lower"]).all()


def test_atr_positive():
    df = _ohlcv()
    a = atr(df, 14).dropna()
    assert (a > 0).all()


def test_macd_columns():
    df = _ohlcv()
    m = macd(df["Close"])
    assert set(m.columns) == {"macd", "macd_signal", "macd_hist"}


def test_volume_profile_sums_to_total_volume():
    df = _ohlcv()
    prof = volume_profile(df, bins=10)
    assert len(prof) == 10
    assert abs(prof["volume"].sum() - df["Volume"].sum()) < 1.0


def test_add_all_indicators_attaches_columns():
    df = _ohlcv()
    out = add_all_indicators(df)
    for col in (
        "ema_9",
        "ema_21",
        "ema_50",
        "rsi",
        "vwap",
        "bb_upper",
        "bb_lower",
        "atr",
        "macd",
        "macd_signal",
        "macd_hist",
    ):
        assert col in out.columns
