"""End-to-end smoke test that wires the engine together without touching the network."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from candleview.config import Config
from candleview.engine import Engine
from candleview.execution.broker import PaperBroker


def _build_breakout_df(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    drift = np.linspace(98, 100, 90)
    flat_close = drift + rng.normal(0, 0.15, 90)
    consolidate = 100 + rng.normal(0, 0.15, 10)
    breakout = np.concatenate([[101.5], np.linspace(101.6, 102.5, 19)])
    close = np.concatenate([flat_close, consolidate, breakout])
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
    # Pin to a known weekday/time so the market-hours filter passes
    idx = pd.date_range("2025-01-06 09:30", periods=n, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def test_engine_run_once_generates_signal_and_opens_position(tmp_path):
    cfg = Config()
    cfg.tickers = ["AAPL"]
    cfg.storage.sqlite_path = str(tmp_path / "trades.sqlite")
    cfg.storage.csv_path = str(tmp_path / "trades.csv")
    cfg.strategies.options_flow.enabled = False  # equity-only for this smoke test
    cfg.filters.market_hours_only = False         # ignore local clock
    cfg.filters.skip_earnings_window_days = 0
    cfg.broker.default_order_type = "market"

    broker = PaperBroker(starting_cash=25_000)
    engine = Engine(cfg, broker=broker)

    df = _build_breakout_df().iloc[:101]
    with patch.object(engine.market_data, "history", return_value=df):
        result = engine.run_once()

    assert result["new_signals"] >= 1
    assert result["open_positions"] >= 1
    snap = engine.snapshot()
    assert snap["signals"]
    assert snap["positions"]


def test_engine_run_once_no_signal_in_chop(tmp_path):
    cfg = Config()
    cfg.tickers = ["AAPL"]
    cfg.storage.sqlite_path = str(tmp_path / "trades.sqlite")
    cfg.storage.csv_path = str(tmp_path / "trades.csv")
    cfg.strategies.options_flow.enabled = False
    cfg.filters.market_hours_only = False
    cfg.filters.skip_earnings_window_days = 0

    broker = PaperBroker(starting_cash=25_000)
    engine = Engine(cfg, broker=broker)

    rng = np.random.default_rng(2)
    n = 120
    close = 100 + rng.normal(0, 0.5, n)
    high = close + 0.2
    low = close - 0.2
    open_ = close + rng.normal(0, 0.1, n)
    volume = rng.integers(80_000, 120_000, n)
    idx = pd.date_range("2025-01-06 09:30", periods=n, freq="5min", tz="US/Eastern")
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=idx)

    with patch.object(engine.market_data, "history", return_value=df):
        result = engine.run_once()

    assert result["new_signals"] == 0
    assert result["open_positions"] == 0
