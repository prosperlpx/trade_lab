"""Strategy and risk configuration, validated at construction time."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class StrategyConfig:
    """All tunable parameters in one immutable object."""

    # Account and risk
    account_size: float = 10_000.0
    risk_pct: float = 0.01
    max_daily_loss_pct: float = 0.02

    # Signal definition
    atr_period: int = 14
    atr_stop_mult: float = 1.5
    reward_risk: float = 1.3
    vwap_tolerance: float = 0.001

    # Trading window in New York local time. Using New York time (not a fixed
    # UTC offset) keeps the window aligned with the US cash session across
    # daylight saving changes.
    session_start: time = time(10, 0)
    session_end: time = time(15, 0)

    # Execution instrument (CFD) sizing. Check these against your broker's
    # contract specification before trusting the lot size in alerts.
    point_value_per_lot: float = 10.0
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 100.0

    def __post_init__(self) -> None:
        numeric_fields = {
            "account_size": self.account_size,
            "risk_pct": self.risk_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "atr_stop_mult": self.atr_stop_mult,
            "reward_risk": self.reward_risk,
            "vwap_tolerance": self.vwap_tolerance,
            "point_value_per_lot": self.point_value_per_lot,
            "min_lot": self.min_lot,
            "lot_step": self.lot_step,
            "max_lot": self.max_lot,
        }
        for name, value in numeric_fields.items():
            try:
                finite = math.isfinite(value)
            except TypeError as exc:
                raise ValueError(f"{name} must be a finite number") from exc
            if not finite:
                raise ValueError(f"{name} must be a finite number")
        if isinstance(self.atr_period, bool) or not isinstance(self.atr_period, int):
            raise ValueError("atr_period must be an integer")
        if self.account_size <= 0:
            raise ValueError("account_size must be positive")
        if not 0 < self.risk_pct < 1:
            raise ValueError("risk_pct must be between 0 and 1 (exclusive)")
        if not 0 < self.max_daily_loss_pct < 1:
            raise ValueError("max_daily_loss_pct must be between 0 and 1 (exclusive)")
        if self.max_daily_loss_pct < self.risk_pct:
            raise ValueError("max_daily_loss_pct must be at least risk_pct")
        if self.atr_period < 1:
            raise ValueError("atr_period must be at least 1")
        if self.atr_stop_mult <= 0 or self.reward_risk <= 0:
            raise ValueError("atr_stop_mult and reward_risk must be positive")
        if self.vwap_tolerance < 0:
            raise ValueError("vwap_tolerance cannot be negative")
        if self.session_start >= self.session_end:
            raise ValueError("session_start must be before session_end")
        if self.point_value_per_lot <= 0 or self.lot_step <= 0 or self.min_lot <= 0:
            raise ValueError("point_value_per_lot, lot_step and min_lot must be positive")
        if self.max_lot < self.min_lot:
            raise ValueError("max_lot must be at least min_lot")

    @property
    def risk_dollars(self) -> float:
        """Dollar amount risked on each trade."""
        return self.account_size * self.risk_pct

    @property
    def max_daily_loss_dollars(self) -> float:
        """Realized loss at which trading stops for the day."""
        return self.account_size * self.max_daily_loss_pct

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> StrategyConfig:
        """Build a config from environment variables, falling back to defaults.

        Recognised variables: ACCOUNT_SIZE, RISK_PERCENTAGE,
        MAX_DAILY_LOSS_PERCENTAGE, REWARD_RISK, ATR_STOP_MULT,
        POINT_VALUE_PER_LOT, MIN_LOT, LOT_STEP.
        """
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
        for var, field in mapping.items():
            raw = env.get(var)
            if raw is None or raw.strip() == "":
                continue
            try:
                overrides[field] = float(raw)
            except ValueError as exc:
                raise ValueError(f"{var} must be a number, got {raw!r}") from exc
            if not math.isfinite(overrides[field]):
                raise ValueError(f"{var} must be a finite number, got {raw!r}")
        return cls(**overrides)
