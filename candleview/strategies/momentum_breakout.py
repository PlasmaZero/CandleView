"""Momentum Breakout — volume-confirmed breakout with EMA alignment."""

from __future__ import annotations

import logging

from candleview.config import MomentumBreakoutConfig
from candleview.signals import Direction, InstrumentType, Signal, SignalSource
from candleview.strategies.base import Strategy, StrategyContext

log = logging.getLogger(__name__)


class MomentumBreakoutStrategy(Strategy):
    name = "momentum_breakout"

    def __init__(self, cfg: MomentumBreakoutConfig):
        self.cfg = cfg

    def generate(self, ctx: StrategyContext) -> list[Signal]:
        if not self.cfg.enabled:
            return []
        df = ctx.history
        c = self.cfg
        # We need enough data to evaluate the lookback resistance and EMAs.
        required = max(c.resistance_lookback + 1, c.ema_trend + 1)
        if df.empty or len(df) < required:
            return []

        ema_fast_col = f"ema_{c.ema_fast}"
        ema_slow_col = f"ema_{c.ema_slow}"
        ema_trend_col = f"ema_{c.ema_trend}"
        for col in (ema_fast_col, ema_slow_col, ema_trend_col, "rsi", "atr"):
            if col not in df.columns:
                log.debug("missing indicator %s for %s", col, ctx.symbol)
                return []

        last = df.iloc[-1]
        prior = df.iloc[-(c.resistance_lookback + 1):-1]
        if prior.empty:
            return []

        resistance = float(prior["High"].max())
        avg_volume = float(prior["Volume"].mean())
        if avg_volume <= 0:
            return []

        close = float(last["Close"])
        volume = float(last["Volume"])
        rsi = float(last["rsi"])
        atr_val = float(last["atr"]) if last["atr"] == last["atr"] else 0.0
        ema_fast = float(last[ema_fast_col])
        ema_slow = float(last[ema_slow_col])
        ema_trend = float(last[ema_trend_col])

        breakout = close > resistance
        volume_ok = volume >= avg_volume * c.volume_multiplier
        ema_aligned = ema_fast > ema_slow > ema_trend
        rsi_ok = c.rsi_min <= rsi <= c.rsi_max

        if not (breakout and volume_ok and ema_aligned and rsi_ok):
            return []

        if atr_val <= 0:
            atr_val = max(close * 0.005, 0.05)
        stop = close - c.atr_stop_multiplier * atr_val
        risk = close - stop
        if risk <= 0:
            return []
        target = close + c.target_r_multiple * risk

        # Confidence is a blend of the breakout strength and volume confirmation.
        breakout_strength = (close - resistance) / max(resistance, 1e-6)
        vol_strength = volume / max(avg_volume, 1.0)
        confidence = float(min(0.95, 0.5 + breakout_strength * 5 + (vol_strength - 1.5) * 0.1))
        confidence = max(0.5, confidence)

        signal = Signal(
            symbol=ctx.symbol,
            direction=Direction.LONG,
            instrument=InstrumentType.EQUITY,
            source=SignalSource.MOMENTUM_BREAKOUT,
            entry_price=close,
            target_price=target,
            stop_loss=stop,
            confidence=confidence,
            notes=(
                f"breakout above {resistance:.2f}; vol {volume:,.0f} vs avg {avg_volume:,.0f}; "
                f"RSI {rsi:.1f}; EMA {c.ema_fast}>{c.ema_slow}>{c.ema_trend}"
            ),
            metadata={
                "resistance": resistance,
                "avg_volume": avg_volume,
                "rsi": rsi,
                "atr": atr_val,
            },
        )
        return [signal]
