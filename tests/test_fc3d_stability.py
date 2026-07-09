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


# --------------------------------------------------------------------------- #
# 新增数学增强工具函数测试
# --------------------------------------------------------------------------- #

from caipiao.core.strategies.lotteries.fc3d.stability import (
    chi_square_uniform_test,
    geometric_missing_zscore,
    raw_missing_periods,
)


def test_raw_missing_periods_returns_int():
    history = _records()
    raw = raw_missing_periods(history, lookback=10)
    for pos in range(3):
        for d in range(10):
            assert isinstance(raw[pos][d], int)
            assert raw[pos][d] >= 0


def test_raw_missing_periods_last_seen_is_zero():
    """最近一期出现的数字，遗漏期数应为 0。"""
    history = _records()
    raw = raw_missing_periods(history, lookback=5)
    last = history[-1]
    for pos in range(3):
        digit = last.groups["pos"][pos]
        assert raw[pos][digit] == 0


def test_geometric_missing_zscore_expected_near_zero():
    """遗漏期数接近期望(9)时，z-score 接近 0。"""
    # 构造遗漏值恰好等于期望 9 的输入
    raw = {pos: {d: 9 for d in range(10)} for pos in range(3)}
    gz = geometric_missing_zscore(raw)
    for pos in range(3):
        for d in range(10):
            assert abs(gz[pos][d]) < 0.01  # z ≈ 0


def test_geometric_missing_zscore_high_missing_positive():
    """遗漏远超期望时，z-score 显著为正（偏冷）。"""
    raw = {0: {d: 30 for d in range(10)}}  # 遗漏=30，远超 E=9
    gz = geometric_missing_zscore(raw)
    assert gz[0][0] > 1.96  # 95% 置信偏冷


def test_geometric_missing_zscore_low_missing_negative():
    """遗漏远低于期望时，z-score 为负（不冷/偏热）。"""
    raw = {0: {d: 0 for d in range(10)}}  # 遗漏=0（最近出现）
    gz = geometric_missing_zscore(raw)
    assert gz[0][0] < 0


def test_chi_square_uniform_uniform_data():
    """均匀分布的数据不应拒绝均匀假设。"""
    counts = [10] * 10  # 完全均匀
    chi2, is_uniform = chi_square_uniform_test(counts)
    assert is_uniform is True
    assert chi2 < 1.0


def test_chi_square_uniform_biased_data():
    """严重偏离均匀的数据应拒绝均匀假设。"""
    counts = [50, 0, 0, 0, 0, 50, 0, 0, 0, 0]  # 极端偏离
    chi2, is_uniform = chi_square_uniform_test(counts)
    assert is_uniform is False
    assert chi2 > 16.92  # 超过 5% 临界值


def test_chi_square_uniform_empty_data():
    """空数据应返回均匀（无法拒绝）。"""
    chi2, is_uniform = chi_square_uniform_test([0] * 10)
    assert is_uniform is True
    assert chi2 == 0.0


def test_stable_scores_zscore_more_concentrated_than_maxnorm():
    """z-score 标准化后，默认温度下的区分度应优于旧的 max 归一化。

    旧 max 归一化: combined 值域 ~[0.46, 0.64], softmax(T=1) -> max/min ~ 1.2x
    新 z-score:    logits 值域 ~[-2, +2], softmax(T=1) -> max/min ~ 2x+
    """
    hot = {d: d / 10.0 for d in range(10)}
    cold = {d: 1.0 - d / 10.0 for d in range(10)}
    probs = stable_scores(hot, cold, hot_weight=60, cold_weight=40, temperature=1.0)
    ratio = max(probs) / min(probs)
    assert ratio > 1.5  # z-score 改进后应明显优于旧的 1.2x
