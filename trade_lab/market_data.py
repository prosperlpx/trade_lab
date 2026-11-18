"""Provider-neutral historical and live market-data contract."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

import pandas as pd


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    bid: float
    ask: float
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if (
            isinstance(self.bid, bool)
            or isinstance(self.ask, bool)
            or not math.isfinite(self.bid)
            or not math.isfinite(self.ask)
        ):
            raise ValueError("bid and ask must be finite numbers")
        if self.bid <= 0 or self.ask < self.bid:
            raise ValueError("quote requires positive bid and ask >= bid")
        if self.timestamp.utcoffset() is None:
            raise ValueError("quote timestamp must be timezone-aware")


@runtime_checkable
class MarketDataProvider(Protocol):
    """A market-data source independent of any broker execution connection."""

    provider_id: str

    async def get_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return normalized OHLCV bars indexed by timezone-aware timestamps."""

    async def get_latest_quote(self, symbol: str) -> MarketQuote: ...
