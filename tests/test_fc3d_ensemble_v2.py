"""福彩3D三策略融合策略回归测试."""

from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from caipiao.core.strategies.lotteries.fc3d.ensemble import FC3DStrategyFusionStrategy
from caipiao.data.models import DrawRecord


def make_record(nums: list[int]) -> DrawRecord:
    """构造一条 3D 历史记录。"""
    return DrawRecord(
        issue="",
        draw_date=datetime.now(timezone.utc),
        profile="3d",
        groups={"pos": list(nums)},
    )


def test_zscore_list_uses_population_std():
    """N10: _zscore_list 应使用总体标准差。"""
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    # 总体标准差 sqrt(((1-3)^2 + ... + (5-3)^2)/5) = sqrt(2)
    expected = [(v - 3.0) / (2.0 ** 0.5) for v in vals]
    result = FC3DStrategyFusionStrategy._zscore_list(vals)
    for r, e in zip(result, expected):
        assert abs(r - e) < 1e-9


def test_balanced_respects_z_threshold():
    """N1: z_threshold 应影响 balanced 子策略的奇偶/大小门控。"""
    strategy = FC3DStrategyFusionStrategy()
    # 构造数据：pos0 强烈偏奇数（chi2>16.92，能通过χ²守卫），
    # pos1/pos2 均匀，整体奇偶比例处于 z≈2.45（在 1.96 与 3.0 之间）。
    records = []
    for i in range(200):
        pos0 = [1, 3, 5, 7, 9][i % 5] if i < 130 else [0, 2, 4, 6, 8][i % 5]
        pos1 = random.randint(0, 9)
        pos2 = random.randint(0, 9)
        records.append(make_record([pos0, pos1, pos2]))

    def pos0_odd_prob(options):
        t = strategy.generate(count=1, options=options)[0]
        p = t.details["pos_probabilities"][0]
        return sum(p[d] for d in [1, 3, 5, 7, 9])

    base = {
        "history": records,
        "lookback": 200,
        "balanced_weight": 100,
        "hot_cold_weight": 0,
        "missing_weight": 0,
        "adaptive": False,
        "temperature": 10,
        "dedup": False,
        "seed": 1,
    }
    # z=1.96 时 parity 信号应注入；z=3.0 时被门控。
    low_threshold = pos0_odd_prob({**base, "z_threshold": 196})
    high_threshold = pos0_odd_prob({**base, "z_threshold": 300})
    assert low_threshold > high_threshold, (
        f"z_threshold=1.96 should let parity signal through "
        f"(odd_prob={low_threshold}), z_threshold=3.0 should block it "
        f"(odd_prob={high_threshold})"
    )


def test_per_position_parity_signal():
    """N5: 奇偶/大小信号应基于逐位比例，而非三位合并的整体比例。"""
    strategy = FC3DStrategyFusionStrategy()
    records = []
    for i in range(200):
        pos0 = random.choice([1, 3, 5, 7, 9]) if random.random() < 0.7 else random.randint(0, 9)
        pos1 = random.choice([0, 2, 4, 6, 8]) if random.random() < 0.7 else random.randint(0, 9)
        pos2 = random.randint(0, 9)
        records.append(make_record([pos0, pos1, pos2]))

    t = strategy.generate(count=1, options={
        "history": records,
        "lookback": 200,
        "balanced_weight": 100,
        "hot_cold_weight": 0,
        "missing_weight": 0,
        "adaptive": False,
        "temperature": 10,
        "dedup": False,
        "seed": 1,
    })[0]

    for pos, expected_odd_high in [(0, True), (1, False)]:
        p = t.details["pos_probabilities"][pos]
        odd = sum(p[d] for d in [1, 3, 5, 7, 9])
        if expected_odd_high:
            assert odd > 0.5, f"pos{pos} should favor odd"
        else:
            assert odd < 0.5, f"pos{pos} should favor even"


def test_temperature_affects_substrategies():
    """N2: 温度应透传给子策略并改变集中度。"""
    strategy = FC3DStrategyFusionStrategy()
    records = []
    for i in range(200):
        nums = [4 if random.random() < 0.6 else random.randint(0, 9) for _ in range(3)]
        records.append(make_record(nums))

    def max_prob(options):
        t = strategy.generate(count=1, options=options)[0]
        return max(t.details["pos_probabilities"][0])

    base = {
        "history": records,
        "lookback": 200,
        "balanced_weight": 0,
        "hot_cold_weight": 100,
        "missing_weight": 0,
        "adaptive": False,
        "dedup": False,
        "seed": 1,
    }
    low_t = max_prob({**base, "temperature": 1})
    mid_t = max_prob({**base, "temperature": 10})
    high_t = max_prob({**base, "temperature": 50})
    assert low_t > mid_t > high_t, (
        f"lower temperature should concentrate probability: "
        f"T=1={low_t}, T=10={mid_t}, T=50={high_t}"
    )


def test_adaptive_boosts_missing_when_cold_signal():
    """N6: 自适应权重应在存在显著冷号时提升 missing 权重。"""
    strategy = FC3DStrategyFusionStrategy()
    # 构造历史：数字 0 在各位置长期未出现
    records = [make_record([1, 2, 3]) for _ in range(200)]

    t = strategy.generate(count=1, options={
        "history": records,
        "lookback": 200,
        "balanced_weight": 33,
        "hot_cold_weight": 33,
        "missing_weight": 34,
        "adaptive": True,
        "temperature": 10,
        "dedup": False,
        "seed": 1,
    })[0]

    # 至少有一位 missing 权重被提升
    boosted = any(w["missing"] > 0.34 for w in t.details["pos_weights"])
    assert boosted, "adaptive should boost missing weight when cold signal exists"


def test_dedup_preserves_permutation_probability():
    """N3: 去重采样应保留组内各排列的相对概率。"""
    from caipiao.core.strategies.lotteries.fc3d._base import (
        _weighted_sample_without_replacement,
    )

    pos_probs = [[0.05] * 10, [0.05] * 10, [0.05] * 10]
    pos_probs[0][1] = 0.55
    pos_probs[1][2] = 0.55
    pos_probs[2][3] = 0.55
    rng = random.Random(1)
    results = _weighted_sample_without_replacement(pos_probs, count=220, rng=rng)
    count_123 = sum(1 for r in results if r == [1, 2, 3])
    count_321 = sum(1 for r in results if r == [3, 2, 1])
    assert count_123 > count_321 * 2, (
        f"123 should be much more likely than 321: 123={count_123}, 321={count_321}"
    )


def test_shape_correction_influences_output():
    """N4: 形态修正应在去重模式下影响输出形态分布。"""
    strategy = FC3DStrategyFusionStrategy()
    # 构造历史：豹子号远多于理论 1%
    records = [make_record([5, 5, 5]) for _ in range(200)]

    t = strategy.generate(count=1, options={
        "history": records,
        "lookback": 200,
        "balanced_weight": 33,
        "hot_cold_weight": 33,
        "missing_weight": 34,
        "adaptive": False,
        "temperature": 10,
        "dedup": True,
        "seed": 1,
    })[0]

    # basis 应包含形态修正权重
    assert "形态修正权重" in t.basis
    assert t.details["shape_weights"] is not None
    # 历史豹子号过多，修正权重应小于 1（抑制豹子）
    assert t.details["shape_weights"]["leopard"] < 1.0


def test_details_has_avg_and_pos_weights():
    """N7: details 应同时提供 avg_weights 与 pos_weights，并保留 weights 别名。"""
    strategy = FC3DStrategyFusionStrategy()
    t = strategy.generate(count=1, options={
        "history": [make_record([1, 2, 3]) for _ in range(50)],
        "lookback": 50,
        "balanced_weight": 33,
        "hot_cold_weight": 33,
        "missing_weight": 34,
        "adaptive": True,
        "temperature": 10,
        "dedup": False,
        "seed": 1,
    })[0]
    assert "avg_weights" in t.details
    assert "pos_weights" in t.details
    assert "weights" in t.details  # 兼容别名
    assert len(t.details["pos_weights"]) == 3
    assert t.details["avg_weights"] == t.details["weights"]


def test_count_over_220_raises():
    """N9: 去重模式下请求超过 220 组应抛出 ValueError。"""
    strategy = FC3DStrategyFusionStrategy()
    with pytest.raises(ValueError):
        strategy.generate(count=300, options={
            "history": [make_record([1, 2, 3]) for _ in range(50)],
            "lookback": 50,
            "dedup": True,
        })


def test_disabled_strategies_respected():
    """N9: 用户禁用 balanced/hot_cold 时权重应为 0。"""
    strategy = FC3DStrategyFusionStrategy()
    t = strategy.generate(count=1, options={
        "history": [make_record([1, 2, 3]) for _ in range(50)],
        "lookback": 50,
        "balanced_weight": 0,
        "hot_cold_weight": 0,
        "missing_weight": 100,
        "adaptive": True,
        "dedup": False,
        "seed": 1,
    })[0]
    for w in t.details["pos_weights"]:
        assert w["balanced"] == 0.0
        assert w["hot_cold"] == 0.0


def test_uniform_data_outputs_near_uniform():
    """N9: 均匀数据上输出不应过度集中。"""
    strategy = FC3DStrategyFusionStrategy()
    random.seed(123)
    records = [make_record([random.randint(0, 9) for _ in range(3)]) for _ in range(200)]
    t = strategy.generate(count=1, options={
        "history": records,
        "lookback": 200,
        "balanced_weight": 33,
        "hot_cold_weight": 33,
        "missing_weight": 34,
        "adaptive": False,
        "temperature": 10,
        "dedup": False,
        "seed": 1,
    })[0]
    for pos in range(3):
        p = t.details["pos_probabilities"][pos]
        assert max(p) < 0.25, f"pos{pos} too concentrated on uniform data"
