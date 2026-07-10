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
