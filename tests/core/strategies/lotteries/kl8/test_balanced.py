"""快乐8历史均衡策略测试."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from caipiao.core.strategies.lotteries.kl8.balanced import (
    KL8BalancedStrategy,
    _coverage_score,
    _consecutive_pairs,
    _compute_overlap_with_prev,
    _zone_counts,
    std_sum_if_nonzero,
)
from caipiao.data.models import DrawRecord


def _make_kl8_records(count: int = 100) -> List[DrawRecord]:
    """创建测试用的快乐8记录."""
    records = []
    for i in range(count):
        # 生成 20 个不重复的 1-80 号码
        nums = sorted([(i * 7 + j * 3) % 80 + 1 for j in range(20)])
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="kl8",
            groups={"main": nums},
        ))
    return records


class TestKL8BalancedStrategyHelpers:
    """辅助函数测试."""

    def test_zone_counts(self):
        nums = [1, 10, 27, 28, 30, 54, 55, 80]  # 各区各两个
        counts = _zone_counts(nums)
        # Zone1(1-27): 1,10,27=3; Zone2(28-54): 28,30,54=3; Zone3(55-80): 55,80=2
        assert counts == [3, 3, 2]

    def test_zone_counts_boundaries(self):
        # 区域边界
        assert _zone_counts([1]) == [1, 0, 0]
        assert _zone_counts([27]) == [1, 0, 0]
        assert _zone_counts([28]) == [0, 1, 0]
        assert _zone_counts([54]) == [0, 1, 0]
        assert _zone_counts([55]) == [0, 0, 1]
        assert _zone_counts([80]) == [0, 0, 1]

    def test_consecutive_pairs(self):
        assert _consecutive_pairs([1, 2, 3, 5, 7, 8]) == 3  # (1,2), (2,3), (7,8)
        assert _consecutive_pairs([1, 3, 5, 7]) == 0
        assert _consecutive_pairs([1, 2]) == 1
        assert _consecutive_pairs([]) == 0

    def test_coverage_score(self):
        # 覆盖 8 个段 -> score 1.0
        nums = [1, 11, 21, 31, 41, 51, 61, 71]
        assert _coverage_score(nums) == 1.0
        # 只覆盖 1 个段
        nums = [1, 2, 3, 4, 5]
        assert _coverage_score(nums) == 1/8
        # 空列表
        assert _coverage_score([]) == 0.0

    def test_compute_overlap_with_prev(self):
        candidate = [1, 2, 3, 4, 5]
        prev = [3, 4, 5, 6, 7]
        assert _compute_overlap_with_prev(candidate, prev) == 3
        assert _compute_overlap_with_prev([1, 2], [3, 4]) == 0
        assert _compute_overlap_with_prev([], [1, 2]) == 0

    def test_std_sum_if_nonzero(self):
        assert std_sum_if_nonzero(100, 90, 110) == pytest.approx(20/6)
        assert std_sum_if_nonzero(100, 100, 100) == 1.0  # 零范围返回 1.0


class TestKL8BalancedStrategy:
    """KL8BalancedStrategy 测试."""

    def test_metadata(self):
        strategy = KL8BalancedStrategy()
        assert strategy.metadata.id == "balanced_kl8"
        assert strategy.metadata.name == "历史均衡"
        assert strategy.metadata.configurable is True
        assert strategy._needs_history is True

    def test_get_config_schema(self):
        strategy = KL8BalancedStrategy()
        schema = strategy.get_config_schema()
        assert "history" in schema
        assert "lookback" in schema
        assert "max_attempts" in schema
        assert "w_odd_even" in schema
        assert "w_high_low" in schema
        assert "w_sum" in schema
        assert "w_zone" in schema
        assert "w_consec" in schema
        assert "w_coverage" in schema
        assert "w_overlap" in schema
        assert "seed" in schema
        # kl8 可变 pick
        assert "pick_count" in schema
        assert schema["pick_count"]["choices"] == list(range(1, 11))

    def test_validate_options_insufficient_history(self):
        strategy = KL8BalancedStrategy()
        with pytest.raises(ValueError, match="至少 20 期历史数据"):
            strategy.validate_options({"history": []})

    def test_generate_basic(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        tickets = strategy.generate(count=3, options={"history": records, "lookback": 50, "pick_count": 5})
        assert len(tickets) == 3
        for ticket in tickets:
            assert ticket.profile.key == "kl8"
            assert "main" in ticket.groups
            assert len(ticket.groups["main"]) == 5
            assert ticket.strategy_name == "历史均衡"
            assert "历史均衡" in ticket.basis

    def test_generate_with_seed(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        options = {"history": records, "lookback": 50, "pick_count": 5, "seed": 42}
        t1 = strategy.generate(count=2, options=options)
        t2 = strategy.generate(count=2, options=options)
        for a, b in zip(t1, t2):
            assert a.groups == b.groups

    def test_generate_different_seeds(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        t1 = strategy.generate(count=2, options={"history": records, "pick_count": 5, "seed": 1})
        t2 = strategy.generate(count=2, options={"history": records, "pick_count": 5, "seed": 2})
        all_same = all(a.groups == b.groups for a, b in zip(t1, t2))
        assert not all_same or len(t1) == 0

    def test_generate_pick_count(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        for pick in [1, 3, 5, 8, 10]:
            tickets = strategy.generate(count=2, options={"history": records, "pick_count": pick})
            for ticket in tickets:
                assert len(ticket.groups["main"]) == pick

    def test_generate_invalid_pick_count_clamped(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        # < min -> clamped to 1
        tickets = strategy.generate(count=1, options={"history": records, "pick_count": 0})
        assert len(tickets[0].groups["main"]) == 1
        # > max -> clamped to 10
        tickets = strategy.generate(count=1, options={"history": records, "pick_count": 20})
        assert len(tickets[0].groups["main"]) == 10

    def test_generate_weighted_score(self):
        """验证自定义权重能生成有效号码."""
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        tickets = strategy.generate(count=5, options={
            "history": records, "pick_count": 5,
            "w_odd_even": 50, "w_high_low": 50, "w_sum": 50,
            "w_zone": 50, "w_consec": 50, "w_coverage": 50, "w_overlap": 50,
        })
        for ticket in tickets:
            assert len(ticket.groups["main"]) == 5
            assert all(1 <= n <= 80 for n in ticket.groups["main"])

    def test_generate_details_in_ticket(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        tickets = strategy.generate(count=1, options={"history": records, "pick_count": 5})
        assert "chi_square" in tickets[0].details
        assert "is_uniform" in tickets[0].details
        assert "target_odd" in tickets[0].details
        assert "target_zones" in tickets[0].details

    def test_compute_target_zones(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        from caipiao.data.analyzer import DrawAnalyzer
        from caipiao.core.profile import get_profile
        analyzer = DrawAnalyzer(records, get_profile("kl8"))
        targets = strategy._compute_target_zones(analyzer, lookback=50, pick=5)
        assert len(targets) == 3
        assert sum(targets) >= 5  # 总和接近 pick
        assert all(t >= 1 for t in targets)

    def test_compute_target_consecutive(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        from caipiao.data.analyzer import DrawAnalyzer
        from caipiao.core.profile import get_profile
        analyzer = DrawAnalyzer(records, get_profile("kl8"))
        target = strategy._compute_target_consecutive(analyzer, lookback=50)
        assert target >= 0

    def test_compute_target_overlap(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(100)
        from caipiao.data.analyzer import DrawAnalyzer
        from caipiao.core.profile import get_profile
        analyzer = DrawAnalyzer(records, get_profile("kl8"))
        target = strategy._compute_target_overlap(analyzer, lookback=50)
        assert target >= 0


class TestKL8BalancedStrategyEdgeCases:
    """边界情况测试."""

    def test_generate_insufficient_history_raises(self):
        strategy = KL8BalancedStrategy()
        records = _make_kl8_records(10)
        with pytest.raises(ValueError, match="至少 20 期"):
            strategy.generate(count=1, options={"history": records})

    def test_generate_empty_history_raises(self):
        strategy = KL8BalancedStrategy()
        with pytest.raises(ValueError, match="至少 20 期"):
            strategy.generate(count=1, options={"history": []})

    def test_score_candidate_zero_score_possible(self):
        """测试评分函数能产生合理分数."""
        strategy = KL8BalancedStrategy()
        # 不实际运行完整流程，只验证评分逻辑不报错
        score = strategy._score_candidate(
            candidate=[1, 2, 3, 4, 5],
            pick=5,
            target_odd=2, target_high=3,
            avg_sum=200, sum_min=150, sum_max=250,
            target_zones=[2, 2, 1], target_consec=1.0, target_overlap=3.0,
            prev_numbers=[3, 4, 5, 6, 7],
            w_oe=0.15, w_hl=0.15, w_sm=0.20, w_zn=0.20, w_cc=0.10, w_cv=0.10, w_ov=0.10,
        )
        assert score >= 0