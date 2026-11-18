"""Alert message formatting."""

from __future__ import annotations

import pandas as pd

from .config import StrategyConfig
from .sessions import to_ny
from .sizing import realized_risk


def format_alert(
    side: str,
    closed_at: pd.Timestamp,
    entry: float,
    stop: float,
    target: float,
    lots: float,
    risk_points: float,
    cfg: StrategyConfig,
) -> str:
    """Plain-text alert. Levels are scaled from QQQ/NQ, so the message also
    states the risk distance, which lets you re-anchor to your actual fill."""
    ny = to_ny(closed_at)
    actual_risk = realized_risk(lots, risk_points, cfg)
    return "\n".join(
        [
            f"US100 VWAP PULLBACK: {side}",
            f"Signal bar closed {ny:%H:%M} New York ({closed_at.tz_convert('UTC'):%H:%M} UTC)",
            f"Entry (reference): {entry:.2f}",
            f"Stop: {stop:.2f}",
            f"Target: {target:.2f} ({cfg.reward_risk:g}R)",
            f"Risk distance: {risk_points:.1f} points",
            f"Size: {lots:.2f} lots (risk ${actual_risk:.2f} of ${cfg.risk_dollars:.2f} budget)",
            "",
            "Levels are scaled from QQQ and NQ futures and can differ from your CFD quote.",
            "Re-anchor stop and target to your actual fill using the risk distance.",
            "Rule: one trade per day.",
        ]
    )
