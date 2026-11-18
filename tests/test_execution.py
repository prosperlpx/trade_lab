from datetime import datetime, timezone

import pytest

from trade_lab.execution import (
    AccountEnvironment,
    AccountSnapshot,
    ExecutionMode,
    OrderRequest,
    OrderSide,
    OrderType,
    assert_execution_allowed,
)
from trade_lab.market_data import MarketQuote


def account(environment=AccountEnvironment.DEMO):
    return AccountSnapshot("123", "sample-broker", environment, "USD", 10_000, 8_000)


def test_demo_mode_requires_demo_account():
    assert_execution_allowed(ExecutionMode.DEMO, account())
    with pytest.raises(PermissionError):
        assert_execution_allowed(ExecutionMode.DEMO, account(AccountEnvironment.LIVE))


def test_live_mode_is_disabled_by_default():
    with pytest.raises(PermissionError, match="disabled"):
        assert_execution_allowed(ExecutionMode.LIVE, account(AccountEnvironment.LIVE))


def test_live_mode_requires_explicit_enable_and_live_account():
    assert_execution_allowed(
        ExecutionMode.LIVE, account(AccountEnvironment.LIVE), live_trading_enabled=True
    )
    with pytest.raises(PermissionError):
        assert_execution_allowed(
            ExecutionMode.LIVE, account(), live_trading_enabled=True
        )


@pytest.mark.parametrize("mode", [ExecutionMode.DISABLED, ExecutionMode.PAPER])
def test_non_broker_modes_reject_broker_submission(mode):
    with pytest.raises(PermissionError):
        assert_execution_allowed(mode, account())


def test_limit_order_requires_limit_price():
    with pytest.raises(ValueError, match="limit_price"):
        OrderRequest("client-1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 1)


def test_order_quantity_must_be_positive():
    with pytest.raises(ValueError, match="quantity"):
        OrderRequest("client-1", "AAPL", OrderSide.BUY, OrderType.MARKET, 0)


def test_quote_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        MarketQuote("AAPL", 10, 10.1, datetime(2026, 11, 18))
    MarketQuote("AAPL", 10, 10.1, datetime(2026, 11, 18, tzinfo=timezone.utc))
