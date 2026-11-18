"""Optional, instrument-independent strategy research filters."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyFilters:
    """Opt-in filters; None disables a criterion."""

    max_pullback_atr: float | None = None
    min_directional_vwap_slope_atr: float | None = None
    min_atr_pct: float | None = None
    max_atr_pct: float | None = None
    vwap_slope_lookback: int = 3

    def __post_init__(self) -> None:
        for name in (
            "max_pullback_atr",
            "min_directional_vwap_slope_atr",
            "min_atr_pct",
            "max_atr_pct",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not math.isfinite(value) or value < 0
            ):
                raise ValueError(f"{name} must be a finite non-negative number or None")
        if (
            isinstance(self.vwap_slope_lookback, bool)
            or not isinstance(self.vwap_slope_lookback, int)
            or self.vwap_slope_lookback < 1
        ):
            raise ValueError("vwap_slope_lookback must be a positive integer")
        if (
            self.min_atr_pct is not None
            and self.max_atr_pct is not None
            and self.min_atr_pct > self.max_atr_pct
        ):
            raise ValueError("min_atr_pct cannot exceed max_atr_pct")
