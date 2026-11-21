import math

import pytest

from trade_lab.config import StrategyConfig


@pytest.mark.parametrize("field", [
    "account_size", "risk_pct", "max_daily_loss_pct", "atr_stop_mult",
    "reward_risk", "vwap_tolerance", "point_value_per_lot", "min_lot",
    "lot_step", "max_lot",
])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_numeric_configuration_rejects_non_finite_values(field, value):
    with pytest.raises(ValueError, match="finite"):
        StrategyConfig(**{field: value})


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf"])
def test_environment_configuration_rejects_non_finite_values(raw):
    with pytest.raises(ValueError, match="finite"):
        StrategyConfig.from_env({"ACCOUNT_SIZE": raw})


def test_atr_period_must_be_an_integer():
    with pytest.raises(ValueError, match="integer"):
        StrategyConfig(atr_period=2.5)
