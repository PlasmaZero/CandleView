"""Trade log tests."""

from __future__ import annotations

import os
import tempfile

from candleview.signals import Direction, InstrumentType, Position, Signal, SignalSource
from candleview.storage.trade_log import TradeLog


def test_trade_log_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "trades.sqlite")
        csv = os.path.join(tmp, "trades.csv")
        log = TradeLog(db, csv)
        log.record_signal(
            Signal(
                symbol="AAPL",
                direction=Direction.LONG,
                instrument=InstrumentType.EQUITY,
                source=SignalSource.MOMENTUM_BREAKOUT,
                entry_price=100.0,
                target_price=102.0,
                stop_loss=99.0,
            )
        )
        pos = Position(
            symbol="AAPL",
            instrument=InstrumentType.EQUITY,
            direction=Direction.LONG,
            quantity=10,
            entry_price=100.0,
            stop_loss=99.0,
            target_price=102.0,
            opened_at=__import__("datetime").datetime.utcnow(),
            source=SignalSource.MOMENTUM_BREAKOUT,
        )
        log.record_open(pos)
        log.record_close(pos, exit_price=102.0, pnl=20.0, reason="target")

        summary = log.summary()
        assert summary["closed_trades"] == 1
        assert summary["wins"] == 1
        assert summary["total_pnl"] == 20.0
        assert os.path.getsize(csv) > 0
