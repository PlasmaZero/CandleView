"""Risk manager: per-trade sizing, daily loss limit, concurrent position cap."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

from candleview.config import RiskConfig
from candleview.risk.position_sizing import fixed_fractional, kelly_position_size
from candleview.signals import InstrumentType, Position, Signal

log = logging.getLogger(__name__)


@dataclass
class RiskState:
    day: date = field(default_factory=lambda: datetime.utcnow().date())
    realized_pnl_today: float = 0.0
    halted: bool = False
    halt_reason: str | None = None


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self.state = RiskState()
        # Simple rolling stats used by Kelly sizing
        self._wins: list[float] = []
        self._losses: list[float] = []

    # ---------- daily loss governor ----------

    def _roll_day_if_needed(self) -> None:
        today = datetime.utcnow().date()
        if today != self.state.day:
            self.state = RiskState(day=today)

    def record_trade_result(self, pnl: float) -> None:
        self._roll_day_if_needed()
        self.state.realized_pnl_today += pnl
        if pnl >= 0:
            self._wins.append(pnl)
        else:
            self._losses.append(-pnl)
        loss_limit = self.cfg.account_value * (self.cfg.max_daily_loss_pct / 100.0)
        if self.state.realized_pnl_today <= -loss_limit:
            self.state.halted = True
            self.state.halt_reason = (
                f"Daily loss cap hit: {self.state.realized_pnl_today:.2f} "
                f"<= -{loss_limit:.2f}"
            )
            log.warning(self.state.halt_reason)

    def is_halted(self) -> bool:
        self._roll_day_if_needed()
        return self.state.halted

    def reset_halt(self) -> None:
        self.state.halted = False
        self.state.halt_reason = None

    # ---------- per-signal admission ----------

    def can_open(self, open_positions: Iterable[Position]) -> tuple[bool, str]:
        self._roll_day_if_needed()
        if self.state.halted:
            return False, self.state.halt_reason or "halted"
        active = [p for p in open_positions if not p.closed]
        if len(active) >= self.cfg.max_concurrent_positions:
            return False, "max_concurrent_positions"
        return True, "ok"

    # ---------- sizing ----------

    def size_for(self, signal: Signal) -> int:
        risk_per_unit = signal.risk_per_share
        if risk_per_unit <= 0:
            return 0
        multiplier = 100 if signal.instrument != InstrumentType.EQUITY else 1
        if self.cfg.position_sizing == "kelly":
            win_rate, wl_ratio = self._kelly_stats()
            qty = kelly_position_size(
                account_value=self.cfg.account_value,
                win_rate=win_rate,
                win_loss_ratio=wl_ratio,
                risk_per_unit=risk_per_unit,
                fraction_of_kelly=self.cfg.kelly_fraction,
                contract_multiplier=multiplier,
            )
            # Never exceed the fixed-fractional ceiling even with Kelly
            ceiling = fixed_fractional(
                self.cfg.account_value,
                self.cfg.max_risk_per_trade_pct,
                risk_per_unit,
                multiplier,
            )
            return min(qty, ceiling) if ceiling > 0 else qty
        return fixed_fractional(
            self.cfg.account_value,
            self.cfg.max_risk_per_trade_pct,
            risk_per_unit,
            multiplier,
        )

    def _kelly_stats(self) -> tuple[float, float]:
        wins, losses = self._wins, self._losses
        total = len(wins) + len(losses)
        if total < 5:
            # Not enough history — assume an even-money 50% prior so Kelly is 0
            return 0.5, 1.0
        win_rate = len(wins) / total
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 1.0
        wl_ratio = (avg_win / avg_loss) if avg_loss > 0 else 1.0
        return win_rate, wl_ratio

    # ---------- reporting ----------

    def stats(self) -> dict:
        win_rate, wl = self._kelly_stats()
        total = len(self._wins) + len(self._losses)
        return {
            "day": self.state.day.isoformat(),
            "realized_pnl_today": round(self.state.realized_pnl_today, 2),
            "halted": self.state.halted,
            "halt_reason": self.state.halt_reason,
            "trades_total": total,
            "wins": len(self._wins),
            "losses": len(self._losses),
            "win_rate": round(win_rate, 3),
            "win_loss_ratio": round(wl, 3),
        }
