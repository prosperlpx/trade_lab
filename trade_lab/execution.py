"""Broker-neutral execution contracts; concrete broker adapters live separately."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .market_data import MarketQuote


class ExecutionMode(str, Enum):
    DISABLED = "disabled"
    PAPER = "paper"
    DEMO = "demo"
    LIVE = "live"


class AccountEnvironment(str, Enum):
    DEMO = "demo"
    LIVE = "live"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WORKING = "working"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: str
    broker_id: str
    environment: AccountEnvironment
    currency: str
    equity: float
    free_margin: float

    def __post_init__(self) -> None:
        if not self.account_id.strip() or not self.broker_id.strip() or not self.currency.strip():
            raise ValueError("account_id, broker_id and currency cannot be empty")
        for name in ("equity", "free_margin"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")


@dataclass(frozen=True)
class OrderRequest:
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    stop_loss: float | None = None
    take_profit: float | None = None
    limit_price: float | None = None

    def __post_init__(self) -> None:
        if not self.client_order_id.strip() or not self.symbol.strip():
            raise ValueError("client_order_id and symbol cannot be empty")
        if (
            isinstance(self.quantity, bool)
            or not math.isfinite(self.quantity)
            or self.quantity <= 0
        ):
            raise ValueError("quantity must be a finite positive number")
        for name in ("stop_loss", "take_profit", "limit_price"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not math.isfinite(value) or value <= 0
            ):
                raise ValueError(f"{name} must be a finite positive number when supplied")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit orders require limit_price")


@dataclass(frozen=True)
class OrderResult:
    client_order_id: str
    broker_order_id: str | None
    status: OrderStatus
    filled_quantity: float = 0.0
    average_fill_price: float | None = None
    message: str = ""


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    average_price: float
    side: OrderSide


@runtime_checkable
class BrokerAdapter(Protocol):
    """Minimum asynchronous interface required from a broker integration."""

    broker_id: str

    async def get_account(self) -> AccountSnapshot: ...

    async def get_quote(self, symbol: str) -> MarketQuote: ...

    async def submit_order(self, request: OrderRequest) -> OrderResult: ...

    async def get_order(self, client_order_id: str) -> OrderResult: ...

    async def cancel_order(self, client_order_id: str) -> OrderResult: ...

    async def list_positions(self) -> list[Position]: ...


def assert_execution_allowed(
    mode: ExecutionMode,
    account: AccountSnapshot,
    *,
    live_trading_enabled: bool = False,
) -> None:
    """Fail closed when execution mode and actual account environment disagree."""
    if mode in (ExecutionMode.DISABLED, ExecutionMode.PAPER):
        raise PermissionError(f"{mode.value} mode does not permit broker order submission")
    if mode == ExecutionMode.DEMO and account.environment != AccountEnvironment.DEMO:
        raise PermissionError("demo mode requires a broker demo account")
    if mode == ExecutionMode.LIVE:
        if not live_trading_enabled:
            raise PermissionError("live trading is disabled by default")
        if account.environment != AccountEnvironment.LIVE:
            raise PermissionError("live mode requires a live broker account")
