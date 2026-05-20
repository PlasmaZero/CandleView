"""Order and position management — bridges signals, broker, and risk.

The OrderManager:
- accepts admitted Signals and turns them into Orders + Positions
- tracks open positions and applies stop-loss / take-profit checks
- handles partial fills by re-querying the broker
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Iterable

from candleview.config import BrokerConfig
from candleview.execution.broker import Broker, BrokerError, BrokerOrder
from candleview.signals import Direction, InstrumentType, Order, Position, Signal

log = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, broker: Broker, cfg: BrokerConfig):
        self.broker = broker
        self.cfg = cfg
        self.positions: dict[str, Position] = {}
        self.open_broker_orders: dict[str, BrokerOrder] = {}

    # ---------- opening ----------

    def open_from_signal(self, signal: Signal, quantity: int) -> Position | None:
        if quantity <= 0:
            return None
        side = "buy" if signal.direction == Direction.LONG else "sell"
        if signal.instrument != InstrumentType.EQUITY:
            # Long options regardless of direction (call = bullish, put = bearish)
            side = "buy"
        order = self._build_order(signal, side, quantity)
        try:
            broker_order = self.broker.submit_order(order)
        except BrokerError as exc:
            log.error("submit failed for %s: %s", signal.symbol, exc)
            return None
        self.open_broker_orders[broker_order.id] = broker_order
        fill_price = broker_order.avg_fill_price or signal.entry_price
        key = self._position_key(signal)
        position = Position(
            symbol=signal.symbol,
            instrument=signal.instrument,
            direction=signal.direction,
            quantity=broker_order.filled_qty or quantity,
            entry_price=fill_price,
            stop_loss=signal.stop_loss,
            target_price=signal.target_price,
            opened_at=datetime.utcnow(),
            option_symbol=signal.option_symbol,
            source=signal.source,
        )
        self.positions[key] = position
        return position

    def _build_order(self, signal: Signal, side: str, quantity: int) -> Order:
        order_type = self.cfg.default_order_type
        limit_price: float | None = None
        if order_type == "limit":
            offset = self.cfg.limit_offset_pct / 100.0
            limit_price = signal.entry_price * (1 + offset if side == "buy" else 1 - offset)
        return Order(
            symbol=signal.symbol,
            quantity=quantity,
            side=side,
            order_type=order_type,
            limit_price=limit_price,
            instrument=signal.instrument,
            option_symbol=signal.option_symbol,
            client_order_id=f"cv-{uuid.uuid4().hex[:12]}",
        )

    # ---------- managing ----------

    def update_marks(self, marks: dict[str, float]) -> None:
        for key, pos in self.positions.items():
            if pos.closed:
                continue
            lookup = pos.option_symbol or pos.symbol
            price = marks.get(lookup) or marks.get(pos.symbol)
            if price is not None:
                pos.update_mark(price)

    def check_exits(self, marks: dict[str, float]) -> list[tuple[Position, str, float]]:
        """Inspect open positions; submit exit orders where stop/target tripped.

        Returns a list of (position, reason, realized_pnl) for positions that
        were closed in this pass.
        """
        closed: list[tuple[Position, str, float]] = []
        for key, pos in list(self.positions.items()):
            if pos.closed:
                continue
            lookup = pos.option_symbol or pos.symbol
            price = marks.get(lookup) or marks.get(pos.symbol)
            if price is None:
                continue
            if pos.should_stop_out(price):
                pnl = self._close_position(pos, price, "stop_loss")
                closed.append((pos, "stop_loss", pnl))
            elif pos.should_take_profit(price):
                pnl = self._close_position(pos, price, "target")
                closed.append((pos, "target", pnl))
        return closed

    def force_close_all(self, marks: dict[str, float], reason: str = "manual") -> list[tuple[Position, str, float]]:
        closed: list[tuple[Position, str, float]] = []
        for key, pos in list(self.positions.items()):
            if pos.closed:
                continue
            lookup = pos.option_symbol or pos.symbol
            price = marks.get(lookup) or marks.get(pos.symbol) or pos.last_price or pos.entry_price
            pnl = self._close_position(pos, price, reason)
            closed.append((pos, reason, pnl))
        return closed

    def _close_position(self, pos: Position, price: float, reason: str) -> float:
        side = "sell" if pos.direction == Direction.LONG else "buy"
        if pos.instrument != InstrumentType.EQUITY:
            # Long options were bought; closing means selling to close
            side = "sell"
        order = Order(
            symbol=pos.symbol,
            quantity=pos.quantity,
            side=side,
            order_type="market",
            instrument=pos.instrument,
            option_symbol=pos.option_symbol,
            client_order_id=f"cv-exit-{uuid.uuid4().hex[:10]}",
        )
        try:
            self.broker.submit_order(order)
        except BrokerError as exc:
            log.error("exit submit failed for %s: %s", pos.symbol, exc)
        sign = 1 if pos.direction == Direction.LONG else -1
        multiplier = 100 if pos.instrument != InstrumentType.EQUITY else 1
        pnl = sign * (price - pos.entry_price) * pos.quantity * multiplier
        pos.realized_pnl = pnl
        pos.unrealized_pnl = 0.0
        pos.closed = True
        pos.closed_at = datetime.utcnow()
        pos.exit_reason = reason
        log.info(
            "closed %s %s qty=%d entry=%.2f exit=%.2f pnl=%.2f reason=%s",
            pos.direction.value,
            pos.option_symbol or pos.symbol,
            pos.quantity,
            pos.entry_price,
            price,
            pnl,
            reason,
        )
        return pnl

    # ---------- accessors ----------

    def open_positions(self) -> Iterable[Position]:
        return [p for p in self.positions.values() if not p.closed]

    def closed_positions(self) -> Iterable[Position]:
        return [p for p in self.positions.values() if p.closed]

    @staticmethod
    def _position_key(signal: Signal) -> str:
        return signal.option_symbol or f"{signal.symbol}:{signal.instrument.value}"

    # ---------- partial fills ----------

    def reconcile_partial_fills(self) -> None:
        for order_id, broker_order in list(self.open_broker_orders.items()):
            if broker_order.status in {"filled", "cancelled", "rejected"}:
                continue
            latest = self.broker.get_order(order_id)
            if latest is None:
                continue
            self.open_broker_orders[order_id] = latest
            if latest.status == "filled":
                key = self._lookup_position_key(latest)
                if key and key in self.positions:
                    self.positions[key].quantity = latest.filled_qty
                    if latest.avg_fill_price:
                        self.positions[key].entry_price = latest.avg_fill_price

    def _lookup_position_key(self, broker_order: BrokerOrder) -> str | None:
        key = broker_order.option_symbol or f"{broker_order.symbol}:{broker_order.instrument}"
        return key if key in self.positions else None
