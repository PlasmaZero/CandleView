"""Signal and order data models shared across the engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


class InstrumentType(str, Enum):
    EQUITY = "equity"
    CALL = "call"
    PUT = "put"


class SignalSource(str, Enum):
    MOMENTUM_BREAKOUT = "momentum_breakout"
    OPTIONS_FLOW = "options_flow"


@dataclass
class Signal:
    symbol: str
    direction: Direction
    instrument: InstrumentType
    source: SignalSource
    entry_price: float
    target_price: float
    stop_loss: float
    confidence: float = 0.5
    timestamp: datetime = field(default_factory=datetime.utcnow)
    expiry: str | None = None
    strike: float | None = None
    option_symbol: str | None = None
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def risk_per_share(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    @property
    def reward_per_share(self) -> float:
        return abs(self.target_price - self.entry_price)

    @property
    def reward_risk_ratio(self) -> float:
        risk = self.risk_per_share
        if risk <= 0:
            return 0.0
        return self.reward_per_share / risk

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "instrument": self.instrument.value,
            "source": self.source.value,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "expiry": self.expiry,
            "strike": self.strike,
            "option_symbol": self.option_symbol,
            "notes": self.notes,
            "reward_risk_ratio": self.reward_risk_ratio,
        }


@dataclass
class Position:
    symbol: str
    instrument: InstrumentType
    direction: Direction
    quantity: int
    entry_price: float
    stop_loss: float
    target_price: float
    opened_at: datetime
    option_symbol: str | None = None
    source: SignalSource | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_price: float = 0.0
    closed: bool = False
    closed_at: datetime | None = None
    exit_reason: str | None = None

    def update_mark(self, price: float) -> None:
        self.last_price = price
        sign = 1 if self.direction == Direction.LONG else -1
        self.unrealized_pnl = sign * (price - self.entry_price) * self.quantity

    def should_stop_out(self, price: float) -> bool:
        if self.direction == Direction.LONG:
            return price <= self.stop_loss
        return price >= self.stop_loss

    def should_take_profit(self, price: float) -> bool:
        if self.direction == Direction.LONG:
            return price >= self.target_price
        return price <= self.target_price


@dataclass
class Order:
    symbol: str
    quantity: int
    side: str   # "buy" or "sell"
    order_type: str = "market"   # market, limit
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: str = "day"
    instrument: InstrumentType = InstrumentType.EQUITY
    option_symbol: str | None = None
    client_order_id: str | None = None
