# tests/test_fc3d_utils.py
from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import get_profile
from caipiao.data.models import DrawRecord
from caipiao.core.strategies.lotteries.fc3d.utils import (
    positional_frequency,
    positional_weights,
    sum_tail_statistics,
    span_statistics,
    road_012_statistics,
    shape_ratio,
    fc3d_bet_type,
    overall_odd_even_ratio,
    overall_high_low_ratio,
    sum_statistics,
)


def make_records():
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(30)
    ]


def test_positional_frequency():
    records = make_records()
    freq = positional_frequency(records, lookback=10)
    assert 0 in freq and 1 in freq and 2 in freq
    # 第 0 位最近 10 期是 20,21,...,29 的 mod 10，即 0,1,2,...,9,0
    assert sum(freq[0].values()) == 10


def test_positional_weights_smoothing():
    records = make_records()
    weights = positional_weights(records, lookback=10, smoothing=1.0)
    assert len(weights) == 3
    assert len(weights[0]) == 10
    assert all(w > 0 for w in weights[0])


def test_sum_tail_statistics():
    records = make_records()
    stats = sum_tail_statistics(records, lookback=10)
    assert "min" in stats and "max" in stats and "avg" in stats


def test_span_statistics():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [0, 5, 9]}),
    ]
    stats = span_statistics(records)
    assert stats["avg"] == (2 + 9) / 2


def test_road_012_statistics():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [0, 1, 2]}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [3, 4, 5]}),
    ]
    stats = road_012_statistics(records)
    assert len(stats) == 3  # 3个位置
    for pos_stats in stats.values():
        assert sum(pos_stats) == pytest.approx(1.0)


def test_shape_ratio():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 1, 1]}),  # 豹子
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [1, 1, 2]}),  # 组三
        DrawRecord("2024003", datetime(2024, 1, 3), profile="3d", groups={"pos": [1, 2, 3]}),  # 组六
    ]
    ratio = shape_ratio(records)
    assert ratio["leopard"] == pytest.approx(1 / 3)
    assert ratio["group3"] == pytest.approx(1 / 3)
    assert ratio["group6"] == pytest.approx(1 / 3)


def test_fc3d_bet_type():
    assert fc3d_bet_type([1, 1, 1]) == "豹子号"
    assert fc3d_bet_type([1, 1, 2]) == "组选3"
    assert fc3d_bet_type([1, 2, 3]) == "组选6"


def test_overall_odd_even_ratio():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [4, 5, 6]}),
    ]
    odd, even = overall_odd_even_ratio(records)
    assert odd == pytest.approx(3 / 6)
    assert even == pytest.approx(3 / 6)


def test_overall_high_low_ratio():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [4, 5, 6]}),
    ]
    high, low = overall_high_low_ratio(records)
    assert high == pytest.approx(2 / 6)
    assert low == pytest.approx(4 / 6)


def test_sum_statistics():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [4, 5, 6]}),
    ]
    stats = sum_statistics(records)
    assert stats["avg"] == (6 + 15) / 2
    assert stats["min"] == 6
    assert stats["max"] == 15
