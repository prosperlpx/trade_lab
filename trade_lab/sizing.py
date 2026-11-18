"""Position sizing and risk guards."""

from __future__ import annotations

import math

from .config import StrategyConfig
from .instruments import InstrumentSpec

_EPS = 1e-9


def units_for_risk(risk_dollars: float, risk_distance: float) -> float:
    """Number of shares/units that lose ``risk_dollars`` if the stop is hit."""
    if risk_distance <= 0:
        raise ValueError("risk_distance must be positive")
    return risk_dollars / risk_distance


def lots_for_risk(risk_dollars: float, risk_points: float, cfg: StrategyConfig) -> float:
    """CFD lot size, rounded DOWN to the lot step so risk is never exceeded.

    Returns 0.0 when the risk budget cannot fund the minimum lot, instead of
    silently rounding up into a larger loss than planned.
    """
    if risk_points <= 0:
        raise ValueError("risk_points must be positive")
    raw = risk_dollars / (risk_points * cfg.point_value_per_lot)
    steps = math.floor(raw / cfg.lot_step + _EPS)
    lots = round(steps * cfg.lot_step, 8)
    if lots < cfg.min_lot - _EPS:
        return 0.0
    return min(lots, cfg.max_lot)


def realized_risk(lots: float, risk_points: float, cfg: StrategyConfig) -> float:
    """Dollar loss if a position of ``lots`` hits a stop ``risk_points`` away."""
    return lots * risk_points * cfg.point_value_per_lot


def scale_price(price: float, factor: float) -> float:
    """Convert a price between instruments using a ratio (for example NQ/QQQ)."""
    return price * factor


def daily_loss_exceeded(realized_pnl: float, cfg: StrategyConfig) -> bool:
    """True once realized losses for the day reach the kill-switch level."""
    return realized_pnl <= -cfg.max_daily_loss_dollars + _EPS


def quantity_for_instrument_risk(
    risk_budget: float,
    stop_distance: float,
    instrument: InstrumentSpec,
    value_to_account_rate: float = 1.0,
) -> float:
    """Size a share/contract/lot quantity from broker-supplied instrument economics.

    Quantity is rounded down to the instrument step and capped at its maximum.
    Returns zero if the risk budget cannot fund the minimum tradable quantity.
    """
    if not isinstance(instrument, InstrumentSpec):
        raise TypeError("instrument must be an InstrumentSpec")
    if isinstance(risk_budget, bool) or not math.isfinite(risk_budget) or risk_budget <= 0:
        raise ValueError("risk_budget must be a finite positive number")
    per_quantity = instrument.risk_per_quantity(stop_distance, value_to_account_rate)
    raw = min(risk_budget / per_quantity, instrument.max_quantity)
    steps = math.floor(raw / instrument.quantity_step + _EPS)
    quantity = round(steps * instrument.quantity_step, 10)
    if quantity < instrument.min_quantity - _EPS:
        return 0.0
    return quantity


def instrument_realized_risk(
    quantity: float,
    stop_distance: float,
    instrument: InstrumentSpec,
    value_to_account_rate: float = 1.0,
) -> float:
    """Account-currency stop risk for a quantity using instrument tick economics."""
    if isinstance(quantity, bool) or not math.isfinite(quantity) or quantity < 0:
        raise ValueError("quantity must be a finite non-negative number")
    return quantity * instrument.risk_per_quantity(stop_distance, value_to_account_rate)
