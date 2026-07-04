import pytest
from caipiao.ui.optimal_period_config import (
    OPTIMAL_PERIOD_RANGES,
    STRATEGY_PARAM_MAP,
    resolve_optimal_param,
)


def test_resolve_param_for_smart_hot_cold():
    result = resolve_optimal_param("smart_hot_cold")
    assert result is not None
    param_name, values = result
    assert param_name == "lookback"
    assert values == OPTIMAL_PERIOD_RANGES["lookback"]


def test_resolve_param_for_xgboost():
    result = resolve_optimal_param("xgboost")
    assert result is not None
    param_name, values = result
    assert param_name == "history_count"
    assert values == OPTIMAL_PERIOD_RANGES["history_count"]


def test_resolve_param_for_generic_balanced():
    result = resolve_optimal_param("balanced_3d")
    assert result is not None
    param_name, values = result
    assert param_name == "lookback"


def test_resolve_param_unsupported():
    assert resolve_optimal_param("random") is None
    assert resolve_optimal_param("odd_even") is None
