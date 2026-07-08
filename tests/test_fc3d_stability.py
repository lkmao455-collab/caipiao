"""Tests for caipiao.core.strategies.lotteries.fc3d.stability."""

import random
from datetime import datetime, timedelta

import pytest

from caipiao.core.strategies.lotteries.fc3d.stability import (
    deterministic_seed,
    sample_weighted,
    stable_frequency,
    stable_missing,
    stable_scores,
)
from caipiao.data.models import DrawRecord


def _records():
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(30)
    ]


def test_deterministic_seed_returns_user_seed():
    history = _records()
    assert deterministic_seed({"seed": 42}, history) == 42


def test_deterministic_seed_is_deterministic():
    history = _records()
    s1 = deterministic_seed({}, history, strategy_id="smart_hot_cold_3d")
    s2 = deterministic_seed({}, history, strategy_id="smart_hot_cold_3d")
    assert s1 == s2


def test_deterministic_seed_differs_by_strategy():
    history = _records()
    s1 = deterministic_seed({}, history, strategy_id="a")
    s2 = deterministic_seed({}, history, strategy_id="b")
    assert s1 != s2


def test_stable_frequency_sums_to_one():
    history = _records()
    freq = stable_frequency(history, lookback=10)
    for pos in range(3):
        assert sum(freq[pos].values()) == pytest.approx(1.0)
        assert all(freq[pos][d] > 0 for d in range(10))


def test_stable_missing_values_in_zero_one():
    history = _records()
    missing = stable_missing(history, lookback=10, cap=5)
    for pos in range(3):
        assert all(0 <= v <= 1 for v in missing[pos].values())


def test_stable_missing_cap_works():
    history = _records()
    missing = stable_missing(history, lookback=10, cap=3)
    for pos in range(3):
        assert all(v <= 1.0 for v in missing[pos].values())


def test_stable_scores_returns_distribution():
    hot = {d: d / 10.0 for d in range(10)}
    cold = {d: 1.0 - d / 10.0 for d in range(10)}
    probs = stable_scores(hot, cold, hot_weight=60, cold_weight=40)
    assert len(probs) == 10
    assert sum(probs) == pytest.approx(1.0)
    assert all(p >= 0 for p in probs)


def test_stable_scores_temperature_changes_concentration():
    hot = {d: 1.0 if d == 0 else 0.0 for d in range(10)}
    cold = {d: 0.0 for d in range(10)}
    low_t = stable_scores(hot, cold, hot_weight=1, cold_weight=0, temperature=0.1)
    high_t = stable_scores(hot, cold, hot_weight=1, cold_weight=0, temperature=2.0)
    assert low_t[0] > high_t[0]


def test_sample_weighted_basic():
    rng = random.Random(1)
    values = list(range(10))
    probs = [0.0] * 10
    probs[5] = 1.0
    assert sample_weighted(rng, values, probs) == 5


def test_sample_weighted_uniform_fallback():
    rng = random.Random(1)
    values = list(range(10))
    probs = [0.0] * 10
    result = sample_weighted(rng, values, probs)
    assert result in values
