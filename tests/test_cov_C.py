"""测试文件 C：将下列核心策略模块的行覆盖率提升到 100%.

覆盖模块（不含 ui / ml 层）：
- caipiao/core/strategies/lotteries/pl3/{balanced,smart_hot_cold}.py
- caipiao/core/strategies/lotteries/pl5/{balanced,smart_hot_cold}.py
- caipiao/core/strategies/lotteries/qxc/{balanced,smart_hot_cold}.py
- caipiao/core/strategies/lotteries/kl8/{balanced,smart_hot_cold,stability}.py
- caipiao/core/strategies/bagua/bagua_strategy.py

部分分支对真实 PROFILE 是死的（如 allow_repeat / positional / variable_pick 的
另一分支、_fill_random_other 的多组路径）。按本仓库其他覆盖测试的做法，通过
monkeypatch 模块级 PROFILE 为一个启用该分支的假档案来覆盖；χ² / 重叠等防御性
分支通过 monkeypatch 分析器方法或传入空记录来覆盖。
"""

from __future__ import annotations

import random
import statistics
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from caipiao.data.analyzer import DrawAnalyzer
from caipiao.data.models import DrawRecord
from caipiao.core.profile import (
    KL8,
    LotteryProfile,
    NumberGroup,
    PL3,
    PL5,
    QXC,
    SSQ,
)
from caipiao.core.strategies.lotteries.pl3 import (
    _base as pl3_base,
    balanced as pl3_bal,
    smart_hot_cold as pl3_shc,
)
from caipiao.core.strategies.lotteries.pl3.balanced import PL3BalancedStrategy
from caipiao.core.strategies.lotteries.pl3.smart_hot_cold import (
    PL3SmartHotColdStrategy,
)
from caipiao.core.strategies.lotteries.pl5 import (
    _base as pl5_base,
    balanced as pl5_bal,
    smart_hot_cold as pl5_shc,
)
from caipiao.core.strategies.lotteries.pl5.balanced import PL5BalancedStrategy
from caipiao.core.strategies.lotteries.pl5.smart_hot_cold import (
    PL5SmartHotColdStrategy,
)
from caipiao.core.strategies.lotteries.qxc import (
    _base as qxc_base,
    balanced as qxc_bal,
    smart_hot_cold as qxc_shc,
)
from caipiao.core.strategies.lotteries.qxc.balanced import QXCBalancedStrategy
from caipiao.core.strategies.lotteries.qxc.smart_hot_cold import (
    QXCSmartHotColdStrategy,
)
from caipiao.core.strategies.lotteries.kl8 import (
    _base as kl8_base,
    balanced as kl8_bal,
    smart_hot_cold as kl8_shc,
    stability as kl8_stability,
)
from caipiao.core.strategies.lotteries.kl8.balanced import KL8BalancedStrategy
from caipiao.core.strategies.lotteries.kl8.smart_hot_cold import (
    KL8SmartHotColdStrategy,
)
from caipiao.core.strategies.bagua.bagua_strategy import BaguaStrategy


# --------------------------------------------------------------------------- #
# 测试数据构造助手
# --------------------------------------------------------------------------- #
def _pos_records(pick: int, n: int) -> list[DrawRecord]:
    """构造按位彩种（pos 组）开奖记录，每组 pick 个 0-9 号码。"""
    recs: list[DrawRecord] = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        nums = [(i + j) % 10 for j in range(pick)]
        recs.append(
            DrawRecord(
                issue=f"pos{i:04d}",
                draw_date=base + timedelta(days=i),
                profile="pl3",
                groups={"pos": nums},
            )
        )
    return recs


def _kl8_records(n: int) -> list[DrawRecord]:
    """构造快乐8记录：每期 20 个分散于 1-80 的号码（近似均匀）。"""
    recs: list[DrawRecord] = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        nums = sorted({(i * 4 + j) % 80 + 1 for j in range(20)})
        recs.append(
            DrawRecord(
                issue=f"kl8{i:04d}",
                draw_date=base + timedelta(days=i),
                profile="kl8",
                groups={"main": nums},
            )
        )
    return recs


def _kl8_records_skewed(n: int) -> list[DrawRecord]:
    """构造快乐8记录：每期恒为 1-20（显著偏离均匀，χ² 检验失败）。"""
    recs: list[DrawRecord] = []
    base = datetime(2024, 1, 1)
    nums = list(range(1, 21))
    for i in range(n):
        recs.append(
            DrawRecord(
                issue=f"kl8s{i:04d}",
                draw_date=base + timedelta(days=i),
                profile="kl8",
                groups={"main": nums},
            )
        )
    return recs


# --------------------------------------------------------------------------- #
# 假档案构造助手（用于覆盖 allow_repeat / positional / variable_pick 死分支）
# --------------------------------------------------------------------------- #
def _positional_variant(
    key: str,
    count: int,
    allow_repeat: bool = True,
    primary_positional: bool = True,
    secondary=None,
    category: str = "sports",
) -> LotteryProfile:
    """构造按位彩种变体：主组 'pos' + 可选附加组，用于强制覆盖分支。"""
    primary = NumberGroup(
        "pos", "pos", 0, 9, count,
        positional=primary_positional, allow_repeat=allow_repeat,
        is_primary=True, pad=1,
    )
    groups = [primary]
    if secondary is not None:
        groups.append(secondary)
    return LotteryProfile(
        key=key, name=key, groups=tuple(groups),
        data_url="", parser_key=key, draw_weekdays=(),
        storage_file="x.json", model_prefix=key, category=category,
    )


def _extra_group(positional: bool, variable_pick: bool = False) -> NumberGroup:
    """构造一个附加号码组（键 'extra'）。"""
    if variable_pick:
        return NumberGroup(
            "extra", "extra", 0, 9, 3,
            positional=positional, pick_min=1, pick_max=5,
        )
    return NumberGroup("extra", "extra", 0, 9, 3, positional=positional)


def _patch_profile(monkeypatch, base_mod, strat_mod, variant) -> None:
    """把 _base 与策略模块的模块级 PROFILE 都替换为变体。"""
    monkeypatch.setattr(base_mod, "PROFILE", variant)
    monkeypatch.setattr(strat_mod, "PROFILE", variant)


def _patch_analyzer_for_break(monkeypatch, pick: int) -> None:
    """monkeypatch 分析器使评分目标与确定性候选完全吻合，触发 break。"""
    cand = list(range(pick))
    odd = sum(1 for n in cand if n % 2 == 1)
    high = sum(1 for n in cand if n >= 5)  # 0-9 组 high_low_border = 5
    total = sum(cand)
    monkeypatch.setattr(
        DrawAnalyzer, "odd_even_ratio",
        lambda self, last_n=None: (odd / pick, 1.0 - odd / pick),
    )
    monkeypatch.setattr(
        DrawAnalyzer, "high_low_ratio",
        lambda self, last_n=None: (high / pick, 1.0 - high / pick),
    )
    monkeypatch.setattr(
        DrawAnalyzer, "sum_statistics",
        lambda self, last_n=None: {"min": 0, "max": 80, "avg": float(total)},
    )
    # 让主循环采样返回确定性候选 list(range(pick))
    monkeypatch.setattr(
        random.Random, "choices",
        lambda self, population, weights=None, k=1, **kw: list(range(k)),
    )


# --------------------------------------------------------------------------- #
# 按位彩种（pl3 / pl5 / qxc）均衡策略
# --------------------------------------------------------------------------- #
def _cover_balanced(strat_cls, strat_mod, base_mod, pick: int, monkeypatch) -> None:
    s = strat_cls()
    # 覆盖 get_config_schema（含 _add_pick_count_schema）
    assert "history" in s.get_config_schema()

    # validate_options：不足 20 期 -> 抛错（覆盖 raise 分支）
    with pytest.raises(ValueError):
        s.validate_options({"history": _pos_records(pick, 10)})
    s.validate_options({"history": _pos_records(pick, 30)})

    recs = _pos_records(pick, 30)
    # 基本生成（real profile, allow_repeat=True 主循环分支）+ 种子 basis 分支
    s.generate(count=2, options={"history": recs, "seed": 1})
    s.generate(count=1, options={"history": recs, "max_attempts": 5})
    # fallback（best 为 None）allow_repeat=True 分支（max_attempts=0）
    s.generate(count=1, options={"history": recs, "max_attempts": 0})
    # break 分支（best_score <= 0.5）
    _patch_analyzer_for_break(monkeypatch, pick)
    s.generate(count=1, options={"history": recs, "max_attempts": 50})

    # 变体：allow_repeat=False -> 主循环 else 分支 + fallback else 分支
    var_false = _positional_variant(
        "plx", pick, allow_repeat=False, primary_positional=False
    )
    _patch_profile(monkeypatch, base_mod, strat_mod, var_false)
    sv = strat_cls()
    sv.generate(count=1, options={"history": _pos_records(pick, 30)})
    sv.generate(
        count=1, options={"history": _pos_records(pick, 30), "max_attempts": 0}
    )

    # _fill_random_other 的 positional / 非positional / variable_pick 分支
    _fill_random_other_balanced(strat_cls(), strat_mod, base_mod, monkeypatch, pick)


def _fill_random_other_balanced(strat_cls_inst, strat_mod, base_mod, monkeypatch, pick):
    rng = random.Random(0)
    # 按位附加组
    var_p = _positional_variant("plx", pick, secondary=_extra_group(True))
    _patch_profile(monkeypatch, base_mod, strat_mod, var_p)
    g = {"pos": list(range(pick))}
    strat_cls_inst._fill_random_other(g, rng)
    assert "extra" in g
    # 非按位、非可变附加组
    var_n = _positional_variant(
        "plx", pick, secondary=_extra_group(False, variable_pick=False)
    )
    _patch_profile(monkeypatch, base_mod, strat_mod, var_n)
    g = {"pos": list(range(pick))}
    strat_cls_inst._fill_random_other(g, rng)
    assert "extra" in g
    # 非按位、可变附加组
    var_v = _positional_variant(
        "plx", pick, secondary=_extra_group(False, variable_pick=True)
    )
    _patch_profile(monkeypatch, base_mod, strat_mod, var_v)
    g = {"pos": list(range(pick))}
    strat_cls_inst._fill_random_other(g, rng)
    assert "extra" in g


# --------------------------------------------------------------------------- #
# 按位彩种（pl3 / pl5 / qxc）智能冷热号策略
# --------------------------------------------------------------------------- #
def _cover_smart(strat_cls, strat_mod, base_mod, pick: int, monkeypatch) -> None:
    s = strat_cls()
    # 覆盖 get_config_schema（含 _add_pick_count_schema）
    assert "history" in s.get_config_schema()

    with pytest.raises(ValueError):
        s.validate_options({"history": _pos_records(pick, 10)})
    s.validate_options({"history": _pos_records(pick, 30)})

    recs = _pos_records(pick, 30)
    # dedup=True 正常生成（positional primary 主循环 + dedup_key + seen.add）
    s.generate(count=2, options={"history": recs, "seed": 1})
    # dedup=False（max_attempts=1 分支 + not dedup 跳过 seen.add）
    s.generate(count=2, options={"history": recs, "dedup": False})

    # 变体：非按位 + allow_repeat=False + 强制去重碰撞
    # -> 主循环非positional 分支 + while 重采样体 + 非positional dedup_key + 兜底非positional
    var_np = _positional_variant(
        "plx", pick, allow_repeat=False, primary_positional=False
    )
    _patch_profile(monkeypatch, base_mod, strat_mod, var_np)
    snp = strat_cls()
    state = {"c": 0}

    def fake_choices_np(self, population, weights=None, k=1, **kw):
        state["c"] += 1
        if state["c"] % 2 == 1:
            return [population[0]] * k  # 重复 -> 触发 while 重采样
        return list(population[:k])      # 去重后确定候选 -> 恒定 -> 碰撞

    monkeypatch.setattr(random.Random, "choices", fake_choices_np)
    # count=2：ticket1 撞空前命中，ticket2 恒定撞 seen -> 触发 else 兜底（非按位）
    snp.generate(count=2, options={"history": _pos_records(pick, 30), "dedup": True})

    # 变体：按位 primary + 强制去重碰撞 -> 兜底按位分支
    var_pos = _positional_variant(
        "plx", pick, allow_repeat=True, primary_positional=True
    )
    _patch_profile(monkeypatch, base_mod, strat_mod, var_pos)
    sp = strat_cls()
    monkeypatch.setattr(
        random.Random, "choices",
        lambda self, population, weights=None, k=1, **kw: [population[0]],
    )
    # count=2：ticket2 恒定撞 seen -> 触发 else 兜底（按位，line 121-122）
    sp.generate(count=2, options={"history": _pos_records(pick, 30), "dedup": True})

    # _fill_random_other 的 positional / 非positional 分支
    _fill_random_other_smart(strat_cls(), strat_mod, base_mod, monkeypatch, pick)


def _fill_random_other_smart(strat_cls_inst, strat_mod, base_mod, monkeypatch, pick):
    rng = random.Random(0)
    var_p = _positional_variant("plx", pick, secondary=_extra_group(True))
    _patch_profile(monkeypatch, base_mod, strat_mod, var_p)
    g = {"pos": list(range(pick))}
    strat_cls_inst._fill_random_other(g, rng)
    assert "extra" in g
    var_n = _positional_variant("plx", pick, secondary=_extra_group(False))
    _patch_profile(monkeypatch, base_mod, strat_mod, var_n)
    g = {"pos": list(range(pick))}
    strat_cls_inst._fill_random_other(g, rng)
    assert "extra" in g


class TestPositionalStrategies:
    def test_pl3_balanced(self, monkeypatch):
        _cover_balanced(PL3BalancedStrategy, pl3_bal, pl3_base, 3, monkeypatch)

    def test_pl5_balanced(self, monkeypatch):
        _cover_balanced(PL5BalancedStrategy, pl5_bal, pl5_base, 5, monkeypatch)

    def test_qxc_balanced(self, monkeypatch):
        _cover_balanced(QXCBalancedStrategy, qxc_bal, qxc_base, 7, monkeypatch)

    def test_pl3_smart(self, monkeypatch):
        _cover_smart(PL3SmartHotColdStrategy, pl3_shc, pl3_base, 3, monkeypatch)

    def test_pl5_smart(self, monkeypatch):
        _cover_smart(PL5SmartHotColdStrategy, pl5_shc, pl5_base, 5, monkeypatch)

    def test_qxc_smart(self, monkeypatch):
        _cover_smart(QXCSmartHotColdStrategy, qxc_shc, qxc_base, 7, monkeypatch)


# --------------------------------------------------------------------------- #
# 快乐8 stability.py —— 纯函数，直接测试覆盖全部分支
# --------------------------------------------------------------------------- #
class TestKL8StabilityFunctions:
    def test_slice_records(self):
        recs = _kl8_records(10)
        assert len(kl8_stability._slice_records(recs, 5)) == 5
        assert len(kl8_stability._slice_records(recs, None)) == 10
        assert len(kl8_stability._slice_records(recs, 100)) == 10
        assert kl8_stability._slice_records(recs, 0) == []

    def test_history_hash_and_seed(self):
        recs = _kl8_records(10)
        h = kl8_stability._history_content_hash(recs)
        assert isinstance(h, str) and len(h) == 16
        s1 = kl8_stability.deterministic_seed({}, recs, 100, "x")
        s2 = kl8_stability.deterministic_seed({}, recs, 100, "x")
        assert s1 == s2
        assert kl8_stability.deterministic_seed({"seed": 9}, recs, 100, "x") == 9

    def test_stable_frequency(self):
        recs = _kl8_records(20)
        f = kl8_stability.stable_frequency(recs, 20)
        assert set(f.keys()) == set(range(1, 81))

    def test_frequency_counts(self):
        recs = _kl8_records(20)
        c = kl8_stability.frequency_counts(recs, 20)
        assert set(c.keys()) == set(range(1, 81))

    def test_raw_missing(self):
        recs = _kl8_records(20)
        m = kl8_stability.raw_missing_periods(recs, 20)
        assert set(m.keys()) == set(range(1, 81))

    def test_geo_zscore(self):
        m = kl8_stability.raw_missing_periods(_kl8_records(20), 20)
        gz = kl8_stability.geometric_missing_zscore(m)
        assert set(gz.keys()) == set(range(1, 81))

    def test_chi_square(self):
        # 空计数
        assert kl8_stability.chi_square_uniform_test([]) == (0.0, True)
        # k < 2
        assert kl8_stability.chi_square_uniform_test([5]) == (0.0, True)
        # n == 0
        assert kl8_stability.chi_square_uniform_test([0] * 80) == (0.0, True)
        # 均匀
        assert kl8_stability.chi_square_uniform_test([5] * 80) == (0.0, True)
        # 显著偏离
        skewed = [50] + [0] * 79
        assert kl8_stability.chi_square_uniform_test(skewed)[1] is False

    def test_zscore_normalize(self):
        out = kl8_stability._zscore_normalize({n: float(n) for n in range(1, 81)})
        assert len(out) == 80
        out2 = kl8_stability._zscore_normalize({n: 5.0 for n in range(1, 81)})
        assert all(v == 0.0 for v in out2.values())

    def test_zscore_normalize_small_pool(self, monkeypatch):
        # MAIN_POOL 仅 1 个元素 -> len(vals) < 2 提前返回全 0
        monkeypatch.setattr(kl8_stability, "MAIN_POOL", [1])
        out = kl8_stability._zscore_normalize({1: 3.0})
        assert out == {1: 0.0}

    def test_zscore_normalize_stats_error(self, monkeypatch):
        # stdev 抛 StatisticsError -> 捕获后 std=0.0 -> 全 0
        def _raise(*a, **k):
            raise statistics.StatisticsError("x")

        monkeypatch.setattr(kl8_stability.statistics, "stdev", _raise)
        out = kl8_stability._zscore_normalize({n: float(n) for n in range(1, 81)})
        assert all(v == 0.0 for v in out.values())

    def test_softmax(self):
        assert abs(sum(kl8_stability.softmax_scores([1.0, 2.0], temperature=0)) - 1.0) < 1e-9
        assert abs(sum(kl8_stability.softmax_scores([1.0, 2.0], temperature=1.0)) - 1.0) < 1e-9

    def test_stable_scores(self):
        hot = {n: 1.0 for n in range(1, 81)}
        cold = {n: 1.0 for n in range(1, 81)}
        # 权重和为 0 -> 退化为 1.0
        out = kl8_stability.stable_scores(hot, cold, 0, 0, 1.0)
        assert abs(sum(out) - 1.0) < 1e-9
        out2 = kl8_stability.stable_scores(hot, cold, 60, 40, 1.0)
        assert len(out2) == 80

    def test_sample_weighted(self):
        rng = random.Random(0)
        with pytest.raises(ValueError):
            kl8_stability.sample_weighted(rng, [1, 2], [0.5])
        assert kl8_stability.sample_weighted(rng, [1, 2, 3], [0.0, 0.0, 0.0]) in (1, 2, 3)
        # 正常加权路径（line 287）
        assert kl8_stability.sample_weighted(rng, [1, 2, 3], [0.5, 0.3, 0.2]) in (1, 2, 3)

    def test_weighted_sample(self):
        rng = random.Random(0)
        # k 超过池大小 -> 截断
        sel = kl8_stability.weighted_sample_without_replacement(rng, [1, 2, 3], [1, 1, 1], 10)
        assert len(sel) == 3
        # k = 0 -> 空
        assert kl8_stability.weighted_sample_without_replacement(rng, [1, 2, 3], [1, 1, 1], 0) == []
        # 权重全 0 -> 退化为均匀随机
        sel2 = kl8_stability.weighted_sample_without_replacement(rng, [1, 2, 3], [0.0, 0.0, 0.0], 2)
        assert len(sel2) == 2


# --------------------------------------------------------------------------- #
# 快乐8 均衡策略
# --------------------------------------------------------------------------- #
class TestKL8BalancedStrategy:
    def test_validate_options(self):
        s = KL8BalancedStrategy()
        assert "history" in s.get_config_schema()
        with pytest.raises(ValueError):
            s.validate_options({"history": _kl8_records(10)})
        s.validate_options({"history": _kl8_records(30)})

    def test_generate_branches(self, monkeypatch):
        s = KL8BalancedStrategy()
        recs = _kl8_records(50)
        # 均匀历史 -> is_uniform True + 种子为 None 的 basis
        t = s.generate(count=2, options={"history": recs, "pick_count": 5})
        assert len(t) == 2
        # 种子 basis 分支
        s.generate(count=1, options={"history": recs, "pick_count": 5, "seed": 7})
        # 显著偏离 -> is_uniform False
        s.generate(count=1, options={"history": _kl8_records_skewed(50), "pick_count": 5})
        # fallback（best 为 None）-> max_attempts=0
        s.generate(
            count=1, options={"history": recs, "pick_count": 5, "max_attempts": 0}
        )
        # break 分支（_score_candidate 恒为 0 -> best_score <= 0.5）
        monkeypatch.setattr(s, "_score_candidate", lambda *a, **k: 0.0)
        s.generate(
            count=1, options={"history": recs, "pick_count": 5, "max_attempts": 50}
        )

    def test_compute_target_zones(self):
        s = KL8BalancedStrategy()
        analyzer = DrawAnalyzer(_kl8_records(50), KL8)
        targets = s._compute_target_zones(analyzer, 50, 5)
        assert len(targets) == 3 and all(x >= 1 for x in targets)
        # 空记录分支
        empty = DrawAnalyzer([], KL8)
        targets2 = s._compute_target_zones(empty, 50, 5)
        assert len(targets2) == 3 and all(x >= 1 for x in targets2)

    def test_compute_target_consecutive(self, monkeypatch):
        s = KL8BalancedStrategy()
        analyzer = DrawAnalyzer(_kl8_records(50), KL8)
        assert s._compute_target_consecutive(analyzer, 50) >= 0
        # 分布为空 -> 返回 0.0
        monkeypatch.setattr(
            DrawAnalyzer, "consecutive_count_distribution",
            lambda self, last_n=None: {},
        )
        assert s._compute_target_consecutive(DrawAnalyzer(_kl8_records(50), KL8), 50) == 0.0

    def test_compute_target_overlap(self):
        s = KL8BalancedStrategy()
        analyzer = DrawAnalyzer(_kl8_records(50), KL8)
        assert s._compute_target_overlap(analyzer, 50) >= 0
        # 仅 1 条记录 -> 返回 5.0
        assert s._compute_target_overlap(DrawAnalyzer(_kl8_records(1), KL8), 50) == 5.0

    def test_get_prev_numbers(self):
        s = KL8BalancedStrategy()
        assert s._get_prev_numbers(_kl8_records(50))
        assert s._get_prev_numbers([]) == []

    def test_score_candidate(self):
        s = KL8BalancedStrategy()
        w = (0.15, 0.15, 0.20, 0.20, 0.10, 0.10, 0.10)
        # 和值在区间内 + 邻期非空 + 覆盖不足 -> 覆盖 357-358 / 379 / 383-384
        sc1 = s._score_candidate(
            [1, 2, 3, 4, 5], 5, 2, 2, 15.0, 0.0, 80.0,
            [5, 0, 0], 1.0, 3.0, [3, 4, 5, 6, 7],
            *w,
        )
        assert sc1 >= 0
        # 和值超区间 + 邻期为空 -> 覆盖 360-363 / 382 的 False 分支
        sc2 = s._score_candidate(
            [60, 61, 62, 63, 64], 5, 2, 2, 15.0, 0.0, 80.0,
            [0, 0, 5], 1.0, 3.0, [],
            *w,
        )
        assert sc2 >= 0

    def test_guided_sample(self):
        s = KL8BalancedStrategy()
        rng = random.Random(0)
        pool = list(range(1, 81))
        weights = [1.0 / 80] * 80
        # k=1 -> 7 个段 need<=0 -> continue 分支
        out1 = s._guided_sample(rng, pool, weights, 1)
        assert len(out1) == 1
        # k=10 且某段权重全 0 -> total<=0 -> randrange 分支
        w2 = list(weights)
        for i in range(70, 80):
            w2[i] = 0.0
        out2 = s._guided_sample(rng, pool, w2, 10)
        assert len(out2) == 10

    def test_fill_random_other(self, monkeypatch):
        s = KL8BalancedStrategy()
        rng = random.Random(0)
        # 按位附加组
        var_p = LotteryProfile(
            key="kl8", name="kl8", groups=(KL8.primary_group, _extra_group(True)),
            data_url="", parser_key="kl8", draw_weekdays=(),
            storage_file="x", model_prefix="kl8",
        )
        _patch_profile(monkeypatch, kl8_base, kl8_bal, var_p)
        g = {"main": list(range(1, 11))}
        s._fill_random_other(g, rng)
        assert "extra" in g
        # 非按位、非可变附加组
        var_n = LotteryProfile(
            key="kl8", name="kl8", groups=(KL8.primary_group, _extra_group(False, variable_pick=False)),
            data_url="", parser_key="kl8", draw_weekdays=(),
            storage_file="x", model_prefix="kl8",
        )
        _patch_profile(monkeypatch, kl8_base, kl8_bal, var_n)
        g = {"main": list(range(1, 11))}
        s._fill_random_other(g, rng)
        assert "extra" in g
        # 非按位、可变附加组
        var_v = LotteryProfile(
            key="kl8", name="kl8", groups=(KL8.primary_group, _extra_group(False, variable_pick=True)),
            data_url="", parser_key="kl8", draw_weekdays=(),
            storage_file="x", model_prefix="kl8",
        )
        _patch_profile(monkeypatch, kl8_base, kl8_bal, var_v)
        g = {"main": list(range(1, 11))}
        s._fill_random_other(g, rng)
        assert "extra" in g


# --------------------------------------------------------------------------- #
# 快乐8 智能冷热号策略
# --------------------------------------------------------------------------- #
class TestKL8SmartHotColdStrategy:
    def test_validate_options(self):
        s = KL8SmartHotColdStrategy()
        assert "history" in s.get_config_schema()
        with pytest.raises(ValueError):
            s.validate_options({"history": _kl8_records(10)})
        s.validate_options({"history": _kl8_records(30)})

    def test_generate_branches(self, monkeypatch):
        s = KL8SmartHotColdStrategy()
        recs = _kl8_records(50)
        # 均匀历史 -> is_uniform True
        t = s.generate(count=2, options={"history": recs})
        assert len(t) == 2
        assert "is_uniform" in t[0].details
        # 种子 -> _make_rng 带种子分支
        s.generate(count=1, options={"history": recs, "seed": 3})
        # dedup=False
        s.generate(count=2, options={"history": recs, "dedup": False})
        # 显著偏离 -> is_uniform False
        t2 = s.generate(count=1, options={"history": _kl8_records_skewed(50)})
        assert t2[0].details["is_uniform"] is False
        # 兜底（selected 为 None）：强制加权采样恒定 -> 去重碰撞
        monkeypatch.setattr(
            kl8_shc, "weighted_sample_without_replacement",
            lambda rng, values, weights, k: (
                list(range(1, 21)) if k == 20 else [1, 2, 3, 4]
            ),
        )
        # count=2：ticket1 命中，ticket2 恒定撞 seen -> 触发 selected is None 兜底
        s.generate(count=2, options={"history": recs, "dedup": True})

    def test_fill_random_other(self, monkeypatch):
        s = KL8SmartHotColdStrategy()
        rng = random.Random(0)
        var_p = LotteryProfile(
            key="kl8", name="kl8", groups=(KL8.primary_group, _extra_group(True)),
            data_url="", parser_key="kl8", draw_weekdays=(),
            storage_file="x", model_prefix="kl8",
        )
        _patch_profile(monkeypatch, kl8_base, kl8_shc, var_p)
        g = {"main": list(range(1, 11))}
        s._fill_random_other(g, rng)
        assert "extra" in g
        var_n = LotteryProfile(
            key="kl8", name="kl8", groups=(KL8.primary_group, _extra_group(False)),
            data_url="", parser_key="kl8", draw_weekdays=(),
            storage_file="x", model_prefix="kl8",
        )
        _patch_profile(monkeypatch, kl8_base, kl8_shc, var_n)
        g = {"main": list(range(1, 11))}
        s._fill_random_other(g, rng)
        assert "extra" in g


# --------------------------------------------------------------------------- #
# 八卦占卜策略
# --------------------------------------------------------------------------- #
class TestBaguaStrategy:
    def test_metadata_and_schema(self):
        s = BaguaStrategy()
        assert s.metadata.id == "bagua"
        sch = s.get_config_schema()
        assert "method" in sch
        assert "use_ganzhi" in sch

    def test_validate_options(self):
        s = BaguaStrategy()
        s.validate_options({})  # 默认 time 合法
        with pytest.raises(ValueError):
            s.validate_options({"method": "bogus"})

    def test_parse_selected_hours(self):
        s = BaguaStrategy()
        # hour 模式
        assert s._parse_selected_hours(
            {"time_mode": "hour", "selected_hours": "0,1,2"}
        ) == [0, 1, 2]
        assert s._parse_selected_hours(
            {"time_mode": "hour", "selected_hours": ""}
        ) == []
        # shichen 模式（返回按数值排序后的去重小时列表）
        assert s._parse_selected_hours(
            {"time_mode": "shichen", "selected_shichen": "子,丑"}
        ) == [0, 1, 2, 23]
        assert s._parse_selected_hours(
            {"time_mode": "shichen", "selected_shichen": ""}
        ) == []

    def test_get_lucky_hours(self):
        s = BaguaStrategy()
        hrs = s._get_lucky_hours({"lucky_min_score": 60, "lucky_max_count": 6})
        assert isinstance(hrs, list)

    def test_generate_numbers_from_hexagram(self):
        s = BaguaStrategy()
        # 合成卦象结果：可控 yao 以覆盖 yao_numbers 与动爻分支
        hex_ = SimpleNamespace(full_name="乾为天", description="刚健中正", nature="吉")
        trig = SimpleNamespace(name="乾", element="金", nature="健")
        result = SimpleNamespace(
            hexagram=hex_, method="time", time_str="2024-01-01 00:00",
            upper_trigram=trig, lower_trigram=trig,
            yao=[1, 2, 3, 4, 1, 2], changed_hexagram=None,
        )
        # 四个号码组覆盖分支：按位 / 非按位可重复 / 非按位不可重复 / 可变选号
        # 号池放大至 0-20、count=15，确保基础数字不足以填满 -> while 补随机必然执行
        g1 = NumberGroup("a", "a", 0, 20, 15, positional=True, allow_repeat=True, is_primary=True)
        g2 = NumberGroup("b", "b", 0, 20, 15, positional=False, allow_repeat=True)
        g3 = NumberGroup("c", "c", 0, 20, 15, positional=False, allow_repeat=False)
        g4 = NumberGroup("d", "d", 0, 20, 15, positional=False, allow_repeat=False, pick_min=1, pick_max=20)
        prof = LotteryProfile(
            key="bag", name="bag", groups=(g1, g2, g3, g4),
            data_url="", parser_key="bag", draw_weekdays=(),
            storage_file="x", model_prefix="bag",
        )
        rng = random.Random(0)
        nums = s._generate_numbers_from_hexagram(result, prof, True, rng)
        assert {"a", "b", "c", "d"} <= set(nums)
        # use_ganzhi=False 分支（跳过天干地支影响块）
        nums2 = s._generate_numbers_from_hexagram(result, prof, False, rng)
        assert "a" in nums2

    def test_generate_methods(self):
        s = BaguaStrategy()
        # 时间起卦（单次）
        s.generate(count=2, options={})
        # 随机起卦（带种子 / 不带种子）
        s.generate(count=2, options={"method": "random", "seed": 1})
        s.generate(count=1, options={"method": "random"})
        # 批量时间起卦（按时辰）
        s.generate(count=1, options={"method": "time_batch", "selected_shichen": "子"})
        # 批量时间起卦（空选中 -> 回退当前小时）
        s.generate(count=1, options={"method": "time_batch"})
        # 自动吉时
        s.generate(count=1, options={"method": "time_lucky"})
        # use_ganzhi=False
        s.generate(count=1, options={"method": "time", "use_ganzhi": False})

    def test_build_ticket_changed_hexagram(self):
        s = BaguaStrategy()
        hex_ = SimpleNamespace(full_name="乾", description="d", nature="吉")
        trig = SimpleNamespace(name="乾", element="金", nature="健")
        res_no = SimpleNamespace(
            hexagram=hex_, method="m", time_str="t", upper_trigram=trig,
            lower_trigram=trig, nature="吉", description="d", changed_hexagram=None,
        )
        res_yes = SimpleNamespace(
            hexagram=hex_, method="m", time_str="t", upper_trigram=trig,
            lower_trigram=trig, nature="吉", description="d", changed_hexagram=hex_,
        )
        t1 = s._build_ticket(
            SSQ, {"red": [1, 2, 3, 4, 5, 6], "blue": [7]}, res_no, {}
        )
        t2 = s._build_ticket(
            SSQ, {"red": [1, 2, 3, 4, 5, 6], "blue": [7]}, res_yes, {}
        )
        assert t1 is not None and t2 is not None
