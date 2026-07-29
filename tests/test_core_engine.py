"""Core Engine 过滤函数单元测试."""

from datetime import datetime, timedelta

import pytest

from caipiao.core.engine import (
    filter_ssq_by_history,
    filter_fc3d_by_history,
    filter_dlt_by_history,
    estimate_fc3d_pass_count,
    fc3d_filtered_gen_count,
    estimate_dlt_pass_ratio,
    dlt_filtered_gen_count,
)
from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord


# ---- Helpers ----

def _make_ssq_draw(reds, blue, days_ago=0):
    return DrawRecord(
        issue=f"2024001",
        draw_date=datetime(2024, 1, 1) + timedelta(days=days_ago),
        red_balls=reds,
        blue_ball=blue,
    )


def _make_ssq_ticket(reds, blue):
    return Ticket(red_balls=reds, blue_ball=blue)


def _make_3d_draw(nums, days_ago=0):
    return DrawRecord(
        issue=f"2024001",
        draw_date=datetime(2024, 1, 1) + timedelta(days=days_ago),
        profile="3d",
        groups={"pos": nums},
    )


def _make_3d_ticket(nums):
    return Ticket(profile="3d", groups={"pos": nums})


def _make_dlt_draw(front, back, days_ago=0):
    return DrawRecord(
        issue=f"2024001",
        draw_date=datetime(2024, 1, 1) + timedelta(days=days_ago),
        profile="dlt",
        groups={"front": front, "back": back},
    )


def _make_dlt_ticket(front, back):
    return Ticket(profile="dlt", groups={"front": front, "back": back})


# ---- SSQ Filter Tests ----

class TestFilterSSQByHistory:
    """双色球历史过滤测试."""

    def test_empty_tickets(self):
        result = filter_ssq_by_history([], [])
        assert result == []

    def test_empty_records(self):
        t1 = _make_ssq_ticket([1, 2, 3, 4, 5, 6], 7)
        result = filter_ssq_by_history([t1], [])
        assert len(result) == 1

    def test_no_overlap_keeps(self):
        hist = _make_ssq_draw([10, 11, 12, 13, 14, 15], 1, days_ago=0)
        t1 = _make_ssq_ticket([1, 2, 3, 4, 5, 6], 7)
        result = filter_ssq_by_history([t1], [hist], compare_periods=1, max_red_overlap=3)
        assert len(result) == 1

    def test_high_overlap_discarded(self):
        hist = _make_ssq_draw([1, 2, 3, 4, 5, 6], 7, days_ago=0)
        t1 = _make_ssq_ticket([1, 2, 3, 4, 5, 6], 7)
        result = filter_ssq_by_history([t1], [hist], compare_periods=1, max_red_overlap=3)
        assert len(result) == 0

    def test_exactly_at_limit_keeps(self):
        hist = _make_ssq_draw([1, 2, 3, 10, 11, 12], 7, days_ago=0)
        t1 = _make_ssq_ticket([1, 2, 3, 4, 5, 6], 7)
        result = filter_ssq_by_history([t1], [hist], compare_periods=1, max_red_overlap=3)
        assert len(result) == 1

    def test_one_over_limit_discards(self):
        hist = _make_ssq_draw([1, 2, 3, 4, 10, 11], 7, days_ago=0)
        t1 = _make_ssq_ticket([1, 2, 3, 4, 5, 6], 7)
        result = filter_ssq_by_history([t1], [hist], compare_periods=1, max_red_overlap=3)
        assert len(result) == 0

    def test_blue_block(self):
        hist = _make_ssq_draw([10, 11, 12, 13, 14, 15], 7, days_ago=0)
        t1 = _make_ssq_ticket([1, 2, 3, 4, 5, 6], 7)
        result = filter_ssq_by_history(
            [t1], [hist], compare_periods=1, max_red_overlap=3,
            block_blue_match=True, blue_compare_periods=1,
        )
        assert len(result) == 0

    def test_blue_no_block(self):
        hist = _make_ssq_draw([10, 11, 12, 13, 14, 15], 7, days_ago=0)
        t1 = _make_ssq_ticket([1, 2, 3, 4, 5, 6], 7)
        result = filter_ssq_by_history(
            [t1], [hist], compare_periods=1, max_red_overlap=3,
            block_blue_match=False,
        )
        assert len(result) == 1

    def test_compare_periods_zero_no_filter(self):
        hist = _make_ssq_draw([1, 2, 3, 4, 5, 6], 7, days_ago=0)
        t1 = _make_ssq_ticket([1, 2, 3, 4, 5, 6], 7)
        result = filter_ssq_by_history([t1], [hist], compare_periods=0)
        assert len(result) == 1

    def test_multiple_histories(self):
        h1 = _make_ssq_draw([1, 2, 3, 10, 11, 12], 7, days_ago=0)
        h2 = _make_ssq_draw([1, 2, 10, 11, 12, 13], 7, days_ago=1)
        t1 = _make_ssq_ticket([1, 2, 3, 4, 5, 6], 7)
        result = filter_ssq_by_history([t1], [h1, h2], compare_periods=2, max_red_overlap=3)
        assert len(result) == 1


# ---- FC3D Filter Tests ----

class TestFilterFC3DByHistory:
    """福彩3D 经验策略过滤测试."""

    def test_empty_tickets(self):
        result = filter_fc3d_by_history([], [])
        assert result == []

    def test_empty_records(self):
        t1 = _make_3d_ticket([1, 2, 3])
        result = filter_fc3d_by_history([t1], [])
        assert len(result) == 1

    def test_no_overlap_keeps(self):
        hist = _make_3d_draw([4, 5, 6], days_ago=0)
        t1 = _make_3d_ticket([1, 2, 3])
        result = filter_fc3d_by_history([t1], [hist], compare_periods=1, max_overlap=1)
        assert len(result) == 1

    def test_overlap_discards(self):
        hist = _make_3d_draw([1, 2, 3], days_ago=0)
        t1 = _make_3d_ticket([1, 2, 3])
        result = filter_fc3d_by_history([t1], [hist], compare_periods=1, max_overlap=1)
        assert len(result) == 0

    def test_sum_too_high(self):
        t1 = _make_3d_ticket([9, 9, 9])
        result = filter_fc3d_by_history([t1], [], min_sum=0, max_sum=20)
        assert len(result) == 0

    def test_sum_too_low(self):
        t1 = _make_3d_ticket([0, 0, 0])
        result = filter_fc3d_by_history([t1], [], min_sum=5, max_sum=27)
        assert len(result) == 0

    def test_multiset_intersection(self):
        """112 vs 123 -> {1:1, 2:1} -> 2 个相同."""
        hist = _make_3d_draw([1, 2, 3], days_ago=0)
        t1 = _make_3d_ticket([1, 1, 2])
        result = filter_fc3d_by_history([t1], [hist], compare_periods=1, max_overlap=1)
        assert len(result) == 0

    def test_compare_periods_zero_no_history_filter(self):
        hist = _make_3d_draw([1, 2, 3], days_ago=0)
        t1 = _make_3d_ticket([1, 2, 3])
        result = filter_fc3d_by_history([t1], [hist], compare_periods=0, max_overlap=1)
        assert len(result) == 1


class TestEstimateFC3DPassCount:
    """3D 通过率估算测试."""

    def test_no_filter_returns_1000(self):
        count = estimate_fc3d_pass_count([], compare_periods=0, max_overlap=1)
        assert count == 1000

    def test_strict_filter_reduces(self):
        hist = _make_3d_draw([5, 5, 5], days_ago=0)
        count = estimate_fc3d_pass_count([hist], compare_periods=1, max_overlap=1)
        assert count < 1000
        assert count > 0

    def test_range_bounds(self):
        count = estimate_fc3d_pass_count([], compare_periods=0, max_overlap=1, min_sum=0, max_sum=27)
        assert count == 1000

    def test_sum_range_reduces(self):
        count = estimate_fc3d_pass_count([], compare_periods=0, max_overlap=1, min_sum=10, max_sum=17)
        assert count < 1000


class TestFC3DFilteredGenCount:
    """3D 自适应候选数量测试."""

    def test_returns_positive(self):
        gen, pass_count = fc3d_filtered_gen_count(5, [], compare_periods=0, max_overlap=1)
        assert gen > 0
        assert pass_count == 1000

    def test_gen_count_at_least_3x(self):
        gen, _ = fc3d_filtered_gen_count(5, [], compare_periods=0, max_overlap=1)
        assert gen >= 5 * 3

    def test_gen_count_minimum_3x(self):
        gen, _ = fc3d_filtered_gen_count(1000, [], compare_periods=0, max_overlap=1)
        assert gen >= 1000 * 3



# ---- DLT Filter Tests ----

class TestFilterDLTByHistory:
    """大乐透历史过滤测试."""

    def test_empty_tickets(self):
        result = filter_dlt_by_history([], [])
        assert result == []

    def test_empty_records(self):
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history([t1], [])
        assert len(result) == 1

    def test_no_overlap_keeps(self):
        hist = _make_dlt_draw([10, 11, 12, 13, 14], [8, 9], days_ago=0)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history([t1], [hist], compare_periods=1, max_front_overlap=2)
        assert len(result) == 1

    def test_high_overlap_discarded(self):
        hist = _make_dlt_draw([1, 2, 3, 4, 5], [1, 2], days_ago=0)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history([t1], [hist], compare_periods=1, max_front_overlap=2)
        assert len(result) == 0

    def test_exactly_at_limit_keeps(self):
        hist = _make_dlt_draw([1, 2, 10, 11, 12], [8, 9], days_ago=0)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history([t1], [hist], compare_periods=1, max_front_overlap=2)
        assert len(result) == 1

    def test_one_over_limit_discards(self):
        hist = _make_dlt_draw([1, 2, 3, 10, 11], [8, 9], days_ago=0)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history([t1], [hist], compare_periods=1, max_front_overlap=2)
        assert len(result) == 0

    def test_back_block(self):
        hist = _make_dlt_draw([10, 11, 12, 13, 14], [1, 2], days_ago=0)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history(
            [t1], [hist], compare_periods=1, max_front_overlap=2,
            block_back_match=True, back_compare_periods=1,
        )
        assert len(result) == 0

    def test_back_no_block(self):
        hist = _make_dlt_draw([10, 11, 12, 13, 14], [1, 2], days_ago=0)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history(
            [t1], [hist], compare_periods=1, max_front_overlap=2,
            block_back_match=False,
        )
        assert len(result) == 1

    def test_compare_periods_zero_no_filter(self):
        hist = _make_dlt_draw([1, 2, 3, 4, 5], [1, 2], days_ago=0)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history([t1], [hist], compare_periods=0)
        assert len(result) == 1

    def test_multiple_histories(self):
        h1 = _make_dlt_draw([1, 2, 10, 11, 12], [8, 9], days_ago=0)
        h2 = _make_dlt_draw([1, 2, 10, 11, 13], [8, 10], days_ago=1)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history([t1], [h1, h2], compare_periods=2, max_front_overlap=2)
        assert len(result) == 1

    def test_back_partial_match_blocks(self):
        """后区部分匹配也应淘汰."""
        hist = _make_dlt_draw([10, 11, 12, 13, 14], [1, 9], days_ago=0)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [1, 2])
        result = filter_dlt_by_history(
            [t1], [hist], compare_periods=1, max_front_overlap=2,
            block_back_match=True, back_compare_periods=1,
        )
        assert len(result) == 0

    def test_default_no_front_overlap(self):
        """默认 max_front_overlap=0，不允许前区任何重合."""
        hist = _make_dlt_draw([1, 11, 12, 13, 14], [8, 9], days_ago=0)
        t1 = _make_dlt_ticket([1, 2, 3, 4, 5], [10, 11])
        result = filter_dlt_by_history([t1], [hist], compare_periods=1)
        assert len(result) == 0

    def test_default_block_back(self):
        """默认 block_back_match=True，后区相同则淘汰."""
        hist = _make_dlt_draw([10, 11, 12, 13, 14], [1, 2], days_ago=0)
        t1 = _make_dlt_ticket([20, 21, 22, 23, 24], [1, 2])
        result = filter_dlt_by_history([t1], [hist], compare_periods=1)
        assert len(result) == 0


class TestEstimateDLTPassRatio:
    """大乐透通过率估算测试."""

    def test_no_filter_returns_1(self):
        ratio = estimate_dlt_pass_ratio([], compare_periods=0, max_front_overlap=0)
        assert ratio == 1.0

    def test_strict_filter_reduces(self):
        hist = _make_dlt_draw([1, 2, 3, 4, 5], [1, 2], days_ago=0)
        ratio = estimate_dlt_pass_ratio([hist], compare_periods=1, max_front_overlap=2)
        assert ratio < 1.0
        assert ratio > 0.0

    def test_range_bounds(self):
        ratio = estimate_dlt_pass_ratio(
            [], compare_periods=0, max_front_overlap=0,
            min_front_sum=15, max_front_sum=165,
        )
        assert ratio == 1.0

    def test_sum_range_reduces(self):
        ratio = estimate_dlt_pass_ratio(
            [], compare_periods=0, max_front_overlap=0,
            min_front_sum=60, max_front_sum=100,
        )
        assert ratio < 1.0


class TestDLTFilteredGenCount:
    """大乐透自适应候选数量测试."""

    def test_returns_positive(self):
        gen, pass_ratio = dlt_filtered_gen_count(5, [], compare_periods=0, max_front_overlap=0)
        assert gen > 0
        assert pass_ratio == 1.0

    def test_gen_count_at_least_3x(self):
        gen, _ = dlt_filtered_gen_count(5, [], compare_periods=0, max_front_overlap=0)
        assert gen >= 5 * 3

    def test_gen_count_minimum_3x(self):
        gen, _ = dlt_filtered_gen_count(100, [], compare_periods=0, max_front_overlap=0)
        assert gen >= 100 * 3
