"""Run the engine for a single scan pass and print the results.

Usage:
    python examples/scan_once.py [config.yaml]
"""

from __future__ import annotations

import json
import logging
import sys

from candleview.config import Config
from candleview.engine import Engine


def main(config_path: str = "config.yaml") -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    cfg = Config.from_yaml(config_path)
    engine = Engine(cfg)
    result = engine.run_once()
    print(json.dumps(result, indent=2, default=str))
    snap = engine.snapshot()
    print(json.dumps(snap, indent=2, default=str))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
