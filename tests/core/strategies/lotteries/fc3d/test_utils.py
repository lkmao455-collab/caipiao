"""福彩3D工具函数测试."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from caipiao.core.strategies.lotteries.fc3d.utils import (
    assign_fc3d_bet_modes,
    fc3d_bet_type,
    overall_high_low_ratio,
    overall_odd_even_ratio,
    positional_frequency,
    positional_weights,
    road_012_statistics,
    shape_ratio,
    span_statistics,
    sum_statistics,
    sum_tail_statistics,
)
from caipiao.data.models import DrawRecord


def _make_fc3d_records(count: int = 100) -> list:
    """创建测试用的福彩3D记录."""
    records = []
    for i in range(count):
        nums = [(i + j) % 10 for j in range(3)]
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": nums},
        ))
    return records


class TestSliceRecords:
    """_slice_records 内部函数测试（通过公开接口间接测试）."""

    def test_positional_frequency_empty(self):
        freq = positional_frequency([], lookback=10)
        assert freq == {0: {}, 1: {}, 2: {}}

    def test_positional_frequency_lookback_none(self):
        records = _make_fc3d_records(50)
        freq = positional_frequency(records, lookback=None)
        # 全部记录
        for pos in range(3):
            assert sum(freq[pos].values()) == 50

    def test_positional_frequency_lookback_limits(self):
        records = _make_fc3d_records(100)
        freq = positional_frequency(records, lookback=10)
        for pos in range(3):
            assert sum(freq[pos].values()) == 10

    def test_positional_frequency_zero_lookback(self):
        records = _make_fc3d_records(50)
        freq = positional_frequency(records, lookback=0)
        for pos in range(3):
            assert sum(freq[pos].values()) == 0


class TestPositionalFrequency:
    """positional_frequency 测试."""

    def test_basic(self):
        records = _make_fc3d_records(30)
        freq = positional_frequency(records, lookback=30)
        # 每位每个数字出现 3 次（0-9 循环）
        for pos in range(3):
            for d in range(10):
                assert freq[pos].get(d, 0) == 3

    def test_partial_lookback(self):
        records = _make_fc3d_records(30)
        freq = positional_frequency(records, lookback=10)
        for pos in range(3):
            assert sum(freq[pos].values()) == 10


class TestPositionalWeights:
    """positional_weights 测试."""

    def test_weights_sum_to_one(self):
        records = _make_fc3d_records(100)
        weights = positional_weights(records, lookback=100)
        for pos in range(3):
            assert sum(weights[pos]) == pytest.approx(1.0, rel=1e-5)

    def test_smoothing_effect(self):
        records = _make_fc3d_records(30)
        w_smooth = positional_weights(records, lookback=30, smoothing=10.0)
        w_no_smooth = positional_weights(records, lookback=30, smoothing=0.001)
        # 大平滑 -> 更接近均匀分布
        var_smooth = sum((x - 0.1) ** 2 for x in w_smooth[0])
        var_no_smooth = sum((x - 0.1) ** 2 for x in w_no_smooth[0])
        assert var_smooth < var_no_smooth


class TestSumTailStatistics:
    """sum_tail_statistics 测试."""

    def test_empty_records(self):
        stats = sum_tail_statistics([], lookback=10)
        assert stats == {"min": 0, "max": 0, "avg": 0, "median": 0}

    def test_valid(self):
        records = _make_fc3d_records(30)
        stats = sum_tail_statistics(records, lookback=30)
        assert "min" in stats and "max" in stats and "avg" in stats and "median" in stats
        assert 0 <= stats["min"] <= 9
        assert 0 <= stats["max"] <= 9


class TestSpanStatistics:
    """span_statistics 测试."""

    def test_empty(self):
        stats = span_statistics([], lookback=10)
        assert stats == {"min": 0, "max": 0, "avg": 0, "median": 0}

    def test_valid(self):
        records = _make_fc3d_records(30)
        stats = span_statistics(records, lookback=30)
        assert 0 <= stats["min"] <= 9
        assert 0 <= stats["max"] <= 9


class TestRoad012Statistics:
    """road_012_statistics 测试."""

    def test_empty(self):
        stats = road_012_statistics([], lookback=10)
        assert stats == {0: [1/3, 1/3, 1/3], 1: [1/3, 1/3, 1/3], 2: [1/3, 1/3, 1/3]}

    def test_valid(self):
        records = _make_fc3d_records(30)
        stats = road_012_statistics(records, lookback=30)
        for pos in range(3):
            p = stats[pos]
            assert len(p) == 3
            assert sum(p) == pytest.approx(1.0, rel=1e-5)
            for prob in p:
                assert 0 <= prob <= 1


class TestFc3dBetType:
    """fc3d_bet_type 测试."""

    def test_leopard(self):
        assert fc3d_bet_type([1, 1, 1]) == "豹子号"
        assert fc3d_bet_type([5, 5, 5]) == "豹子号"

    def test_group3(self):
        assert fc3d_bet_type([1, 1, 2]) == "组选3"
        assert fc3d_bet_type([3, 3, 3]) == "豹子号"  # 先判断豹子
        assert fc3d_bet_type([5, 5, 7]) == "组选3"

    def test_group6(self):
        assert fc3d_bet_type([1, 2, 3]) == "组选6"
        assert fc3d_bet_type([0, 5, 9]) == "组选6"

    def test_invalid_length(self):
        assert fc3d_bet_type([1, 2]) == "未知"
        assert fc3d_bet_type([1, 2, 3, 4]) == "未知"


class TestShapeRatio:
    """shape_ratio 测试."""

    def test_empty_returns_theoretical(self):
        stats = shape_ratio([], lookback=10)
        assert stats == {"leopard": 0.01, "group3": 0.27, "group6": 0.72}

    def test_with_records(self):
        # 生成包含各种形态的记录
        import random
        records = []
        for i in range(1000):
            r = random.random()
            if r < 0.01:
                nums = [i % 10] * 3  # 豹子
            elif r < 0.28:
                a = i % 10
                b = (i + 1) % 10
                if a == b:
                    b = (b + 1) % 10
                nums = [a, a, b]  # 组选3
            else:
                nums = [(i + j) % 10 for j in range(3)]
                if len(set(nums)) < 3:
                    nums = [0, 1, 2]  # 确保组选6
            records.append(DrawRecord(
                issue=f"2024{i + 1:03d}",
                draw_date=datetime(2024, 1, 1) + timedelta(days=i),
                profile="3d",
                groups={"pos": nums},
            ))
        stats = shape_ratio(records, lookback=1000)
        assert sum(stats.values()) == pytest.approx(1.0, rel=1e-5)
        # 接近理论值
        assert abs(stats["leopard"] - 0.01) < 0.02
        assert abs(stats["group3"] - 0.27) < 0.05
        assert abs(stats["group6"] - 0.72) < 0.05


class TestOverallOddEvenRatio:
    """overall_odd_even_ratio 测试."""

    def test_empty(self):
        odd, even = overall_odd_even_ratio([], lookback=10)
        assert odd == 0.5 and even == 0.5

    def test_valid(self):
        records = _make_fc3d_records(30)
        odd, even = overall_odd_even_ratio(records, lookback=30)
        assert odd + even == pytest.approx(1.0, rel=1e-5)
        assert 0 <= odd <= 1
        assert 0 <= even <= 1


class TestOverallHighLowRatio:
    """overall_high_low_ratio 测试."""

    def test_empty(self):
        high, low = overall_high_low_ratio([], lookback=10)
        assert high == 0.5 and low == 0.5

    def test_valid(self):
        records = _make_fc3d_records(30)
        high, low = overall_high_low_ratio(records, lookback=30, border=5)
        assert high + low == pytest.approx(1.0, rel=1e-5)
        assert 0 <= high <= 1
        assert 0 <= low <= 1


class TestSumStatistics:
    """sum_statistics 测试."""

    def test_empty(self):
        stats = sum_statistics([], lookback=10)
        assert stats == {"min": 0, "max": 0, "avg": 0, "median": 0}

    def test_valid(self):
        records = _make_fc3d_records(30)
        stats = sum_statistics(records, lookback=30)
        assert 0 <= stats["min"] <= 27
        assert 0 <= stats["max"] <= 27


class TestAssignFc3dBetModes:
    """assign_fc3d_bet_modes 测试."""

    def test_assign_modes(self):
        # 使用简单对象模拟 ticket
        class MockTicket:
            def __init__(self, nums):
                self.groups = {"pos": nums}
                self.details = {}

        tickets = [
            MockTicket([1, 2, 3]),  # 组选6
            MockTicket([4, 4, 5]),  # 组选3
            MockTicket([6, 6, 6]),  # 豹子号
            MockTicket([7, 8, 9]),  # 组选6
        ]
        result = assign_fc3d_bet_modes(tickets)
        assert len(result) == 4
        # N=4 -> zu_count=2, 前2张组选（除豹子）
        assert tickets[0].details["bet_mode"] == "组选"  # 组选6
        assert tickets[1].details["bet_mode"] == "组选"  # 组选3
        # 第3张是豹子号，虽然在前2但会被改为直选
        assert tickets[2].details["bet_mode"] == "直选"
        assert tickets[3].details["bet_mode"] == "直选"

    def test_single_ticket(self):
        class MockTicket:
            def __init__(self, nums):
                self.groups = {"pos": nums}
                self.details = {}

        tickets = [MockTicket([1, 2, 3])]
        assign_fc3d_bet_modes(tickets)
        assert tickets[0].details["bet_mode"] == "组选"

    def test_two_tickets(self):
        class MockTicket:
            def __init__(self, nums):
                self.groups = {"pos": nums}
                self.details = {}

        tickets = [MockTicket([1, 1, 1]), MockTicket([2, 3, 4])]
        assign_fc3d_bet_modes(tickets)
        # zu_count = 1, 第1张是豹子 -> 直选, 第2张 -> 直选
        assert tickets[0].details["bet_mode"] == "直选"
        assert tickets[1].details["bet_mode"] == "直选"

    def test_leopard_in_zu_section(self):
        """豹子号在组选区间时应自动改为直选."""
        class MockTicket:
            def __init__(self, nums):
                self.groups = {"pos": nums}
                self.details = {}

        tickets = [
            MockTicket([1, 1, 1]),  # 豹子，位置 0 < zu_count(2)
            MockTicket([2, 2, 3]),  # 组选3
            MockTicket([4, 5, 6]),  # 组选6
        ]
        assign_fc3d_bet_modes(tickets)
        # N=3, zu_count=2, 前2张标组选但豹子改直选
        assert tickets[0].details["bet_mode"] == "直选"  # 豹子
        assert tickets[1].details["bet_mode"] == "组选"  # 组选3
        assert tickets[2].details["bet_mode"] == "直选"  # 剩余直选