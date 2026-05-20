"""APScheduler-backed loop runner."""

from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)


class LoopRunner:
    """Thin scheduler that runs `task` every `interval_seconds`.

    Uses APScheduler when available, otherwise a thread-based loop. The
    SIGINT / SIGTERM handler triggers a graceful shutdown so on_stop can
    flatten positions before exit.
    """

    def __init__(
        self,
        task: Callable[[], None],
        interval_seconds: int,
        on_stop: Callable[[], None] | None = None,
    ):
        self.task = task
        self.interval = interval_seconds
        self.on_stop = on_stop
        self._stop = threading.Event()
        self._scheduler = None

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            self._scheduler = BackgroundScheduler()
            self._scheduler.add_job(self._safe_task, "interval", seconds=self.interval, max_instances=1)
            self._scheduler.start()
            log.info("APScheduler started; running every %ds", self.interval)
            # Block main thread until stop event
            while not self._stop.is_set():
                self._stop.wait(timeout=1.0)
            self._scheduler.shutdown(wait=False)
        except ImportError:
            log.info("APScheduler not available; using thread loop")
            self._run_thread_loop()
        finally:
            if self.on_stop is not None:
                try:
                    self.on_stop()
                except Exception as exc:
                    log.exception("on_stop failed: %s", exc)

    def _run_thread_loop(self) -> None:
        while not self._stop.is_set():
            self._safe_task()
            self._stop.wait(timeout=self.interval)

    def _safe_task(self) -> None:
        try:
            self.task()
        except Exception as exc:
            log.exception("scan task failed: %s", exc)

    def _handle_signal(self, signum, _frame) -> None:
        log.warning("received signal %s; shutting down", signum)
        self._stop.set()

    def stop(self) -> None:
        self._stop.set()
