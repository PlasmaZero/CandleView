"""Walk historical bars through the strategies and report hypothetical signals.

This is not a full backtester — it's a sanity check that the strategy
fires under realistic conditions, so you can tune thresholds before going
live. Use the SQLite trade log for actual P&L review.

Usage:
    python examples/backtest_replay.py AAPL 2025-01-02 2025-01-15
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

import yfinance as yf

from candleview.config import MomentumBreakoutConfig
from candleview.data.indicators import add_all_indicators
from candleview.strategies.base import StrategyContext
from candleview.strategies.momentum_breakout import MomentumBreakoutStrategy


def replay(symbol: str, start: str, end: str, interval: str = "5m") -> None:
    df = yf.Ticker(symbol).history(start=start, end=end, interval=interval, prepost=False)
    if df.empty:
        print("no data")
        return
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert("US/Eastern")
    df = df[["Open", "High", "Low", "Close", "Volume"]]

    strat = MomentumBreakoutStrategy(MomentumBreakoutConfig())
    window = 60
    fired = 0
    for i in range(window, len(df)):
        slice_ = add_all_indicators(df.iloc[:i + 1])
        ctx = StrategyContext(symbol=symbol, history=slice_, options_chain=None)
        for s in strat.generate(ctx):
            fired += 1
            print(f"{slice_.index[-1]} {s.symbol} entry={s.entry_price:.2f} stop={s.stop_loss:.2f} target={s.target_price:.2f} ({s.notes})")
    print(f"\nTotal signals: {fired}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        end = datetime.utcnow().date().isoformat()
        start = (datetime.utcnow().date() - timedelta(days=5)).isoformat()
        replay("AAPL", start, end)
    else:
        replay(sys.argv[1], sys.argv[2], sys.argv[3])
