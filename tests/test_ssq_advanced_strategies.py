from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import SSQ
from caipiao.core.strategies import build_strategies, is_ml_strategy
from caipiao.core.strategies.advanced.lotteries.ssq import (
    SSQBayesianStrategy,
    SSQCorrelationStrategy,
    SSQEnsembleStrategy,
    SSQMarkovStrategy,
    SSQPeriodicStrategy,
    SSQRandomForestStrategy,
    SSQTrendStrategy,
    SSQTransformerStrategy,
)
from caipiao.data.models import DrawRecord


ADVANCED_STRATEGIES = [
    (SSQRandomForestStrategy, "random_forest", True),
    (SSQBayesianStrategy, "bayesian", False),
    (SSQMarkovStrategy, "markov", False),
    (SSQTrendStrategy, "trend", False),
    (SSQPeriodicStrategy, "periodic", False),
    (SSQEnsembleStrategy, "ensemble", True),
    (SSQCorrelationStrategy, "correlation", False),
    (SSQTransformerStrategy, "transformer", True),
]


def make_ssq_history(n=50):
    rng = __import__("random").Random(0)
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=sorted(rng.sample(range(1, 34), 6)),
            blue_ball=rng.randint(1, 16),
        )
        for i in range(n)
    ]


@pytest.mark.parametrize("cls,strategy_id,is_ml", ADVANCED_STRATEGIES)
def test_ssq_advanced_metadata(cls, strategy_id, is_ml):
    s = cls()
    assert s.metadata.id == strategy_id
    assert s.metadata.configurable is True
    assert s.is_ml is is_ml
    assert is_ml_strategy(strategy_id) is is_ml


def test_ssq_random_forest_generates_valid():
    s = SSQRandomForestStrategy()
    history = make_ssq_history(50)
    tickets = s.generate(count=2, options={"history": history})
    assert len(tickets) == 2
    for t in tickets:
        assert t.profile.key == "ssq"
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1


@pytest.mark.parametrize("cls,_,__", ADVANCED_STRATEGIES)
def test_ssq_advanced_generates_valid(cls, _, __):
    if cls is SSQTransformerStrategy:
        pytest.importorskip("torch")
    s = cls()
    history = make_ssq_history(50)
    tickets = s.generate(count=2, options={"history": history})
    assert len(tickets) == 2
    for t in tickets:
        assert t.profile.key == "ssq"
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1


def test_build_strategies_includes_advanced():
    strategies = build_strategies(SSQ)
    ids = {s.metadata.id for s in strategies}
    assert "random_forest" in ids
    assert "transformer" in ids
    assert "bayesian" in ids
    assert "ensemble" in ids
