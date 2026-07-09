import random
from datetime import datetime, timedelta

import numpy as np
import pytest
from caipiao.core.profile import SSQ
from caipiao.core.strategies.advanced.lotteries.ssq.consensus_constraint import (
    SSQConsensusConstraintStrategy,
)
from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord


@pytest.fixture
def sample_history():
    """生成 100 期双色球历史记录作为测试样本。"""
    records = []
    for i in range(100):
        red_start = (i % 28) + 1
        reds = sorted([red_start + j for j in range(6)])
        blue = (i % 16) + 1
        records.append(
            DrawRecord(
                issue=f"{i + 1:03d}",
                draw_date=datetime(2024, 1, 1) + timedelta(days=i),
                red_balls=reds,
                blue_ball=blue,
            )
        )
    return records


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


def test_statistical_prior_is_probability_distribution(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "stats_enabled": True,
        "smart_hot_cold_enabled": True,
        "hot_cold_enabled": True,
        "missing_number_enabled": True,
    }
    red_probs, blue_probs, basis = strategy._compute_statistical_prior(
        [r for r in sample_history], options
    )
    assert abs(red_probs.sum() - 1.0) < 1e-10
    assert abs(blue_probs.sum() - 1.0) < 1e-10
    assert len(red_probs) == 33
    assert len(blue_probs) == 16
    assert isinstance(basis, str)
    assert basis.startswith("共识约束策略：统计先验融合")


def test_generate_candidates_valid(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {"history": sample_history, "seed": 42, "candidate_count": 1000}
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    assert len(candidates) <= 1000
    assert all(len(c[0]) == 6 and len(set(c[0])) == 6 for c in candidates)
    assert all(1 <= c[1] <= 16 for c in candidates)


def test_hard_constraints_filter(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "odd_even_enabled": True,
        "odd_count": 3,
        "balanced_enabled": True,
        "balanced_lookback": 100,
        "sum_min": 80,
        "sum_max": 150,
        "target_odd": 3,
        "target_high": 3,
        "exclude_include_enabled": False,
    }
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    filtered = strategy._apply_hard_constraints(candidates, records, options)
    assert len(filtered) <= len(candidates)
    sum_min = options["sum_min"]
    sum_max = options["sum_max"]
    for reds, blue in filtered:
        assert sum(1 for n in reds if n % 2 == 1) == 3
        assert sum_min <= sum(reds) <= sum_max
