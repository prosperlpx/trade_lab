import math

import pytest

from trade_lab.config import AccountRiskConfig, StrategyConfig, StrategyParameters


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


def test_strategy_parameters_are_separate_from_account_risk():
    strategy = StrategyParameters(atr_period=7, reward_risk=1.8)
    risk = AccountRiskConfig(account_size=20_000, risk_pct=0.005)
    assert strategy.atr_period == 7
    assert risk.risk_dollars == pytest.approx(100)
    assert not hasattr(strategy, "account_size")


def test_legacy_strategy_config_remains_compatible():
    config = StrategyConfig(account_size=5_000, risk_pct=0.005)
    assert config.risk_dollars == pytest.approx(25)
    assert isinstance(config, StrategyParameters)
