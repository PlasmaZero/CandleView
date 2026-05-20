"""Optional FastAPI web dashboard.

Run with: uvicorn candleview.dashboard.web:app
The engine populates `state` via `set_state`.
"""

from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore


_state: dict[str, Any] = {
    "signals": [],
    "positions": [],
    "risk": {},
    "log": {},
}


def set_state(signals: list[dict], positions: list[dict], risk: dict, log: dict) -> None:
    _state["signals"] = signals
    _state["positions"] = positions
    _state["risk"] = risk
    _state["log"] = log


def create_app():
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed; pip install fastapi uvicorn")
    app = FastAPI(title="CandleView Dashboard")

    @app.get("/api/state")
    def get_state() -> dict[str, Any]:
        return _state

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    return app


_INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>CandleView Dashboard</title>
  <style>
    body { font-family: -apple-system, sans-serif; background: #0f1115; color: #e5e7eb; margin: 0; padding: 24px; }
    h1 { color: #38bdf8; margin: 0 0 16px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    .card { background: #1a1d23; padding: 16px; border-radius: 8px; border: 1px solid #2a2f38; }
    h2 { margin: 0 0 12px; font-size: 14px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; padding: 6px 8px; color: #94a3b8; border-bottom: 1px solid #2a2f38; }
    td { padding: 6px 8px; border-bottom: 1px solid #1f242c; }
    .pos { color: #22c55e; }
    .neg { color: #ef4444; }
    .pill { background: #2a2f38; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
    .halted { background: #ef4444; color: white; }
  </style>
</head>
<body>
  <h1>CandleView</h1>
  <div id="header" class="card" style="margin-bottom: 24px;"></div>
  <div class="grid">
    <div class="card"><h2>Active signals</h2><div id="signals"></div></div>
    <div class="card"><h2>Open positions</h2><div id="positions"></div></div>
  </div>
  <script>
    async function refresh() {
      const r = await fetch('/api/state');
      const s = await r.json();
      const risk = s.risk || {};
      const log = s.log || {};
      document.getElementById('header').innerHTML =
        '<strong>Day ' + (risk.day||'-') + '</strong> &middot; PnL today: ' +
        (risk.realized_pnl_today||0).toFixed(2) + ' &middot; Trades: ' + (risk.trades_total||0) +
        ' &middot; Win rate: ' + ((risk.win_rate||0)*100).toFixed(0) + '%' +
        (risk.halted ? ' <span class="pill halted">HALTED</span>' : '') +
        ' &middot; Lifetime PnL: ' + (log.total_pnl||0).toFixed(2) +
        ' (' + (log.closed_trades||0) + ' closed)';
      const sigRows = (s.signals||[]).map(x =>
        `<tr><td>${x.symbol}</td><td>${x.direction}</td><td>${x.source}</td>
         <td>${(+x.entry_price).toFixed(2)}</td><td>${(+x.target_price).toFixed(2)}</td>
         <td>${(+x.stop_loss).toFixed(2)}</td><td>${((+x.confidence)*100).toFixed(0)}%</td></tr>`).join('');
      document.getElementById('signals').innerHTML =
        '<table><tr><th>Symbol</th><th>Side</th><th>Source</th><th>Entry</th><th>Target</th><th>Stop</th><th>Conf</th></tr>' + sigRows + '</table>';
      const posRows = (s.positions||[]).map(x => {
        const cls = (x.unrealized_pnl||0) >= 0 ? 'pos' : 'neg';
        return `<tr><td>${x.option_symbol||x.symbol}</td><td>${x.instrument}</td>
                <td>${x.quantity}</td><td>${(+x.entry_price).toFixed(2)}</td>
                <td>${(+x.last_price).toFixed(2)}</td>
                <td class="${cls}">${(+x.unrealized_pnl).toFixed(2)}</td></tr>`;
      }).join('');
      document.getElementById('positions').innerHTML =
        '<table><tr><th>Symbol</th><th>Inst</th><th>Qty</th><th>Entry</th><th>Last</th><th>uPnL</th></tr>' + posRows + '</table>';
    }
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""

app = create_app() if FastAPI is not None else None
