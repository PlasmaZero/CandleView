"""Tradier broker adapter using the REST API."""

from __future__ import annotations

import logging
from typing import Any

import requests

from candleview.execution.broker import Broker, BrokerError, BrokerOrder
from candleview.signals import InstrumentType, Order

log = logging.getLogger(__name__)


class TradierBroker(Broker):
    name = "tradier"

    def __init__(
        self,
        access_token: str,
        account_id: str,
        paper: bool = True,
        base_url: str | None = None,
    ):
        self.token = access_token
        self.account_id = account_id
        self.base_url = base_url or (
            "https://sandbox.tradier.com/v1" if paper else "https://api.tradier.com/v1"
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            }
        )

    def submit_order(self, order: Order) -> BrokerOrder:
        is_option = order.instrument != InstrumentType.EQUITY and order.option_symbol
        payload: dict[str, Any] = {
            "class": "option" if is_option else "equity",
            "symbol": order.symbol,
            "side": _map_side(order.side, is_option),
            "quantity": str(order.quantity),
            "type": order.order_type,
            "duration": order.time_in_force or "day",
        }
        if is_option:
            payload["option_symbol"] = order.option_symbol
        if order.order_type == "limit" and order.limit_price is not None:
            payload["price"] = f"{order.limit_price:.2f}"

        try:
            r = self.session.post(
                f"{self.base_url}/accounts/{self.account_id}/orders",
                data=payload,
                timeout=10,
            )
            r.raise_for_status()
            body = r.json().get("order", {})
        except Exception as exc:
            raise BrokerError(f"Tradier submit_order failed: {exc}") from exc

        return BrokerOrder(
            id=str(body.get("id", "")),
            symbol=order.symbol,
            quantity=order.quantity,
            side=order.side.lower(),
            order_type=order.order_type,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            status=str(body.get("status", "submitted")).lower(),
            instrument=order.instrument.value,
            option_symbol=order.option_symbol,
        )

    def cancel_order(self, order_id: str) -> None:
        try:
            r = self.session.delete(
                f"{self.base_url}/accounts/{self.account_id}/orders/{order_id}",
                timeout=10,
            )
            r.raise_for_status()
        except Exception as exc:
            raise BrokerError(f"Tradier cancel failed: {exc}") from exc

    def get_order(self, order_id: str) -> BrokerOrder | None:
        try:
            r = self.session.get(
                f"{self.base_url}/accounts/{self.account_id}/orders/{order_id}",
                timeout=10,
            )
            r.raise_for_status()
            body = r.json().get("order", {})
        except Exception as exc:
            log.warning("Tradier get_order failed: %s", exc)
            return None
        if not body:
            return None
        return BrokerOrder(
            id=str(body.get("id", order_id)),
            symbol=str(body.get("symbol", "")),
            quantity=int(body.get("quantity") or 0),
            side=str(body.get("side", "")).lower(),
            order_type=str(body.get("type", "")).lower(),
            limit_price=float(body.get("price") or 0) or None,
            stop_price=float(body.get("stop") or 0) or None,
            status=str(body.get("status", "")).lower(),
            filled_qty=int(body.get("exec_quantity") or 0),
            avg_fill_price=float(body.get("avg_fill_price") or 0) or None,
            instrument="option" if body.get("class") == "option" else "equity",
            option_symbol=body.get("option_symbol"),
        )

    def get_account_value(self) -> float:
        try:
            r = self.session.get(
                f"{self.base_url}/accounts/{self.account_id}/balances",
                timeout=10,
            )
            r.raise_for_status()
            body = r.json().get("balances", {})
        except Exception as exc:
            raise BrokerError(f"Tradier balances failed: {exc}") from exc
        for key in ("total_equity", "equity", "total_cash"):
            if key in body:
                try:
                    return float(body[key])
                except Exception:
                    continue
        return 0.0


def _map_side(side: str, is_option: bool) -> str:
    side = side.lower()
    if not is_option:
        return "buy" if side == "buy" else "sell"
    # Tradier options sides: buy_to_open, sell_to_close, etc.
    return "buy_to_open" if side == "buy" else "sell_to_close"
