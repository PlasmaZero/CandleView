"""CandleView CLI entry point.

Usage:
    python -m candleview.main --config config.yaml --mode paper --dashboard terminal
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading

from candleview.config import Config
from candleview.engine import Engine
from candleview.scheduler import LoopRunner


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="candleview", description="Day trading strategy engine")
    p.add_argument("--config", default="config.yaml", help="Path to YAML config")
    p.add_argument(
        "--mode",
        choices=["paper", "live", "scan-once"],
        default="paper",
        help="Execution mode (default: paper)",
    )
    p.add_argument(
        "--dashboard",
        choices=["none", "terminal", "web"],
        default="terminal",
        help="Dashboard to render (default: terminal)",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    log = logging.getLogger("candleview")

    if not os.path.exists(args.config):
        log.error("config not found: %s", args.config)
        log.error("copy config.example.yaml to config.yaml and edit it")
        return 2

    cfg = Config.from_yaml(args.config)
    if args.mode == "live":
        cfg.broker.paper = False
    elif args.mode == "paper":
        cfg.broker.paper = True

    engine = Engine(cfg)
    log.info(
        "started with %d tickers, broker=%s paper=%s",
        len(cfg.tickers),
        engine.broker.name,
        cfg.broker.paper,
    )

    if args.mode == "scan-once":
        result = engine.run_once()
        log.info("scan result: %s", result)
        snap = engine.snapshot()
        for s in snap["signals"]:
            log.info("signal: %s", s)
        return 0

    dashboard = _setup_dashboard(args.dashboard, cfg, engine)

    def task():
        result = engine.run_once()
        log.info(
            "scan: %d signals, %d open, %d closed-now, pnl_today=%.2f",
            result["new_signals"],
            result["open_positions"],
            result["closed_now"],
            result["risk"]["realized_pnl_today"],
        )
        if dashboard is not None:
            dashboard()

    runner = LoopRunner(
        task=task,
        interval_seconds=cfg.scheduler.scan_interval_seconds,
        on_stop=lambda: _on_stop(engine),
    )
    runner.run()
    return 0


def _setup_dashboard(kind: str, cfg: Config, engine: Engine):
    if kind == "none":
        return None
    if kind == "terminal":
        from candleview.dashboard.terminal import TerminalDashboard

        dash = TerminalDashboard()
        dash.start()

        def refresh():
            snap = engine.snapshot()
            dash.update(engine.recent_signals[-10:], engine.orders.open_positions(), snap["risk"], snap["log"])
        return refresh
    if kind == "web":
        from candleview.dashboard import web as web_dashboard
        import uvicorn

        def serve():
            uvicorn.run(web_dashboard.app, host="0.0.0.0", port=cfg.dashboard.web_port, log_level="warning")

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()

        def refresh():
            snap = engine.snapshot()
            web_dashboard.set_state(snap["signals"], snap["positions"], snap["risk"], snap["log"])

        return refresh
    return None


def _on_stop(engine: Engine) -> None:
    logging.getLogger("candleview").info("flattening positions before exit")
    engine.flatten_all(reason="shutdown")


if __name__ == "__main__":
    sys.exit(main())
