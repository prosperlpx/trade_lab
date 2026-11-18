import dataclasses

import pytest

from trade_lab.config import StrategyConfig
from trade_lab.sizing import (
    daily_loss_exceeded,
    lots_for_risk,
    realized_risk,
    scale_price,
    units_for_risk,
)

CFG = StrategyConfig()


def test_units_for_risk():
    assert units_for_risk(100.0, 0.5) == pytest.approx(200.0)


def test_units_rejects_bad_distance():
    with pytest.raises(ValueError):
        units_for_risk(100.0, 0.0)


def test_lots_exact():
    assert lots_for_risk(100.0, 20.0, CFG) == pytest.approx(0.5)


def test_lots_round_down_to_step():
    assert lots_for_risk(100.0, 23.0, CFG) == pytest.approx(0.43)


def test_lots_below_minimum_returns_zero():
    assert lots_for_risk(100.0, 20_000.0, CFG) == 0.0


def test_lots_capped_at_max():
    cfg = dataclasses.replace(CFG, max_lot=1.0)
    assert lots_for_risk(100.0, 1.0, cfg) == 1.0


@pytest.mark.parametrize("points", [3.7, 11.3, 23.9, 47.1, 88.8, 150.25])
def test_planned_risk_is_never_exceeded(points):
    lots = lots_for_risk(CFG.risk_dollars, points, CFG)
    assert realized_risk(lots, points, CFG) <= CFG.risk_dollars + 1e-9


def test_scale_price():
    assert scale_price(686.0, 35.0) == pytest.approx(24010.0)


def test_daily_loss_kill_switch_boundary():
    assert daily_loss_exceeded(-200.0, CFG)
    assert daily_loss_exceeded(-250.0, CFG)
    assert not daily_loss_exceeded(-199.99, CFG)
    assert not daily_loss_exceeded(50.0, CFG)


def test_config_defaults_match_readme_claims():
    assert CFG.risk_dollars == pytest.approx(100.0)
    assert CFG.max_daily_loss_dollars == pytest.approx(200.0)
    assert CFG.reward_risk == pytest.approx(1.3)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"risk_pct": 0.05, "max_daily_loss_pct": 0.02},
        {"risk_pct": 0.0},
        {"account_size": -1.0},
        {"atr_period": 0},
        {"reward_risk": 0.0},
    ],
)
def test_config_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        StrategyConfig(**kwargs)


def test_config_from_env_overrides_and_validates():
    cfg = StrategyConfig.from_env({"ACCOUNT_SIZE": "5000", "RISK_PERCENTAGE": "0.005"})
    assert cfg.account_size == 5000.0
    assert cfg.risk_dollars == pytest.approx(25.0)
    with pytest.raises(ValueError):
        StrategyConfig.from_env({"ACCOUNT_SIZE": "abc"})
