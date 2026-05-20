"""Risk manager and position sizing tests."""

from __future__ import annotations

import pytest

from candleview.config import RiskConfig
from candleview.risk.manager import RiskManager
from candleview.risk.position_sizing import (
    fixed_fractional,
    kelly_fraction,
    kelly_position_size,
)
from candleview.signals import Direction, InstrumentType, Signal, SignalSource


def _equity_signal(entry: float = 100.0, stop: float = 99.0, target: float = 102.0) -> Signal:
    return Signal(
        symbol="AAPL",
        direction=Direction.LONG,
        instrument=InstrumentType.EQUITY,
        source=SignalSource.MOMENTUM_BREAKOUT,
        entry_price=entry,
        target_price=target,
        stop_loss=stop,
    )


def test_fixed_fractional_size_with_known_inputs():
    # 25k account, 1% risk = $250 risk budget. Risk/share = $1 → 250 shares.
    qty = fixed_fractional(25_000, 1.0, 1.0)
    assert qty == 250


def test_kelly_fraction_basic():
    # 60% win, 2:1 reward = 0.6 - 0.4/2 = 0.4
    assert kelly_fraction(0.6, 2.0) == pytest.approx(0.4)


def test_kelly_position_size_caps_at_fixed_fractional_via_manager():
    cfg = RiskConfig(
        account_value=25_000,
        max_risk_per_trade_pct=1.0,
        position_sizing="kelly",
        kelly_fraction=1.0,
    )
    risk = RiskManager(cfg)
    # Force "good" history so Kelly says big size
    for _ in range(8):
        risk.record_trade_result(100.0)
    for _ in range(2):
        risk.record_trade_result(-50.0)
    qty = risk.size_for(_equity_signal())
    # Even with great stats, fixed_fractional cap of 250 holds
    assert qty <= 250


def test_risk_manager_size_zero_when_risk_zero():
    risk = RiskManager(RiskConfig(account_value=25_000))
    qty = risk.size_for(_equity_signal(entry=100, stop=100, target=101))
    assert qty == 0


def test_daily_loss_cap_halts_engine():
    cfg = RiskConfig(account_value=10_000, max_daily_loss_pct=3.0)
    risk = RiskManager(cfg)
    risk.record_trade_result(-200)
    assert not risk.is_halted()
    risk.record_trade_result(-150)  # total -350 > 3% of 10k = 300
    assert risk.is_halted()
    ok, reason = risk.can_open([])
    assert not ok
    assert "Daily loss cap" in reason


def test_position_sizing_for_options_uses_100_multiplier():
    risk = RiskManager(RiskConfig(account_value=25_000, max_risk_per_trade_pct=1.0))
    sig = Signal(
        symbol="AAPL",
        direction=Direction.LONG,
        instrument=InstrumentType.CALL,
        source=SignalSource.OPTIONS_FLOW,
        entry_price=2.00,
        target_price=4.00,
        stop_loss=1.00,
    )
    # Risk/contract = $1 * 100 multiplier = $100. Budget $250 → 2 contracts.
    qty = risk.size_for(sig)
    assert qty == 2


def test_concurrent_positions_cap():
    from types import SimpleNamespace

    cfg = RiskConfig(max_concurrent_positions=2)
    risk = RiskManager(cfg)
    fake_positions = [SimpleNamespace(closed=False), SimpleNamespace(closed=False)]
    ok, reason = risk.can_open(fake_positions)
    assert not ok
    assert reason == "max_concurrent_positions"
