import pytest

from caipiao.core.profile import get_profile
from caipiao.core.strategies import build_strategies, is_ml_strategy, needs_history


EXPECTED_IDS = {
    "ssq": {
        "random", "odd_even", "hot_cold", "exclude_include", "smart_hot_cold",
        "missing_number", "balanced", "stats", "ml_xgboost", "ml_lightgbm", "ml_catboost",
        "ml_lstm", "ml_hybrid", "random_forest", "bayesian", "markov", "trend",
        "periodic", "ensemble", "correlation", "transformer", "consensus_constraint",
    },
    "3d": {
        "random_3d", "odd_even_3d", "hot_cold_3d", "exclude_include_3d",
        "smart_hot_cold_3d", "missing_number_3d", "balanced_3d",
        "ensemble_v2_3d", "dispersed_random_3d",
        "xgboost_3d", "lightgbm_3d", "catboost_3d",
        "random_forest_3d", "bayesian_3d", "markov_3d", "trend_3d",
        "periodic_3d", "ensemble_3d", "correlation_3d", "transformer_3d",
    },
    "qlc": {
        "random_qlc", "odd_even_qlc", "hot_cold_qlc", "exclude_include_qlc",
        "smart_hot_cold_qlc", "missing_number_qlc", "balanced_qlc",
        "xgboost_qlc", "lightgbm_qlc", "catboost_qlc",
        "random_forest_qlc", "bayesian_qlc", "markov_qlc", "trend_qlc",
        "periodic_qlc", "ensemble_qlc", "correlation_qlc", "transformer_qlc",
    },
    "kl8": {
        "random_kl8", "odd_even_kl8", "hot_cold_kl8", "exclude_include_kl8",
        "smart_hot_cold_kl8", "missing_number_kl8", "balanced_kl8",
        "xgboost_kl8", "lightgbm_kl8", "catboost_kl8",
        "random_forest_kl8", "bayesian_kl8", "markov_kl8", "trend_kl8",
        "periodic_kl8", "ensemble_kl8", "correlation_kl8", "transformer_kl8",
    },
    "dlt": {
        "random_dlt", "odd_even_dlt", "hot_cold_dlt", "exclude_include_dlt",
        "smart_hot_cold_dlt", "missing_number_dlt", "balanced_dlt",
        "xgboost_dlt", "lightgbm_dlt", "catboost_dlt",
        "random_forest_dlt", "bayesian_dlt", "markov_dlt", "trend_dlt",
        "periodic_dlt", "ensemble_dlt", "correlation_dlt", "transformer_dlt",
    },
    "pl3": {
        "random_pl3", "odd_even_pl3", "hot_cold_pl3", "exclude_include_pl3",
        "smart_hot_cold_pl3", "missing_number_pl3", "balanced_pl3",
        "xgboost_pl3", "lightgbm_pl3", "catboost_pl3",
        "random_forest_pl3", "bayesian_pl3", "markov_pl3", "trend_pl3",
        "periodic_pl3", "ensemble_pl3", "correlation_pl3", "transformer_pl3",
    },
    "pl5": {
        "random_pl5", "odd_even_pl5", "hot_cold_pl5", "exclude_include_pl5",
        "smart_hot_cold_pl5", "missing_number_pl5", "balanced_pl5",
        "xgboost_pl5", "lightgbm_pl5", "catboost_pl5",
        "random_forest_pl5", "bayesian_pl5", "markov_pl5", "trend_pl5",
        "periodic_pl5", "ensemble_pl5", "correlation_pl5", "transformer_pl5",
    },
    "qxc": {
        "random_qxc", "odd_even_qxc", "hot_cold_qxc", "exclude_include_qxc",
        "smart_hot_cold_qxc", "missing_number_qxc", "balanced_qxc",
        "xgboost_qxc", "lightgbm_qxc", "catboost_qxc",
        "random_forest_qxc", "bayesian_qxc", "markov_qxc", "trend_qxc",
        "periodic_qxc", "ensemble_qxc", "correlation_qxc", "transformer_qxc",
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
    assert needs_history("consensus_constraint") is True


def test_is_ml_strategy_prefixes():
    assert is_ml_strategy("ml_xgboost") is True
    assert is_ml_strategy("xgboost_3d") is True
    assert is_ml_strategy("lightgbm_kl8") is True
    assert is_ml_strategy("random_forest") is True
    assert is_ml_strategy("ensemble") is True
    assert is_ml_strategy("random") is False
    assert is_ml_strategy("balanced") is False
