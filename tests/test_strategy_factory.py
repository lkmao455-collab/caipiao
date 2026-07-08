import pytest

from caipiao.core.profile import get_profile
from caipiao.core.strategies import build_strategies, is_ml_strategy, needs_history


EXPECTED_IDS = {
    "ssq": {
        "random", "odd_even", "hot_cold", "exclude_include", "smart_hot_cold",
        "missing_number", "balanced", "stats", "ml_xgboost", "ml_lightgbm", "ml_catboost",
        "random_forest", "bayesian", "markov", "trend", "periodic", "ensemble",
        "correlation", "transformer",
    },
    "3d": {
        "random_3d", "odd_even_3d", "hot_cold_3d", "exclude_include_3d",
        "smart_hot_cold_3d", "missing_number_3d", "balanced_3d",
        "xgboost_3d", "lightgbm_3d", "catboost_3d",
    },
}


@pytest.mark.parametrize("key", list(EXPECTED_IDS))
def test_build_strategies_returns_expected_ids(key):
    profile = get_profile(key)
    strategies = build_strategies(profile)
    ids = {s.metadata.id for s in strategies}
    assert ids == EXPECTED_IDS[key], f"{key}: got {ids}"


def test_needs_history_prefixes():
    assert needs_history("hot_cold_3d") is True
    assert needs_history("balanced") is True
    assert needs_history("random") is False
    assert needs_history("xgboost_3d") is True
    assert needs_history("random_forest") is True


def test_is_ml_strategy_prefixes():
    assert is_ml_strategy("ml_xgboost") is True
    assert is_ml_strategy("xgboost_3d") is True
    assert is_ml_strategy("lightgbm_kl8") is True
    assert is_ml_strategy("random_forest") is True
    assert is_ml_strategy("ensemble") is True
    assert is_ml_strategy("random") is False
    assert is_ml_strategy("balanced") is False
