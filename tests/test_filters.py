"""Filter logic — uses a dummy market_data client so no network calls."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytz

from candleview.config import FiltersConfig
from candleview.filters.trade_filters import TradeFilter

ET = pytz.timezone("US/Eastern")


def _fake_market_data():
    m = MagicMock()
    m.next_earnings_date.return_value = None
    return m


def test_market_hours_open_inside_window():
    f = TradeFilter(FiltersConfig(), _fake_market_data())
    assert f.is_market_open(now=ET.localize(datetime(2025, 1, 6, 10, 30)))  # Mon 10:30 ET


def test_market_hours_closed_on_weekend():
    f = TradeFilter(FiltersConfig(), _fake_market_data())
    assert not f.is_market_open(now=ET.localize(datetime(2025, 1, 4, 10, 30)))  # Sat


def test_market_hours_closed_before_open():
    f = TradeFilter(FiltersConfig(), _fake_market_data())
    assert not f.is_market_open(now=ET.localize(datetime(2025, 1, 6, 9, 0)))


def test_volume_filter_passes_above_threshold():
    cfg = FiltersConfig(min_avg_volume=1_000)
    f = TradeFilter(cfg, _fake_market_data())
    history = pd.DataFrame({"Volume": [10_000] * 10}, index=pd.date_range("2025-01-02", periods=10, freq="5min"))
    assert f.passes_volume(history)


def test_volume_filter_fails_below_threshold():
    cfg = FiltersConfig(min_avg_volume=10_000_000)
    f = TradeFilter(cfg, _fake_market_data())
    history = pd.DataFrame({"Volume": [100] * 10}, index=pd.date_range("2025-01-02", periods=10, freq="5min"))
    assert not f.passes_volume(history)


def test_earnings_window_skip():
    cfg = FiltersConfig(skip_earnings_window_days=2)
    md = _fake_market_data()
    # next earnings 1 day from now
    md.next_earnings_date.return_value = datetime.utcnow().replace(microsecond=0) + __import__("datetime").timedelta(days=1)
    f = TradeFilter(cfg, md)
    assert f.near_earnings("AAPL")
