"""多彩种统一层单元测试（福彩3D / 七乐彩 / 快乐8 + 双色球兼容）."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from caipiao.core.profile import get_profile, list_profiles
from caipiao.core.strategies import build_strategies, needs_history
from caipiao.core.ticket import Ticket
from caipiao.data.analyzer import DrawAnalyzer, LotteryAnalyzer
from caipiao.data.fetcher import LotteryDataFetcher
from caipiao.data.models import DrawRecord
from caipiao.data.repository import DrawRepository
from caipiao.ml.common.features import build_features
from caipiao.ml.common.base import LotteryGenericModel
from caipiao.ml.common.predictor import BaseMLPredictor as GenericMLPredictor


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #
def test_profile_registry():
    profiles = list_profiles()
    assert {p.key for p in profiles} == {
        "ssq", "3d", "qlc", "kl8",
        "dlt", "pl3", "pl5", "qxc",
    }
    assert get_profile("3d").primary_group.key == "pos"
    assert get_profile("kl8").primary_group.effective_pick_max == 10
    assert get_profile("dlt").category == "sports"
    assert get_profile("ssq").category == "welfare"


def test_group_constraints():
    p3d = get_profile("3d")
    assert p3d.primary_group.allow_repeat
    assert p3d.primary_group.positional
    pkl8 = get_profile("kl8")
    assert pkl8.primary_group.variable_pick


# --------------------------------------------------------------------------- #
# Ticket / DrawRecord 兼容
# --------------------------------------------------------------------------- #
def test_ssq_ticket_legacy():
    t = Ticket([1, 2, 3, 4, 5, 6], 7)
    assert len(t.red_balls) == 6
    assert t.blue_ball.number == 7
    assert t.profile.key == "ssq"
    d = t.to_dict()
    assert "red" in d and "blue" in d
    t2 = Ticket.from_dict(d)
    assert t == t2


def test_3d_ticket_repeatable():
    t = Ticket(profile="3d", groups={"pos": [4, 4, 5]})
    assert t.profile.key == "3d"
    assert t.groups["pos"] == [4, 4, 5]
    assert t.to_dict()["profile"] == "3d"


def test_kl8_ticket_variable_pick():
    t = Ticket(profile="kl8", groups={"main": [3, 15, 27]})
    assert t.profile.key == "kl8"
    assert len(t.groups["main"]) == 3


def test_ssq_drawrecord_legacy():
    r = DrawRecord("2024001", datetime(2024, 1, 1), [1, 2, 3, 4, 5, 6], 7)
    assert r.red_balls == [1, 2, 3, 4, 5, 6]
    assert r.blue_ball == 7
    r2 = DrawRecord.from_dict(r.to_dict())
    assert r == r2


# --------------------------------------------------------------------------- #
# Fetcher 解析器
# --------------------------------------------------------------------------- #
def test_parse_ssq():
    f = LotteryDataFetcher(profile=get_profile("ssq"))
    parts = ["2024001", "2024-01-01"] + [str(i) for i in range(1, 7)] + ["7"]
    rec = f._parse_ssq(parts, "")
    assert rec is not None
    assert rec.red_balls == [1, 2, 3, 4, 5, 6]
    assert rec.blue_ball == 7


def test_parse_3d():
    f = LotteryDataFetcher(profile=get_profile("3d"))
    parts = ["2026172", "2026-07-01", "4", "4", "5"] + ["0"] * 10
    rec = f._parse_3d(parts, "")
    assert rec is not None
    assert rec.groups["pos"] == [4, 4, 5]


def test_parse_qlc():
    f = LotteryDataFetcher(profile=get_profile("qlc"))
    parts = ["2024001", "2024-01-01"] + [str(i) for i in range(1, 8)] + ["30"]
    rec = f._parse_qlc(parts, "")
    assert rec is not None
    assert rec.groups["basic"] == list(range(1, 8))
    assert rec.groups["special"] == [30]


def test_parse_kl8():
    f = LotteryDataFetcher(profile=get_profile("kl8"))
    parts = ["2026172", "2026-07-01"] + [str(i) for i in range(1, 21)]
    rec = f._parse_kl8(parts, "")
    assert rec is not None
    assert len(rec.groups["main"]) == 20


def test_parse_dlt():
    f = LotteryDataFetcher(profile=get_profile("dlt"))
    parts = ["2024001", "2024-01-01"] + [str(i) for i in range(1, 6)] + ["1", "2"]
    rec = f._parse_dlt(parts, "")
    assert rec is not None
    assert rec.groups["front"] == list(range(1, 6))
    assert rec.groups["back"] == [1, 2]


def test_parse_pl3():
    f = LotteryDataFetcher(profile=get_profile("pl3"))
    parts = ["2026172", "2026-07-01", "4", "4", "5"] + ["0"] * 10
    rec = f._parse_pl3(parts, "")
    assert rec is not None
    assert rec.groups["pos"] == [4, 4, 5]


def test_parse_pl5():
    f = LotteryDataFetcher(profile=get_profile("pl5"))
    parts = ["2026172", "2026-07-01", "1", "2", "3", "4", "5"] + ["0"] * 10
    rec = f._parse_pl5(parts, "")
    assert rec is not None
    assert rec.groups["pos"] == [1, 2, 3, 4, 5]


def test_parse_qxc():
    f = LotteryDataFetcher(profile=get_profile("qxc"))
    parts = ["2026172", "2026-07-01", "1", "2", "3", "4", "5", "6", "7"] + ["0"] * 10
    rec = f._parse_qxc(parts, "")
    assert rec is not None
    assert rec.groups["pos"] == [1, 2, 3, 4, 5, 6, 7]


# --------------------------------------------------------------------------- #
# Repository 下一期推算
# --------------------------------------------------------------------------- #
def test_repository_3d_next_daily(tmp_path):
    repo = DrawRepository(tmp_path / "d.json", profile=get_profile("3d"))
    repo.update([DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [0, 1, 2]})])
    info = repo.next_period_info()
    assert info["next_date"] == datetime(2024, 1, 2)


def test_repository_qlc_weekdays(tmp_path):
    repo = DrawRepository(tmp_path / "d.json", profile=get_profile("qlc"))
    # 2024-01-01 是周一
    repo.update([DrawRecord("2024001", datetime(2024, 1, 1), profile="qlc", groups={"basic": list(range(1, 8)), "special": [30]})])
    info = repo.next_period_info()
    # 周一 -> 周三
    assert info["next_date"] == datetime(2024, 1, 3)


# --------------------------------------------------------------------------- #
# Analyzer
# --------------------------------------------------------------------------- #
def make_ssq_records():
    return [
        DrawRecord("2024001", datetime(2024, 1, 1), [1, 2, 3, 4, 5, 6], 7),
        DrawRecord("2024002", datetime(2024, 1, 3), [1, 2, 3, 10, 11, 12], 8),
        DrawRecord("2024003", datetime(2024, 1, 5), [13, 14, 15, 16, 17, 18], 9),
    ]


def test_lottery_analyzer_compat():
    # 旧 API 不变
    analyzer = LotteryAnalyzer(make_ssq_records())
    assert analyzer.red_frequency()[1] == 2
    assert 1 in analyzer.hot_reds(3)
    assert 7 in analyzer.cold_reds(3)
    assert dict(analyzer.missing_reds(3))[7] == 3


def test_generic_analyzer_3d():
    records = [
        DrawRecord(f"2024{i:03d}", datetime(2024, 1, 1) + timedelta(days=i), profile="3d", groups={"pos": [1, 2, 3]})
        for i in range(1, 6)
    ]
    analyzer = DrawAnalyzer(records, get_profile("3d"))
    freq = analyzer.frequency("pos")
    assert freq[1] == 5
    pos_freq = analyzer.positional_frequency()
    assert 0 in pos_freq


def test_generic_analyzer_kl8():
    records = [
        DrawRecord(f"2024{i:03d}", datetime(2024, 1, 1) + timedelta(days=i), profile="kl8", groups={"main": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]})
        for i in range(1, 6)
    ]
    analyzer = DrawAnalyzer(records, get_profile("kl8"))
    assert analyzer.frequency("main")[1] == 5
    assert len(analyzer.missing("main", 5)) == 80


# --------------------------------------------------------------------------- #
# Generic ML
# --------------------------------------------------------------------------- #
def make_ssq_records_ml(count: int = 120):
    records = []
    base = datetime(2024, 1, 1)
    for i in range(count):
        base_offset = (i * 7) % 33
        nums = sorted({((base_offset + j * 13) % 33) + 1 for j in range(6)})
        while len(nums) < 6:
            nums.append(next(n for n in range(1, 34) if n not in nums))
            nums.sort()
        blue = (i * 5 + 3) % 16 + 1
        records.append(
            DrawRecord(
                issue=f"2024{i + 1:03d}",
                draw_date=base,
                red_balls=sorted(nums),
                blue_ball=blue,
            )
        )
    return records


def test_generic_features_ssq_shapes():
    profile = get_profile("ssq")
    records = make_ssq_records_ml(120)
    X, y_dict = build_features(records, profile, lookback=50)
    assert X.shape[0] == 70
    assert y_dict["red"].shape == (70, 33)
    assert y_dict["blue"].shape == (70, 16)


def test_generic_model_ssq_train_predict():
    profile = get_profile("ssq")
    records = make_ssq_records_ml(120)
    X, y_dict = build_features(records, profile, lookback=50)
    model = LotteryGenericModel(profile, lookback=50, backend="xgboost")
    model.fit(X, y_dict)
    proba = model.predict_proba(X[-1].reshape(1, -1))
    assert proba["red"].shape == (33,)
    assert proba["blue"].shape == (16,)


def test_generic_predictor_recommend_ssq():
    profile = get_profile("ssq")
    records = make_ssq_records_ml(120)
    predictor = GenericMLPredictor(records, profile, lookback=50)
    rec = predictor.recommend(group_picks={"red": 6, "blue": 1})
    assert len(rec["red"]) == 6
    assert len(rec["blue"]) == 1


def test_generic_predictor_recommend_3d():
    profile = get_profile("3d")
    records = [
        DrawRecord(f"2024{i:03d}", datetime(2024, 1, 1) + timedelta(days=i), profile="3d", groups={"pos": [(i + j) % 10 for j in range(3)]})
        for i in range(120)
    ]
    predictor = GenericMLPredictor(records, profile, lookback=50)
    rec = predictor.recommend()
    assert len(rec["pos"]) == 3
    assert all(0 <= n <= 9 for n in rec["pos"])


def test_generic_model_positional_missing_classes():
    """按位组训练数据未覆盖全部类别时，不应发出类别数警告，且概率维度保持完整."""
    profile = get_profile("3d")
    # 仅使用 0-8，缺失 9
    records = [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 9 for j in range(3)]},
        )
        for i in range(120)
    ]
    X, y_dict = build_features(records, profile, lookback=50)
    for backend in ("lightgbm", "catboost"):
        model = LotteryGenericModel(profile, lookback=50, backend=backend)
        model.fit(X, y_dict)
        proba = model.predict_proba(X[-1].reshape(1, -1))
        assert proba["pos"].shape == (3, 10)
        # 缺失的类别应保留一个较小的基线概率，而不是 0
        assert np.all(proba["pos"][:, 9] > 0)
        np.testing.assert_array_almost_equal(proba["pos"].sum(axis=1), 1.0, decimal=5)


# --------------------------------------------------------------------------- #
# Generic Strategies
# --------------------------------------------------------------------------- #
def test_generic_random_3d():
    profile = get_profile("3d")
    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    tickets = strategies["random_3d"].generate(count=5)
    assert len(tickets) == 5
    for t in tickets:
        assert len(t.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in t.groups["pos"])


def test_generic_exclude_include_kl8():
    profile = get_profile("kl8")
    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    tickets = strategies["exclude_include_kl8"].generate(
        count=3,
        options={"include_main": [1, 2], "exclude_main": [80]},
    )
    for t in tickets:
        nums = t.groups["main"]
        assert 1 in nums and 2 in nums and 80 not in nums


def test_generic_hot_cold_qlc():
    profile = get_profile("qlc")
    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    history = [
        DrawRecord(f"2024{i:03d}", datetime(2024, 1, 1) + timedelta(days=i), profile="qlc", groups={"basic": list(range(1, 8)), "special": [30]})
        for i in range(30)
    ]
    tickets = strategies["hot_cold_qlc"].generate(count=2, options={"mode": "hot", "history": history})
    assert len(tickets) == 2


# --------------------------------------------------------------------------- #
# DrawAnalysisDialog analysis tests
# --------------------------------------------------------------------------- #
def test_analyze_adjacent_ssq():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), [1, 2, 3, 4, 5, 6], 7),
        DrawRecord("2024002", datetime(2024, 1, 3), [1, 2, 3, 10, 11, 12], 8),
        DrawRecord("2024003", datetime(2024, 1, 5), [13, 14, 15, 16, 17, 18], 9),
        DrawRecord("2024004", datetime(2024, 1, 7), [1, 2, 4, 5, 6, 7], 7),
    ]
    from caipiao.ui.components.draw_analysis_dialog import _analyze_adjacent

    stats, details = _analyze_adjacent(records, get_profile("ssq"))
    assert stats.total_pairs == 3
    assert stats.group_stats["red"].same_counts[3] == 1
    assert stats.group_stats["red"].same_counts[0] == 2
    assert stats.group_stats["blue"].same_counts[0] == 3

    # 间隔 1 期：第 1 期 [1-6] vs 第 3 期 [13-18] = 0 相同
    # 第 2 期 [1,2,3,10,11,12] vs 第 4 期 [1,2,4,5,6,7] = 2 相同
    assert stats.gap_stats["red"][1].total_pairs == 2
    assert stats.gap_stats["red"][1].same_counts[0] == 1
    assert stats.gap_stats["red"][1].same_counts[2] == 1
    assert stats.gap_stats["blue"][1].same_counts[0] == 2

    # 间隔 2 期：第 1 期 vs 第 4 期 [1-6] vs [1,2,4,5,6,7] = 5 相同；蓝球 7 == 7
    assert stats.gap_stats["red"][2].total_pairs == 1
    assert stats.gap_stats["red"][2].same_counts[5] == 1
    assert stats.gap_stats["blue"][2].same_counts[1] == 1

    assert details[1]["red"] == 3
    assert details[1]["blue"] is False


def test_analyze_adjacent_3d():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [1, 2, 4]}),
        DrawRecord("2024003", datetime(2024, 1, 3), profile="3d", groups={"pos": [5, 6, 7]}),
        DrawRecord("2024004", datetime(2024, 1, 4), profile="3d", groups={"pos": [1, 8, 3]}),
    ]
    from caipiao.ui.components.draw_analysis_dialog import _analyze_adjacent

    stats, details = _analyze_adjacent(records, get_profile("3d"))
    assert stats.total_pairs == 3
    assert stats.group_stats["pos"].same_counts[2] == 1
    assert stats.group_stats["pos"].same_counts[0] == 2
    assert details[1]["pos"] == 2

    # 间隔 1 期：第 1 期 [1,2,3] vs 第 3 期 [5,6,7] = 0 相同
    # 第 2 期 [1,2,4] vs 第 4 期 [1,8,3] = 1 相同
    assert stats.gap_stats["pos"][1].same_counts[0] == 1
    assert stats.gap_stats["pos"][1].same_counts[1] == 1

    # 间隔 2 期：第 1 期 vs 第 4 期 [1,2,3] vs [1,8,3] = 2 相同
    assert stats.gap_stats["pos"][2].same_counts[2] == 1


def test_analyze_adjacent_qlc():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="qlc",
                   groups={"basic": list(range(1, 8)), "special": [30]}),
        DrawRecord("2024002", datetime(2024, 1, 3), profile="qlc",
                   groups={"basic": list(range(1, 7)) + [31], "special": [30]}),
        DrawRecord("2024003", datetime(2024, 1, 5), profile="qlc",
                   groups={"basic": list(range(10, 17)), "special": [1]}),
        DrawRecord("2024004", datetime(2024, 1, 7), profile="qlc",
                   groups={"basic": list(range(1, 8)), "special": [30]}),
    ]
    from caipiao.ui.components.draw_analysis_dialog import _analyze_adjacent

    stats, details = _analyze_adjacent(records, get_profile("qlc"))
    assert stats.total_pairs == 3
    # 相邻：第1 vs 第2 = 6 个基本号相同；第2 vs 第3 = 0 个；第3 vs 第4 = 0 个
    assert stats.group_stats["basic"].same_counts[6] == 1
    assert stats.group_stats["basic"].same_counts[0] == 2
    # 特别号：第1 vs 第2 相同(30)，第2 vs 第3 不同，第3 vs 第4 不同
    assert stats.group_stats["special"].same_counts[1] == 1
    assert stats.group_stats["special"].same_counts[0] == 2
    assert details[1]["basic"] == 6
    assert details[1]["special"] is True

    # 间隔 1 期
    assert stats.gap_stats["basic"][1].total_pairs == 2
    assert stats.gap_stats["special"][1].total_pairs == 2
    # 间隔 2 期：第 1 期 vs 第 4 期完全相同
    assert stats.gap_stats["basic"][2].same_counts[7] == 1
    assert stats.gap_stats["special"][2].same_counts[1] == 1


def test_analyze_adjacent_kl8():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="kl8",
                   groups={"main": list(range(1, 21))}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="kl8",
                   groups={"main": list(range(1, 11)) + list(range(21, 31))}),
        DrawRecord("2024003", datetime(2024, 1, 3), profile="kl8",
                   groups={"main": list(range(41, 61))}),
        DrawRecord("2024004", datetime(2024, 1, 4), profile="kl8",
                   groups={"main": list(range(11, 31))}),
    ]
    from caipiao.ui.components.draw_analysis_dialog import _analyze_adjacent

    stats, details = _analyze_adjacent(records, get_profile("kl8"))
    assert stats.total_pairs == 3
    assert stats.group_stats["main"].same_counts[10] == 1
    assert stats.group_stats["main"].same_counts[0] == 2
    assert details[1]["main"] == 10

    # 间隔 1 期：第 1 期 vs 第 3 期 0 相同；第 2 期 vs 第 4 期 10 相同
    assert stats.gap_stats["main"][1].same_counts[0] == 1
    assert stats.gap_stats["main"][1].same_counts[10] == 1
    # 间隔 2 期：第 1 期 vs 第 4 期 10 相同
    assert stats.gap_stats["main"][2].same_counts[10] == 1
    assert needs_history("hot_cold_3d")
    assert needs_history("xgboost_kl8")
    assert not needs_history("random_3d")
