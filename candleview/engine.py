"""Core engine — orchestrates data, strategies, risk, and execution."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from candleview.config import Config, alpaca_credentials, tradier_credentials
from candleview.data import (
    MarketDataClient,
    OptionsDataClient,
    add_all_indicators,
)
from candleview.execution import OrderManager, PaperBroker
from candleview.execution.broker import Broker
from candleview.filters import TradeFilter
from candleview.risk import RiskManager
from candleview.signals import InstrumentType, Position, Signal
from candleview.storage import TradeLog
from candleview.strategies import (
    MomentumBreakoutStrategy,
    OptionsFlowStrategy,
    Strategy,
)
from candleview.strategies.base import StrategyContext

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, cfg: Config, broker: Broker | None = None):
        self.cfg = cfg
        self.market_data = MarketDataClient(rate_limit_per_minute=cfg.data.rate_limit_per_minute)
        self.options_data = OptionsDataClient(provider=cfg.data.options_provider)
        self.filters = TradeFilter(cfg.filters, self.market_data)
        self.risk = RiskManager(cfg.risk)
        self.broker = broker or _build_broker(cfg)
        self.orders = OrderManager(self.broker, cfg.broker)
        self.log = TradeLog(cfg.storage.sqlite_path, cfg.storage.csv_path)
        self.strategies: list[Strategy] = self._build_strategies()
        self.recent_signals: list[Signal] = []

    def _build_strategies(self) -> list[Strategy]:
        out: list[Strategy] = []
        if self.cfg.strategies.momentum_breakout.enabled:
            out.append(MomentumBreakoutStrategy(self.cfg.strategies.momentum_breakout))
        if self.cfg.strategies.options_flow.enabled:
            out.append(OptionsFlowStrategy(self.cfg.strategies.options_flow))
        return out

    # ---------- main scan loop ----------

    def run_once(self) -> dict:
        if self.risk.is_halted():
            log.warning("Engine halted: %s", self.risk.state.halt_reason)
        if not self.filters.is_market_open():
            log.debug("Outside market hours; manage open positions only")

        new_signals: list[Signal] = []
        marks: dict[str, float] = {}

        for symbol in self.cfg.tickers:
            history = self.market_data.history(
                symbol,
                interval=self.cfg.data.interval,
                lookback_days=self.cfg.data.lookback_days,
            )
            if history.empty:
                continue
            indicators = add_all_indicators(
                history,
                ema_periods=(
                    self.cfg.strategies.momentum_breakout.ema_fast,
                    self.cfg.strategies.momentum_breakout.ema_slow,
                    self.cfg.strategies.momentum_breakout.ema_trend,
                ),
            )
            last_close = float(indicators["Close"].iloc[-1])
            marks[symbol] = last_close

            ok, reason = self.filters.accept(symbol, indicators)
            if not ok:
                log.debug("filter skip %s: %s", symbol, reason)
                continue

            options_chain = None
            if self.cfg.strategies.options_flow.enabled:
                try:
                    options_chain = self.options_data.chain(symbol)
                except Exception as exc:
                    log.warning("options chain failed for %s: %s", symbol, exc)
                    options_chain = None

            ctx = StrategyContext(symbol=symbol, history=indicators, options_chain=options_chain)
            for strategy in self.strategies:
                try:
                    signals = strategy.generate(ctx)
                except Exception as exc:
                    log.exception("strategy %s failed for %s: %s", strategy.name, symbol, exc)
                    continue
                for s in signals:
                    new_signals.append(s)
                    self.log.record_signal(s)

        # Update marks for already-open option positions where we can
        for pos in self.orders.open_positions():
            if pos.last_price <= 0 and pos.symbol in marks:
                pos.update_mark(marks[pos.symbol])

        # Manage existing positions first — exits free up budget for new entries
        closed = self.orders.check_exits(marks)
        for pos, reason, pnl in closed:
            self.risk.record_trade_result(pnl)
            exit_price = pos.last_price or pos.entry_price
            self.log.record_close(pos, exit_price, pnl, reason)

        # Open new positions only if not halted and we have spare capacity
        if not self.risk.is_halted() and self.filters.is_market_open():
            for signal in new_signals:
                self._maybe_open(signal)

        self.recent_signals = (self.recent_signals + new_signals)[-50:]
        self.orders.reconcile_partial_fills()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "new_signals": len(new_signals),
            "open_positions": len(list(self.orders.open_positions())),
            "closed_now": len(closed),
            "risk": self.risk.stats(),
            "log_summary": self.log.summary(),
        }

    def _maybe_open(self, signal: Signal) -> Position | None:
        admitted, reason = self.risk.can_open(self.orders.open_positions())
        if not admitted:
            log.info("risk rejected %s: %s", signal.symbol, reason)
            return None
        qty = self.risk.size_for(signal)
        if qty <= 0:
            log.info("zero size for %s (risk/share=%.2f)", signal.symbol, signal.risk_per_share)
            return None
        position = self.orders.open_from_signal(signal, qty)
        if position is not None:
            self.log.record_open(position)
        return position

    # ---------- shutdown ----------

    def flatten_all(self, reason: str = "shutdown") -> list[tuple[Position, str, float]]:
        marks = {p.symbol: p.last_price for p in self.orders.open_positions() if p.last_price}
        closed = self.orders.force_close_all(marks, reason=reason)
        for pos, reason, pnl in closed:
            self.risk.record_trade_result(pnl)
            self.log.record_close(pos, pos.last_price or pos.entry_price, pnl, reason)
        return closed

    # ---------- snapshot for dashboards ----------

    def snapshot(self) -> dict:
        return {
            "signals": [s.to_dict() for s in self.recent_signals[-10:]],
            "positions": [_position_to_dict(p) for p in self.orders.open_positions()],
            "risk": self.risk.stats(),
            "log": self.log.summary(),
        }


def _position_to_dict(p: Position) -> dict:
    return {
        "symbol": p.symbol,
        "instrument": p.instrument.value,
        "direction": p.direction.value,
        "quantity": p.quantity,
        "entry_price": p.entry_price,
        "last_price": p.last_price,
        "stop_loss": p.stop_loss,
        "target_price": p.target_price,
        "unrealized_pnl": p.unrealized_pnl,
        "option_symbol": p.option_symbol,
    }


def _build_broker(cfg: Config) -> Broker:
    name = cfg.broker.name.lower()
    if name == "alpaca":
        key, secret = alpaca_credentials()
        if not key or not secret:
            log.warning("Alpaca credentials missing — falling back to PaperBroker")
            return PaperBroker(starting_cash=cfg.risk.account_value)
        from candleview.execution.alpaca_broker import AlpacaBroker

        return AlpacaBroker(key, secret, paper=cfg.broker.paper)
    if name == "tradier":
        token, account_id = tradier_credentials()
        if not token or not account_id:
            log.warning("Tradier credentials missing — falling back to PaperBroker")
            return PaperBroker(starting_cash=cfg.risk.account_value)
        from candleview.execution.tradier_broker import TradierBroker

        return TradierBroker(token, account_id, paper=cfg.broker.paper)
    if name == "paper":
        return PaperBroker(starting_cash=cfg.risk.account_value)
    raise ValueError(f"Unknown broker: {cfg.broker.name}")
