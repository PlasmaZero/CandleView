"""Typed config loaded from YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DataConfig:
    interval: str = "5m"
    lookback_days: int = 5
    options_provider: str = "yfinance"
    rate_limit_per_minute: int = 60


@dataclass
class MomentumBreakoutConfig:
    enabled: bool = True
    resistance_lookback: int = 20
    volume_multiplier: float = 1.5
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 50
    rsi_min: float = 50.0
    rsi_max: float = 75.0
    atr_stop_multiplier: float = 1.5
    target_r_multiple: float = 2.0


@dataclass
class OptionsFlowConfig:
    enabled: bool = True
    volume_oi_ratio_min: float = 2.0
    iv_percentile_min: float = 60.0
    min_premium: float = 0.10
    max_premium: float = 10.0
    days_to_expiry_min: int = 1
    days_to_expiry_max: int = 14


@dataclass
class StrategiesConfig:
    momentum_breakout: MomentumBreakoutConfig = field(default_factory=MomentumBreakoutConfig)
    options_flow: OptionsFlowConfig = field(default_factory=OptionsFlowConfig)


@dataclass
class FiltersConfig:
    market_hours_only: bool = True
    market_open_et: str = "09:30"
    market_close_et: str = "16:00"
    min_avg_volume: int = 500_000
    skip_earnings_window_days: int = 2


@dataclass
class RiskConfig:
    account_value: float = 25_000.0
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_concurrent_positions: int = 5
    position_sizing: str = "fixed_fractional"
    kelly_fraction: float = 0.25


@dataclass
class BrokerConfig:
    name: str = "alpaca"
    paper: bool = True
    default_order_type: str = "limit"
    limit_offset_pct: float = 0.05


@dataclass
class StorageConfig:
    sqlite_path: str = "data/trades.sqlite"
    csv_path: str = "data/trades.csv"


@dataclass
class DashboardConfig:
    type: str = "terminal"
    refresh_seconds: int = 5
    web_port: int = 8000


@dataclass
class SchedulerConfig:
    scan_interval_seconds: int = 60


@dataclass
class Config:
    tickers: list[str] = field(default_factory=lambda: ["SPY"])
    data: DataConfig = field(default_factory=DataConfig)
    strategies: StrategiesConfig = field(default_factory=StrategiesConfig)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        with open(path, "r") as f:
            raw = yaml.safe_load(f) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Config":
        cfg = cls()
        if "tickers" in raw:
            cfg.tickers = list(raw["tickers"])
        cfg.data = _merge(DataConfig(), raw.get("data", {}))
        strat = raw.get("strategies", {})
        cfg.strategies = StrategiesConfig(
            momentum_breakout=_merge(MomentumBreakoutConfig(), strat.get("momentum_breakout", {})),
            options_flow=_merge(OptionsFlowConfig(), strat.get("options_flow", {})),
        )
        cfg.filters = _merge(FiltersConfig(), raw.get("filters", {}))
        cfg.risk = _merge(RiskConfig(), raw.get("risk", {}))
        cfg.broker = _merge(BrokerConfig(), raw.get("broker", {}))
        cfg.storage = _merge(StorageConfig(), raw.get("storage", {}))
        cfg.dashboard = _merge(DashboardConfig(), raw.get("dashboard", {}))
        cfg.scheduler = _merge(SchedulerConfig(), raw.get("scheduler", {}))
        return cfg


def _merge(target: Any, overrides: dict[str, Any]) -> Any:
    for key, value in overrides.items():
        if hasattr(target, key):
            setattr(target, key, value)
    return target


def alpaca_credentials() -> tuple[str | None, str | None]:
    return os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")


def tradier_credentials() -> tuple[str | None, str | None]:
    return os.getenv("TRADIER_TOKEN"), os.getenv("TRADIER_ACCOUNT_ID")
