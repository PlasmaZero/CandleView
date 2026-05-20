"""Alpaca broker adapter — uses alpaca-py for equities and options."""

from __future__ import annotations

import logging

from candleview.execution.broker import Broker, BrokerError, BrokerOrder
from candleview.signals import InstrumentType, Order

log = logging.getLogger(__name__)


class AlpacaBroker(Broker):
    name = "alpaca"

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
            from alpaca.trading.requests import (
                LimitOrderRequest,
                MarketOrderRequest,
            )
        except ImportError as exc:  # pragma: no cover
            raise BrokerError(
                "alpaca-py is not installed. Run: pip install alpaca-py"
            ) from exc

        self._OrderSide = OrderSide
        self._OrderType = OrderType
        self._TimeInForce = TimeInForce
        self._MarketOrderRequest = MarketOrderRequest
        self._LimitOrderRequest = LimitOrderRequest
        self.client = TradingClient(api_key, secret_key, paper=paper)
        self.paper = paper

    def submit_order(self, order: Order) -> BrokerOrder:
        side = (
            self._OrderSide.BUY if order.side.lower() == "buy" else self._OrderSide.SELL
        )
        tif = self._tif(order.time_in_force)
        symbol = (
            order.option_symbol
            if order.instrument != InstrumentType.EQUITY and order.option_symbol
            else order.symbol
        )

        try:
            if order.order_type == "limit" and order.limit_price is not None:
                req = self._LimitOrderRequest(
                    symbol=symbol,
                    qty=order.quantity,
                    side=side,
                    time_in_force=tif,
                    limit_price=round(order.limit_price, 2),
                    client_order_id=order.client_order_id,
                )
            else:
                req = self._MarketOrderRequest(
                    symbol=symbol,
                    qty=order.quantity,
                    side=side,
                    time_in_force=tif,
                    client_order_id=order.client_order_id,
                )
            resp = self.client.submit_order(req)
        except Exception as exc:
            raise BrokerError(f"Alpaca submit_order failed: {exc}") from exc

        return self._from_alpaca(resp, order)

    def cancel_order(self, order_id: str) -> None:
        try:
            self.client.cancel_order_by_id(order_id)
        except Exception as exc:
            raise BrokerError(f"Alpaca cancel failed: {exc}") from exc

    def get_order(self, order_id: str) -> BrokerOrder | None:
        try:
            resp = self.client.get_order_by_id(order_id)
        except Exception as exc:
            log.warning("Alpaca get_order failed: %s", exc)
            return None
        return self._from_alpaca(resp, None)

    def get_account_value(self) -> float:
        try:
            account = self.client.get_account()
            return float(account.equity)
        except Exception as exc:
            raise BrokerError(f"Alpaca account fetch failed: {exc}") from exc

    # --- helpers ---

    def _tif(self, value: str):
        value = (value or "day").lower()
        if value == "gtc":
            return self._TimeInForce.GTC
        if value == "ioc":
            return self._TimeInForce.IOC
        if value == "fok":
            return self._TimeInForce.FOK
        return self._TimeInForce.DAY

    def _from_alpaca(self, resp, source: Order | None) -> BrokerOrder:
        filled_qty = int(getattr(resp, "filled_qty", 0) or 0)
        avg = getattr(resp, "filled_avg_price", None)
        return BrokerOrder(
            id=str(getattr(resp, "id", "")),
            symbol=getattr(resp, "symbol", source.symbol if source else ""),
            quantity=int(getattr(resp, "qty", source.quantity if source else 0)),
            side=str(getattr(resp, "side", source.side if source else "")).lower(),
            order_type=str(getattr(resp, "order_type", source.order_type if source else "")).lower(),
            limit_price=float(getattr(resp, "limit_price", 0) or 0) or None,
            stop_price=float(getattr(resp, "stop_price", 0) or 0) or None,
            status=str(getattr(resp, "status", "submitted")).lower(),
            filled_qty=filled_qty,
            avg_fill_price=float(avg) if avg is not None else None,
            instrument=source.instrument.value if source else "equity",
            option_symbol=source.option_symbol if source else None,
        )
