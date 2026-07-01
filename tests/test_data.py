"""数据模块测试."""

from datetime import datetime

from caipiao.data.analyzer import LotteryAnalyzer
from caipiao.data.models import DrawRecord
from caipiao.data.repository import DataRepository


def make_records():
    return [
        DrawRecord("2024001", datetime(2024, 1, 1), [1, 2, 3, 4, 5, 6], 7),
        DrawRecord("2024002", datetime(2024, 1, 3), [1, 2, 3, 10, 11, 12], 8),
        DrawRecord("2024003", datetime(2024, 1, 5), [13, 14, 15, 16, 17, 18], 9),
    ]


def test_red_frequency():
    analyzer = LotteryAnalyzer(make_records())
    freq = analyzer.red_frequency()
    assert freq[1] == 2
    assert freq[18] == 1


def test_hot_cold_reds():
    analyzer = LotteryAnalyzer(make_records())
    hot = analyzer.hot_reds(top_n=3)
    assert 1 in hot
    assert 2 in hot
    cold = analyzer.cold_reds(top_n=3)
    # Numbers never appeared are the coldest
    assert 7 in cold
    assert 8 in cold


def test_missing_reds():
    analyzer = LotteryAnalyzer(make_records())
    missing = dict(analyzer.missing_reds(last_n=3))
    # Number 1 appeared one record ago (not in the latest), so missing = 1
    assert missing[1] == 1
    # Number 4 appeared two records ago, missing = 2
    assert missing[4] == 2
    # Number 7 never appeared, so missing = lookback = 3
    assert missing[7] == 3


def test_odd_even_ratio():
    analyzer = LotteryAnalyzer(make_records())
    odd, even = analyzer.odd_even_ratio()
    assert 0 <= odd <= 1
    assert 0 <= even <= 1
    assert abs(odd + even - 1.0) < 1e-9


def test_sum_statistics():
    analyzer = LotteryAnalyzer(make_records())
    stats = analyzer.sum_statistics()
    assert stats["min"] <= stats["avg"] <= stats["max"]


def test_next_period_info_empty(tmp_path):
    repo = DataRepository(tmp_path / "data.json")
    assert repo.next_period_info() is None


def test_next_period_info_same_year(tmp_path):
    repo = DataRepository(tmp_path / "data.json")
    # 最新一期为周五（2024-01-05），下一期开奖应为周日 2024-01-07
    repo.update(make_records())
    info = repo.next_period_info()
    assert info["base_issue"] == "2024003"
    assert info["next_issue"] == "2024004"
    assert info["next_date"] == datetime(2024, 1, 7)


def test_next_period_info_cross_year(tmp_path):
    repo = DataRepository(tmp_path / "data.json")
    # 2024-12-31 为周二，下一期开奖为 2025-01-02（周四），期号跨年重置为 001
    repo.update([DrawRecord("2024150", datetime(2024, 12, 31), [1, 2, 3, 4, 5, 6], 7)])
    info = repo.next_period_info()
    assert info["next_issue"] == "2025001"
    assert info["next_date"] == datetime(2025, 1, 2)
