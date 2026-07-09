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


def test_refinement_scores_candidates(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "candidate_count": 100,
        "bayesian_enabled": True,
        "markov_enabled": False,
        "trend_enabled": False,
        "periodic_enabled": False,
        "correlation_enabled": False,
    }
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    scored = strategy._score_candidates(candidates, records, options)
    assert len(scored) == len(candidates)
    assert all(isinstance(s, float) for s, _, _ in scored)


def test_generate_is_deterministic(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {"history": sample_history, "seed": 42, "candidate_count": 1000}
    result1 = strategy.generate(5, options)
    result2 = strategy.generate(5, options)
    assert result1 == result2
    assert len(result1) == 5
    for t in result1:
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1


def test_conflict_relaxation(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "candidate_count": 5000,
        "odd_even_enabled": True,
        "odd_count": 0,
        "balanced_enabled": True,
        "sum_min": 21,
        "sum_max": 30,
        "target_odd": 0,
        "target_high": 0,
        "relaxation_order": "reverse",
    }
    result = strategy.generate(1, options)
    assert len(result) == 1
    assert "放宽" in result[0].basis or "relax" in result[0].basis.lower()


def test_score_candidates_no_zero_division_when_all_weights_zero(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "candidate_count": 50,
        "bayesian_enabled": True,
        "bayesian_weight": 0,
        "markov_enabled": False,
        "trend_enabled": False,
        "periodic_enabled": False,
        "correlation_enabled": False,
    }
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    scored = strategy._score_candidates(candidates, records, options)
    assert len(scored) == len(candidates)
    assert all(isinstance(s, float) for s, _, _ in scored)


def test_blue_sampling_mode_uniform(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "candidate_count": 100,
        "blue_sampling_mode": "uniform",
    }
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    assert len(candidates) <= 100
    assert all(1 <= c[1] <= 16 for c in candidates)


def test_candidate_attempt_multiplier_changes_behavior(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, {"history": sample_history})

    options_low = {
        "history": sample_history,
        "seed": 42,
        "candidate_count": 200000,
        "candidate_attempt_multiplier": 1,
    }
    rng = random.Random(42)
    candidates_low = strategy._generate_candidates(rng, red_probs, blue_probs, options_low)

    options_high = dict(options_low, candidate_attempt_multiplier=20)
    rng = random.Random(42)
    candidates_high = strategy._generate_candidates(rng, red_probs, blue_probs, options_high)

    # 低倍数下尝试次数不足，无法填满候选池；高倍数可以填满。
    assert len(candidates_low) < options_low["candidate_count"]
    assert len(candidates_high) == options_high["candidate_count"]
    assert len(candidates_high) > len(candidates_low)


def test_new_schema_parameters_exposed():
    strategy = SSQConsensusConstraintStrategy()
    schema = strategy.get_config_schema()
    for key in (
        "candidate_attempt_multiplier",
        "high_number_threshold",
        "score_log_epsilon",
        "relaxation_sum_iterations",
        "relaxation_sum_floor",
        "relaxation_sum_cap",
        "relaxation_sum_expand_min",
        "relaxation_sum_expand_max",
        "relaxation_odd_deltas",
        "sample_top_pool_fraction",
        "stats_red_pool_size_hot_cold",
        "stats_red_pool_size_mixed_half",
        "stats_blue_pool_size",
        "smart_hot_cold_smoothing_floor",
        "smart_hot_cold_smoothing_offset",
        "hot_cold_red_pool_size",
        "hot_cold_red_pool_size_mixed_half",
        "hot_cold_blue_pool_size",
        "missing_blue_pool_cap",
        "missing_blue_pool_formula_offset",
        "missing_blue_pool_formula_divisor",
    ):
        assert key in schema, f"{key} 未在 schema 中暴露"
        assert "default" in schema[key]

    # SSQ 规则固定值不应暴露为用户可调参数
    assert "red_pool_size" not in schema
    assert "blue_pool_size" not in schema
    assert "red_pick_count" not in schema


def test_predict_date_wired_to_periodic(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    records = [r for r in sample_history]
    # 明确指定 predict_date 不应报错，且概率向量维度正确
    prob = strategy._periodic_probability(records, {"predict_date": "2025-06-15"})
    assert len(prob) == SSQ.group("red").size
    assert abs(prob.sum() - 1.0) < 1e-10


def test_hard_constraints_use_high_number_threshold(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "odd_even_enabled": False,
        "balanced_enabled": True,
        "sum_min": 21,
        "sum_max": 183,
        "target_high": 6,
        "high_number_threshold": 33,
        "exclude_include_enabled": False,
    }
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    filtered = strategy._apply_hard_constraints(candidates, records, options)
    # high_number_threshold=33 时只有 33 算大号，6 个红球都 >=33 不可能
    assert len(filtered) == 0


def test_blue_sampling_mode_weighted(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "candidate_count": 100,
        "blue_sampling_mode": "weighted",
    }
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    assert len(candidates) <= 100
    assert all(1 <= c[1] <= 16 for c in candidates)
