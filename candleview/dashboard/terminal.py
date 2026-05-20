"""Rich-based terminal dashboard."""

from __future__ import annotations

import logging
from typing import Iterable

from candleview.signals import Position, Signal

log = logging.getLogger(__name__)


class TerminalDashboard:
    def __init__(self):
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            from rich.layout import Layout
            from rich.live import Live
            from rich.text import Text
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("rich is not installed; pip install rich") from exc
        self._Console = Console
        self._Table = Table
        self._Panel = Panel
        self._Layout = Layout
        self._Live = Live
        self._Text = Text
        self.console = Console()
        self._live = None

    def start(self) -> None:
        layout = self._build_layout([], [], {}, {})
        self._live = self._Live(layout, console=self.console, refresh_per_second=2, screen=False)
        self._live.start()

    def stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def update(
        self,
        signals: Iterable[Signal],
        positions: Iterable[Position],
        risk_stats: dict,
        log_summary: dict,
    ) -> None:
        layout = self._build_layout(list(signals), list(positions), risk_stats, log_summary)
        if self._live is not None:
            self._live.update(layout)
        else:
            self.console.print(layout)

    def _build_layout(
        self,
        signals: list[Signal],
        positions: list[Position],
        risk_stats: dict,
        log_summary: dict,
    ):
        layout = self._Layout()
        layout.split_column(
            self._Layout(name="header", size=3),
            self._Layout(name="body"),
        )
        layout["body"].split_row(
            self._Layout(name="signals"),
            self._Layout(name="positions"),
        )
        layout["header"].update(self._header_panel(risk_stats, log_summary))
        layout["signals"].update(self._signals_panel(signals))
        layout["positions"].update(self._positions_panel(positions))
        return layout

    def _header_panel(self, risk_stats: dict, log_summary: dict):
        text = self._Text()
        text.append("CandleView Day Trading Engine\n", style="bold cyan")
        if risk_stats:
            text.append(
                f"Day {risk_stats.get('day')} | PnL today: "
                f"{risk_stats.get('realized_pnl_today', 0):.2f} | "
                f"Trades: {risk_stats.get('trades_total', 0)} | "
                f"Win rate: {risk_stats.get('win_rate', 0):.1%}",
                style="white",
            )
            if risk_stats.get("halted"):
                text.append("  [HALTED]", style="bold red")
        if log_summary:
            text.append(
                f"  |  Lifetime PnL: {log_summary.get('total_pnl', 0):.2f}"
                f"  ({log_summary.get('closed_trades', 0)} closed)",
                style="dim",
            )
        return self._Panel(text, border_style="cyan")

    def _signals_panel(self, signals: list[Signal]):
        table = self._Table(title="Active Signals", expand=True)
        for col in ("Symbol", "Side", "Source", "Entry", "Target", "Stop", "Conf"):
            table.add_column(col)
        for s in signals[-10:]:
            side = s.direction.value
            if s.instrument.value in {"call", "put"}:
                side = s.instrument.value.upper()
            table.add_row(
                s.symbol,
                side,
                s.source.value,
                f"{s.entry_price:.2f}",
                f"{s.target_price:.2f}",
                f"{s.stop_loss:.2f}",
                f"{s.confidence:.0%}",
            )
        return self._Panel(table, border_style="green")

    def _positions_panel(self, positions: list[Position]):
        table = self._Table(title="Open Positions", expand=True)
        for col in ("Symbol", "Inst", "Qty", "Entry", "Last", "Stop", "Target", "uPnL"):
            table.add_column(col)
        for p in positions:
            color = "green" if p.unrealized_pnl >= 0 else "red"
            table.add_row(
                p.option_symbol or p.symbol,
                p.instrument.value,
                str(p.quantity),
                f"{p.entry_price:.2f}",
                f"{p.last_price:.2f}",
                f"{p.stop_loss:.2f}",
                f"{p.target_price:.2f}",
                f"[{color}]{p.unrealized_pnl:.2f}[/]",
            )
        return self._Panel(table, border_style="magenta")
