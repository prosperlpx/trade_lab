"""Position sizing and risk guards."""

from __future__ import annotations

import math

from .config import StrategyConfig

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
