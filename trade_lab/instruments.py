"""Broker-neutral instrument economics and trading constraints."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class AssetClass(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    INDEX_CFD = "index_cfd"
    FX = "fx"
    FUTURE = "future"
    CRYPTO = "crypto"
    OTHER = "other"


@dataclass(frozen=True)
class InstrumentSpec:
    """Tradable instrument specification supplied by a venue/broker.

    tick_value is the value of one tick_size move for one quantity unit,
    denominated in tick_value_currency. A quantity unit may be a share,
    contract, or CFD lot. Values must come from the actual venue specification.
    """

    symbol: str
    asset_class: AssetClass
    quote_currency: str
    tick_size: float
    tick_value: float
    tick_value_currency: str
    quantity_unit: str
    min_quantity: float
    quantity_step: float
    max_quantity: float

    def __post_init__(self) -> None:
        for name in ("symbol", "quote_currency", "tick_value_currency", "quantity_unit"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be empty")
        for name in (
            "tick_size",
            "tick_value",
            "min_quantity",
            "quantity_step",
            "max_quantity",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_quantity < self.min_quantity:
            raise ValueError("max_quantity must be at least min_quantity")

    def risk_per_quantity(
        self, stop_distance: float, value_to_account_rate: float = 1.0
    ) -> float:
        """Account-currency loss for one quantity unit at the specified stop."""
        _positive_finite("stop_distance", stop_distance)
        _positive_finite("value_to_account_rate", value_to_account_rate)
        ticks = stop_distance / self.tick_size
        return ticks * self.tick_value * value_to_account_rate

    def price_cost_per_quantity(
        self, price_cost: float, value_to_account_rate: float = 1.0
    ) -> float:
        """Convert a price-distance cost into account currency per quantity."""
        if isinstance(price_cost, bool) or not math.isfinite(price_cost) or price_cost < 0:
            raise ValueError("price_cost must be a finite non-negative number")
        _positive_finite("value_to_account_rate", value_to_account_rate)
        return (price_cost / self.tick_size) * self.tick_value * value_to_account_rate


def _positive_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
