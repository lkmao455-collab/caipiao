"""测试文件 B：将下列核心策略模块的行覆盖率提升到 100%.

覆盖模块（不含 ui / ml 层）：
- caipiao/core/strategies/lotteries/fc3d/{balanced,stability,smart_hot_cold}.py
- caipiao/core/strategies/lotteries/dlt/{balanced,smart_hot_cold}.py
- caipiao/core/strategies/lotteries/ssq/{balanced,smart_hot_cold,stability}.py
- caipiao/core/strategies/{hybrid_strategy,lstm_strategy}.py
- caipiao/core/strategies/common/ml.py
- caipiao/core/strategies/stability_validator.py

对重训练（LSTM / XGBoost）相关代码以 mock 替换，保持测试快速且确定性，
但仍执行源码真实的分支路径。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from caipiao.core.strategies.common import ml as common_ml
from caipiao.core.strategies.lotteries.dlt import (
    balanced as dlt_balanced,
    smart_hot_cold as dlt_shc,
)
from caipiao.core.strategies.lotteries.dlt import _base as dlt_base
from caipiao.core.profile import LotteryProfile, NumberGroup, DLT
from caipiao.core.strategies.lotteries.fc3d import (
    balanced as fc3d_balanced,
    smart_hot_cold as fc3d_shc,
    stability as fc3d_stability,
)
from caipiao.core.strategies.lotteries.ssq import (
    balanced as ssq_balanced,
    smart_hot_cold as ssq_shc,
    stability as ssq_stability,
)
from caipiao.core.strategies import hybrid_strategy, lstm_strategy, stability_validator
from caipiao.data.models import DrawRecord
from caipiao.core.backtest_data import (
    BatchBacktestResult,
    RoundBacktestContext,
    RoundResult,
    RoundTask,
)


# --------------------------------------------------------------------------- #
# 测试数据构造助手
# --------------------------------------------------------------------------- #
def _fc3d_records(n: int, mode: str = "uniform") -> list[DrawRecord]:
    """构造 fc3d 开奖记录（groups={'pos':[a,b,c]}）。"""
    recs: list[DrawRecord] = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        if mode == "uniform":
            pos = [(i + p) % 10 for p in range(3)]
        elif mode == "skew0":
            # 第 0 位恒为 0 -> 该位显著偏离均匀
            pos = [0, i % 10, (i + 1) % 10]
        else:
            pos = [i % 10, (i + 1) % 10, (i + 2) % 10]
        recs.append(
            DrawRecord(
                issue=f"3d{i:04d}",
                draw_date=base + timedelta(days=i),
                profile="3d",
                groups={"pos": pos},
            )
        )
    return recs


def _dlt_records(n: int) -> list[DrawRecord]:
    recs: list[DrawRecord] = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        front = [(i * 5 + j) % 35 + 1 for j in range(5)]
        back = [(i % 12) + 1, ((i + 1) % 12) + 1]
        recs.append(
            DrawRecord(
                issue=f"dlt{i:04d}",
                draw_date=base + timedelta(days=i),
                profile="dlt",
                groups={"front": front, "back": back},
            )
        )
    return recs


def _ssq_uniform_records(n: int = 33) -> list[DrawRecord]:
    """红球/蓝球均接近均匀（用于 χ² 通过均匀检验）。"""
    recs: list[DrawRecord] = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        red = [((i * 6 + j) % 33) + 1 for j in range(6)]
        blue = (i % 16) + 1
        recs.append(
            DrawRecord(
                issue=f"ssq{i:04d}",
                draw_date=base + timedelta(days=i),
                profile="ssq",
                groups={"red": red, "blue": [blue]},
            )
        )
    return recs


def _ssq_skew_red_records(n: int = 33) -> list[DrawRecord]:
    """红球恒为 1-6（显著偏离均匀），蓝球均匀。"""
    recs: list[DrawRecord] = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        blue = (i % 16) + 1
        recs.append(
            DrawRecord(
                issue=f"ssq{i:04d}",
                draw_date=base + timedelta(days=i),
                profile="ssq",
                groups={"red": [1, 2, 3, 4, 5, 6], "blue": [blue]},
            )
        )
    return recs


def _ssq_skew_blue_records(n: int = 33) -> list[DrawRecord]:
    """红球均匀，蓝球恒为 1（显著偏离均匀）。"""
    recs: list[DrawRecord] = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        red = [((i * 6 + j) % 33) + 1 for j in range(6)]
        recs.append(
            DrawRecord(
                issue=f"ssq{i:04d}",
                draw_date=base + timedelta(days=i),
                profile="ssq",
                groups={"red": red, "blue": [1]},
            )
        )
    return recs


def _ssq_single_record() -> list[DrawRecord]:
    return [
        DrawRecord(
            issue="ssq0001",
            draw_date=datetime(2024, 1, 1),
            profile="ssq",
            groups={"red": [1, 2, 3, 4, 5, 6], "blue": [1]},
        )
    ]


def _fc3d_records_constant(n: int = 40, digit: int = 0) -> list[DrawRecord]:
    """构造 fc3d 开奖记录，每位恒为同一数字（显著偏离均匀，且最优候选确定）。"""
    recs: list[DrawRecord] = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        recs.append(
            DrawRecord(
                issue=f"3d{i:04d}",
                draw_date=base + timedelta(days=i),
                profile="3d",
                groups={"pos": [digit, digit, digit]},
            )
        )
    return recs


def _make_dlt_variant(
    front_allow_repeat: bool = False,
    front_positional: bool = False,
    back_positional: bool = False,
    front_lo: int = 1,
    front_hi: int = 35,
    front_count: int = 5,
    back_lo: int = 1,
    back_hi: int = 12,
    back_count: int = 2,
) -> LotteryProfile:
    """构造一个 DLT 变体档案，用于强制覆盖 allow_repeat / positional 等分支。"""
    front = NumberGroup(
        "front", "前区", front_lo, front_hi, front_count,
        color="#D32F2F", is_primary=True,
        allow_repeat=front_allow_repeat, positional=front_positional,
    )
    back = NumberGroup(
        "back", "后区", back_lo, back_hi, back_count,
        color="#1976D2", positional=back_positional,
    )
    return LotteryProfile(
        key="dlt", name="超级大乐透", groups=(front, back),
        data_url=DLT.data_url, parser_key="dlt",
        draw_weekdays=DLT.draw_weekdays, storage_file=DLT.storage_file,
        model_prefix="dlt", category=DLT.category,
    )


def _patch_dlt_profile(monkeypatch, variant: LotteryProfile) -> None:
    """把 dlt 策略各模块的模块级 PROFILE 都替换为变体（保证 _base 与策略类一致）。"""
    monkeypatch.setattr(dlt_base, "PROFILE", variant)
    monkeypatch.setattr(dlt_balanced, "PROFILE", variant)
    monkeypatch.setattr(dlt_shc, "PROFILE", variant)


# =========================================================================== #
# fc3d/stability.py —— 纯函数，直接测试
# =========================================================================== #
class TestFC3DStabilityFunctions:
    def test_history_content_hash_and_seed(self):
        recs = _fc3d_records(10)
        h1 = fc3d_stability._history_content_hash(recs)
        assert isinstance(h1, str) and len(h1) == 16
        # 确定性 seed：无 seed 时基于历史派生
        s1 = fc3d_stability.deterministic_seed({}, recs, 100, "balanced_3d")
        s2 = fc3d_stability.deterministic_seed({}, recs, 100, "balanced_3d")
        assert s1 == s2
        # 显式 seed 优先
        assert fc3d_stability.deterministic_seed({"seed": 7}, recs, 100, "x") == 7

    def test_stable_frequency(self):
        recs = _fc3d_records(20)
        freq = fc3d_stability.stable_frequency(recs, 20, smoothing=2.0)
        assert set(freq.keys()) == {0, 1, 2}
        # 每位置概率和为 1
        for pos in freq:
            assert abs(sum(freq[pos].values()) - 1.0) < 1e-9

    def test_stable_missing_default_and_cap(self):
        recs = _fc3d_records(20)
        m = fc3d_stability.stable_missing(recs, 20)
        assert set(m.keys()) == {0, 1, 2}
        # 自定义 cap
        m2 = fc3d_stability.stable_missing(recs, 20, cap=5)
        assert all(0.0 <= v <= 1.0 for pos in m2 for v in m2[pos].values())
        # 空记录 -> effective_cap=1
        m3 = fc3d_stability.stable_missing([], None)
        assert set(m3.keys()) == {0, 1, 2}

    def test_zscore_normalize_branches(self):
        # 正常（键须为完整 DIGIT_POOL）
        out = fc3d_stability._zscore_normalize({d: float(d) for d in range(10)})
        assert len(out) == 10
        # 全相等 -> std<1e-10 -> 全 0
        out2 = fc3d_stability._zscore_normalize({d: 5.0 for d in range(10)})
        assert all(v == 0.0 for v in out2.values())

    def test_softmax_scores(self):
        # 温度 <= 0 退化为 1.0
        r1 = fc3d_stability.softmax_scores([1.0, 2.0, 3.0], temperature=0)
        assert abs(sum(r1) - 1.0) < 1e-9
        r2 = fc3d_stability.softmax_scores([1.0, 2.0, 3.0], temperature=1.0)
        assert abs(sum(r2) - 1.0) < 1e-9

    def test_stable_scores_weight_sum_zero(self):
        hot = {d: 1.0 for d in range(10)}
        cold = {d: 1.0 for d in range(10)}
        out = fc3d_stability.stable_scores(hot, cold, 0, 0, 1.0)
        assert abs(sum(out) - 1.0) < 1e-9

    def test_sample_weighted(self):
        rng = random.Random(0)
        # 长度不一致 -> ValueError
        with pytest.raises(ValueError):
            fc3d_stability.sample_weighted(rng, [1, 2], [0.5])
        # 概率全 0 -> 退化均匀
        val = fc3d_stability.sample_weighted(rng, [1, 2, 3], [0.0, 0.0, 0.0])
        assert val in (1, 2, 3)
        # 正常加权
        val2 = fc3d_stability.sample_weighted(rng, [1, 2], [1.0, 0.0])
        assert val2 in (1, 2)

    def test_raw_missing_periods(self):
        recs = _fc3d_records(15)
        mp = fc3d_stability.raw_missing_periods(recs, 15)
        assert set(mp.keys()) == {0, 1, 2}

    def test_geometric_missing_zscore(self):
        mp = fc3d_stability.raw_missing_periods(_fc3d_records(15), 15)
        gz = fc3d_stability.geometric_missing_zscore(mp, p=0.1)
        assert set(gz.keys()) == {0, 1, 2}

    def test_chi_square_uniform_test(self):
        # 空计数
        assert fc3d_stability.chi_square_uniform_test([]) == (0.0, True)
        # 均匀
        counts = [5] * 10
        chi2, is_uniform = fc3d_stability.chi_square_uniform_test(counts)
        assert is_uniform is True and chi2 == 0.0
        # 显著偏离
        skewed = [50] + [0] * 9
        _, is_uniform2 = fc3d_stability.chi_square_uniform_test(skewed)
        assert is_uniform2 is False

    def test_zscore_normalize_single_pool(self, monkeypatch):
        # DIGIT_POOL 仅含 1 个键 -> len(vals) < 2 提前返回全 0（覆盖 line 104）
        monkeypatch.setattr(fc3d_stability, "DIGIT_POOL", (0,))
        out = fc3d_stability._zscore_normalize({0: 3.0})
        assert out == {0: 0.0}


# =========================================================================== #
# ssq/stability.py —— 纯函数，直接测试
# =========================================================================== #
class TestSSQStabilityFunctions:
    def test_slice_records(self):
        recs = _ssq_uniform_records(10)
        assert len(ssq_stability._slice_records(recs, 5)) == 5
        assert len(ssq_stability._slice_records(recs, None)) == 10
        assert len(ssq_stability._slice_records(recs, 100)) == 10

    def test_history_content_hash_and_seed(self):
        recs = _ssq_uniform_records(10)
        h = ssq_stability._history_content_hash(recs)
        assert isinstance(h, str) and len(h) == 16
        s1 = ssq_stability.deterministic_seed({}, recs, 100, "smart_hot_cold")
        s2 = ssq_stability.deterministic_seed({}, recs, 100, "smart_hot_cold")
        assert s1 == s2
        assert ssq_stability.deterministic_seed({"seed": 9}, recs, 100, "x") == 9

    def test_stable_frequency_and_blue(self):
        recs = _ssq_uniform_records(33)
        rf = ssq_stability.stable_frequency(recs, 33)
        assert set(rf.keys()) == set(range(1, 34))
        bf = ssq_stability.stable_blue_frequency(recs, 33)
        assert set(bf.keys()) == set(range(1, 17))

    def test_raw_missing_periods(self):
        recs = _ssq_uniform_records(33)
        rm = ssq_stability.raw_missing_periods(recs, 33)
        assert set(rm.keys()) == set(range(1, 34))
        rmb = ssq_stability.raw_blue_missing_periods(recs, 33)
        assert set(rmb.keys()) == set(range(1, 17))

    def test_geometric_zscore(self):
        red_mp = {n: float(n) for n in range(1, 34)}
        gz = ssq_stability.geometric_missing_zscore(red_mp, p=1 / 33)
        assert set(gz.keys()) == set(range(1, 34))
        blue_mp = {n: float(n) for n in range(1, 17)}
        bgz = ssq_stability.geometric_blue_missing_zscore(blue_mp, p=1 / 16)
        assert set(bgz.keys()) == set(range(1, 17))

    def test_geometric_zscore_zero_sigma(self):
        # p=1.0 -> sigma≈0 -> 提前返回全 0（覆盖 line 133 与 149）
        red_mp = {n: 5.0 for n in range(1, 34)}
        rz = ssq_stability.geometric_missing_zscore(red_mp, p=1.0)
        assert all(v == 0.0 for v in rz.values())
        blue_mp = {n: 5.0 for n in range(1, 17)}
        bz = ssq_stability.geometric_blue_missing_zscore(blue_mp, p=1.0)
        assert all(v == 0.0 for v in bz.values())

    def test_zscore_normalize(self):
        out = ssq_stability._zscore_normalize({n: float(n) for n in range(1, 34)})
        assert len(out) == 33
        out2 = ssq_stability._zscore_normalize({n: 3.0 for n in range(1, 34)})
        assert all(v == 0.0 for v in out2.values())
        out3 = ssq_stability._zscore_normalize({1: 1.0})
        assert out3 == {1: 0.0}

    def test_softmax_scores(self):
        assert abs(sum(ssq_stability.softmax_scores([1.0, 2.0], temperature=-1)) - 1.0) < 1e-9
        assert abs(sum(ssq_stability.softmax_scores([1.0, 2.0], temperature=1.0)) - 1.0) < 1e-9

    def test_stable_scores_and_blue(self):
        hot = {n: 1.0 for n in range(1, 34)}
        cold = {n: 1.0 for n in range(1, 34)}
        rs = ssq_stability.stable_scores(hot, cold, 0, 0, 1.0)
        assert abs(sum(rs) - 1.0) < 1e-9
        hot_b = {n: 1.0 for n in range(1, 17)}
        cold_b = {n: 1.0 for n in range(1, 17)}
        bs = ssq_stability.stable_blue_scores(hot_b, cold_b, 0, 0, 1.0)
        assert abs(sum(bs) - 1.0) < 1e-9
        # 正常权重
        rs2 = ssq_stability.stable_scores(hot, cold, 60, 40, 1.0)
        assert len(rs2) == 33

    def test_chi_square_uniform_test_branches(self):
        # 空
        assert ssq_stability.chi_square_uniform_test([]) == (0.0, True)
        # k=33 均匀 / 偏离
        assert ssq_stability.chi_square_uniform_test([2] * 33)[1] is True
        assert ssq_stability.chi_square_uniform_test([50] + [0] * 32)[1] is False
        # k=16 均匀 / 偏离
        assert ssq_stability.chi_square_uniform_test([2] * 16)[1] is True
        assert ssq_stability.chi_square_uniform_test([30] + [0] * 15)[1] is False
        # 其他长度 -> 近似临界（else 分支）
        assert ssq_stability.chi_square_uniform_test([10, 0, 0, 0, 0, 0, 0, 0, 0, 0])[1] is False

    def test_sample_weighted(self):
        rng = random.Random(0)
        with pytest.raises(ValueError):
            ssq_stability.sample_weighted(rng, [1, 2], [0.5])
        assert ssq_stability.sample_weighted(rng, [1, 2, 3], [0.0, 0.0, 0.0]) in (1, 2, 3)

    def test_weighted_sample_reds(self):
        probs = [1.0 / 33] * 33
        rng = random.Random(0)
        sel = ssq_stability.weighted_sample_reds(probs, 6, rng)
        assert len(sel) == 6
        # 含 0 概率（inf 分支）
        probs2 = [0.0] + [1.0 / 32] * 32
        sel2 = ssq_stability.weighted_sample_reds(probs2, 6, random.Random(1))
        assert len(sel2) == 6


# =========================================================================== #
# fc3d/balanced.py
# =========================================================================== #
class TestFC3DBalancedStrategy:
    def test_metadata_and_schema(self):
        s = fc3d_balanced.FC3DBalancedStrategy()
        assert s.metadata.id == "balanced_3d"
        assert s.get_config_schema()["lookback"]["default"] == 100

    def test_validate_options(self):
        s = fc3d_balanced.FC3DBalancedStrategy()
        with pytest.raises(ValueError, match="至少 30"):
            s.validate_options({"history": []})
        s.validate_options({"history": _fc3d_records(30)})

    def test_generate_uniform_dedup(self):
        s = fc3d_balanced.FC3DBalancedStrategy()
        recs = _fc3d_records(40, mode="uniform")
        tickets = s.generate(count=3, options={"history": recs, "dedup": True})
        assert len(tickets) == 3
        for t in tickets:
            assert len(t.groups["pos"]) == 3
            assert t.details["is_uniform"] == [True, True, True]

    def test_generate_uniform_no_dedup(self):
        s = fc3d_balanced.FC3DBalancedStrategy()
        recs = _fc3d_records(40, mode="uniform")
        tickets = s.generate(count=2, options={"history": recs, "dedup": False})
        assert len(tickets) == 2

    def test_generate_nonuniform_enumeration_with_seed(self):
        s = fc3d_balanced.FC3DBalancedStrategy()
        recs = _fc3d_records(40, mode="skew0")
        tickets = s.generate(
            count=2,
            options={"history": recs, "seed": 123, "use_enumeration": True},
        )
        assert len(tickets) == 2
        assert "随机种子：123" in tickets[0].basis
        # 非均匀分支：至少第 0 位偏离
        assert tickets[0].details["is_uniform"][0] is False

    def test_generate_nonuniform_no_enumeration(self):
        s = fc3d_balanced.FC3DBalancedStrategy()
        recs = _fc3d_records(40, mode="skew0")
        tickets = s.generate(
            count=2,
            options={"history": recs, "use_enumeration": False, "dedup": True},
        )
        assert len(tickets) == 2

    def test_generate_nonuniform_no_dedup(self):
        s = fc3d_balanced.FC3DBalancedStrategy()
        recs = _fc3d_records(40, mode="skew0")
        tickets = s.generate(
            count=2,
            options={"history": recs, "use_enumeration": False, "dedup": False},
        )
        assert len(tickets) == 2

    def test_generate_uniform_dedup_collision(self, monkeypatch):
        # 强制 uniform 分支去重时发生碰撞，覆盖 while 重采样的 body (line 259-260)
        state = {"calls": 0}

        def fake_randint(self, a, b):
            state["calls"] += 1
            sample_idx = (state["calls"] - 1) // 3
            return 0 if sample_idx < 2 else 1

        monkeypatch.setattr(random.Random, "randint", fake_randint)
        s = fc3d_balanced.FC3DBalancedStrategy()
        recs = _fc3d_records(40, mode="uniform")
        tickets = s.generate(count=2, options={"history": recs, "dedup": True})
        assert len(tickets) == 2

    def test_generate_nonuniform_dedup_collision_fallback(self, monkeypatch):
        # 强制 sample_one 恒返回 [0,0,0]：第 2 张票必然去重碰撞，
        # 覆盖非均匀分支的 continue (line 298) 与 best 为 None 的兜底采样 (line 307)
        monkeypatch.setattr(
            random.Random, "choices",
            lambda self, population, weights=None, k=1, **kw: [population[0]],
        )
        s = fc3d_balanced.FC3DBalancedStrategy()
        recs = _fc3d_records_constant(40, digit=0)
        tickets = s.generate(
            count=2,
            options={"history": recs, "dedup": True, "use_enumeration": False},
        )
        assert len(tickets) == 2


# =========================================================================== #
# fc3d/smart_hot_cold.py
# =========================================================================== #
class TestFC3DSmartHotColdStrategy:
    def test_metadata_and_schema(self):
        s = fc3d_shc.FC3DSmartHotColdStrategy()
        assert s.metadata.id == "smart_hot_cold_3d"
        assert "hot_weight" in s.get_config_schema()

    def test_validate_options(self):
        s = fc3d_shc.FC3DSmartHotColdStrategy()
        with pytest.raises(ValueError, match="至少 20"):
            s.validate_options({"history": []})
        s.validate_options({"history": _fc3d_records(20)})

    def test_generate_uniform_dedup(self):
        s = fc3d_shc.FC3DSmartHotColdStrategy()
        recs = _fc3d_records(40, mode="uniform")
        tickets = s.generate(count=3, options={"history": recs, "dedup": True})
        assert len(tickets) == 3
        assert tickets[0].details["is_uniform"] == [True, True, True]

    def test_generate_nonuniform_dedup(self):
        s = fc3d_shc.FC3DSmartHotColdStrategy()
        recs = _fc3d_records(40, mode="skew0")
        tickets = s.generate(count=3, options={"history": recs, "dedup": True})
        assert tickets[0].details["is_uniform"][0] is False

    def test_generate_with_seed_and_no_dedup(self):
        s = fc3d_shc.FC3DSmartHotColdStrategy()
        recs = _fc3d_records(40, mode="skew0")
        tickets = s.generate(
            count=3, options={"history": recs, "seed": 5, "dedup": False}
        )
        assert len(tickets) == 3
        assert "随机种子：5" in tickets[0].basis


# =========================================================================== #
# dlt/balanced.py
# =========================================================================== #
class TestDLTBalancedStrategy:
    def test_metadata_and_schema(self):
        s = dlt_balanced.DLTBalancedStrategy()
        assert s.metadata.id == "balanced_dlt"
        assert s.get_config_schema()["lookback"]["default"] == 100

    def test_validate_options(self):
        s = dlt_balanced.DLTBalancedStrategy()
        with pytest.raises(ValueError, match="至少 20"):
            s.validate_options({"history": []})
        s.validate_options({"history": _dlt_records(20)})

    def test_generate_dedup(self):
        s = dlt_balanced.DLTBalancedStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(count=3, options={"history": recs})
        assert len(tickets) == 3
        for t in tickets:
            assert len(t.groups["front"]) == 5
            assert len(t.groups["back"]) == 2

    def test_generate_no_dedup_with_seed(self):
        s = dlt_balanced.DLTBalancedStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(
            count=3, options={"history": recs, "dedup": False, "seed": 11}
        )
        assert len(tickets) == 3
        assert "随机种子：11" in tickets[0].basis

    def test_generate_allow_repeat_true(self, monkeypatch):
        # 覆盖主循环中 primary.allow_repeat 为 True 的分支 (line 92)
        variant = _make_dlt_variant(front_allow_repeat=True)
        _patch_dlt_profile(monkeypatch, variant)
        s = dlt_balanced.DLTBalancedStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(count=3, options={"history": recs})
        assert len(tickets) == 3
        for t in tickets:
            assert len(t.groups["front"]) == 5
            assert len(t.groups["back"]) == 2

    def test_generate_fallback_allow_repeat_true(self, monkeypatch):
        # max_attempts=0 -> best 为 None -> 走 fallback；allow_repeat=True 分支 (111-112,116-117)
        variant = _make_dlt_variant(front_allow_repeat=True)
        _patch_dlt_profile(monkeypatch, variant)
        s = dlt_balanced.DLTBalancedStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(
            count=1, options={"history": recs, "max_attempts": 0}
        )
        assert len(tickets) == 1
        assert len(tickets[0].groups["front"]) == 5

    def test_generate_fallback_allow_repeat_false(self, monkeypatch):
        # max_attempts=0 + 真实 DLT（allow_repeat=False）-> fallback 的 else 分支
        # (111, 114-117) 以及 _fill_random_other 的非按位分支 (126)
        s = dlt_balanced.DLTBalancedStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(
            count=1, options={"history": recs, "max_attempts": 0}
        )
        assert len(tickets) == 1
        assert len(tickets[0].groups["back"]) == 2

    def test_fill_random_other_branches(self, monkeypatch):
        # 直接覆盖 _fill_random_other 的按位 / 非按位两个分支
        s = dlt_balanced.DLTBalancedStrategy()
        rng = random.Random(0)
        # 非按位后区 -> else 分支 (126)
        _patch_dlt_profile(monkeypatch, _make_dlt_variant(back_positional=False))
        groups_np = {"front": [1, 2, 3, 4, 5]}
        s._fill_random_other(groups_np, rng)
        assert "back" in groups_np
        # 按位后区 -> positional 分支 (125)
        _patch_dlt_profile(monkeypatch, _make_dlt_variant(back_positional=True))
        groups_p = {"front": [1, 2, 3, 4, 5]}
        s._fill_random_other(groups_p, rng)
        assert "back" in groups_p


# =========================================================================== #
# dlt/smart_hot_cold.py
# =========================================================================== #
class TestDLTSmartHotColdStrategy:
    def test_metadata_and_schema(self):
        s = dlt_shc.DLTSmartHotColdStrategy()
        assert s.metadata.id == "smart_hot_cold_dlt"
        assert "hot_weight" in s.get_config_schema()

    def test_validate_options(self):
        s = dlt_shc.DLTSmartHotColdStrategy()
        with pytest.raises(ValueError, match="至少 20"):
            s.validate_options({"history": []})
        s.validate_options({"history": _dlt_records(20)})

    def test_generate_dedup(self):
        s = dlt_shc.DLTSmartHotColdStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(count=50, options={"history": recs, "dedup": True})
        assert len(tickets) == 50
        for t in tickets:
            assert len(t.groups["front"]) == 5
            assert len(t.groups["back"]) == 2

    def test_generate_no_dedup_with_seed(self):
        s = dlt_shc.DLTSmartHotColdStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(
            count=3, options={"history": recs, "dedup": False, "seed": 3}
        )
        assert len(tickets) == 3
        assert "随机种子：3" in tickets[0].basis

    def test_generate_positional_primary(self, monkeypatch):
        # 强制 primary 为按位 -> 覆盖主循环的 positional 分支 (104, 112)
        variant = _make_dlt_variant(front_positional=True, front_allow_repeat=True)
        _patch_dlt_profile(monkeypatch, variant)
        s = dlt_shc.DLTSmartHotColdStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(count=2, options={"history": recs, "dedup": True})
        assert len(tickets) == 2
        assert len(tickets[0].groups["front"]) == 5

    def test_generate_fallback_non_positional(self, monkeypatch):
        # 强制采样恒返回相同候选 -> 第 2 张票必然去重碰撞 -> 触发 for-else fallback（非按位）
        # (120, 122, 124-125)
        monkeypatch.setattr(
            random.Random, "choices",
            lambda self, population, weights=None, k=1, **kw: list(population[:k]),
        )
        variant = _make_dlt_variant(front_positional=False)
        _patch_dlt_profile(monkeypatch, variant)
        s = dlt_shc.DLTSmartHotColdStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(count=2, options={"history": recs, "dedup": True})
        assert len(tickets) == 2
        assert len(tickets[0].groups["front"]) == 5

    def test_generate_fallback_positional(self, monkeypatch):
        # 按位 primary + 强制碰撞 -> fallback 走 positional 分支 (121)，同时覆盖 (120)
        monkeypatch.setattr(
            random.Random, "choices",
            lambda self, population, weights=None, k=1, **kw: list(population[:k]),
        )
        variant = _make_dlt_variant(front_positional=True, front_allow_repeat=True)
        _patch_dlt_profile(monkeypatch, variant)
        s = dlt_shc.DLTSmartHotColdStrategy()
        recs = _dlt_records(30)
        tickets = s.generate(count=2, options={"history": recs, "dedup": True})
        assert len(tickets) == 2
        assert len(tickets[0].groups["front"]) == 5

    def test_fill_random_other_branches(self, monkeypatch):
        # 直接覆盖 _fill_random_other 的按位 / 非按位两个分支 (133, 134)
        s = dlt_shc.DLTSmartHotColdStrategy()
        rng = random.Random(0)
        _patch_dlt_profile(monkeypatch, _make_dlt_variant(back_positional=False))
        g_np = {"front": [1, 2, 3, 4, 5]}
        s._fill_random_other(g_np, rng)
        assert "back" in g_np
        _patch_dlt_profile(monkeypatch, _make_dlt_variant(back_positional=True))
        g_p = {"front": [1, 2, 3, 4, 5]}
        s._fill_random_other(g_p, rng)
        assert "back" in g_p


# =========================================================================== #
# ssq/balanced.py
# =========================================================================== #
class TestSSQBalancedStrategy:
    def test_metadata_and_schema(self):
        s = ssq_balanced.SSQBalancedStrategy()
        assert s.metadata.id == "balanced"
        assert "blue_odd_even" in s.get_config_schema()

    def test_validate_options(self):
        s = ssq_balanced.SSQBalancedStrategy()
        with pytest.raises(ValueError, match="历史均衡策略需要历史"):
            s.validate_options({"history": []})
        s.validate_options({"history": _ssq_uniform_records(10)})

    def test_generate_default(self):
        s = ssq_balanced.SSQBalancedStrategy()
        recs = _ssq_uniform_records(40)
        tickets = s.generate(count=3, options={"history": recs, "lookback": 1000})
        assert len(tickets) == 3
        for t in tickets:
            assert len(t.groups["red"]) == 6
            assert len(t.groups["blue"]) == 1

    def test_generate_blue_missing_false(self):
        s = ssq_balanced.SSQBalancedStrategy()
        recs = _ssq_uniform_records(40)
        tickets = s.generate(count=2, options={"history": recs, "blue_use_missing": False})
        assert len(tickets) == 2

    def test_generate_blue_odd_even(self):
        s = ssq_balanced.SSQBalancedStrategy()
        recs = _ssq_uniform_records(40)
        for control in (1, 2):
            tickets = s.generate(
                count=2, options={"history": recs, "blue_odd_even": control}
            )
            for t in tickets:
                blues = t.groups["blue"]
                if control == 1:
                    assert all(b % 2 == 1 for b in blues)
                else:
                    assert all(b % 2 == 0 for b in blues)

    def test_generate_blue_size(self):
        s = ssq_balanced.SSQBalancedStrategy()
        recs = _ssq_uniform_records(40)
        for size in (1, 2):
            tickets = s.generate(
                count=2, options={"history": recs, "blue_size": size}
            )
            for t in tickets:
                for b in t.groups["blue"]:
                    if size == 1:
                        assert b <= 8
                    else:
                        assert b >= 9

    def test_generate_lookback_slice(self):
        s = ssq_balanced.SSQBalancedStrategy()
        recs = _ssq_uniform_records(40)
        tickets = s.generate(count=2, options={"history": recs, "lookback": 10})
        assert len(tickets) == 2

    def test_generate_single_record_std_fallback(self):
        s = ssq_balanced.SSQBalancedStrategy()
        recs = _ssq_single_record()
        tickets = s.generate(count=1, options={"history": recs})
        assert len(tickets) == 1

    def test_weighted_sample_zero_weight(self):
        # 权重为 0 -> log_weights 取 inf（覆盖 line 32 的 else 分支），该号码被优先选中
        rng = random.Random(0)
        out = ssq_balanced._weighted_sample_without_replacement(
            rng, [1, 2, 3], [0.0, 1.0, 1.0], 2
        )
        assert len(out) == 2
        assert 1 in out  # 0 权重建出 inf，被 Gumbel-max 视为最可能

    def test_generate_with_seed(self):
        # 覆盖 basis 拼接随机种子的分支 (line 224)
        s = ssq_balanced.SSQBalancedStrategy()
        recs = _ssq_uniform_records(40)
        tickets = s.generate(count=2, options={"history": recs, "seed": 99})
        assert len(tickets) == 2
        assert "随机种子：99" in tickets[0].basis

    def test_generate_break_on_perfect_score(self, monkeypatch):
        # 强制红球采样为确定性 [1..6]；在红球恒为 1..6 的历史下得分=0 -> 触发 break (line 269)
        monkeypatch.setattr(
            ssq_balanced,
            "_weighted_sample_without_replacement",
            lambda rng, values, weights, k: sorted(values[:k]),
        )
        s = ssq_balanced.SSQBalancedStrategy()
        recs = _ssq_skew_red_records(33)
        tickets = s.generate(count=1, options={"history": recs})
        assert len(tickets) == 1
        assert tickets[0].groups["red"] == [1, 2, 3, 4, 5, 6]


# =========================================================================== #
# ssq/smart_hot_cold.py
# =========================================================================== #
class TestSSQSmartHotColdStrategy:
    def test_metadata_and_schema(self):
        s = ssq_shc.SSQSmartHotColdStrategy()
        assert s.metadata.id == "smart_hot_cold"
        assert "hot_weight" in s.get_config_schema()

    def test_validate_options(self):
        s = ssq_shc.SSQSmartHotColdStrategy()
        with pytest.raises(ValueError, match="至少 20"):
            s.validate_options({"history": []})
        s.validate_options({"history": _ssq_uniform_records(20)})

    def test_generate_both_uniform(self):
        s = ssq_shc.SSQSmartHotColdStrategy()
        tickets = s.generate(count=2, options={"history": _ssq_uniform_records(33)})
        assert len(tickets) == 2
        assert tickets[0].details["red_is_uniform"] is True
        assert tickets[0].details["blue_is_uniform"] is True

    def test_generate_red_deviates(self):
        s = ssq_shc.SSQSmartHotColdStrategy()
        tickets = s.generate(count=2, options={"history": _ssq_skew_red_records(33)})
        assert tickets[0].details["red_is_uniform"] is False
        assert tickets[0].details["blue_is_uniform"] is True

    def test_generate_blue_deviates(self):
        s = ssq_shc.SSQSmartHotColdStrategy()
        tickets = s.generate(count=2, options={"history": _ssq_skew_blue_records(33)})
        assert tickets[0].details["red_is_uniform"] is True
        assert tickets[0].details["blue_is_uniform"] is False

    def test_generate_both_deviate_with_seed(self):
        s = ssq_shc.SSQSmartHotColdStrategy()
        tickets = s.generate(
            count=2,
            options={
                "history": _ssq_skew_red_records(33),
                "seed": 77,
            },
        )
        # 红球偏离 + 蓝匀（skew_red 历史蓝球均匀）
        assert tickets[0].details["red_is_uniform"] is False
        assert "随机种子：77" in tickets[0].basis


# =========================================================================== #
# hybrid_strategy.py —— mock 重训练相关
# =========================================================================== #
class _FakeBlueLSTM:
    def __init__(self, *a, **k):
        pass

    def train(self, blue_list, epochs=50, progress_callback=None):
        pass

    def predict(self, seq):
        return np.ones(16) / 16.0


class _FakeMLPredictorNotReady:
    def __init__(self, *a, **k):
        self._ready = False

    def is_ready(self):
        return self._ready

    def train(self):
        self._ready = True

    def predict(self):
        return (np.ones(33) / 33.0, np.zeros((33, 33)))


class _FakeMLPredictorReady:
    def __init__(self, *a, **k):
        self._ready = True

    def is_ready(self):
        return self._ready

    def train(self):
        raise AssertionError("train should not be called when ready")

    def predict(self):
        return (np.ones(33) / 33.0, np.zeros((33, 33)))


class TestHybridStrategy:
    def _patch(self, monkeypatch, find_returns=None, predictor_cls=None):
        monkeypatch.setattr(hybrid_strategy, "BlueBallLSTM", _FakeBlueLSTM)
        monkeypatch.setattr(
            hybrid_strategy,
            "MLPredictor",
            predictor_cls or _FakeMLPredictorNotReady,
        )
        monkeypatch.setattr(hybrid_strategy, "compute_lookback", lambda n: 50)
        monkeypatch.setattr(
            hybrid_strategy, "find_current_model", lambda *a, **k: find_returns
        )
        monkeypatch.setattr(
            hybrid_strategy,
            "new_model_path",
            lambda *a, **k: Path("/tmp/fake_hybrid_model.pkl"),
        )

    def test_metadata_and_schema(self):
        s = hybrid_strategy.HybridStrategy()
        assert s.metadata.id == "hybrid"
        assert s.is_ml is True
        assert "history_count" in s.get_config_schema()

    def test_validate_options(self):
        s = hybrid_strategy.HybridStrategy()
        with pytest.raises(ValueError, match="至少 100"):
            s.validate_options({"history": []})
        s.validate_options({"history": _ssq_uniform_records(100)})

    def test_generate_finds_existing_model_and_trains(self, monkeypatch):
        self._patch(monkeypatch, find_returns=Path("/tmp/existing.pkl"))
        s = hybrid_strategy.HybridStrategy()
        recs = _ssq_uniform_records(120)
        tickets = s.generate(
            count=2,
            options={"history": recs, "seed": 1, "blue_epochs": 1},
        )
        assert len(tickets) == 2
        assert len(tickets[0].groups["red"]) == 6

    def test_generate_progress_with_blue_present(self, monkeypatch):
        # 蓝球数据充足且提供进度回调 -> 覆盖“蓝球 LSTM 训练完成”进度分支 (line 115)
        self._patch(monkeypatch, find_returns=Path("/tmp/existing.pkl"))
        progress = []
        s = hybrid_strategy.HybridStrategy()
        recs = _ssq_uniform_records(120)
        tickets = s.generate(
            count=2,
            options={
                "history": recs,
                "seed": 5,
                "blue_epochs": 1,
                "_progress_callback": lambda m: progress.append(m),
            },
        )
        assert len(tickets) == 2
        assert any("蓝球 LSTM 训练完成" in m for m in progress)

    def test_generate_no_existing_model_ready_predictor(self, monkeypatch):
        # find_current_model 返回 None -> 新建模型路径；predictor 已就绪 -> 不训练
        self._patch(
            monkeypatch,
            find_returns=None,
            predictor_cls=_FakeMLPredictorReady,
        )
        s = hybrid_strategy.HybridStrategy()
        recs = _ssq_uniform_records(120)
        tickets = s.generate(count=2, options={"history": recs, "seed": 2})
        assert len(tickets) == 2

    def test_generate_empty_blue_and_progress(self, monkeypatch):
        self._patch(monkeypatch, find_returns=None)

        # 用真实 DrawRecord 但 blue 为空列表
        recs = [
            DrawRecord(
                issue=f"h{i:04d}",
                draw_date=datetime(2024, 1, 1) + timedelta(days=i),
                profile="ssq",
                groups={"red": [1, 2, 3, 4, 5, 6], "blue": []},
            )
            for i in range(120)
        ]
        progress_calls = []
        s = hybrid_strategy.HybridStrategy()
        tickets = s.generate(
            count=2,
            options={
                "history": recs,
                "seed": 3,
                "blue_epochs": 1,
                "_progress_callback": lambda msg: progress_calls.append(msg),
            },
        )
        assert len(tickets) == 2
        assert len(tickets[0].groups["blue"]) == 1
        assert progress_calls  # 进度回调被调用

    def test_generate_history_count_slice_and_non_drawrecord(self, monkeypatch):
        self._patch(monkeypatch, find_returns=None)
        s = hybrid_strategy.HybridStrategy()

        # 传入非 DrawRecord 的历史对象 -> 走 else 分支构造 DrawRecord
        class _HistObj:
            def __init__(self, i):
                self.groups = {"red": [1, 2, 3, 4, 5, 6], "blue": [1]}
                self.profile = type("P", (), {"key": "ssq"})()
                self.generated_at = datetime(2024, 1, 1) + timedelta(days=i)

        history = [_HistObj(i) for i in range(120)]
        tickets = s.generate(
            count=2,
            options={"history": history, "history_count": 50, "seed": 4},
        )
        assert len(tickets) == 2

    def test_generate_count_zero(self, monkeypatch):
        self._patch(monkeypatch, find_returns=None)
        s = hybrid_strategy.HybridStrategy()
        recs = _ssq_uniform_records(120)
        assert s.generate(count=0, options={"history": recs}) == []


# =========================================================================== #
# lstm_strategy.py —— mock 重训练，覆盖全部分支
# =========================================================================== #
class _LSTMRedFake:
    def __init__(self, *a, **k):
        pass

    def train(self, red_lists, epochs=50, progress_callback=None):
        pass

    def predict(self, seq):
        return np.ones(33) / 33.0


class _LSTMBlueFake:
    def __init__(self, *a, **k):
        pass

    def train(self, blue_list, epochs=50, progress_callback=None):
        pass

    def predict(self, seq):
        return np.ones(16) / 16.0


class TestLSTMStrategyCov:
    def _patch(self, monkeypatch):
        monkeypatch.setattr(lstm_strategy, "RedBallLSTM", _LSTMRedFake)
        monkeypatch.setattr(lstm_strategy, "BlueBallLSTM", _LSTMBlueFake)

    def test_module_helpers(self):
        recs = _ssq_uniform_records(5)
        assert lstm_strategy._to_red_lists(recs) == [r.red_balls for r in recs]
        # 含一个无蓝球记录
        recs2 = _ssq_uniform_records(5) + [
            DrawRecord(
                issue="x",
                draw_date=datetime(2024, 6, 1),
                profile="ssq",
                groups={"red": [1, 2, 3, 4, 5, 6], "blue": []},
            )
        ]
        assert lstm_strategy._to_blue_list(recs2) == [
            r.blue_ball for r in recs2 if r.blue_ball
        ]

    def test_metadata_schema_validate(self):
        s = lstm_strategy.LSTMStrategy()
        assert s.metadata.id == "lstm"
        assert s.get_config_schema()["seq_len"]["default"] == 20
        with pytest.raises(ValueError, match="至少 100"):
            s.validate_options({"history": []})
        s.validate_options({"history": _ssq_uniform_records(100)})

    def test_generate_normal_with_progress(self, monkeypatch):
        self._patch(monkeypatch)
        s = lstm_strategy.LSTMStrategy()
        recs = _ssq_uniform_records(120)
        progress = []
        tickets = s.generate(
            count=2,
            options={
                "history": recs,
                "seq_len": 10,
                "epochs": 1,
                "seed": 42,
                "_progress_callback": lambda m: progress.append(m),
            },
        )
        assert len(tickets) == 2
        assert len(tickets[0].groups["red"]) == 6
        assert progress  # 进度分支被覆盖

    def test_generate_empty_blue(self, monkeypatch):
        self._patch(monkeypatch)
        s = lstm_strategy.LSTMStrategy()
        recs = [
            DrawRecord(
                issue=f"e{i:04d}",
                draw_date=datetime(2024, 1, 1) + timedelta(days=i),
                profile="ssq",
                groups={"red": [1, 2, 3, 4, 5, 6], "blue": []},
            )
            for i in range(120)
        ]
        progress = []
        tickets = s.generate(
            count=1,
            options={
                "history": recs,
                "seq_len": 10,
                "epochs": 1,
                "seed": 7,
                "_progress_callback": lambda m: progress.append(m),
            },
        )
        assert len(tickets) == 1
        assert len(tickets[0].groups["blue"]) == 1
        # 蓝球数据不足时仍应触发进度回调 (line 120)
        assert any("数据不足" in m for m in progress)

    def test_generate_history_count_and_count_zero(self, monkeypatch):
        self._patch(monkeypatch)
        s = lstm_strategy.LSTMStrategy()
        recs = _ssq_uniform_records(120)
        tickets = s.generate(
            count=2,
            options={"history": recs, "history_count": 50, "seq_len": 10, "epochs": 1},
        )
        assert len(tickets) == 2
        assert s.generate(count=0, options={"history": recs}) == []


# =========================================================================== #
# common/ml.py
# =========================================================================== #
class _StubPredictorNotReady:
    def __init__(self, *a, **k):
        self._ready = False

    def is_ready(self):
        return self._ready

    def train(self):
        self._ready = True

    def predict(self):
        # 同时覆盖 1D 与 2D 分支
        return {"red": np.random.rand(33), "blue": np.random.rand(16, 2)}

    def recommend(self, group_picks=None, diversity_boost=0.3, rng=None):
        return {"red": [1, 2, 3, 4, 5, 6], "blue": [7]}


class _StubPredictorReady:
    def __init__(self, *a, **k):
        self._ready = True

    def is_ready(self):
        return self._ready

    def train(self):
        raise AssertionError("train must not run when ready")

    def predict(self):
        return {"red": np.random.rand(33), "blue": np.random.rand(16, 2)}

    def recommend(self, group_picks=None, diversity_boost=0.3, rng=None):
        return {"red": [1, 2, 3, 4, 5, 6], "blue": [7]}


class TestCommonML:
    def _patch_store(self, monkeypatch):
        monkeypatch.setattr(common_ml, "compute_lookback", lambda n: 50)
        monkeypatch.setattr(
            common_ml, "find_current_model", lambda *a, **k: None
        )
        monkeypatch.setattr(
            common_ml, "new_model_path", lambda *a, **k: Path("/tmp/fake_ml.pkl")
        )

    @staticmethod
    def _concrete(base_cls):
        from caipiao.core.strategy import StrategyMetadata

        class _Concrete(base_cls):
            @property
            def metadata(self):
                return StrategyMetadata(id="cov", name="cov", description="cov")

        return _Concrete

    def test_make_generic_ml_base_not_ready_trains(self, monkeypatch):
        self._patch_store(monkeypatch)
        monkeypatch.setattr(common_ml, "GenericMLPredictor", _StubPredictorNotReady)
        SSQ = __import__("caipiao.core.profile", fromlist=["SSQ"]).SSQ
        base = self._concrete(common_ml.make_generic_ml_base(SSQ))
        assert base().get_config_schema()["diversity_boost"]["default"] == 3
        with pytest.raises(ValueError, match="至少 100"):
            base().validate_options({"history": []})
        with pytest.raises(ValueError, match="大于等于 -1"):
            base().validate_options(
                {"history": _ssq_uniform_records(100), "history_count": -2}
            )
        recs = _ssq_uniform_records(120)
        tickets = base().generate(count=2, options={"history": recs, "history_count": 50})
        assert len(tickets) == 2
        assert tickets[0].details["backend"] == "xgboost"

    def test_make_generic_ml_base_ready_no_train(self, monkeypatch):
        self._patch_store(monkeypatch)
        SSQ = __import__("caipiao.core.profile", fromlist=["SSQ"]).SSQ
        base = self._concrete(
            common_ml.make_generic_ml_base(SSQ, predictor_class=_StubPredictorReady)
        )
        recs = _ssq_uniform_records(120)
        tickets = base().generate(count=2, options={"history": recs})
        assert len(tickets) == 2

    def test_make_placeholder_ml_base(self, monkeypatch):
        SSQ = __import__("caipiao.core.profile", fromlist=["SSQ"]).SSQ
        base = self._concrete(common_ml.make_placeholder_ml_base(SSQ, "未实现"))
        assert base().get_config_schema()["history"]["type"] == "history"
        with pytest.raises(ValueError, match="至少 100"):
            base().validate_options({"history": []})
        base().validate_options({"history": _ssq_uniform_records(100)})
        with pytest.raises(NotImplementedError):
            base().generate(count=1, options={"history": _ssq_uniform_records(100)})

    def test_deterministic_seed_explicit(self):
        # 显式 seed 优先直接返回 int(seed)（覆盖 common/ml.py line 38）
        assert common_ml._deterministic_seed({"seed": 5}, [], "x") == 5
        assert common_ml._deterministic_seed({"seed": "7"}, [], "x") == 7


# =========================================================================== #
# stability_validator.py
# =========================================================================== #
class TestStabilityValidator:
    def _ctx(self, is_ml=False, records=None):
        return RoundBacktestContext(
            strategy_id="x",
            profile_key="ssq",
            tickets_per_round=1,
            options={},
            is_ml=is_ml,
            needs_history=True,
            records=records or [],
            seed=0,
        )

    def _tasks(self, n):
        base = datetime(2024, 1, 1)
        return [
            RoundTask(
                index=i,
                actual=DrawRecord(
                    issue=f"t{i:04d}",
                    draw_date=base + timedelta(days=i),
                    profile="ssq",
                    groups={"red": [1, 2, 3, 4, 5, 6], "blue": [1]},
                ),
            )
            for i in range(n)
        ]

    def test_stability_score(self):
        assert stability_validator.stability_score(0.0, 1.0) == 0.0
        assert stability_validator.stability_score(-5.0, 1.0) == 0.0
        assert 0.0 <= stability_validator.stability_score(100.0, 10.0) <= 1.0
        assert stability_validator.stability_score(100.0, 0.0) == 1.0

    def test_split_tasks(self):
        tasks = self._tasks(5)
        # n_folds<=1 或 n<folds -> 整体
        assert stability_validator._split_tasks(tasks, 1) == [tasks]
        assert stability_validator._split_tasks(tasks, 10) == [tasks]
        folds = stability_validator._split_tasks(tasks, 2)
        assert len(folds) == 2
        assert sum(len(f) for f in folds) == 5

    def test_cross_validate_normal(self, monkeypatch):
        monkeypatch.setattr(
            stability_validator, "worker_round_backtest",
            lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=100),
        )
        monkeypatch.setattr(
            stability_validator, "merge_round_results",
            lambda results, n: BatchBacktestResult(total_fixed_prize=100, errors=[]),
        )
        progress = []
        status = []
        results = stability_validator.cross_validate_params(
            self._ctx(is_ml=False),
            self._tasks(60),
            [{"a": 1}, {"a": 2}],
            n_folds=3,
            progress_callback=lambda i, t: progress.append((i, t)),
            status_callback=lambda m: status.append(m),
        )
        assert len(results) == 2
        assert all(r.fold_results for r in results)
        assert progress

    def test_cross_validate_force_n_folds_ml(self, monkeypatch):
        monkeypatch.setattr(
            stability_validator, "worker_round_backtest",
            lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=100),
        )
        monkeypatch.setattr(
            stability_validator, "merge_round_results",
            lambda results, n: BatchBacktestResult(total_fixed_prize=100, errors=[]),
        )
        status = []
        stability_validator.cross_validate_params(
            self._ctx(is_ml=True),
            self._tasks(60),
            [{"a": 1}],
            n_folds=3,
            status_callback=lambda m: status.append(m),
        )
        assert any("单区间" in m for m in status)

    def test_cross_validate_insufficient_data(self, monkeypatch):
        monkeypatch.setattr(
            stability_validator, "worker_round_backtest",
            lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=100),
        )
        monkeypatch.setattr(
            stability_validator, "merge_round_results",
            lambda results, n: BatchBacktestResult(total_fixed_prize=100, errors=[]),
        )
        status = []
        stability_validator.cross_validate_params(
            self._ctx(is_ml=False),
            self._tasks(10),
            [{"a": 1}],
            n_folds=3,
            status_callback=lambda m: status.append(m),
        )
        assert any("单区间" in m for m in status)

    def test_cross_validate_interruption(self, monkeypatch):
        monkeypatch.setattr(
            stability_validator, "worker_round_backtest",
            lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=100),
        )
        monkeypatch.setattr(
            stability_validator, "merge_round_results",
            lambda results, n: BatchBacktestResult(total_fixed_prize=100, errors=[]),
        )
        results = stability_validator.cross_validate_params(
            self._ctx(is_ml=False),
            self._tasks(60),
            [{"a": 1}, {"a": 2}],
            n_folds=3,
            interruption_callback=lambda: True,
        )
        assert results == []

    def test_cross_validate_worker_exception(self, monkeypatch):
        def _boom(ctx, task):
            raise RuntimeError("boom")

        monkeypatch.setattr(stability_validator, "worker_round_backtest", _boom)
        monkeypatch.setattr(
            stability_validator, "merge_round_results",
            lambda results, n: BatchBacktestResult(total_fixed_prize=100, errors=[]),
        )
        results = stability_validator.cross_validate_params(
            self._ctx(is_ml=False),
            self._tasks(60),
            [{"a": 1}],
            n_folds=3,
        )
        assert results and results[0].errors and "boom" in results[0].errors[0]

    def test_cross_validate_merged_errors(self, monkeypatch):
        monkeypatch.setattr(
            stability_validator, "worker_round_backtest",
            lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=100),
        )
        monkeypatch.setattr(
            stability_validator, "merge_round_results",
            lambda results, n: BatchBacktestResult(total_fixed_prize=100, errors=["bad"]),
        )
        results = stability_validator.cross_validate_params(
            self._ctx(is_ml=False),
            self._tasks(60),
            [{"a": 1}],
            n_folds=3,
        )
        assert results and results[0].errors and results[0].errors[0] == "bad"

    def test_cross_validate_empty_fold_skip(self, monkeypatch):
        monkeypatch.setattr(
            stability_validator, "worker_round_backtest",
            lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=100),
        )
        monkeypatch.setattr(
            stability_validator, "merge_round_results",
            lambda results, n: BatchBacktestResult(total_fixed_prize=100, errors=[]),
        )
        # 注入一个空折 -> 覆盖 `if not fold_tasks: continue`
        monkeypatch.setattr(
            stability_validator, "_split_tasks",
            lambda tasks, n: [[], tasks],
        )
        results = stability_validator.cross_validate_params(
            self._ctx(is_ml=False),
            self._tasks(60),
            [{"a": 1}],
            n_folds=3,
        )
        assert results and results[0].fold_results

    def test_cross_validate_all_folds_empty_no_results(self, monkeypatch):
        monkeypatch.setattr(
            stability_validator, "worker_round_backtest",
            lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=100),
        )
        monkeypatch.setattr(
            stability_validator, "merge_round_results",
            lambda results, n: BatchBacktestResult(total_fixed_prize=100, errors=[]),
        )
        # 全部折为空 -> "no fold results" 分支
        monkeypatch.setattr(
            stability_validator, "_split_tasks",
            lambda tasks, n: [[], []],
        )
        results = stability_validator.cross_validate_params(
            self._ctx(is_ml=False),
            self._tasks(60),
            [{"a": 1}],
            n_folds=3,
        )
        assert results and results[0].errors == ["no fold results"]

    def test_pick_best_param_cv(self):
        # 无合格结果
        assert stability_validator.pick_best_param_cv(
            [stability_validator.CrossValidationResult(params={"a": 1}, errors=["x"])]
        ) is None
        # 合格结果 -> 取稳定性最高
        good1 = stability_validator.CrossValidationResult(
            params={"a": 1}, stability_score=0.5, mean_fixed_prize=10.0,
            std_fixed_prize=1.0, fold_results=["x"],
        )
        good2 = stability_validator.CrossValidationResult(
            params={"a": 2}, stability_score=0.9, mean_fixed_prize=20.0,
            std_fixed_prize=1.0, fold_results=["x"],
        )
        best = stability_validator.pick_best_param_cv([good1, good2])
        assert best[0] == {"a": 2}
