"""Broker interface plus an in-memory PaperBroker for testing.

Concrete adapters live in alpaca_broker.py and tradier_broker.py.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from candleview.signals import Order

log = logging.getLogger(__name__)


class BrokerError(Exception):
    pass


@dataclass
class BrokerOrder:
    id: str
    symbol: str
    quantity: int
    side: str
    order_type: str
    limit_price: float | None
    stop_price: float | None
    status: str
    filled_qty: int = 0
    avg_fill_price: float | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    instrument: str = "equity"
    option_symbol: str | None = None


class Broker(ABC):
    name: str = "broker"

    @abstractmethod
    def submit_order(self, order: Order) -> BrokerOrder:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> BrokerOrder | None:
        ...

    @abstractmethod
    def get_account_value(self) -> float:
        ...


class PaperBroker(Broker):
    """Local-only paper broker — used in tests and offline runs."""

    name = "paper"

    def __init__(self, starting_cash: float = 25_000.0):
        self.cash = starting_cash
        self.orders: dict[str, BrokerOrder] = {}

    def submit_order(self, order: Order) -> BrokerOrder:
        order_id = order.client_order_id or f"paper-{uuid.uuid4().hex[:10]}"
        fill_price = order.limit_price if order.order_type == "limit" else None
        b = BrokerOrder(
            id=order_id,
            symbol=order.symbol,
            quantity=order.quantity,
            side=order.side,
            order_type=order.order_type,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            status="filled",
            filled_qty=order.quantity,
            avg_fill_price=fill_price,
            instrument=order.instrument.value,
            option_symbol=order.option_symbol,
        )
        self.orders[order_id] = b
        log.info("PaperBroker filled %s %s x%d @ %s", order.side, order.symbol, order.quantity, fill_price)
        return b

    def cancel_order(self, order_id: str) -> None:
        if order_id in self.orders:
            self.orders[order_id].status = "cancelled"

    def get_order(self, order_id: str) -> BrokerOrder | None:
        return self.orders.get(order_id)

    def get_account_value(self) -> float:
        return self.cash
