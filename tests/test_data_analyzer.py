"""DrawAnalyzer 集成测试."""

from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import SSQ, FC3D, KL8
from caipiao.data.analyzer import DrawAnalyzer, LotteryAnalyzer
from caipiao.data.models import DrawRecord


# ---- Helpers ----

def _make_ssq_records(count=30):
    records = []
    for i in range(count):
        reds = sorted([(i + j) % 33 + 1 for j in range(6)])
        blue = (i % 16) + 1
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=reds,
            blue_ball=blue,
        ))
    return records


def _make_3d_records(count=20):
    records = []
    for i in range(count):
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [i % 10, (i + 1) % 10, (i + 2) % 10]},
        ))
    return records


# ---- Frequency Tests ----

class TestDrawAnalyzerFrequency:
    """频率分析测试."""

    def test_frequency_ssq(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        freq = analyzer.frequency("red")
        assert isinstance(freq, dict)
        assert len(freq) > 0
        assert all(isinstance(k, int) for k in freq.keys())
        assert all(isinstance(v, int) for v in freq.values())

    def test_frequency_last_n(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        freq_all = analyzer.frequency("red")
        freq_10 = analyzer.frequency("red", last_n=10)
        # last_n=10 应该总次数更少
        assert sum(freq_10.values()) < sum(freq_all.values())

    def test_frequency_empty(self):
        analyzer = DrawAnalyzer([], profile=SSQ)
        assert analyzer.frequency("red") == {}


# ---- Hot/Cold Tests ----

class TestDrawAnalyzerHotCold:
    """热冷号测试."""

    def test_hot_returns_list(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        hot = analyzer.hot("red", top_n=5)
        assert isinstance(hot, list)
        assert len(hot) == 5
        assert all(isinstance(n, int) for n in hot)

    def test_cold_returns_list(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        cold = analyzer.cold("red", top_n=5)
        assert isinstance(cold, list)
        assert len(cold) == 5

    def test_hot_cold_different(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        hot = analyzer.hot("red", top_n=5)
        cold = analyzer.cold("red", top_n=5)
        # 热号和冷号不应该完全相同
        assert hot != cold

    def test_cold_invalid_group_raises(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        with pytest.raises(ValueError, match="not found"):
            analyzer.cold("nonexistent")


# ---- Missing Tests ----

class TestDrawAnalyzerMissing:
    """遗漏值测试."""

    def test_missing_returns_list(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        missing = analyzer.missing("red", last_n=30)
        assert isinstance(missing, list)
        assert len(missing) == 33  # 红球 1-33

    def test_missing_values_non_negative(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        missing = analyzer.missing("red")
        assert all(v >= 0 for _, v in missing)

    def test_missing_sorted_descending(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        missing = analyzer.missing("red")
        values = [v for _, v in missing]
        assert values == sorted(values, reverse=True)


# ---- Odd/Even & High/Low Tests ----

class TestDrawAnalyzerRatios:
    """奇偶比和大小比测试."""

    def test_odd_even_ratio(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        odd, even = analyzer.odd_even_ratio()
        assert 0 <= odd <= 1
        assert 0 <= even <= 1
        assert abs(odd + even - 1.0) < 1e-10

    def test_high_low_ratio(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        high, low = analyzer.high_low_ratio()
        assert 0 <= high <= 1
        assert 0 <= low <= 1
        assert abs(high + low - 1.0) < 1e-10

    def test_odd_even_empty(self):
        analyzer = DrawAnalyzer([], profile=SSQ)
        odd, even = analyzer.odd_even_ratio()
        assert odd == 0.5
        assert even == 0.5


# ---- Sum Statistics Tests ----

class TestDrawAnalyzerSum:
    """和值统计测试."""

    def test_sum_statistics(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        stats = analyzer.sum_statistics()
        assert "min" in stats
        assert "max" in stats
        assert "avg" in stats
        assert "median" in stats
        assert stats["min"] <= stats["avg"] <= stats["max"]
        assert stats["min"] <= stats["median"] <= stats["max"]

    def test_sum_statistics_empty(self):
        analyzer = DrawAnalyzer([], profile=SSQ)
        stats = analyzer.sum_statistics()
        assert stats == {"min": 0, "max": 0, "avg": 0, "median": 0}


# ---- Consecutive Tests ----

class TestDrawAnalyzerConsecutive:
    """连号统计测试."""

    def test_consecutive_frequency(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        ratio = analyzer.consecutive_frequency()
        assert 0 <= ratio <= 1

    def test_consecutive_frequency_empty(self):
        analyzer = DrawAnalyzer([], profile=SSQ)
        assert analyzer.consecutive_frequency() == 0.0

    def test_consecutive_count_distribution(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        dist = analyzer.consecutive_count_distribution()
        assert isinstance(dist, dict)
        assert abs(sum(dist.values()) - 1.0) < 1e-10


# ---- Zone Distribution Tests ----

class TestDrawAnalyzerZone:
    """三区分布测试."""

    def test_zone_distribution(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        zones = analyzer.zone_distribution()
        assert "zone1" in zones
        assert "zone2" in zones
        assert "zone3" in zones
        assert abs(sum(zones.values()) - 1.0) < 1e-10

    def test_zone_distribution_empty(self):
        analyzer = DrawAnalyzer([], profile=SSQ)
        zones = analyzer.zone_distribution()
        assert zones == {"zone1": 1 / 3, "zone2": 1 / 3, "zone3": 1 / 3}


# ---- Common Pairs Tests ----

class TestDrawAnalyzerPairs:
    """常见组合测试."""

    def test_common_pairs(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        pairs = analyzer.common_pairs(top_n=5)
        assert isinstance(pairs, list)
        assert len(pairs) <= 5
        for pair, count in pairs:
            assert isinstance(pair, tuple)
            assert len(pair) == 2
            assert isinstance(count, int)


# ---- Positional Frequency (3D) Tests ----

class TestDrawAnalyzerPositional:
    """按位频率测试（3D 专用）."""

    def test_positional_frequency(self):
        records = _make_3d_records(20)
        analyzer = DrawAnalyzer(records, profile=FC3D)
        pf = analyzer.positional_frequency()
        assert isinstance(pf, dict)
        assert 0 in pf  # 百位
        assert 1 in pf  # 十位
        assert 2 in pf  # 个位


# ---- Span Tests ----

class TestDrawAnalyzerSpan:
    """跨度统计测试."""

    def test_span(self):
        records = _make_3d_records(20)
        analyzer = DrawAnalyzer(records, profile=FC3D)
        span = analyzer.span()
        assert "min" in span
        assert "max" in span
        assert "avg" in span
        assert span["min"] <= span["avg"] <= span["max"]


# ---- Summary Tests ----

class TestDrawAnalyzerSummary:
    """综合摘要测试."""

    def test_summary_ssq(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        summary = analyzer.summary()
        assert "total_records" in summary
        assert summary["total_records"] == 30
        assert "hot_reds_30" in summary  # SSQ 兼容字段
        assert "cold_reds_30" in summary
        assert "missing_reds_50" in summary
        assert "hot_blues_30" in summary
        assert "odd_even_ratio" in summary
        assert "high_low_ratio" in summary
        assert "sum_stats" in summary
        assert "consecutive_ratio" in summary

    def test_summary_3d(self):
        records = _make_3d_records(20)
        analyzer = DrawAnalyzer(records, profile=FC3D)
        summary = analyzer.summary()
        assert summary["total_records"] == 20
        assert "hot_30" in summary
        assert "cold_30" in summary


# ---- Last Draw Tests ----

class TestDrawAnalyzerLastDraw:
    """最后一期测试."""

    def test_last_draw(self):
        records = _make_ssq_records(30)
        analyzer = DrawAnalyzer(records, profile=SSQ)
        last = analyzer.last_draw()
        assert last is not None
        assert last.issue == "2024030"

    def test_last_draw_empty(self):
        analyzer = DrawAnalyzer([], profile=SSQ)
        assert analyzer.last_draw() is None


# ---- LotteryAnalyzer Alias Tests ----

class TestLotteryAnalyzerAlias:
    """LotteryAnalyzer 别名兼容性测试."""

    def test_alias_is_class(self):
        assert LotteryAnalyzer is not None

    def test_alias_has_ssq_methods(self):
        records = _make_ssq_records(30)
        analyzer = LotteryAnalyzer(records)
        assert hasattr(analyzer, "red_frequency")
        assert hasattr(analyzer, "blue_frequency")
        assert hasattr(analyzer, "hot_reds")
        assert hasattr(analyzer, "cold_reds")
        assert hasattr(analyzer, "hot_blues")
        assert hasattr(analyzer, "missing_reds")
        assert hasattr(analyzer, "missing_blues")

    def test_alias_red_frequency(self):
        records = _make_ssq_records(30)
        analyzer = LotteryAnalyzer(records)
        freq = analyzer.red_frequency()
        assert isinstance(freq, dict)
        assert len(freq) > 0

    def test_alias_hot_reds(self):
        records = _make_ssq_records(30)
        analyzer = LotteryAnalyzer(records)
        hot = analyzer.hot_reds(top_n=5)
        assert isinstance(hot, list)
        assert len(hot) == 5
