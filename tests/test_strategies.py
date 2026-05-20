"""Strategy unit tests with synthetic data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from candleview.config import MomentumBreakoutConfig, OptionsFlowConfig
from candleview.data.indicators import add_all_indicators
from candleview.signals import Direction, InstrumentType, SignalSource
from candleview.strategies.base import StrategyContext
from candleview.strategies.momentum_breakout import MomentumBreakoutStrategy
from candleview.strategies.options_flow import OptionsFlowStrategy


def _flat_then_breakout(n: int = 120) -> pd.DataFrame:
    # First 90 bars: drift up gently to build EMA stack. Bar 100: clean breakout
    # above resistance with a single volume spike. Bars 101..119: cool off so
    # RSI doesn't go parabolic but the breakout bar still wins.
    rng = np.random.default_rng(11)
    drift = np.linspace(98, 100, 90)
    flat_close = drift + rng.normal(0, 0.15, 90)
    consolidate = 100 + rng.normal(0, 0.15, 10)
    breakout = np.concatenate([[101.5], np.linspace(101.6, 102.5, 19)])
    close = np.concatenate([flat_close, consolidate, breakout])
    assert len(close) == n
    high = close + 0.3
    low = close - 0.3
    open_ = close + rng.normal(0, 0.1, n)
    volume = np.concatenate(
        [
            rng.integers(80_000, 120_000, 90),
            rng.integers(80_000, 120_000, 10),
            [600_000],
            rng.integers(150_000, 250_000, 19),
        ]
    )
    idx = pd.date_range("2025-01-02 09:30", periods=n, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def test_momentum_breakout_fires_on_clean_breakout():
    # Fire the strategy at the bar where the breakout actually happens
    # (bar 100 — the one with the volume spike).
    df = _flat_then_breakout()
    cut = df.iloc[:101]
    indicators = add_all_indicators(cut)
    strat = MomentumBreakoutStrategy(MomentumBreakoutConfig())
    ctx = StrategyContext(symbol="AAPL", history=indicators, options_chain=None)
    signals = strat.generate(ctx)
    assert len(signals) == 1
    s = signals[0]
    assert s.direction == Direction.LONG
    assert s.source == SignalSource.MOMENTUM_BREAKOUT
    assert s.instrument == InstrumentType.EQUITY
    assert s.target_price > s.entry_price > s.stop_loss
    assert s.reward_risk_ratio >= 1.5


def test_momentum_breakout_silent_in_chop():
    rng = np.random.default_rng(3)
    n = 80
    close = 100 + rng.normal(0, 0.5, n)
    high = close + 0.2
    low = close - 0.2
    open_ = close + rng.normal(0, 0.1, n)
    volume = rng.integers(80_000, 120_000, n)
    idx = pd.date_range("2025-01-02 09:30", periods=n, freq="5min", tz="US/Eastern")
    df = add_all_indicators(
        pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=idx)
    )
    strat = MomentumBreakoutStrategy(MomentumBreakoutConfig())
    ctx = StrategyContext(symbol="AAPL", history=df, options_chain=None)
    assert strat.generate(ctx) == []


def _unusual_chain() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {  # unusual call: 5x vol vs OI, high IV percentile, near expiry
                "symbol": "AAPL",
                "expiry": (pd.Timestamp.now("UTC") + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
                "strike": 200.0,
                "type": "call",
                "bid": 1.95,
                "ask": 2.05,
                "last": 2.00,
                "volume": 5000,
                "open_interest": 1000,
                "implied_volatility": 0.65,
                "delta": 0.5,
                "gamma": 0.04,
                "theta": -0.03,
                "vega": 0.10,
                "contract_symbol": "AAPL250115C00200000",
            },
            {
                "symbol": "AAPL",
                "expiry": (pd.Timestamp.now("UTC") + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
                "strike": 195.0,
                "type": "put",
                "bid": 0.95,
                "ask": 1.05,
                "last": 1.00,
                "volume": 50,
                "open_interest": 2000,
                "implied_volatility": 0.30,
                "delta": -0.4,
                "gamma": 0.03,
                "theta": -0.02,
                "vega": 0.08,
                "contract_symbol": "AAPL250115P00195000",
            },
        ]
    )


def test_options_flow_picks_unusual_calls():
    chain = _unusual_chain()
    strat = OptionsFlowStrategy(OptionsFlowConfig(iv_percentile_min=50.0))
    ctx = StrategyContext(symbol="AAPL", history=pd.DataFrame(), options_chain=chain)
    signals = strat.generate(ctx)
    assert any(s.instrument == InstrumentType.CALL for s in signals)
    s = next(s for s in signals if s.instrument == InstrumentType.CALL)
    assert s.entry_price > 0
    assert s.target_price > s.entry_price > s.stop_loss
