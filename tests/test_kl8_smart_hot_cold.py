"""快乐8智能冷热号策略（数学稳定化版）回归测试."""

from collections import Counter
from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import KL8
from caipiao.core.strategies.lotteries.kl8.smart_hot_cold import (
    DEFAULT_PICK_COUNT,
    KL8SmartHotColdStrategy,
)
from caipiao.core.strategies.lotteries.kl8.stability import (
    DRAW_PER_NUMBER_PROB,
    MAIN_POOL,
    _chi_square_critical,
    chi_square_uniform_test,
    frequency_counts,
    geometric_missing_zscore,
    raw_missing_periods,
    stable_frequency,
    weighted_sample_without_replacement,
)
from caipiao.data.models import DrawRecord


def make_history(n=120, seed=1):
    import random as _r

    rng = _r.Random(seed)
    return [
        DrawRecord(
            f"2024{i:04d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="kl8",
            groups={"main": sorted(rng.sample(range(1, 81), 20))},
        )
        for i in range(n)
    ]


def _biased_history(n=80):
    """生成有偏历史：每期 15 个号取自热池 1-20，5 个取自 21-80。"""
    import random as _r

    rng = _r.Random(0)
    return [
        DrawRecord(
            f"2024{i:04d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="kl8",
            groups={
                "main": sorted(rng.sample(range(1, 21), 15))
                + sorted(rng.sample(range(21, 81), 5))
            },
        )
        for i in range(n)
    ]


def _max_number_concentration(tickets):
    counts = Counter()
    for t in tickets:
        counts.update(t.groups["main"])
    total = sum(counts.values())
    return max(counts.values()) / total if total else 0.0


# --------------------------------------------------------------------------- #
# 默认选四
# --------------------------------------------------------------------------- #
def test_default_pick_count_is_four():
    schema = KL8SmartHotColdStrategy().get_config_schema()
    assert schema["pick_count"]["default"] == 4
    assert schema["pick_count"]["choices"] == list(range(1, 11))


def test_default_pick_count_constant():
    assert DEFAULT_PICK_COUNT == 4


def test_generate_without_pick_count_uses_default_four():
    strategy = KL8SmartHotColdStrategy()
    history = make_history(120)
    ticket = strategy.generate(count=1, options={"history": history, "lookback": 100})[0]
    assert len(ticket.groups["main"]) == 4


def test_pick_count_one_to_ten_all_valid():
    strategy = KL8SmartHotColdStrategy()
    history = make_history(120)
    for pick in range(1, 11):
        ticket = strategy.generate(
            count=1,
            options={"history": history, "lookback": 100, "seed": 3, "pick_count": pick},
        )[0]
        assert len(ticket.groups["main"]) == pick, pick
        assert len(set(ticket.groups["main"])) == pick, pick
        assert all(1 <= n <= 80 for n in ticket.groups["main"])


# --------------------------------------------------------------------------- #
# 可复现性
# --------------------------------------------------------------------------- #
def test_seed_reproducible():
    strategy = KL8SmartHotColdStrategy()
    history = make_history(120)
    opts = {"history": history, "lookback": 100, "seed": 42}
    t1 = strategy.generate(count=1, options=opts)[0].groups["main"]
    t2 = strategy.generate(count=1, options=opts)[0].groups["main"]
    assert t1 == t2


def test_deterministic_without_user_seed():
    """无用户 seed 时基于历史内容派生确定性 seed，保证可复现。"""
    strategy = KL8SmartHotColdStrategy()
    history = make_history(120)
    opts = {"history": history, "lookback": 100}
    t1 = strategy.generate(count=1, options=opts)[0].groups["main"]
    t2 = strategy.generate(count=1, options=opts)[0].groups["main"]
    assert t1 == t2


def test_different_history_different_output():
    strategy = KL8SmartHotColdStrategy()
    t1 = strategy.generate(count=1, options={"history": make_history(120, seed=1)})[0].groups["main"]
    t2 = strategy.generate(count=1, options={"history": make_history(120, seed=2)})[0].groups["main"]
    assert t1 != t2


# --------------------------------------------------------------------------- #
# χ² 均匀性守卫
# --------------------------------------------------------------------------- #
def test_chi_square_guard_random_history_is_uniform():
    """随机历史在统计噪声范围内，χ² 守卫应判定为均匀（冷热信号弱）。"""
    strategy = KL8SmartHotColdStrategy()
    history = make_history(120)
    ticket = strategy.generate(count=1, options={"history": history, "lookback": 100})[0]
    assert ticket.details["is_uniform"] is True
    assert ticket.details["chi_square"] < _chi_square_critical(79)


def test_chi_square_guard_biased_history_is_not_uniform():
    """有偏历史显著偏离均匀，χ² 守卫应触发（冷热信号有效）。"""
    strategy = KL8SmartHotColdStrategy()
    history = _biased_history(80)
    ticket = strategy.generate(count=1, options={"history": history, "lookback": 80})[0]
    assert ticket.details["is_uniform"] is False
    assert ticket.details["chi_square"] > _chi_square_critical(79)


def test_basis_mentions_random_disclaimer():
    strategy = KL8SmartHotColdStrategy()
    history = make_history(120)
    ticket = strategy.generate(count=1, options={"history": history, "lookback": 100})[0]
    assert "不能预测独立随机开奖" in ticket.basis


# --------------------------------------------------------------------------- #
# 温度参数影响集中度
# --------------------------------------------------------------------------- #
def test_temperature_changes_concentration():
    """低温度应比高温度更集中在高频号码上。"""
    strategy = KL8SmartHotColdStrategy()
    history = _biased_history(80)
    low_t = strategy.generate(
        count=60, options={"history": history, "lookback": 80, "temperature": 5}
    )
    high_t = strategy.generate(
        count=60, options={"history": history, "lookback": 80, "temperature": 50}
    )
    assert _max_number_concentration(low_t) > _max_number_concentration(high_t)


def test_high_temperature_approaches_uniform():
    """极高温度下分布应接近均匀（纯随机）。"""
    strategy = KL8SmartHotColdStrategy()
    history = _biased_history(80)
    tickets = strategy.generate(
        count=200, options={"history": history, "lookback": 80, "temperature": 50}
    )
    # 在接近均匀分布下，每个号码被选中频率应接近 pick/80
    counts = Counter()
    for t in tickets:
        counts.update(t.groups["main"])
    # 期望每个号码出现 200*4/80 = 10 次；最热号不应超过期望的 3 倍
    assert max(counts.values()) < 10 * 3


# --------------------------------------------------------------------------- #
# 数学工具单元测试
# --------------------------------------------------------------------------- #
def test_geometric_missing_zscore_expected_value():
    """遗漏=期望(3)时 z=0；遗漏=10时 z>1.96（95%显著偏冷）。"""
    full = {n: 3 for n in MAIN_POOL}
    full[1] = 10
    z = geometric_missing_zscore(full)
    assert round(z[2], 6) == 0.0  # missing=3 → z=0
    assert z[1] > 1.96  # missing=10 → 显著偏冷


def test_chi_square_critical_matches_known_values():
    """Wilson-Hilferty 近似与已知 χ² 分位数吻合。"""
    assert abs(_chi_square_critical(9) - 16.92) < 0.1   # df=9, 5%
    assert abs(_chi_square_critical(79) - 100.75) < 0.2  # df=79, 5%


def test_chi_square_uniform_test_uniform_input():
    counts = [25] * 80  # 完全均匀
    chi2, is_uniform = chi_square_uniform_test(counts)
    assert chi2 == 0.0
    assert is_uniform is True


def test_stable_frequency_sums_to_one():
    history = make_history(100)
    prob = stable_frequency(history, 100)
    assert len(prob) == 80
    assert abs(sum(prob.values()) - 1.0) < 1e-9


def test_stable_frequency_under_null_near_uniform():
    """随机历史下平滑频率应接近 1/80。"""
    history = make_history(200)
    prob = stable_frequency(history, 200)
    avg = sum(prob.values()) / 80
    assert abs(avg - 1 / 80) < 1e-6
    # 每个号码频率偏离 1/80 不应超过 50%
    for n in MAIN_POOL:
        assert abs(prob[n] - 1 / 80) < 0.5 / 80


def test_frequency_counts_total_equals_draws_times_twenty():
    history = make_history(50)
    counts = frequency_counts(history, 50)
    assert sum(counts.values()) == 50 * 20


def test_weighted_sample_without_replacement_distinct():
    import random as _r

    rng = _r.Random(0)
    values = list(range(1, 81))
    weights = [1.0] * 80
    sample = weighted_sample_without_replacement(rng, values, weights, 10)
    assert len(sample) == 10
    assert len(set(sample)) == 10
    assert all(1 <= n <= 80 for n in sample)


def test_weighted_sample_respects_heavy_weight():
    """极高权重号码应几乎总是被选中。"""
    import random as _r

    rng = _r.Random(0)
    values = list(range(1, 81))
    weights = [0.001] * 80
    weights[0] = 1000.0  # 号码 1 几乎必中
    hits = sum(
        1 in weighted_sample_without_replacement(rng, values, weights, 4)
        for _ in range(100)
    )
    assert hits >= 95


# --------------------------------------------------------------------------- #
# 边界与异常
# --------------------------------------------------------------------------- #
def test_insufficient_history_raises():
    strategy = KL8SmartHotColdStrategy()
    with pytest.raises(ValueError):
        strategy.generate(count=1, options={"history": make_history(19)})


def test_lookback_window_smaller_than_history():
    strategy = KL8SmartHotColdStrategy()
    history = make_history(120)
    tickets = strategy.generate(count=3, options={"history": history, "lookback": 30, "seed": 1})
    assert len(tickets) == 3
    for t in tickets:
        assert len(t.groups["main"]) == 4


def test_all_numbers_in_range_and_dedup():
    strategy = KL8SmartHotColdStrategy()
    history = make_history(120)
    tickets = strategy.generate(
        count=20, options={"history": history, "lookback": 100, "seed": 5}
    )
    assert len(tickets) == 20
    seen = set()
    for t in tickets:
        nums = tuple(t.groups["main"])
        assert nums not in seen  # 去重生效
        seen.add(nums)
        assert all(1 <= n <= 80 for n in nums)


def test_probability_distribution_valid():
    strategy = KL8SmartHotColdStrategy()
    history = make_history(120)
    ticket = strategy.generate(count=1, options={"history": history, "lookback": 100})[0]
    probs = ticket.details["probabilities"]
    assert len(probs) == 80
    assert abs(sum(probs) - 1.0) < 1e-6
    assert all(p > 0 for p in probs)
