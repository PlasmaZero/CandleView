"""Execution layer tests using the PaperBroker."""

from __future__ import annotations

from candleview.config import BrokerConfig
from candleview.execution.broker import PaperBroker
from candleview.execution.order_manager import OrderManager
from candleview.signals import Direction, InstrumentType, Signal, SignalSource


def _signal() -> Signal:
    return Signal(
        symbol="AAPL",
        direction=Direction.LONG,
        instrument=InstrumentType.EQUITY,
        source=SignalSource.MOMENTUM_BREAKOUT,
        entry_price=100.0,
        target_price=102.0,
        stop_loss=99.0,
    )


def test_open_from_signal_creates_position():
    broker = PaperBroker(25_000)
    om = OrderManager(broker, BrokerConfig(default_order_type="market"))
    pos = om.open_from_signal(_signal(), quantity=10)
    assert pos is not None
    assert pos.quantity == 10
    assert pos.direction == Direction.LONG
    assert pos.entry_price == 100.0
    assert list(om.open_positions())


def test_stop_out_closes_position():
    broker = PaperBroker(25_000)
    om = OrderManager(broker, BrokerConfig(default_order_type="market"))
    pos = om.open_from_signal(_signal(), quantity=10)
    closed = om.check_exits({"AAPL": 98.5})
    assert len(closed) == 1
    closed_pos, reason, pnl = closed[0]
    assert reason == "stop_loss"
    assert pnl < 0
    assert closed_pos.closed


def test_take_profit_closes_position():
    broker = PaperBroker(25_000)
    om = OrderManager(broker, BrokerConfig(default_order_type="market"))
    pos = om.open_from_signal(_signal(), quantity=10)
    closed = om.check_exits({"AAPL": 102.5})
    assert len(closed) == 1
    closed_pos, reason, pnl = closed[0]
    assert reason == "target"
    assert pnl > 0


def test_options_position_uses_option_symbol_for_marks():
    broker = PaperBroker(25_000)
    om = OrderManager(broker, BrokerConfig(default_order_type="market"))
    sig = Signal(
        symbol="AAPL",
        direction=Direction.LONG,
        instrument=InstrumentType.CALL,
        source=SignalSource.OPTIONS_FLOW,
        entry_price=2.00,
        target_price=4.00,
        stop_loss=1.00,
        option_symbol="AAPL250115C00200000",
    )
    pos = om.open_from_signal(sig, quantity=1)
    assert pos is not None
    # Target hit on option symbol-keyed mark
    closed = om.check_exits({"AAPL250115C00200000": 4.10})
    assert len(closed) == 1
    assert closed[0][1] == "target"
    # Option PnL uses 100x multiplier
    assert closed[0][2] > 100  # (4.10 - 2.00) * 1 * 100 = $210
