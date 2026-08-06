"""覆盖率测试：核心数据/持久化模块的 100% line coverage.

只覆盖分配到的 9 个核心模块（data/*、persistence/*），不触及 caipiao/ui、caipiao/ml。
网络 I/O 全部 mock；持久化全部用 tmp_path（或 mock）隔离。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from caipiao.core.profile import (
    SSQ,
    GD36X7,
    LotteryProfile,
    NumberGroup,
    get_profile,
)
from caipiao.core.ticket import Ticket
from caipiao.data.analyzer import DrawAnalyzer, LotteryAnalyzer
from caipiao.data.fetcher import LotteryDataFetcher
from caipiao.data.models import DrawRecord
from caipiao.data.repository import DataRepository, DrawRepository
from caipiao.persistence.backtest_db import (
    BacktestDatabase,
    BatchBacktestRecord,
    SingleBacktestRecord,
    _db_path,
)
from caipiao.persistence.history import HistoryManager
from caipiao.persistence.optimal_param_store import (
    LockedParameter,
    OptimalParamStore,
    OptimalParamsConfig,
)
from caipiao.core.parameter_group import ParameterGroup, StrategyParameterItem
from caipiao.persistence.parameter_group_store import ParameterGroupStore
from caipiao.persistence.settings import AppSettings


# --------------------------------------------------------------------------- #
# 构造辅助
# --------------------------------------------------------------------------- #
def _dt(y, m, d):
    return datetime(y, m, d)


def ssq_rec(issue, y, m, d, reds, blue):
    return DrawRecord(issue=str(issue), draw_date=_dt(y, m, d), red_balls=reds, blue_ball=blue)


def make_ticket(reds, blue, when=None, strategy="s", basis="b"):
    return Ticket(
        red_balls=reds, blue_ball=blue, generated_at=when, strategy_name=strategy, basis=basis
    )


# =========================================================================== #
# caipiao/data/models.py
# =========================================================================== #
class TestModels:
    def test_init_ssq_compat(self):
        r = ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)
        assert r.red_balls == [1, 2, 3, 4, 5, 6]
        assert r.blue_ball == 7
        assert r.profile.key == "ssq"

    def test_init_ssq_missing_blue_raises(self):
        with pytest.raises(ValueError, match="蓝球"):
            DrawRecord(issue="1", draw_date=_dt(2024, 1, 1), red_balls=[1, 2, 3, 4, 5, 6])

    def test_init_groups_profile(self):
        r = DrawRecord(
            issue="x", draw_date=_dt(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}
        )
        assert r.profile.key == "3d"
        assert r.groups == {"pos": [1, 2, 3]}

    def test_init_groups_default_profile(self):
        r = DrawRecord(issue="x", draw_date=_dt(2024, 1, 1), groups={"pos": [1, 2, 3]})
        assert r.profile.key == "ssq"

    def test_red_balls_property(self):
        r = DrawRecord(issue="x", draw_date=_dt(2024, 1, 1), groups={"pos": [1, 2, 3]})
        assert r.red_balls == []

    def test_blue_ball_property(self):
        r = DrawRecord(issue="x", draw_date=_dt(2024, 1, 1), groups={"pos": [1, 2, 3]})
        assert r.blue_ball is None
        r2 = ssq_rec("1", 2024, 1, 1, [1, 2, 3, 4, 5, 6], 9)
        assert r2.blue_ball == 9

    def test_to_dict_ssq(self):
        r = ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)
        d = r.to_dict()
        assert d["red_balls"] == [1, 2, 3, 4, 5, 6]
        assert d["blue_ball"] == 7
        assert d["issue"] == "2024001"

    def test_to_dict_ssq_missing_raises(self):
        r = DrawRecord(issue="x", draw_date=_dt(2024, 1, 1), profile="ssq", groups={})
        with pytest.raises(ValueError, match="无法序列化"):
            r.to_dict()

    def test_to_dict_non_ssq(self):
        r = DrawRecord(
            issue="x", draw_date=_dt(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}
        )
        d = r.to_dict()
        assert d["profile"] == "3d"
        assert d["groups"] == {"pos": [1, 2, 3]}

    def test_from_dict_groups(self):
        data = {"issue": "x", "draw_date": "2024-01-07", "profile": "3d", "groups": {"pos": [1, 2, 3]}}
        r = DrawRecord.from_dict(data)
        assert r.profile.key == "3d"
        assert r.groups == {"pos": [1, 2, 3]}

    def test_from_dict_groups_default_profile(self):
        data = {"issue": "x", "draw_date": "2024-01-07", "groups": {"pos": [1, 2, 3]}}
        r = DrawRecord.from_dict(data)
        assert r.profile.key == "ssq"

    def test_from_dict_legacy(self):
        data = {"issue": "x", "draw_date": "2024-01-07", "red_balls": [1, 2, 3, 4, 5, 6], "blue_ball": 7}
        r = DrawRecord.from_dict(data)
        assert r.red_balls == [1, 2, 3, 4, 5, 6]
        assert r.blue_ball == 7

    def test_repr_ssq_valid(self):
        r = ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)
        assert "红" in repr(r) and "蓝" in repr(r)

    def test_repr_ssq_invalid(self):
        r = DrawRecord(issue="x", draw_date=_dt(2024, 1, 1), profile="ssq", groups={})
        assert "无效记录" in repr(r)

    def test_repr_non_ssq(self):
        r = DrawRecord(
            issue="x", draw_date=_dt(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}
        )
        assert "号码" in repr(r)

    def test_eq(self):
        a = ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)
        b = ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)
        c = ssq_rec("2024002", 2024, 1, 8, [1, 2, 3, 4, 5, 6], 7)
        assert a == b
        assert a != c
        assert a.__eq__("not a record") is NotImplemented


# =========================================================================== #
# caipiao/data/analyzer.py
# =========================================================================== #
class TestAnalyzer:
    def _ssq_records(self):
        return [
            ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7),
            ssq_rec("2024002", 2024, 1, 9, [2, 3, 4, 5, 6, 7], 8),
            ssq_rec("2024003", 2024, 1, 11, [1, 3, 5, 7, 9, 11], 9),
        ]

    def test_init_branches(self):
        recs = self._ssq_records()
        # 显式 profile
        a = DrawAnalyzer(recs, profile=SSQ)
        assert a.profile.key == "ssq"
        # 无 profile，用首条
        b = DrawAnalyzer(recs)
        assert b.profile.key == "ssq"
        # 无记录无 profile -> SSQ
        c = DrawAnalyzer([])
        assert c.profile.key == "ssq"
        assert c.records == []

    def test_frequency_and_hot(self):
        a = DrawAnalyzer(self._ssq_records())
        freq = a.frequency("red")
        assert isinstance(freq, dict)
        assert len(a.hot("red", 5)) == 5

    def test_cold_missing_value_error(self):
        a = DrawAnalyzer(self._ssq_records())
        with pytest.raises(ValueError, match="not found"):
            a.cold("nope")
        with pytest.raises(ValueError, match="not found"):
            a.missing("nope")

    def test_cold_ok(self):
        a = DrawAnalyzer(self._ssq_records())
        assert isinstance(a.cold("red", 10, 30), list)

    def test_missing_ok(self):
        a = DrawAnalyzer(self._ssq_records())
        res = a.missing("red", 50)
        assert isinstance(res, list)
        assert all(isinstance(item, tuple) for item in res)

    def test_primary_numbers(self):
        a = DrawAnalyzer(self._ssq_records())
        nums = a._primary_numbers(a.records[0])
        assert nums == [1, 2, 3, 4, 5, 6]

    def test_odd_even_ratio_empty(self):
        a = DrawAnalyzer([])
        assert a.odd_even_ratio() == (0.5, 0.5)

    def test_odd_even_ratio(self):
        a = DrawAnalyzer(self._ssq_records())
        odd, even = a.odd_even_ratio()
        assert odd + even == 1.0

    def test_high_low_ratio_empty(self):
        a = DrawAnalyzer([])
        assert a.high_low_ratio() == (0.5, 0.5)

    def test_high_low_ratio(self):
        a = DrawAnalyzer(self._ssq_records())
        hi, lo = a.high_low_ratio()
        assert hi + lo == 1.0

    def test_sum_statistics_empty(self):
        a = DrawAnalyzer([])
        assert a.sum_statistics() == {"min": 0, "max": 0, "avg": 0, "median": 0}

    def test_sum_statistics_odd_median(self):
        a = DrawAnalyzer([ssq_rec("1", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)])
        s = a.sum_statistics()
        assert s["median"] == 21

    def test_sum_statistics_even_median(self):
        a = DrawAnalyzer(
            [
                ssq_rec("1", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7),
                ssq_rec("2", 2024, 1, 8, [2, 3, 4, 5, 6, 7], 7),
            ]
        )
        s = a.sum_statistics()
        assert s["median"] == 24.0

    def test_consecutive_frequency_empty(self):
        a = DrawAnalyzer([])
        assert a.consecutive_frequency() == 0.0

    def test_consecutive_frequency(self):
        a = DrawAnalyzer(self._ssq_records())
        assert 0.0 <= a.consecutive_frequency() <= 1.0

    def test_consecutive_count_distribution_empty(self):
        a = DrawAnalyzer([])
        assert a.consecutive_count_distribution() == {0: 1.0}

    def test_consecutive_count_distribution(self):
        a = DrawAnalyzer(self._ssq_records())
        dist = a.consecutive_count_distribution()
        assert sum(dist.values()) == 1.0

    def test_zone_distribution_empty(self):
        a = DrawAnalyzer([])
        assert a.zone_distribution() == {"zone1": 1 / 3, "zone2": 1 / 3, "zone3": 1 / 3}

    def test_zone_distribution_total_zero(self):
        # 记录存在但主组为空 -> total == 0 分支
        r = DrawRecord(issue="x", draw_date=_dt(2024, 1, 1), profile="ssq", groups={})
        a = DrawAnalyzer([r])
        assert a.zone_distribution() == {"zone1": 1 / 3, "zone2": 1 / 3, "zone3": 1 / 3}

    def test_zone_distribution(self):
        a = DrawAnalyzer(self._ssq_records())
        z = a.zone_distribution()
        assert abs(sum(z.values()) - 1.0) < 1e-9

    def test_zone_distribution_spans_all_zones(self):
        recs = [
            ssq_rec("2024001", 2024, 1, 7, [1, 12, 23, 5, 20, 30], 7),
            ssq_rec("2024002", 2024, 1, 9, [2, 13, 24, 6, 21, 31], 8),
        ]
        a = DrawAnalyzer(recs)
        z = a.zone_distribution()
        assert z["zone1"] > 0 and z["zone2"] > 0 and z["zone3"] > 0

    def test_common_pairs(self):
        a = DrawAnalyzer(self._ssq_records())
        assert isinstance(a.common_pairs(5), list)

    def test_positional_frequency(self):
        a = DrawAnalyzer(self._ssq_records())
        pf = a.positional_frequency()
        assert isinstance(pf, dict)

    def test_span_empty(self):
        a = DrawAnalyzer([])
        assert a.span() == {"min": 0, "max": 0, "avg": 0, "median": 0}

    def test_span_odd_median(self):
        a = DrawAnalyzer([ssq_rec("1", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)])
        s = a.span()
        assert s["median"] == 5

    def test_span_even_median(self):
        a = DrawAnalyzer(
            [
                ssq_rec("1", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7),
                ssq_rec("2", 2024, 1, 8, [2, 3, 4, 5, 6, 7], 7),
            ]
        )
        s = a.span()
        assert s["median"] == 5.0

    def test_last_draw(self):
        a = DrawAnalyzer([])
        assert a.last_draw() is None
        b = DrawAnalyzer(self._ssq_records())
        assert b.last_draw().issue == "2024003"

    def test_slice(self):
        a = DrawAnalyzer(self._ssq_records())
        assert a._slice(None) == a.records
        assert a._slice(1000) == a.records
        assert a._slice(0) == []
        assert a._slice(2) == a.records[-2:]

    def test_summary_ssq(self):
        a = DrawAnalyzer(self._ssq_records())
        s = a.summary()
        assert "hot_blues_30" in s
        assert "hot_reds_30" in s
        assert "missing_reds_50" in s

    def test_summary_non_ssq(self):
        recs = [
            DrawRecord(issue="1", draw_date=_dt(2024, 1, 7), profile="3d", groups={"pos": [1, 2, 3]}),
            DrawRecord(issue="2", draw_date=_dt(2024, 1, 8), profile="3d", groups={"pos": [4, 5, 6]}),
        ]
        a = DrawAnalyzer(recs, profile=get_profile("3d"))
        s = a.summary()
        assert "hot_blues_30" not in s
        assert "hot_30" in s

    def test_legacy_alias_methods(self):
        a = LotteryAnalyzer(self._ssq_records())
        assert isinstance(a, DrawAnalyzer)
        assert a.red_frequency(30) == a.frequency("red", 30)
        assert a.blue_frequency(30) == a.frequency("blue", 30)
        assert a.hot_reds(5, 30) == a.hot("red", 5, 30)
        assert a.cold_reds(5, 30) == a.cold("red", 5, 30)
        assert a.hot_blues(3, 30) == a.hot("blue", 3, 30)
        assert a.missing_reds(50) == a.missing("red", 50)
        assert a.missing_blues(50) == a.missing("blue", 50)


# =========================================================================== #
# caipiao/data/repository.py
# =========================================================================== #
class _FakeNDProfile:
    """用于触发 _next_draw_date 中 draw_weekdays 为空的 ValueError 分支。"""

    is_daily = False
    draw_weekdays = ()


class TestRepository:
    def test_init_default_profile(self, tmp_path):
        p = tmp_path / "draws.json"
        repo = DrawRepository(p)
        assert repo.profile.key == "ssq"
        assert repo.get_count() == 0

    def test_load_missing_file(self, tmp_path):
        repo = DrawRepository(tmp_path / "nope.json")
        assert repo.get_count() == 0

    def test_load_corrupt(self, tmp_path):
        p = tmp_path / "draws.json"
        p.write_text("not json {", encoding="utf-8")
        repo = DrawRepository(p)
        assert repo.get_count() == 0

    def test_load_dedup_saves(self, tmp_path):
        p = tmp_path / "draws.json"
        data = [
            {"issue": "2024001", "draw_date": "2024-01-07", "red_balls": [1, 2, 3, 4, 5, 6], "blue_ball": 7},
            {"issue": "2024001", "draw_date": "2024-01-07", "red_balls": [1, 2, 3, 4, 5, 6], "blue_ball": 7},
        ]
        p.write_text(__import__("json").dumps(data), encoding="utf-8")
        repo = DrawRepository(p)
        assert repo.get_count() == 1

    def test_normalize_issue_short(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        r = ssq_rec("12", 2024, 1, 1, [1, 2, 3, 4, 5, 6], 1)
        assert repo._normalize_issue(r) is r

    def test_normalize_issue_changed(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        r = DrawRecord(issue="2024010", draw_date=_dt(2025, 1, 1), red_balls=[1, 2, 3, 4, 5, 6], blue_ball=1)
        out = repo._normalize_issue(r)
        assert out.issue == "2025010"

    def test_normalize_issue_same(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        r = DrawRecord(issue="2024010", draw_date=_dt(2024, 1, 1), red_balls=[1, 2, 3, 4, 5, 6], blue_ball=1)
        assert repo._normalize_issue(r) is r

    def test_normalize_issue_value_error(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        r = DrawRecord(issue="ab12", draw_date=_dt(2024, 1, 1), red_balls=[1, 2, 3, 4, 5, 6], blue_ball=1)
        assert repo._normalize_issue(r) is r

    def test_save_and_load_roundtrip(self, tmp_path):
        p = tmp_path / "draws.json"
        repo = DrawRepository(p)
        repo.update([ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)])
        repo2 = DrawRepository(p)
        assert repo2.get_count() == 1

    def test_update_dedup(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        n = repo.update([ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)])
        assert n == 1
        n2 = repo.update([ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)])
        assert n2 == 0
        assert repo.get_count() == 1

    def test_get_recent(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        repo.update(self._three())
        assert repo.get_recent(0) == []
        assert len(repo.get_recent(2)) == 2

    def test_get_count_latest(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        assert repo.get_latest() is None
        assert repo.get_count() == 0
        repo.update(self._three())
        assert repo.get_count() == 3
        assert repo.get_latest().issue == "2024003"

    def test_get_all(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        repo.update(self._three())
        assert len(repo.get_all()) == 3

    def test_get_date_range(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        assert repo.get_date_range() == (None, None)
        repo.update(self._three())
        lo, hi = repo.get_date_range()
        assert lo == _dt(2024, 1, 7)
        assert hi == _dt(2024, 1, 11)

    def test_get_records_before(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        repo.update(self._three())
        before = repo.get_records_before(_dt(2024, 1, 9))
        assert len(before) == 1

    def test_get_record_by_date(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        repo.update(self._three())
        assert repo.get_record_by_date(_dt(2024, 1, 7)).issue == "2024001"
        assert repo.get_record_by_date(_dt(2030, 1, 1)) is None

    def test_clear(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        repo.update(self._three())
        repo.clear()
        assert repo.get_count() == 0

    def test_next_issue_static(self):
        assert DrawRepository._next_issue("2024001", _dt(2024, 1, 7)) == "2024002"
        assert DrawRepository._next_issue("2024123", _dt(2025, 1, 1)) == "2025001"
        assert DrawRepository._next_issue("12", _dt(2024, 1, 1)) == ""
        assert DrawRepository._next_issue("abcd123", _dt(2024, 1, 1)) == ""
        assert DrawRepository._next_issue("2024xyz", _dt(2024, 1, 1)) == ""

    def test_next_period_info_none(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        assert repo.next_period_info() is None

    def test_next_period_daily(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json", profile=get_profile("kl8"))
        repo.update([DrawRecord(issue="2024001", draw_date=_dt(2024, 1, 7), profile="kl8", groups={"main": list(range(1, 21))})])
        info = repo.next_period_info()
        assert info is not None
        # 每日 -> 次日
        assert info["next_date"] == _dt(2024, 1, 8)

    def test_next_period_weekday_loop(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json")
        # 2024-01-07 是周日(6)，下一天周一(0) 非开奖日 -> 循环到周二(1)
        repo.update([ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)])
        info = repo.next_period_info()
        assert info["next_date"].weekday() in (1, 3, 6)

    def test_next_period_empty_weekdays_raises(self, tmp_path):
        repo = DrawRepository(tmp_path / "d.json", profile=_FakeNDProfile())
        repo.update([ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7)])
        with pytest.raises(ValueError, match="draw_weekdays"):
            repo.next_period_info()

    def _three(self):
        return [
            ssq_rec("2024001", 2024, 1, 7, [1, 2, 3, 4, 5, 6], 7),
            ssq_rec("2024002", 2024, 1, 9, [2, 3, 4, 5, 6, 7], 8),
            ssq_rec("2024003", 2024, 1, 11, [1, 3, 5, 7, 9, 11], 9),
        ]


# =========================================================================== #
# caipiao/data/fetcher.py
# =========================================================================== #
def _make_profile(key, parser_key):
    return LotteryProfile(
        key=key,
        name=key,
        groups=(NumberGroup("red", "红", 1, 33, 6),),
        data_url="http://example.com/x.txt",
        parser_key=parser_key,
        draw_weekdays=(1,),
        storage_file="x.json",
        model_prefix="x",
    )


def _fake_response(status=200, content=b"", apparent="utf-8"):
    m = MagicMock()
    m.status_code = status
    m.content = content
    m.apparent_encoding = apparent
    m.close = MagicMock()
    return m


class TestFetcher:
    def test_init_defaults(self):
        f = LotteryDataFetcher(profile=SSQ)
        assert f.profile.key == "ssq"
        assert f.timeout == 60
        assert f.max_retries == 3
        assert "User-Agent" in f.headers

    def test_init_invalid_retries(self):
        with pytest.raises(ValueError, match="max_retries"):
            LotteryDataFetcher(profile=SSQ, max_retries=0)

    def test_init_unsupported_parser(self):
        with pytest.raises(ValueError, match="Unsupported parser_key"):
            LotteryDataFetcher(profile=_make_profile("x", "bogus"))

    # --- 行解析器 ---
    def test_parse_ssq(self):
        f = LotteryDataFetcher(profile=SSQ)
        parts = ["2024001", "2024-01-07", "1", "2", "3", "4", "5", "6", "7"]
        r = f._parse_ssq(parts, "")
        assert r.red_balls == [1, 2, 3, 4, 5, 6]
        assert f._parse_ssq(["1", "2024-01-07"], "") is None

    def test_parse_3d(self):
        f = LotteryDataFetcher(profile=get_profile("3d"))
        parts = ["2024001", "2024-01-07", "1", "2", "3"]
        r = f._parse_3d(parts, "")
        assert r.groups["pos"] == [1, 2, 3]
        assert f._parse_3d(["1", "2024-01-07"], "") is None

    def test_parse_kl8(self):
        f = LotteryDataFetcher(profile=get_profile("kl8"))
        parts = ["2024001", "2024-01-07"] + [str(i) for i in range(1, 21)]
        r = f._parse_kl8(parts, "")
        assert len(r.groups["main"]) == 20
        assert f._parse_kl8(["1", "2024-01-07"], "") is None

    def test_parse_dlt(self):
        f = LotteryDataFetcher(profile=get_profile("dlt"))
        parts = ["2024001", "2024-01-07", "1", "2", "3", "4", "5", "6", "7"]
        r = f._parse_dlt(parts, "")
        assert r.groups["front"] == [1, 2, 3, 4, 5]
        assert r.groups["back"] == [6, 7]
        assert f._parse_dlt(["1", "2024-01-07"], "") is None

    def test_parse_pl3(self):
        f = LotteryDataFetcher(profile=get_profile("pl3"))
        parts = ["2024001", "2024-01-07", "1", "2", "3"]
        r = f._parse_pl3(parts, "")
        assert r.groups["pos"] == [1, 2, 3]
        assert f._parse_pl3(["1", "2024-01-07"], "") is None

    def test_parse_pl5(self):
        f = LotteryDataFetcher(profile=get_profile("pl5"))
        parts = ["2024001", "2024-01-07", "1", "2", "3", "4", "5"]
        r = f._parse_pl5(parts, "")
        assert r.groups["pos"] == [1, 2, 3, 4, 5]
        assert f._parse_pl5(["1", "2024-01-07"], "") is None

    def test_parse_qxc(self):
        f = LotteryDataFetcher(profile=get_profile("qxc"))
        parts = ["2024001", "2024-01-07", "1", "2", "3", "4", "5", "6", "7"]
        r = f._parse_qxc(parts, "")
        assert r.groups["pos"] == [1, 2, 3, 4, 5, 6, 7]
        assert f._parse_qxc(["1", "2024-01-07"], "") is None
        # 越界值 -> None
        bad = ["2024001", "2024-01-07", "1", "2", "3", "4", "5", "6", "10"]
        assert f._parse_qxc(bad, "") is None

    def test_parse_gd36x7(self):
        f = LotteryDataFetcher(profile=GD36X7)
        parts = ["2024001", "2024-01-07", "1", "2", "3", "4", "5", "6", "7", "8"]
        r = f._parse_gd36x7(parts, "")
        assert r.groups["basic"] == [1, 2, 3, 4, 5, 6, 7]
        assert r.groups["special"] == [8]
        assert f._parse_gd36x7(["1", "2024-01-07"], "") is None

    # --- 网络重试 ---
    def test_get_with_retry_success(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        f = LotteryDataFetcher(profile=SSQ)
        monkeypatch.setattr(requests, "get", lambda *a, **k: _fake_response(200, b"x"))
        assert f._get_with_retry("url").status_code == 200

    def test_get_with_retry_then_success(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        f = LotteryDataFetcher(profile=SSQ)
        seq = iter([_fake_response(500, b""), _fake_response(200, b"ok")])
        monkeypatch.setattr(requests, "get", lambda *a, **k: next(seq))
        resp = f._get_with_retry("url")
        assert resp.status_code == 200

    def test_get_with_retry_all_fail(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        f = LotteryDataFetcher(profile=SSQ, max_retries=3)
        monkeypatch.setattr(
            requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.RequestException("boom"))
        )
        with pytest.raises(requests.RequestException):
            f._get_with_retry("url")

    # --- 解码 ---
    def test_decode_utf8(self):
        class R:
            content = "测试".encode("utf-8")
            apparent_encoding = "utf-8"

        assert LotteryDataFetcher._decode_response(R()) == "测试"

    def test_decode_none_apparent(self):
        class R:
            content = "hi".encode("utf-8")
            apparent_encoding = None

        assert LotteryDataFetcher._decode_response(R()) == "hi"

    def test_decode_gbk(self):
        # gb18030 是 gbk 的严格超集；修复后优先尝试 gb18030 而非单独的 gbk。
        class FakeContent:
            def decode(self, enc, *args, **kwargs):
                if enc in ("gbk", "gb18030"):
                    return "gb18030-ok"
                raise UnicodeDecodeError(enc, b"x", 0, 1, "e")

        class R:
            content = FakeContent()
            apparent_encoding = "utf-8"

        assert LotteryDataFetcher._decode_response(R()) == "gb18030-ok"

    def test_decode_fallback(self):
        class FakeContent:
            def decode(self, enc, *args, **kwargs):
                if kwargs.get("errors") == "replace":
                    return "\ufffd"
                raise UnicodeDecodeError(enc, b"x", 0, 1, "e")

        class R:
            content = FakeContent()
            apparent_encoding = "utf-8"

        # 全部失败 -> 以 errors='replace' 兜底
        assert LotteryDataFetcher._decode_response(R()) == "\ufffd"

    # --- fetch_all / fetch_latest ---
    def test_fetch_all(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        f = LotteryDataFetcher(profile=SSQ)
        text = (
            "2024001 2024-01-07 1 2 3 4 5 6 7\n"
            "short line\n"
            "2024002 2024-01-07 a b c d e f g h\n"
        )
        monkeypatch.setattr(requests, "get", lambda *a, **k: _fake_response(200, text.encode("utf-8")))
        records = f.fetch_all()
        assert len(records) == 1
        assert records[0].issue == "2024001"

    def test_fetch_all_empty_raises(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        f = LotteryDataFetcher(profile=SSQ)
        monkeypatch.setattr(requests, "get", lambda *a, **k: _fake_response(200, b"bad line\n"))
        with pytest.raises(ValueError, match="未解析"):
            f.fetch_all()

    def test_fetch_latest(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        f = LotteryDataFetcher(profile=SSQ)
        text = "2024001 2024-01-07 1 2 3 4 5 6 7\n"
        monkeypatch.setattr(requests, "get", lambda *a, **k: _fake_response(200, text.encode("utf-8")))
        rec = f.fetch_latest()
        assert rec is not None
        assert rec.issue == "2024001"

    def test_fetch_latest_empty(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        f = LotteryDataFetcher(profile=SSQ)
        monkeypatch.setattr(requests, "get", lambda *a, **k: _fake_response(200, b""))
        assert f.fetch_latest() is None

    def test_fetch_latest_exception(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *a, **k: None)
        f = LotteryDataFetcher(profile=SSQ)
        monkeypatch.setattr(
            requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.RequestException("x"))
        )
        assert f.fetch_latest() is None


# =========================================================================== #
# caipiao/persistence/optimal_param_store.py
# =========================================================================== #
class TestOptimalParamStore:
    def test_init_and_path(self, tmp_path):
        store = OptimalParamStore(tmp_path)
        assert store._path("ssq").name == "ssq.json"

    def test_init_default_dir(self):
        # 覆盖 data_dir or app_data_dir() 的默认分支
        store = OptimalParamStore()
        assert store._base_dir.name == "optimal_params"

    def test_load_missing(self, tmp_path):
        store = OptimalParamStore(tmp_path)
        cfg = store.load("ssq")
        assert isinstance(cfg, OptimalParamsConfig)
        assert cfg.profile_key == "ssq"

    def test_save_load_roundtrip(self, tmp_path):
        store = OptimalParamStore(tmp_path)
        store.lock("ssq", "strat1", "k", 5, source="scan", stability_score=0.9)
        cfg = store.load("ssq")
        assert cfg.locked[0].param_value == 5
        assert cfg.locked[0].source == "scan"

    def test_lock_dedup(self, tmp_path):
        store = OptimalParamStore(tmp_path)
        store.lock("ssq", "strat1", "k", 5)
        store.lock("ssq", "strat1", "k", 9)
        assert len(store.load("ssq").locked) == 1
        assert store.load("ssq").locked[0].param_value == 9

    def test_unlock(self, tmp_path):
        store = OptimalParamStore(tmp_path)
        store.lock("ssq", "strat1", "k", 5)
        store.unlock("ssq", "strat1", "k")
        assert store.load("ssq").locked == []

    def test_get_locked(self, tmp_path):
        store = OptimalParamStore(tmp_path)
        store.lock("ssq", "strat1", "k", 5)
        assert store.get_locked("ssq", "strat1") == {"k": 5}
        assert store.get_locked("ssq", "other") == {}

    def test_apply_defaults(self, tmp_path):
        store = OptimalParamStore(tmp_path)
        schema = {"k": {"default": 1, "type": "int"}, "j": {"default": 2}}
        # 无锁定时原样返回
        assert store.apply_defaults("ssq", "strat1", schema) == schema
        store.lock("ssq", "strat1", "k", 99)
        new = store.apply_defaults("ssq", "strat1", schema)
        assert new["k"]["default"] == 99
        assert new["j"]["default"] == 2

    def test_load_corrupt_backup(self, tmp_path):
        store = OptimalParamStore(tmp_path)
        p = store._path("ssq")
        p.write_text("{ corruption", encoding="utf-8")
        cfg = store.load("ssq")
        assert cfg.locked == []
        # 产生了备份文件（位于 optimal_params 子目录）
        assert list(store._base_dir.glob("ssq.corrupted-*.json"))

    def test_load_corrupt_rename_fail(self, tmp_path, monkeypatch):
        store = OptimalParamStore(tmp_path)
        p = store._path("ssq")
        p.write_text("{ corruption", encoding="utf-8")

        def _fail_rename(self, target):
            raise OSError("cannot rename")

        monkeypatch.setattr(Path, "rename", _fail_rename)
        cfg = store.load("ssq")
        assert cfg.locked == []

    def test_model_from_dict_defaults(self):
        lp = LockedParameter.from_dict({})
        assert lp.strategy_id == "" and lp.source == "user"
        cfg = OptimalParamsConfig.from_dict({})
        assert cfg.profile_key == "" and cfg.locked == [] and cfg.last_scan_at is None


# =========================================================================== #
# caipiao/persistence/parameter_group_store.py
# =========================================================================== #
def _pg(id_, name="G1"):
    return ParameterGroup(
        id=id_,
        name=name,
        profile_key="ssq",
        created_at="2024",
        items=[StrategyParameterItem(strategy_id="s", strategy_name="S", param_name="n", param_value=1)],
    )


class TestParameterGroupStore:
    def test_init(self, tmp_path):
        store = ParameterGroupStore(tmp_path)
        assert store._base_dir.name == "param_groups"
        assert store.path_for("ssq").name == "ssq.json"

    def test_load_missing(self, tmp_path):
        store = ParameterGroupStore(tmp_path)
        assert store.load_all("ssq") == []

    def test_save_new_and_update(self, tmp_path):
        store = ParameterGroupStore(tmp_path)
        g = _pg("g1")
        store.save(g)
        assert len(store.load_all("ssq")) == 1
        g2 = _pg("g1", name="G1-updated")
        store.save(g2)
        allg = store.load_all("ssq")
        assert len(allg) == 1
        assert allg[0].name == "G1-updated"

    def test_delete(self, tmp_path):
        store = ParameterGroupStore(tmp_path)
        store.save(_pg("g1"))
        assert store.delete("ssq", "g1") is True
        assert store.delete("ssq", "g1") is False
        assert store.load_all("ssq") == []

    def test_rename(self, tmp_path):
        store = ParameterGroupStore(tmp_path)
        store.save(_pg("g1"))
        assert store.rename("ssq", "g1", "NewName") is True
        assert store.get("ssq", "g1").name == "NewName"
        assert store.rename("ssq", "missing", "X") is False

    def test_get(self, tmp_path):
        store = ParameterGroupStore(tmp_path)
        store.save(_pg("g1"))
        assert store.get("ssq", "g1").id == "g1"
        assert store.get("ssq", "nope") is None

    def test_load_corrupt(self, tmp_path):
        store = ParameterGroupStore(tmp_path)
        p = store.path_for("ssq")
        p.write_text("not json", encoding="utf-8")
        assert store.load_all("ssq") == []

    def test_load_not_list(self, tmp_path):
        store = ParameterGroupStore(tmp_path)
        p = store.path_for("ssq")
        p.write_text('{"a": 1}', encoding="utf-8")
        assert store.load_all("ssq") == []


# =========================================================================== #
# caipiao/persistence/history.py
# =========================================================================== #
DRAW_ONLY_PROFILE = LotteryProfile(
    key="do",
    name="DO",
    groups=(NumberGroup("special", "特别号", 1, 36, 1, draw_only=True),),
    data_url="",
    parser_key="ssq",
    draw_weekdays=(),
    storage_file="do.json",
    model_prefix="do",
)


class TestHistory:
    def test_init_max_entries(self, tmp_path):
        assert HistoryManager(tmp_path / "h.json", max_entries="abc").max_entries == 1000
        assert HistoryManager(tmp_path / "h2.json", max_entries=None).max_entries == 1000
        assert HistoryManager(tmp_path / "h3.json", max_entries=3).max_entries == 3

    def test_load_corrupt(self, tmp_path):
        p = tmp_path / "h.json"
        p.write_text("not json", encoding="utf-8")
        assert HistoryManager(p).get_all() == []

    def test_load_not_list(self, tmp_path):
        p = tmp_path / "h.json"
        p.write_text("{}", encoding="utf-8")
        assert HistoryManager(p).get_all() == []

    def test_load_value_error(self, tmp_path):
        p = tmp_path / "h.json"
        bad = [{"generated_at": datetime.now(timezone.utc).astimezone().isoformat(), "strategy_name": "s"}]
        p.write_text(__import__("json").dumps(bad), encoding="utf-8")
        assert HistoryManager(p).get_all() == []

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "h.json"
        hm = HistoryManager(p)
        hm.add(make_ticket([1, 2, 3, 4, 5, 6], 7))
        hm2 = HistoryManager(p)
        assert len(hm2.get_all()) == 1

    def test_add_skip_duplicates(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json")
        t = make_ticket([1, 2, 3, 4, 5, 6], 7)
        assert hm.add(t) is True
        assert hm.add(t, skip_duplicates=True) is False
        assert hm.add(t) is True

    def test_add_many(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json")
        assert hm.add_many([make_ticket([1, 2, 3, 4, 5, 6], 7) for _ in range(3)]) == 3
        assert hm.add_many([]) == 0
        # 全部重复
        hm2 = HistoryManager(tmp_path / "h2.json")
        t = make_ticket([1, 2, 3, 4, 5, 6], 7)
        hm2.add(t)
        assert hm2.add_many([t], skip_duplicates=True) == 0

    def test_trim(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json", max_entries=3)
        for i in range(5):
            hm.add(make_ticket([1, 2, 3, 4, 5, 6], i + 1))
        assert len(hm.get_all()) == 3

    def test_get_recent(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json")
        now = datetime.now(timezone.utc).astimezone()
        recent = make_ticket([1, 2, 3, 4, 5, 6], 7, when=now)
        old = make_ticket([1, 2, 3, 4, 5, 6], 8, when=now - timedelta(days=100))
        naive = make_ticket([1, 2, 3, 4, 5, 6], 9, when=datetime(2024, 1, 1))
        none_t = make_ticket([1, 2, 3, 4, 5, 6], 9)
        none_t.generated_at = None
        hm.add(recent)
        hm.add(old)
        hm.add(naive)
        # 直接追加（不触发 save/to_dict），用于覆盖 generated_at 为 None 的跳过分支
        hm._tickets.append(none_t)
        res = hm.get_recent(30)
        assert recent in res
        assert old not in res
        assert none_t not in res

    def test_clear(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json")
        hm.add(make_ticket([1, 2, 3, 4, 5, 6], 7))
        hm.clear()
        assert hm.get_all() == []

    def test_delete(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json")
        t = make_ticket([1, 2, 3, 4, 5, 6], 7)
        hm.add(t)
        assert hm.delete(t) is True
        assert hm.delete(t) is False

    def test_export_csv(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json")
        hm.add(make_ticket([1, 2, 3, 4, 5, 6], 7))
        out = tmp_path / "out.csv"
        hm.export_csv(out)
        assert out.exists()
        content = out.read_text(encoding="utf-8-sig")
        assert "红球" in content

    def test_export_csv_empty_groups(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json")
        t = Ticket(profile=DRAW_ONLY_PROFILE, groups={"special": [1]}, validate=False)
        hm.add(t)
        out = tmp_path / "out.csv"
        hm.export_csv(out)
        assert "号码" in out.read_text(encoding="utf-8-sig")

    def test_export_txt(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json")
        hm.add(make_ticket([1, 2, 3, 4, 5, 6], 7))
        out = tmp_path / "out.txt"
        hm.export_txt(out)
        assert out.exists()

    def test_export_excel(self, tmp_path):
        hm = HistoryManager(tmp_path / "h.json")
        hm.add(make_ticket([1, 2, 3, 4, 5, 6], 7))
        hm.add(Ticket(profile=DRAW_ONLY_PROFILE, groups={"special": [1]}, validate=False))
        out = tmp_path / "out.xlsx"
        hm.export_excel(out)
        assert out.exists()

    def test_import_from_json(self, tmp_path):
        src = tmp_path / "src.json"
        src.write_text(
            __import__("json").dumps(
                [
                    {
                        "red": [1, 2, 3, 4, 5, 6],
                        "blue": 7,
                        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
                        "strategy_name": "s",
                        "basis": "b",
                        "details": {},
                    }
                ]
            ),
            encoding="utf-8",
        )
        hm = HistoryManager(tmp_path / "h.json")
        assert hm.import_from_json(src) == 1
        assert len(hm.get_all()) == 1

    def test_import_corrupt(self, tmp_path):
        src = tmp_path / "src.json"
        src.write_text("not json", encoding="utf-8")
        hm = HistoryManager(tmp_path / "h.json")
        assert hm.import_from_json(src) == 0

    def test_import_not_list(self, tmp_path):
        src = tmp_path / "src.json"
        src.write_text('{"a":1}', encoding="utf-8")
        hm = HistoryManager(tmp_path / "h.json")
        assert hm.import_from_json(src) == 0

    def test_import_value_error(self, tmp_path):
        src = tmp_path / "src.json"
        bad = [{"generated_at": datetime.now(timezone.utc).astimezone().isoformat(), "strategy_name": "s"}]
        src.write_text(__import__("json").dumps(bad), encoding="utf-8")
        hm = HistoryManager(tmp_path / "h.json")
        assert hm.import_from_json(src) == 0


# =========================================================================== #
# caipiao/persistence/backtest_db.py
# =========================================================================== #
def _bt_tickets():
    return [
        {
            "ticket": Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=1),
            "hits": [1, 2],
            "prize_name": "二等奖",
            "prize_amount": 100,
        },
        {
            "ticket": Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=2),
            "hits": [],
            "prize_name": "",
            "prize_amount": 0,
        },
    ]


class TestBacktestDB:
    def test_db_path(self):
        # 覆盖模块级 _db_path（默认分支）
        assert _db_path().name == "backtests.db"

    def test_single_roundtrip(self, tmp_path):
        db = BacktestDatabase(tmp_path / "b.db")
        tid = db.save_single(
            "ssq", "strat1", "2024-01-07", "2024001", 2,
            {"a": 1}, {"red": [1, 2, 3, 4, 5, 6], "blue": [1]}, 100, 50, 1, 1,
            _bt_tickets(),
        )
        rec = db.get_single(tid)
        assert isinstance(rec, SingleBacktestRecord)
        assert len(rec.tickets) == 2
        assert db.delete_single(tid) is None
        assert db.get_single(tid) is None

    def test_list_single_filters(self, tmp_path):
        db = BacktestDatabase(tmp_path / "b.db")
        db.save_single(
            "ssq", "strat1", "2024-01-07", "2024001", 2,
            {}, {"red": [1], "blue": [1]}, 100, 50, 1, 1, _bt_tickets(),
        )
        db.save_single(
            "3d", "strat2", "2024-01-08", "2024002", 1,
            {}, {"pos": [1, 2, 3]}, 50, 0, 0, 0, [],
        )
        assert len(db.list_single()) == 2
        assert len(db.list_single(profile_key="ssq")) == 1
        assert len(db.list_single(strategy_id="strat2")) == 1
        assert len(db.list_single(target_date="2024-01-07")) == 1
        assert len(db.list_single(profile_key="nope")) == 0
        assert len(db.list_single(limit=1)) == 1
        assert len(db.list_single(offset=1)) == 1

    def test_batch_roundtrip(self, tmp_path):
        db = BacktestDatabase(tmp_path / "b.db")
        bid = db.save_batch(
            "ssq", "strat1", "2024-01-01", "2024-01-07", 5,
            {"x": 1}, 200, 100, 2, 2, 3, 1, {0: 2, 1: 1},
        )
        rec = db.get_batch(bid)
        assert isinstance(rec, BatchBacktestRecord)
        # 修复后：整型键被正确还原为 int（此前被 JSON 反序列化为字符串键）
        assert rec.ticket_index_hits == {0: 2, 1: 1}
        db.delete_batch(bid)
        assert db.get_batch(bid) is None

    def test_list_batch_filters(self, tmp_path):
        db = BacktestDatabase(tmp_path / "b.db")
        db.save_batch(
            "ssq", "strat1", "2024-01-01", "2024-01-07", 5,
            {}, 200, 100, 2, 2, 3, 1, {0: 1},
        )
        db.save_batch(
            "3d", "strat2", "2024-02-01", "2024-02-07", 5,
            {}, 50, 0, 0, 0, 1, 0, {},
        )
        assert len(db.list_batch()) == 2
        assert len(db.list_batch(profile_key="ssq")) == 1
        assert len(db.list_batch(strategy_id="strat2")) == 1
        assert len(db.list_batch(start_date="2024-01-01")) == 2
        assert len(db.list_batch(end_date="2024-01-07")) == 1
        assert len(db.list_batch(profile_key="nope")) == 0
        assert len(db.list_batch(limit=1)) == 1

    def test_summary(self, tmp_path):
        db = BacktestDatabase(tmp_path / "b.db")
        assert db.summary() == {"single_count": 0, "batch_count": 0}
        db.save_single("ssq", "s", "2024-01-07", "1", 1, {}, {"red": [1], "blue": [1]}, 1, 0, 0, 0, [])
        db.save_batch("ssq", "s", "2024-01-01", "2024-01-07", 1, {}, 1, 0, 0, 0, 1, 0, {})
        s = db.summary()
        assert s["single_count"] == 1
        assert s["batch_count"] == 1


# =========================================================================== #
# caipiao/persistence/settings.py
# =========================================================================== #
INT_PROPS = {
    "default_count": (1, 1, 1000, True),
    "auto_update_interval_days": (1, 1, 30, True),
    "last_history_count": (-1, -1, -1, False),
    "draw_analysis_max_gap": (1, 0, 50, True),
    "draw_analysis_filter_threshold": (1, 0, 10, True),
    "last_backtest_count": (5, 1, 1000, True),
    "ssq_filter_compare_periods": (1, 0, 50, True),
    "ssq_filter_max_red_overlap": (3, 0, 6, True),
    "fc3d_filter_compare_periods": (5, 0, 50, True),
    "fc3d_filter_max_overlap": (1, 0, 3, True),
    "fc3d_filter_min_sum": (0, 0, 27, True),
    "fc3d_filter_max_sum": (27, 0, 27, True),
    "dlt_filter_compare_periods": (7, 0, 50, True),
    "dlt_filter_max_front_overlap": (0, 0, 5, True),
    "dlt_filter_back_compare_periods": (1, 0, 50, True),
    "dlt_filter_min_front_sum": (15, 0, 165, True),
    "dlt_filter_max_front_sum": (165, 0, 165, True),
    "pl3_filter_compare_periods": (5, 0, 50, True),
    "pl3_filter_max_overlap": (1, 0, 3, True),
    "pl3_filter_min_sum": (0, 0, 27, True),
    "pl3_filter_max_sum": (27, 0, 27, True),
    "pl5_filter_compare_periods": (5, 0, 50, True),
    "pl5_filter_max_overlap": (2, 0, 5, True),
    "pl5_filter_min_sum": (0, 0, 45, True),
    "pl5_filter_max_sum": (45, 0, 45, True),
    "qxc_filter_compare_periods": (5, 0, 50, True),
    "qxc_filter_max_overlap": (3, 0, 7, True),
    "qxc_filter_min_sum": (0, 0, 63, True),
    "qxc_filter_max_sum": (63, 0, 63, True),
    "kl8_filter_compare_periods": (5, 0, 50, True),
    "kl8_filter_max_overlap": (5, 0, 20, True),
    "kl8_filter_min_sum": (0, 0, 800, True),
    "kl8_filter_max_sum": (800, 0, 800, True),
}

BOOL_PROPS = [
    "dark_theme",
    "auto_update_on_start",
    "ssq_filter_block_blue",
    "dlt_filter_block_back",
    "fc3d_filter_enabled",
    "pl3_filter_enabled",
    "pl5_filter_enabled",
    "qxc_filter_enabled",
    "kl8_filter_enabled",
    "dlt_filter_enabled",
]

STR_PROPS = [
    "last_strategy_id",
    "plugin_dir",
    "last_data_update",
    "last_backtest_date",
]


@pytest.fixture
def settings():
    s = AppSettings("CovDOrg", "CovDApp")
    for k in list(s._settings.allKeys()):
        s._settings.remove(k)
    s.sync()
    yield s
    for k in list(s._settings.allKeys()):
        s._settings.remove(k)
    s.sync()


class TestSettings:
    def test_base_get_set(self, settings):
        settings.set("custom_key", 123)
        assert settings.get("custom_key", 0) == 123
        assert settings.get("missing", "def") == "def"

    def test_int_props(self, settings):
        for name, (default, lo, hi, clamp) in INT_PROPS.items():
            setattr(settings, name, 2)
            assert getattr(settings, name) == 2
            # 通过属性 setter 传入不可转换的值 -> 覆盖 setter 的 except 分支
            setattr(settings, name, "abc")
            assert getattr(settings, name) == default
            above = hi + 100 if hi >= 0 else 100
            setattr(settings, name, above)
            got = getattr(settings, name)
            if clamp and hi >= 0:
                assert got == hi
            else:
                assert got == above
            below = lo - 100 if lo > 0 else -100
            setattr(settings, name, below)
            got = getattr(settings, name)
            if clamp and lo > 0:
                assert got == lo
            elif clamp and lo == 0:
                assert got == 0
            else:
                assert got == below
            settings.set(name, "garbage")
            assert getattr(settings, name) == default

    def test_bool_props(self, settings):
        for name in BOOL_PROPS:
            # 首次读取（key 未设置）-> raw 为默认 bool -> 覆盖 `return bool(raw)`
            assert getattr(settings, name) in (True, False)
            setattr(settings, name, True)
            assert getattr(settings, name) is True
            setattr(settings, name, False)
            assert getattr(settings, name) is False
            settings.set(name, "true")
            assert getattr(settings, name) is True
            settings.set(name, "no")
            assert getattr(settings, name) is False

    def test_auto_update_on_start_none(self, monkeypatch):
        s = AppSettings("CovDOrgNone", "CovDApp")
        mock = MagicMock()
        mock.value.return_value = None
        monkeypatch.setattr(s, "_settings", mock)
        assert s.auto_update_on_start is True

    def test_str_props(self, settings):
        for name in STR_PROPS:
            setattr(settings, name, "value")
            assert getattr(settings, name) == "value"

    def test_boss_key(self, settings):
        settings.boss_key = "  abc  "
        assert settings.boss_key == "abc"
        settings.boss_key = None
        assert settings.boss_key == ""
        settings.boss_key = ""
        assert settings.boss_key == ""

    def test_dict_options(self, settings):
        for name in ("last_strategy_options", "last_backtest_options"):
            setattr(settings, name, {"a": 1})
            assert getattr(settings, name) == {"a": 1}
            s2 = AppSettings("CovDOrg2", "CovDApp")
            assert getattr(s2, name) == {}
            settings.set(name, "not-json")
            assert getattr(settings, name) == {}
            setattr(settings, name, {"x": object()})
            assert getattr(settings, name) == {}

    def test_per_profile_methods(self, settings):
        pk = "ssq"
        # draw_analysis_max_gap
        settings.set_draw_analysis_max_gap(pk, 12)
        assert settings.get_draw_analysis_max_gap(pk) == 12
        settings.set_draw_analysis_max_gap(pk, "x")
        assert settings.get_draw_analysis_max_gap(pk) == 1
        settings.set(f"draw_analysis_{pk}_max_gap", "garbage")
        assert settings.get_draw_analysis_max_gap(pk) == 1
        assert settings.get_draw_analysis_max_gap("nope") == 1

        # draw_analysis_filter_threshold
        settings.set_draw_analysis_filter_threshold(pk, 8)
        assert settings.get_draw_analysis_filter_threshold(pk) == 8
        settings.set_draw_analysis_filter_threshold(pk, "x")
        assert settings.get_draw_analysis_filter_threshold(pk) == 1
        settings.set(f"draw_analysis_{pk}_filter_threshold", "garbage")
        assert settings.get_draw_analysis_filter_threshold(pk) == 1
        assert settings.get_draw_analysis_filter_threshold("nope") == 1

        # draw_analysis_group_mode
        settings.set_draw_analysis_group_mode(pk, "front")
        assert settings.get_draw_analysis_group_mode(pk) == "front"
        assert settings.get_draw_analysis_group_mode("nope") == "all"

        # batch_backtest_count
        settings.set_batch_backtest_count(pk, 33)
        assert settings.get_batch_backtest_count(pk) == 33
        settings.set_batch_backtest_count(pk, "x")
        assert settings.get_batch_backtest_count(pk) == 5
        settings.set(f"batch_backtest_{pk}_count", "garbage")
        assert settings.get_batch_backtest_count(pk) == 5
        assert settings.get_batch_backtest_count("nope") == 5

        # batch_backtest_filter_threshold
        settings.set_batch_backtest_filter_threshold(pk, 4)
        assert settings.get_batch_backtest_filter_threshold(pk) == 4
        settings.set_batch_backtest_filter_threshold(pk, "x")
        assert settings.get_batch_backtest_filter_threshold(pk) == 1
        settings.set(f"batch_backtest_{pk}_filter_threshold", "garbage")
        assert settings.get_batch_backtest_filter_threshold(pk) == 1
        assert settings.get_batch_backtest_filter_threshold("nope") == 1

        # batch_backtest_filter_periods
        settings.set_batch_backtest_filter_periods(pk, 9)
        assert settings.get_batch_backtest_filter_periods(pk) == 9
        settings.set_batch_backtest_filter_periods(pk, "x")
        assert settings.get_batch_backtest_filter_periods(pk) == 7
        settings.set(f"batch_backtest_{pk}_filter_periods", "garbage")
        assert settings.get_batch_backtest_filter_periods(pk) == 7
        assert settings.get_batch_backtest_filter_periods("nope") == 7

    def test_sync(self, settings):
        settings.sync()
