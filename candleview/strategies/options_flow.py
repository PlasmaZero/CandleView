"""Options Flow — unusual options activity as a directional signal.

Heuristic: find contracts with abnormally high volume relative to open
interest, sitting in the upper IV percentile of the chain. Calls suggest
bullish bias on the underlying; puts suggest bearish. We size the trade
around the option premium rather than the underlying.
"""

from __future__ import annotations

import logging

import pandas as pd

from candleview.config import OptionsFlowConfig
from candleview.data.options_data import OptionsDataClient
from candleview.signals import Direction, InstrumentType, Signal, SignalSource
from candleview.strategies.base import Strategy, StrategyContext

log = logging.getLogger(__name__)


class OptionsFlowStrategy(Strategy):
    name = "options_flow"

    def __init__(self, cfg: OptionsFlowConfig):
        self.cfg = cfg

    def generate(self, ctx: StrategyContext) -> list[Signal]:
        if not self.cfg.enabled or ctx.options_chain is None or ctx.options_chain.empty:
            return []
        chain = ctx.options_chain.copy()
        c = self.cfg

        chain["volume"] = pd.to_numeric(chain["volume"], errors="coerce").fillna(0)
        chain["open_interest"] = pd.to_numeric(chain["open_interest"], errors="coerce").fillna(0)
        chain["implied_volatility"] = pd.to_numeric(chain["implied_volatility"], errors="coerce")
        chain["last"] = pd.to_numeric(chain["last"], errors="coerce").fillna(0)
        chain["bid"] = pd.to_numeric(chain["bid"], errors="coerce").fillna(0)
        chain["ask"] = pd.to_numeric(chain["ask"], errors="coerce").fillna(0)

        chain["vol_oi_ratio"] = chain["volume"] / chain["open_interest"].replace(0, pd.NA)
        chain["iv_pct"] = OptionsDataClient.iv_percentile(chain)
        chain["dte"] = OptionsDataClient.days_to_expiry(chain)
        chain["mid"] = (chain["bid"] + chain["ask"]) / 2.0
        chain["mid"] = chain["mid"].where(chain["mid"] > 0, chain["last"])

        filtered = chain[
            (chain["vol_oi_ratio"] >= c.volume_oi_ratio_min)
            & (chain["iv_pct"] >= c.iv_percentile_min)
            & (chain["mid"].between(c.min_premium, c.max_premium))
            & (chain["dte"].between(c.days_to_expiry_min, c.days_to_expiry_max))
            & (chain["volume"] > 0)
        ]
        if filtered.empty:
            return []

        # Rank by vol/OI to surface the most unusual activity first
        filtered = filtered.sort_values("vol_oi_ratio", ascending=False).head(3)

        signals: list[Signal] = []
        for _, row in filtered.iterrows():
            opt_type = str(row["type"]).lower()
            is_call = opt_type.startswith("c")
            direction = Direction.LONG if is_call else Direction.SHORT
            instrument = InstrumentType.CALL if is_call else InstrumentType.PUT
            premium = float(row["mid"])
            if premium <= 0:
                continue
            # Risk and reward measured in option premium
            stop = premium * 0.5            # cut losses if option halves
            target = premium * 2.0          # 2x premium target
            confidence = float(
                min(
                    0.95,
                    0.4
                    + min(float(row["vol_oi_ratio"]), 10.0) * 0.05
                    + (float(row["iv_pct"]) - c.iv_percentile_min) / 200.0,
                )
            )
            confidence = max(0.4, confidence)
            signals.append(
                Signal(
                    symbol=ctx.symbol,
                    direction=direction,
                    instrument=instrument,
                    source=SignalSource.OPTIONS_FLOW,
                    entry_price=premium,
                    target_price=target,
                    stop_loss=stop,
                    confidence=confidence,
                    expiry=str(row["expiry"]),
                    strike=float(row["strike"]),
                    option_symbol=str(row.get("contract_symbol") or ""),
                    notes=(
                        f"{opt_type.upper()} {row['strike']} exp {row['expiry']}: "
                        f"vol {int(row['volume'])} / OI {int(row['open_interest'])} "
                        f"= {row['vol_oi_ratio']:.1f}x; IV pct {row['iv_pct']:.0f}"
                    ),
                    metadata={
                        "vol_oi_ratio": float(row["vol_oi_ratio"]),
                        "iv_percentile": float(row["iv_pct"]),
                        "dte": int(row["dte"]),
                        "implied_volatility": float(row.get("implied_volatility") or 0.0),
                    },
                )
            )
        return signals
