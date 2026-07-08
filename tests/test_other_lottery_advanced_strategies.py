import pytest

from caipiao.core.profile import FC3D, DLT, KL8, PL3, PL5, QLC, QXC, get_profile
from caipiao.core.strategies import build_strategies, is_ml_strategy, needs_history
from caipiao.core.strategies.advanced.common.base import UnsupportedLotteryError
from caipiao.core.strategies.advanced.lotteries.dlt import (
    DLTBayesianStrategy,
    DLTCorrelationStrategy,
    DLTEnsembleStrategy,
    DLTMarkovStrategy,
    DLTPeriodicStrategy,
    DLTRandomForestStrategy,
    DLTTrendStrategy,
    DLTTransformerStrategy,
)
from caipiao.core.strategies.advanced.lotteries.fc3d import (
    FC3DBayesianStrategy,
    FC3DCorrelationStrategy,
    FC3DEnsembleStrategy,
    FC3DMarkovStrategy,
    FC3DPeriodicStrategy,
    FC3DRandomForestStrategy,
    FC3DTrendStrategy,
    FC3DTransformerStrategy,
)
from caipiao.core.strategies.advanced.lotteries.kl8 import (
    KL8BayesianStrategy,
    KL8CorrelationStrategy,
    KL8EnsembleStrategy,
    KL8MarkovStrategy,
    KL8PeriodicStrategy,
    KL8RandomForestStrategy,
    KL8TrendStrategy,
    KL8TransformerStrategy,
)
from caipiao.core.strategies.advanced.lotteries.pl3 import (
    PL3BayesianStrategy,
    PL3CorrelationStrategy,
    PL3EnsembleStrategy,
    PL3MarkovStrategy,
    PL3PeriodicStrategy,
    PL3RandomForestStrategy,
    PL3TrendStrategy,
    PL3TransformerStrategy,
)
from caipiao.core.strategies.advanced.lotteries.pl5 import (
    PL5BayesianStrategy,
    PL5CorrelationStrategy,
    PL5EnsembleStrategy,
    PL5MarkovStrategy,
    PL5PeriodicStrategy,
    PL5RandomForestStrategy,
    PL5TrendStrategy,
    PL5TransformerStrategy,
)
from caipiao.core.strategies.advanced.lotteries.qlc import (
    QLCBayesianStrategy,
    QLCCorrelationStrategy,
    QLCEnsembleStrategy,
    QLCMarkovStrategy,
    QLCPeriodicStrategy,
    QLCRandomForestStrategy,
    QLCTrendStrategy,
    QLCTransformerStrategy,
)
from caipiao.core.strategies.advanced.lotteries.qxc import (
    QXCBayesianStrategy,
    QXCCorrelationStrategy,
    QXCEnsembleStrategy,
    QXCMarkovStrategy,
    QXCPeriodicStrategy,
    QXCRandomForestStrategy,
    QXCTrendStrategy,
    QXCTransformerStrategy,
)


LOTTERY_ADVANCED_STRATEGIES = [
    ("3d", FC3DRandomForestStrategy, "random_forest_3d", True),
    ("3d", FC3DBayesianStrategy, "bayesian_3d", False),
    ("3d", FC3DMarkovStrategy, "markov_3d", False),
    ("3d", FC3DTrendStrategy, "trend_3d", False),
    ("3d", FC3DPeriodicStrategy, "periodic_3d", False),
    ("3d", FC3DEnsembleStrategy, "ensemble_3d", True),
    ("3d", FC3DCorrelationStrategy, "correlation_3d", False),
    ("3d", FC3DTransformerStrategy, "transformer_3d", True),
    ("qlc", QLCRandomForestStrategy, "random_forest_qlc", True),
    ("qlc", QLCBayesianStrategy, "bayesian_qlc", False),
    ("qlc", QLCMarkovStrategy, "markov_qlc", False),
    ("qlc", QLCTrendStrategy, "trend_qlc", False),
    ("qlc", QLCPeriodicStrategy, "periodic_qlc", False),
    ("qlc", QLCEnsembleStrategy, "ensemble_qlc", True),
    ("qlc", QLCCorrelationStrategy, "correlation_qlc", False),
    ("qlc", QLCTransformerStrategy, "transformer_qlc", True),
    ("kl8", KL8RandomForestStrategy, "random_forest_kl8", True),
    ("kl8", KL8BayesianStrategy, "bayesian_kl8", False),
    ("kl8", KL8MarkovStrategy, "markov_kl8", False),
    ("kl8", KL8TrendStrategy, "trend_kl8", False),
    ("kl8", KL8PeriodicStrategy, "periodic_kl8", False),
    ("kl8", KL8EnsembleStrategy, "ensemble_kl8", True),
    ("kl8", KL8CorrelationStrategy, "correlation_kl8", False),
    ("kl8", KL8TransformerStrategy, "transformer_kl8", True),
    ("dlt", DLTRandomForestStrategy, "random_forest_dlt", True),
    ("dlt", DLTBayesianStrategy, "bayesian_dlt", False),
    ("dlt", DLTMarkovStrategy, "markov_dlt", False),
    ("dlt", DLTTrendStrategy, "trend_dlt", False),
    ("dlt", DLTPeriodicStrategy, "periodic_dlt", False),
    ("dlt", DLTEnsembleStrategy, "ensemble_dlt", True),
    ("dlt", DLTCorrelationStrategy, "correlation_dlt", False),
    ("dlt", DLTTransformerStrategy, "transformer_dlt", True),
    ("pl3", PL3RandomForestStrategy, "random_forest_pl3", True),
    ("pl3", PL3BayesianStrategy, "bayesian_pl3", False),
    ("pl3", PL3MarkovStrategy, "markov_pl3", False),
    ("pl3", PL3TrendStrategy, "trend_pl3", False),
    ("pl3", PL3PeriodicStrategy, "periodic_pl3", False),
    ("pl3", PL3EnsembleStrategy, "ensemble_pl3", True),
    ("pl3", PL3CorrelationStrategy, "correlation_pl3", False),
    ("pl3", PL3TransformerStrategy, "transformer_pl3", True),
    ("pl5", PL5RandomForestStrategy, "random_forest_pl5", True),
    ("pl5", PL5BayesianStrategy, "bayesian_pl5", False),
    ("pl5", PL5MarkovStrategy, "markov_pl5", False),
    ("pl5", PL5TrendStrategy, "trend_pl5", False),
    ("pl5", PL5PeriodicStrategy, "periodic_pl5", False),
    ("pl5", PL5EnsembleStrategy, "ensemble_pl5", True),
    ("pl5", PL5CorrelationStrategy, "correlation_pl5", False),
    ("pl5", PL5TransformerStrategy, "transformer_pl5", True),
    ("qxc", QXCRandomForestStrategy, "random_forest_qxc", True),
    ("qxc", QXCBayesianStrategy, "bayesian_qxc", False),
    ("qxc", QXCMarkovStrategy, "markov_qxc", False),
    ("qxc", QXCTrendStrategy, "trend_qxc", False),
    ("qxc", QXCPeriodicStrategy, "periodic_qxc", False),
    ("qxc", QXCEnsembleStrategy, "ensemble_qxc", True),
    ("qxc", QXCCorrelationStrategy, "correlation_qxc", False),
    ("qxc", QXCTransformerStrategy, "transformer_qxc", True),
]


@pytest.mark.parametrize("key,cls,strategy_id,is_ml", LOTTERY_ADVANCED_STRATEGIES)
def test_placeholder_metadata(key, cls, strategy_id, is_ml):
    s = cls()
    assert s.metadata.id == strategy_id
    assert get_profile(key).name in s.metadata.name
    assert s.metadata.configurable is True
    assert s.is_ml is is_ml
    assert is_ml_strategy(strategy_id) is is_ml
    assert needs_history(strategy_id) is True


@pytest.mark.parametrize("key,cls,strategy_id,is_ml", LOTTERY_ADVANCED_STRATEGIES)
def test_placeholder_generate_raises(key, cls, strategy_id, is_ml):
    s = cls()
    with pytest.raises(UnsupportedLotteryError):
        s.generate(count=2)


@pytest.mark.parametrize("key", ["3d", "qlc", "kl8", "dlt", "pl3", "pl5", "qxc"])
def test_build_strategies_includes_advanced_placeholders(key):
    profile = get_profile(key)
    strategies = build_strategies(profile)
    ids = {s.metadata.id for s in strategies}
    assert f"random_forest_{key}" in ids
    assert f"bayesian_{key}" in ids
    assert f"transformer_{key}" in ids
    assert f"ensemble_{key}" in ids
