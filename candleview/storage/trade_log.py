"""SQLite + CSV trade journal.

Schema is intentionally flat so signals, fills, and exits all live in
one `trades` table with a `kind` column. This keeps backtesting queries
simple — one source of truth.
"""

from __future__ import annotations

import csv
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from candleview.signals import Position, Signal

log = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,            -- signal | open | close
    symbol TEXT NOT NULL,
    instrument TEXT NOT NULL,
    direction TEXT NOT NULL,
    source TEXT,
    quantity INTEGER,
    price REAL,
    target REAL,
    stop REAL,
    pnl REAL,
    confidence REAL,
    option_symbol TEXT,
    strike REAL,
    expiry TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_kind ON trades(kind);
"""


CSV_HEADERS = [
    "ts",
    "kind",
    "symbol",
    "instrument",
    "direction",
    "source",
    "quantity",
    "price",
    "target",
    "stop",
    "pnl",
    "confidence",
    "option_symbol",
    "strike",
    "expiry",
    "notes",
]


class TradeLog:
    def __init__(self, sqlite_path: str, csv_path: str):
        self.sqlite_path = sqlite_path
        self.csv_path = csv_path
        os.makedirs(os.path.dirname(sqlite_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        with self._db() as conn:
            conn.executescript(SCHEMA)
        if not os.path.exists(csv_path):
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writeheader()

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.sqlite_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _insert(self, row: dict[str, Any]) -> None:
        row.setdefault("ts", datetime.utcnow().isoformat())
        with self._db() as conn:
            placeholders = ", ".join("?" for _ in CSV_HEADERS)
            cols = ", ".join(CSV_HEADERS)
            values = [row.get(col) for col in CSV_HEADERS]
            conn.execute(f"INSERT INTO trades ({cols}) VALUES ({placeholders})", values)
        with open(self.csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({k: row.get(k, "") for k in CSV_HEADERS})

    def record_signal(self, signal: Signal) -> None:
        self._insert(
            {
                "kind": "signal",
                "symbol": signal.symbol,
                "instrument": signal.instrument.value,
                "direction": signal.direction.value,
                "source": signal.source.value,
                "price": signal.entry_price,
                "target": signal.target_price,
                "stop": signal.stop_loss,
                "confidence": signal.confidence,
                "option_symbol": signal.option_symbol,
                "strike": signal.strike,
                "expiry": signal.expiry,
                "notes": signal.notes,
            }
        )

    def record_open(self, position: Position) -> None:
        self._insert(
            {
                "kind": "open",
                "symbol": position.symbol,
                "instrument": position.instrument.value,
                "direction": position.direction.value,
                "source": position.source.value if position.source else None,
                "quantity": position.quantity,
                "price": position.entry_price,
                "target": position.target_price,
                "stop": position.stop_loss,
                "option_symbol": position.option_symbol,
            }
        )

    def record_close(self, position: Position, exit_price: float, pnl: float, reason: str) -> None:
        self._insert(
            {
                "kind": "close",
                "symbol": position.symbol,
                "instrument": position.instrument.value,
                "direction": position.direction.value,
                "source": position.source.value if position.source else None,
                "quantity": position.quantity,
                "price": exit_price,
                "pnl": pnl,
                "option_symbol": position.option_symbol,
                "notes": reason,
            }
        )

    def summary(self) -> dict[str, Any]:
        with self._db() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) as trades, "
                "       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins, "
                "       SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses, "
                "       COALESCE(SUM(pnl), 0) as total_pnl, "
                "       COALESCE(AVG(pnl), 0) as avg_pnl "
                "FROM trades WHERE kind = 'close'"
            )
            row = cur.fetchone() or (0, 0, 0, 0.0, 0.0)
        trades, wins, losses, total_pnl, avg_pnl = row
        total = (wins or 0) + (losses or 0)
        win_rate = (wins / total) if total else 0.0
        return {
            "closed_trades": trades or 0,
            "wins": wins or 0,
            "losses": losses or 0,
            "win_rate": round(win_rate, 3),
            "total_pnl": round(total_pnl or 0.0, 2),
            "avg_pnl": round(avg_pnl or 0.0, 2),
        }
