import pytest
from caipiao.core.profile import SSQ
from caipiao.core.strategies.advanced.lotteries.ssq.consensus_constraint import (
    SSQConsensusConstraintStrategy,
)
from caipiao.core.ticket import Ticket


def test_metadata_and_schema():
    strategy = SSQConsensusConstraintStrategy()
    assert strategy.metadata.id == "consensus_constraint"
    assert strategy.metadata.name == "共识约束策略"
    assert strategy.metadata.configurable is True

    schema = strategy.get_config_schema()
    assert "seed" in schema
    assert "candidate_count" in schema
    assert "stats_lookback" in schema
    assert "bayesian_alpha" in schema


def _make_history(n: int = 30):
    return [
        Ticket(
            profile=SSQ,
            groups={"red": [1, 2, 3, 4, 5, 6], "blue": [1]},
        )
        for _ in range(n)
    ]


def test_validate_options_requires_at_least_30_records():
    strategy = SSQConsensusConstraintStrategy()
    with pytest.raises(ValueError, match="至少 30 期"):
        strategy.validate_options({"history": _make_history(29)})

    strategy.validate_options({"history": _make_history(30)})


def test_validate_options_checks_sum_range():
    strategy = SSQConsensusConstraintStrategy()
    history = _make_history(30)
    with pytest.raises(ValueError, match="和值下限不能大于上限"):
        strategy.validate_options({"history": history, "sum_min": 100, "sum_max": 99})

    strategy.validate_options({"history": history, "sum_min": 60, "sum_max": 160})
