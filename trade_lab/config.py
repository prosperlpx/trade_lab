"""Strategy, account-risk, and legacy execution configuration."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import time

from .filters import StrategyFilters


@dataclass(frozen=True)
class StrategyParameters:
    """Instrument-independent parameters defining the signal and session."""

    filters: StrategyFilters = field(default_factory=StrategyFilters)
    atr_period: int = 14
    atr_stop_mult: float = 1.5
    reward_risk: float = 1.3
    vwap_tolerance: float = 0.001
    session_start: time = time(10, 0)
    session_end: time = time(15, 0)

    def __post_init__(self) -> None:
        for name in ("atr_stop_mult", "reward_risk", "vwap_tolerance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if isinstance(self.atr_period, bool) or not isinstance(self.atr_period, int):
            raise ValueError("atr_period must be an integer")
        if self.atr_period < 1:
            raise ValueError("atr_period must be at least 1")
        if self.atr_stop_mult <= 0 or self.reward_risk <= 0:
            raise ValueError("atr_stop_mult and reward_risk must be positive")
        if self.vwap_tolerance < 0:
            raise ValueError("vwap_tolerance cannot be negative")
        if self.session_start >= self.session_end:
            raise ValueError("session_start must be before session_end")


@dataclass(frozen=True)
class AccountRiskConfig:
    """Account-currency capital and risk limits, independent of instruments."""

    account_size: float = 10_000.0
    risk_pct: float = 0.01
    max_daily_loss_pct: float = 0.02

    def __post_init__(self) -> None:
        for name in ("account_size", "risk_pct", "max_daily_loss_pct"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if self.account_size <= 0:
            raise ValueError("account_size must be positive")
        if not 0 < self.risk_pct < 1:
            raise ValueError("risk_pct must be between 0 and 1 (exclusive)")
        if not 0 < self.max_daily_loss_pct < 1:
            raise ValueError("max_daily_loss_pct must be between 0 and 1 (exclusive)")
        if self.max_daily_loss_pct < self.risk_pct:
            raise ValueError("max_daily_loss_pct must be at least risk_pct")

    @property
    def risk_dollars(self) -> float:
        """Account-currency amount risked per trade."""
        return self.account_size * self.risk_pct

    @property
    def max_daily_loss_dollars(self) -> float:
        """Account-currency daily realized-loss limit."""
        return self.account_size * self.max_daily_loss_pct


@dataclass(frozen=True)
class StrategyConfig(StrategyParameters):
    """Backward-compatible combined config for the existing live monitor.

    New strategy research should use StrategyParameters and pass
    AccountRiskConfig separately. The CFD lot fields are legacy monitor
    settings; instrument-aware research must use InstrumentSpec instead.
    """

    account_size: float = 10_000.0
    risk_pct: float = 0.01
    max_daily_loss_pct: float = 0.02
    point_value_per_lot: float = 10.0
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 100.0

    def __post_init__(self) -> None:
        super().__post_init__()
        AccountRiskConfig(
            account_size=self.account_size,
            risk_pct=self.risk_pct,
            max_daily_loss_pct=self.max_daily_loss_pct,
        )
        for name in ("point_value_per_lot", "min_lot", "lot_step", "max_lot"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_lot < self.min_lot:
            raise ValueError("max_lot must be at least min_lot")

    @property
    def risk_dollars(self) -> float:
        return AccountRiskConfig(
            self.account_size, self.risk_pct, self.max_daily_loss_pct
        ).risk_dollars

    @property
    def max_daily_loss_dollars(self) -> float:
        return AccountRiskConfig(
            self.account_size, self.risk_pct, self.max_daily_loss_pct
        ).max_daily_loss_dollars

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> StrategyConfig:
        """Build the legacy live-monitor config from environment variables."""
        env = os.environ if environ is None else environ
        mapping = {
            "ACCOUNT_SIZE": "account_size",
            "RISK_PERCENTAGE": "risk_pct",
            "MAX_DAILY_LOSS_PERCENTAGE": "max_daily_loss_pct",
            "REWARD_RISK": "reward_risk",
            "ATR_STOP_MULT": "atr_stop_mult",
            "POINT_VALUE_PER_LOT": "point_value_per_lot",
            "MIN_LOT": "min_lot",
            "LOT_STEP": "lot_step",
        }
        overrides: dict[str, float] = {}
        for var, config_field in mapping.items():
            raw = env.get(var)
            if raw is None or raw.strip() == "":
                continue
            try:
                overrides[config_field] = float(raw)
            except ValueError as exc:
                raise ValueError(f"{var} must be a number, got {raw!r}") from exc
            if not math.isfinite(overrides[config_field]):
                raise ValueError(f"{var} must be a finite number, got {raw!r}")
        return cls(**overrides)
