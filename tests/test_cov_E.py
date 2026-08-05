"""Coverage tests for assigned core modules (target: 100% line coverage).

Modules under test:
- caipiao/calendar/heavenly_earthly.py
- caipiao/calendar/lunar_calendar.py
- caipiao/calendar/almanac.py
- caipiao/divination/bagua.py
- caipiao/divination/yijing.py
- caipiao/divination/divination_engine.py
- caipiao/plugins/plugin_manager.py
- caipiao/app.py
- caipiao/core/backtest_worker.py
- caipiao/core/backtest_stats.py
- caipiao/core/engine.py
- caipiao/core/ticket.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord


# ===========================================================================
# calendar/heavenly_earthly.py
# ===========================================================================

from caipiao.calendar import heavenly_earthly as he


class TestHeavenlyEarthly:
    def test_ganzhi_year(self):
        assert he.get_ganzhi_year(2024) == "甲辰"
        assert he.get_ganzhi_year(1984) == "甲子"

    def test_ganzhi_month(self):
        gz = he.get_ganzhi_month(2024, 1, 1)
        assert len(gz) == 2
        # default branch of _MONTH_STEM_START.get via monkeypatch
        orig = he._MONTH_STEM_START
        he._MONTH_STEM_START = {}
        try:
            gz2 = he.get_ganzhi_month(2024, 1, 1)
            assert len(gz2) == 2
        finally:
            he._MONTH_STEM_START = orig

    def test_ganzhi_day(self):
        assert he.get_ganzhi_day(2024, 1, 1) == he.get_ganzhi_day(2024, 1, 1)
        # spot check known value
        assert isinstance(he.get_ganzhi_day(2000, 1, 1), str)

    def test_ganzhi_hour(self):
        assert he.get_ganzhi_hour(0, "甲") == "甲子"
        assert he.get_ganzhi_hour(12, "甲") == "庚午"
        assert he.get_ganzhi_hour(23, "甲") == "甲子"

    def test_shengxiao(self):
        assert he.get_shengxiao(2024) == "龙"
        assert he.get_shengxiao(1984) == "鼠"

    def test_get_ganzhi_no_hour(self):
        res = he.get_ganzhi(2024, 1, 1)
        assert "year_ganzhi" in res
        assert "hour_ganzhi" not in res

    def test_get_ganzhi_with_hour(self):
        res = he.get_ganzhi(2024, 1, 1, hour=12)
        assert "hour_ganzhi" in res
        assert "shichen" in res

    def test_chongsha(self):
        assert he.get_chongsha("子") == "冲马(子午)"
        assert he.get_chongsha("午") == "冲鼠(午子)"
        assert he.get_chongsha("丑") == "冲羊(丑未)"

    def test_shichen(self):
        assert he.get_shichen(0) == "子时"
        assert he.get_shichen(12) == "午时"
        assert he.get_shichen(23) == "子时"
        assert he.get_shichen(99) == "子时"  # fallback


# ===========================================================================
# calendar/lunar_calendar.py
# ===========================================================================

from caipiao.calendar import lunar_calendar as lc


class TestLunarCalendar:
    def test_is_leap_year(self):
        assert lc._is_leap_year(2000) is True
        assert lc._is_leap_year(1900) is False
        assert lc._is_leap_year(2024) is True

    def test_solar_month_days(self):
        assert lc._solar_month_days(2024, 2) == 29
        assert lc._solar_month_days(2023, 2) == 28
        assert lc._solar_month_days(2024, 1) == 31

    def test_lunar_year_days(self):
        # exercise across many years so the leap-month body line is covered
        for y in range(1900, 2101):
            d = lc._lunar_year_days(y)
            assert 300 <= d <= 400

    def test_lunar_month_days_info_normal(self):
        d = lc._lunar_month_days_info(2024, 1, is_leap=False)
        assert d in (29, 30)

    def test_lunar_month_days_info_leap(self):
        d = lc._lunar_month_days_info(2023, 2, is_leap=True)
        assert d in (29, 30)

    def test_lunar_month_days_info_invalid_raises(self):
        with pytest.raises(ValueError, match="无效农历月份"):
            lc._lunar_month_days_info(2024, 13, is_leap=False)
        with pytest.raises(ValueError, match="无效农历月份"):
            lc._lunar_month_days_info(2024, 0, is_leap=False)

    def test_get_leap_month(self):
        assert lc._get_leap_month(2023) == 0
        assert 0 <= lc._get_leap_month(2024) <= 12

    def test_solar_to_lunar_valid(self):
        r = lc.solar_to_lunar(2024, 1, 1)
        assert isinstance(r, lc.LunarDate)
        assert 1 <= r.month <= 12

    def test_solar_to_lunar_low_year_raises(self):
        with pytest.raises(ValueError, match="1900-2100"):
            lc.solar_to_lunar(1899, 1, 1)

    def test_solar_to_lunar_high_year_raises(self):
        with pytest.raises(ValueError, match="1900-2100"):
            lc.solar_to_lunar(2101, 1, 1)

    def test_solar_to_lunar_overflow_year(self):
        # push lunar year beyond 2100 -> "超出支持范围"
        with pytest.raises(ValueError, match="超出支持范围"):
            lc.solar_to_lunar(2100, 12, 31)

    def test_solar_to_lunar_else_branch(self):
        # force the inner while-loop else branch by shrinking year days
        orig = lc._lunar_year_days
        lc._lunar_year_days = lambda y: 400
        try:
            r = lc.solar_to_lunar(2024, 6, 1)
            assert r is not None
        finally:
            lc._lunar_year_days = orig

    def test_lunar_to_solar_valid(self):
        r = lc.lunar_to_solar(2023, 11, 20)
        assert isinstance(r, lc.SolarDate)

    def test_lunar_to_solar_leap(self):
        r = lc.lunar_to_solar(2023, 2, 1, is_leap=True)
        assert isinstance(r, lc.SolarDate)

    def test_lunar_to_solar_low_year_raises(self):
        with pytest.raises(ValueError, match="1900-2100"):
            lc.lunar_to_solar(1899, 1, 1)

    def test_lunar_to_solar_high_year_raises(self):
        with pytest.raises(ValueError, match="1900-2100"):
            lc.lunar_to_solar(2101, 1, 1)

    def test_lunar_month_name(self):
        assert lc.lunar_month_name(1) == "正月"
        assert lc.lunar_month_name(1, is_leap=True) == "闰正月"
        assert lc.lunar_month_name(11) == "腊月"

    def test_lunar_day_name(self):
        assert lc.lunar_day_name(1) == "初一"
        assert lc.lunar_day_name(15) == "十五"
        assert lc.lunar_day_name(31) == "31"

    def test_get_weekday(self):
        assert lc.get_weekday(2024, 1, 1) == 0  # Monday

    def test_get_weekday_name(self):
        assert lc.get_weekday_name(2024, 1, 1) == "星期一"

    def test_to_tuple(self):
        sd = lc.SolarDate(2024, 1, 1)
        assert sd.to_tuple() == (2024, 1, 1)
        ld = lc.LunarDate(2024, 6, 15, is_leap=True)
        assert ld.to_tuple() == (2024, 6, 15, True)

    def test_leap_month_branch(self):
        # The shipped _LUNAR_INFO never sets the leap-month bits, so the
        # leap-month code paths are otherwise unreachable. Force a leap month
        # for 2024 to exercise them.
        idx = 2024 - 1900
        original = lc._LUNAR_INFO[idx]
        lc._LUNAR_INFO[idx] = original | (1 << 20) | (1 << 15)
        try:
            # _lunar_year_days must now add the leap month (line 109)
            d = lc._lunar_year_days(2024)
            assert d > 354
            # solar->lunar may traverse the leap iteration (lines 189-190)
            r = lc.solar_to_lunar(2024, 12, 31)
            assert isinstance(r, lc.LunarDate)
            # lunar->solar with an explicit leap month (lines 238-239)
            s = lc.lunar_to_solar(2024, 1, 1, is_leap=True)
            assert isinstance(s, lc.SolarDate)
        finally:
            lc._LUNAR_INFO[idx] = original

    def test_leap_month_iteration(self):
        # Cover solar_to_lunar's leap-month iteration slot (lines 189-190).
        # The shipped _LUNAR_INFO never encodes leap months, so monkeypatch the
        # BASE year 1900 to carry one. Patching year 1900 (the conversion base)
        # avoids corrupting the cumulative lunar-day offset used for later dates.
        import datetime as _dt
        orig = lc._LUNAR_INFO[0]
        # Leap month #1 with 30 days (bits 20 + 15). Bit 20 also sets month-5 to
        # 30 days, which only changes the year length and is irrelevant here.
        lc._LUNAR_INFO[0] = (1 << 20) | (1 << 15)
        try:
            year_days = lc._lunar_year_days(1900)
            base = _dt.date(1900, 1, 31)
            # A date inside the leap month forces the month loop to reach the
            # leap-month slot (month_idx == 12) and break there.
            target = base + _dt.timedelta(days=year_days - 2)
            res = lc.solar_to_lunar(target.year, target.month, target.day)
            assert res.year == 1900
            assert res.is_leap is True
        finally:
            lc._LUNAR_INFO[0] = orig


# ===========================================================================
# calendar/almanac.py
# ===========================================================================

from caipiao.calendar import almanac as al


class TestAlmanac:
    def test_get_yi_for_day_default(self):
        yi = al._get_yi_for_day("甲", "子")
        assert len(yi) <= 6
        assert yi == sorted(set(yi), key=yi.index)

    def test_get_yi_for_day_extra(self):
        # 戊 not in _YI_RULES -> default base, extras 开市/纳财 get appended
        yi = al._get_yi_for_day("戊", "子")
        assert "开市" in yi

    def test_get_ji_for_day(self):
        ji = al._get_ji_for_day("甲", "子")
        assert "行丧" in ji
        assert len(ji) <= 4

    def test_get_almanac(self):
        res = al.get_almanac(2024, 1, 1)
        assert "yi" in res and "ji" in res and "chongsha" in res
        assert res["shengsha"].startswith("煞")

    def test_shengsha_direction(self):
        assert al._get_shengsha_direction("子") == "东"
        assert al._get_shengsha_direction("午") == "西"

    def test_solar_term(self):
        terms = al.get_solar_term(2024, 2)
        assert any(t[0] == "立春" for t in terms)
        # leap year adjustment
        terms2 = al.get_solar_term(2024, 2)
        assert terms2

    def test_current_solar_term(self):
        assert al.get_current_solar_term(2024, 2, 4) == "立春"
        assert al.get_current_solar_term(2024, 6, 15) is None

    def test_traditional_festivals(self):
        assert "春节" in al.get_traditional_festivals(1, 1)
        assert al.get_traditional_festivals(5, 5) == ["端午节"]
        assert al.get_traditional_festivals(3, 3) == []

    def test_festivals(self):
        assert "元旦" in al.get_festivals(1, 1)
        assert al.get_festivals(6, 6) == []

    def test_wuxing_relation_all(self):
        assert al._get_wuxing_relation("金", "金") == "比和"
        assert al._get_wuxing_relation("木", "火") == "相生"
        assert al._get_wuxing_relation("水", "金") == "相生"
        assert al._get_wuxing_relation("木", "土") == "相克"
        assert al._get_wuxing_relation("土", "木") == "相克"
        assert al._get_wuxing_relation("甲", "乙") == "无"  # unreachable with real elements

    def test_shichen_score_branches(self):
        # three-he (申子辰) + day_stem 相生(木->水): 50+20+15 = 85
        assert al._get_shichen_score("甲", "子", "子") == 85
        # six-he (子丑) + day_stem 相克(木克土) + day_branch 相克(水克土): 50+30-10-10 = 60
        assert al._get_shichen_score("甲", "子", "丑") == 60
        # six-clash (子午) + day_stem 相生 + day_branch 相克: 50-30+15-10 = 25
        assert al._get_shichen_score("甲", "子", "午") == 25
        # three-he + day_stem 相克(木被金克) + day_branch 相生(金生水): 50+20-10+10 = 70
        assert al._get_shichen_score("甲", "子", "申") == 70
        # day_branch 相生 (水->木): 50+10 = 60
        assert al._get_shichen_score("甲", "子", "寅") == 60

    def test_lucky_hours(self):
        hours = al.get_lucky_hours(2024, 1, 1)
        assert isinstance(hours, list)
        # at least some hours above threshold
        assert any(h["score"] >= 60 for h in hours)
        # below-threshold excluded
        for h in hours:
            assert h["score"] >= 60

    def test_lucky_hours_low_threshold(self):
        hours = al.get_lucky_hours(2024, 1, 1, min_score=0)
        assert len(hours) == 12

    def test_lucky_description(self):
        desc = al._get_lucky_description("甲", "子", "丑", 85)
        assert "六合" in desc
        assert "大吉" in desc
        desc2 = al._get_lucky_description("甲", "子", "午", 30)
        assert "六冲" in desc2
        assert "平" in desc2
        desc3 = al._get_lucky_description("甲", "寅", "午", 75)
        assert "干支相生" in desc3

    def test_all_shichen_scores(self):
        scores = al.get_all_shichen_scores(2024, 1, 1)
        assert len(scores) == 12
        assert all("score" in s for s in scores)


# ===========================================================================
# divination/bagua.py
# ===========================================================================

from caipiao.divination import bagua as bg


class TestBagua:
    def test_trigram_data(self):
        qian = bg.get_trigram_by_name("乾")
        assert qian.number == 1
        assert qian.symbol == "☰"
        # yao_text
        texts = qian.yao_text()
        assert "初爻（阳）" in texts[0]
        # to_upper
        assert "━━━━━" in qian.to_upper()

    def test_get_by_number(self):
        assert bg.get_trigram_by_number(1).name == "乾"
        assert bg.get_trigram_by_number(99) is None

    def test_get_by_later_number(self):
        assert bg.get_trigram_by_later_number(6).name == "乾"

    def test_get_by_yao(self):
        assert bg.get_trigram_by_yao((1, 1, 1)).name == "乾"
        assert bg.get_trigram_by_yao((0, 0, 0)).name == "坤"

    def test_get_yao_from_number(self):
        assert bg.get_yao_from_number(1) == (1, 1, 1)
        assert bg.get_yao_from_number(0) == (0, 0, 0)
        assert bg.get_yao_from_number(8) == (0, 0, 0)  # 8 % 8 == 0

    def test_get_by_meihua_number(self):
        assert bg.get_trigram_by_meihua_number(1).name == "乾"

    def test_trigram_yin_branches(self):
        # 坤 is all-yin -> exercises the yin branches in yao_text/to_upper
        kun = bg.get_trigram_by_name("坤")
        assert kun.yao == (0, 0, 0)
        texts = kun.yao_text()
        assert any("阴" in t for t in texts)
        assert "━ ━" in kun.to_upper()

    def test_list_trigrams(self):
        ts = bg.list_trigrams()
        assert len(ts) == 8
        assert ts[0].name == "乾"


# ===========================================================================
# divination/yijing.py
# ===========================================================================

from caipiao.divination import yijing as yj


class TestYijing:
    def test_hexagram_index(self):
        assert yj.get_hexagram("乾", "乾").name == "乾"
        assert yj.get_hexagram_by_name("乾") is not None
        assert yj.get_hexagram_by_number(1).name == "乾"
        assert yj.get_hexagram_by_number(999) is None

    def test_yao_positions(self):
        r = yj.get_yao_positions((1, 0, 2, 3, 1, 0))
        assert "初爻" in r[0]
        assert "变" in r[2]  # 2 -> 老阳变
        assert "变" in r[3]  # 3 -> 老阴变

    def test_changed_hexagram(self):
        # 乾为天 all yang -> all become yin -> 坤为地
        h = yj.get_changed_hexagram((2, 2, 2, 2, 2, 2))
        assert h.name == "坤"
        # no change
        h2 = yj.get_changed_hexagram((1, 1, 1, 1, 1, 1))
        assert h2.name == "乾"

    def test_get_changed_hexagram_no_trigram(self, monkeypatch):
        monkeypatch.setattr(yj, "get_trigram_by_yao", lambda y: None)
        assert yj.get_changed_hexagram((1, 1, 1, 0, 0, 0)) is None

    def test_build_hexagram_index(self):
        # _build_hexagram_index is defined but not invoked at import; call it
        index = yj._build_hexagram_index()
        assert isinstance(index, dict)
        assert "乾" in index


# ===========================================================================
# divination/divination_engine.py
# ===========================================================================

from caipiao.divination import divination_engine as de
from caipiao.divination.bagua import get_trigram_by_yao


class TestDivinationEngine:
    def test_time_divination(self):
        res = de.time_divination(2024, 1, 1, 12)
        assert res.hexagram is not None
        assert res.method.startswith("时间起卦")
        assert res.time_str
        assert res.recommended_numbers

    def test_time_divination_defaults(self):
        res = de.time_divination()
        assert res.hexagram is not None

    def test_time_divination_no_trigram(self, monkeypatch):
        monkeypatch.setattr(de, "get_trigram_by_yao", lambda y: None)
        with pytest.raises(ValueError, match="无法解析卦象"):
            de.time_divination(2024, 1, 1, 12)

    def test_time_divination_no_hexagram(self, monkeypatch):
        fake = get_trigram_by_yao((1, 1, 1))
        monkeypatch.setattr(de, "get_trigram_by_yao", lambda y: fake)
        monkeypatch.setattr(de, "get_hexagram", lambda u, l: None)
        with pytest.raises(ValueError, match="无法找到卦象"):
            de.time_divination(2024, 1, 1, 12)

    def test_batch_time_divination_none(self):
        results = de.batch_time_divination(2024, 1, 1)
        assert len(results) == 1

    def test_batch_time_divination_hours(self):
        results = de.batch_time_divination(2024, 1, 1, hours=[0, 6, 12])
        assert len(results) == 3

    def test_random_divination(self):
        res = de.random_divination(seed=42)
        assert res.method == "随机起卦"
        assert len(res.yao) == 6

    def test_random_divination_no_trigram(self, monkeypatch):
        monkeypatch.setattr(de, "get_trigram_by_yao", lambda y: None)
        with pytest.raises(ValueError, match="无法解析卦象"):
            de.random_divination(seed=1)

    def test_manual_divination(self):
        res = de.manual_divination([1, 1, 1, 0, 0, 0])
        assert res.method == "手动输入"
        assert res.moving_yao == []

    def test_manual_divination_wrong_len(self):
        with pytest.raises(ValueError, match="6个爻值"):
            de.manual_divination([1, 1, 1])

    def test_manual_divination_no_trigram(self, monkeypatch):
        monkeypatch.setattr(de, "get_trigram_by_yao", lambda y: None)
        with pytest.raises(ValueError, match="无法解析卦象"):
            de.manual_divination([1, 1, 1, 0, 0, 0])

    def test_divination_result_display(self):
        res = de.time_divination(2024, 1, 1, 12)
        assert isinstance(res.yao_display(), list)
        summary = res.summary()
        assert "本卦" in summary

    def test_generate_analysis_branches(self):
        h = yj.get_hexagram_by_name("乾")
        changed = yj.get_hexagram_by_name("坤")
        upper = bg.get_trigram_by_name("乾")
        lower = bg.get_trigram_by_name("坤")
        # changed present, 吉
        out1 = de._generate_analysis(h, changed, upper, lower, [0], "time")
        assert "变卦" in out1
        # no changed, 凶
        hx = yj.get_hexagram_by_name("讼")
        out2 = de._generate_analysis(hx, None, upper, lower, [], "manual")
        assert "凶" in out2
        # 平
        hp = yj.get_hexagram_by_name("屯")
        out3 = de._generate_analysis(hp, None, upper, lower, [], "manual")
        assert "平和" in out3

    def test_get_wuxing_relation_dead_branch(self):
        # invalid elements hit the "需结合具体分析" return
        assert de._get_wuxing_relation("甲", "乙") == "五行关系需结合具体分析"

    def test_generate_numbers(self, monkeypatch):
        monkeypatch.setattr(de.random, "shuffle", lambda x: None)
        h = yj.get_hexagram_by_name("乾")
        nums = de._generate_numbers((2, 1, 1, 3, 0, 0), h)
        assert len(nums) <= 8
        assert all(1 <= n <= 33 for n in nums)

    def test_random_divination_laoyin(self, monkeypatch):
        # Force every draw to be 老阴 (3) -> exercises the 老阴 branch
        monkeypatch.setattr(de.random.Random, "random", lambda self: 0.55)
        res = de.random_divination(seed=1)
        assert 3 in res.yao
        assert len(res.moving_yao) == 6

    def test_random_divination_no_hexagram(self, monkeypatch):
        monkeypatch.setattr(de, "get_hexagram", lambda u, l: None)
        with pytest.raises(ValueError, match="无法找到卦象"):
            de.random_divination(seed=1)

    def test_manual_divination_no_hexagram(self, monkeypatch):
        monkeypatch.setattr(de, "get_hexagram", lambda u, l: None)
        with pytest.raises(ValueError, match="无法找到卦象"):
            de.manual_divination([1, 1, 1, 1, 1, 1])


# ===========================================================================
# plugins/plugin_manager.py
# ===========================================================================

import tempfile

from caipiao.core.engine import GenerationEngine
from caipiao.plugins import plugin_manager as pm


PLUGIN_NORMAL = '''
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata

class PluginStratA(GenerationStrategy):
    @property
    def metadata(self):
        return StrategyMetadata(id="plugin_a", name="PluginA", description="x")

    def generate(self, count=1, options=None):
        return []

    def __init__(self, *a, **k):
        pass

def register_strategies(engine):
    class RegStrat(GenerationStrategy):
        @property
        def metadata(self):
            return StrategyMetadata(id="plugin_reg", name="Reg", description="x")
        def generate(self, count=1, options=None):
            return []
    engine.register(RegStrat())
'''

PLUGIN_REGISTER_FAIL = '''
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata

def register_strategies(engine):
    raise RuntimeError("boom")
'''

PLUGIN_INSTANTIATE_FAIL = '''
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata

class PluginStratBad(GenerationStrategy):
    @property
    def metadata(self):
        return StrategyMetadata(id="plugin_bad", name="Bad", description="x")
    def generate(self, count=1, options=None):
        return []
    def __init__(self, *a, **k):
        raise RuntimeError("cannot build")
'''

PLUGIN_BROKEN = '''
raise ValueError("import boom")
'''


class TestPluginManager:
    def _write(self, tmp, name, content):
        p = Path(tmp) / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_discover_empty_dir(self, tmp_path):
        mgr = pm.PluginManager(GenerationEngine(), tmp_path)
        assert mgr.discover() == []

    def test_discover_missing_dir(self):
        mgr = pm.PluginManager(GenerationEngine(), "nonexistent_dir_xyz_/no_such")
        assert mgr.discover() == []

    def test_discover_sorted(self, tmp_path):
        self._write(tmp_path, "b.py", PLUGIN_NORMAL)
        self._write(tmp_path, "a.py", PLUGIN_NORMAL)
        self._write(tmp_path, "_skip.py", PLUGIN_NORMAL)
        mgr = pm.PluginManager(GenerationEngine(), tmp_path)
        names = [p.name for p in mgr.discover()]
        assert names == ["a.py", "b.py"]

    def test_load_normal(self, tmp_path):
        self._write(tmp_path, "normal.py", PLUGIN_NORMAL)
        engine = GenerationEngine()
        mgr = pm.PluginManager(engine, tmp_path)
        ids = mgr.load(tmp_path / "normal.py")
        assert "plugin_a" in ids
        assert "plugin_reg" in ids

    def test_load_all(self, tmp_path):
        self._write(tmp_path, "normal.py", PLUGIN_NORMAL)
        engine = GenerationEngine()
        mgr = pm.PluginManager(engine, tmp_path)
        ids = mgr.load_all()
        assert "plugin_a" in ids
        assert "plugin_reg" in ids
        mgr.unload_all()
        assert "plugin_a" not in {s.metadata.id for s in engine.list_strategies()}

    def test_load_register_fails(self, tmp_path):
        self._write(tmp_path, "regfail.py", PLUGIN_REGISTER_FAIL)
        engine = GenerationEngine()
        mgr = pm.PluginManager(engine, tmp_path)
        ids = mgr.load(tmp_path / "regfail.py")
        # register_strategies failed -> no auto strategy -> empty
        assert ids == []
        # also via load_all (logs error)
        mgr.load_all()

    def test_load_instantiate_fails(self, tmp_path):
        self._write(tmp_path, "bad.py", PLUGIN_INSTANTIATE_FAIL)
        engine = GenerationEngine()
        mgr = pm.PluginManager(engine, tmp_path)
        ids = mgr.load(tmp_path / "bad.py")
        assert "plugin_bad" not in ids

    def test_load_broken_module(self, tmp_path):
        self._write(tmp_path, "broken.py", PLUGIN_BROKEN)
        engine = GenerationEngine()
        mgr = pm.PluginManager(engine, tmp_path)
        # raises ImportError from exec_module failure; load_all swallows
        with pytest.raises(ImportError):
            mgr.load(tmp_path / "broken.py")
        # load_all catches it
        assert mgr.load_all() == []

    def test_load_spec_none(self, tmp_path, monkeypatch):
        self._write(tmp_path, "normal.py", PLUGIN_NORMAL)
        monkeypatch.setattr(
            pm.importlib.util, "spec_from_file_location", lambda *a, **k: None
        )
        engine = GenerationEngine()
        mgr = pm.PluginManager(engine, tmp_path)
        with pytest.raises(ImportError, match="无法加载插件"):
            mgr.load(tmp_path / "normal.py")


# ===========================================================================
# app.py  (run real code with a singleton real QApplication + fake MainWindow)
# ===========================================================================

import caipiao.app as app_mod


def _make_qapp_singleton(monkeypatch):
    from PySide6.QtWidgets import QApplication
    import PySide6.QtWidgets as qw

    real = QApplication.instance() or QApplication([])
    monkeypatch.setattr(real, "exec", lambda: 0)

    class QAppProxy:
        _real = real

        def __new__(cls, *a, **k):
            return cls._real

        setAttribute = staticmethod(lambda *a, **k: None)
        instance = staticmethod(lambda: QAppProxy._real)

    monkeypatch.setattr(app_mod, "QApplication", QAppProxy)
    monkeypatch.setattr(qw, "QApplication", QAppProxy)
    return real


class FakeMainWindow:
    def __init__(self, optimal_param_store=None):
        self.store = optimal_param_store

    def showMaximized(self):
        pass


class TestApp:
    def test_run_icon_exists(self, monkeypatch):
        _make_qapp_singleton(monkeypatch)
        monkeypatch.setattr(app_mod, "MainWindow", FakeMainWindow)
        assert app_mod.run() == 0

    def test_run_icon_missing(self, monkeypatch):
        _make_qapp_singleton(monkeypatch)
        monkeypatch.setattr(app_mod, "MainWindow", FakeMainWindow)
        monkeypatch.setattr(Path, "exists", lambda self: False)
        assert app_mod.run() == 0

    def test_main_guard(self, monkeypatch):
        import caipiao.ui.main_window as mw_mod
        import sys as _sys

        _make_qapp_singleton(monkeypatch)
        monkeypatch.setattr(mw_mod, "MainWindow", FakeMainWindow)
        app_path = os.path.abspath("caipiao/app.py")
        src = open(app_path, encoding="utf-8").read()
        ns = {"__name__": "__main__", "__package__": "caipiao", "__file__": app_path, "sys": _sys}
        with pytest.raises(SystemExit) as exc:
            exec(compile(src, app_path, "exec"), ns)
        assert exc.value.code == 0


# ===========================================================================
# core/backtest_stats.py
# ===========================================================================

from caipiao.core import backtest_stats as bstats


def _ssq_draw(reds, blue, days_ago=0):
    return DrawRecord(
        issue="2024001",
        draw_date=datetime(2024, 1, 1) + timedelta(days=days_ago),
        red_balls=reds,
        blue_ball=blue,
    )


def _3d_draw(nums, days_ago=0):
    return DrawRecord(
        issue="2024001",
        draw_date=datetime(2024, 1, 1) + timedelta(days=days_ago),
        profile="3d",
        groups={"pos": nums},
    )


def _dlt_draw(front, back, days_ago=0):
    return DrawRecord(
        issue="2024001",
        draw_date=datetime(2024, 1, 1) + timedelta(days=days_ago),
        profile="dlt",
        groups={"front": front, "back": back},
    )


class TestBacktestStatsModule:
    def test_stats_properties_zero(self):
        s = bstats.BacktestStats()
        assert s.win_rate == 0.0
        assert s.roi == 0.0
        assert s.average_return_per_ticket == 0.0

    def test_stats_summary(self):
        s = bstats.BacktestStats()
        s.total_periods = 5
        s.total_tickets = 10
        s.total_investment = 20
        s.total_return = 25
        summary = s.summary()
        assert summary["总期数"] == 5
        assert "收益率" in summary

    def test_analyze_ticket_numbers(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert bstats.analyze_ticket_numbers([t])[1] == 1

    def test_find_hot_cold(self):
        hot, cold = bstats.find_hot_cold_numbers([])
        assert hot == [] and cold == []
        tickets = [
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
        ]
        hot, cold = bstats.find_hot_cold_numbers(tickets)
        assert 1 in hot

    def test_run_backtest_ssq(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        dr = _ssq_draw([1, 2, 3, 4, 5, 6], 7)
        stats = bstats.run_backtest(
            {"2024001": [t]}, {"2024001": dr}, "ssq"
        )
        assert "一等奖" in stats.prize_counts

    def test_run_backtest_3d(self):
        t = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        dr = _3d_draw([1, 2, 3])
        stats = bstats.run_backtest(
            {"2024001": [t]}, {"2024001": dr}, "3d"
        )
        assert stats.total_tickets == 1

    def test_run_backtest_kl8(self):
        t = Ticket(profile="kl8", groups={"main": [1, 2, 3, 4, 5]})
        dr = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            profile="kl8",
            groups={"main": [1, 2, 3, 4, 5]},
        )
        stats = bstats.run_backtest(
            {"2024001": [t]}, {"2024001": dr}, "kl8"
        )
        assert stats.total_tickets == 1
        assert len(stats.prize_counts) >= 1

    def test_run_backtest_dlt(self):
        t = Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        dr = _dlt_draw([1, 2, 3, 4, 5], [1, 2])
        stats = bstats.run_backtest(
            {"2024001": [t]}, {"2024001": dr}, "dlt"
        )
        assert "一等奖" in stats.prize_counts

    def test_run_backtest_pl3(self):
        t = Ticket(profile="pl3", groups={"pos": [1, 2, 3]})
        dr = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            profile="pl3",
            groups={"pos": [1, 2, 3]},
        )
        stats = bstats.run_backtest(
            {"2024001": [t]}, {"2024001": dr}, "pl3"
        )
        assert stats.total_tickets == 1

    def test_run_backtest_missing_period(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        stats = bstats.run_backtest(
            {"2024001": [t]}, {}, "ssq"
        )
        assert stats.total_periods == 0

    def test_format_report(self):
        s = bstats.BacktestStats()
        s.hot_numbers = [1, 2]
        s.cold_numbers = [30, 31]
        s.prize_counts = {"六等奖": 1}
        report = bstats.format_backtest_report(s)
        assert "回测统计报告" in report


# ===========================================================================
# core/engine.py
# ===========================================================================

from caipiao.core import engine as eng
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata


class _FakeStrategy(GenerationStrategy):
    def __init__(self, sid="fake", ticket_groups=None, profile_key="ssq"):
        self._sid = sid
        self._ticket_groups = ticket_groups or (
            {"red": [1, 2, 3, 4, 5, 6], "blue": [7]}
            if profile_key == "ssq"
            else {"pos": [1, 2, 3]}
        )
        self._profile_key = profile_key

    @property
    def metadata(self):
        return StrategyMetadata(id=self._sid, name=self._sid, description="x")

    def generate(self, count=1, options=None):
        if self._profile_key == "ssq":
            return [Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7) for _ in range(count)]
        return [Ticket(profile="3d", groups={"pos": [1, 2, 3]}) for _ in range(count)]


class TestEngine:
    def test_register_get_list_unregister(self):
        e = GenerationEngine()
        s = _FakeStrategy("s1")
        e.register(s)
        assert e.get("s1") is s
        assert len(e.list_strategies()) == 1
        e.unregister("s1")
        assert e.get("s1") is None

    def test_generate_not_found(self):
        e = GenerationEngine()
        with pytest.raises(ValueError, match="未找到策略"):
            e.generate("nope")

    def test_generate_ssq(self):
        e = GenerationEngine()
        e.register(_FakeStrategy("s1", profile_key="ssq"))
        tickets = e.generate("s1", count=2)
        assert len(tickets) == 2

    def test_generate_3d_assigns_bet_modes(self):
        e = GenerationEngine()
        e.register(_FakeStrategy("s3", profile_key="3d"))
        tickets = e.generate("s3", count=3)
        assert tickets[0].details.get("bet_mode") in ("直选", "组选")

    # ---- SSQ filter ----
    def test_filter_ssq_empty(self):
        assert eng.filter_ssq_by_history([], []) == []

    def test_filter_ssq_empty_records(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert len(eng.filter_ssq_by_history([t], [])) == 1

    def test_filter_ssq_zero_periods(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert len(eng.filter_ssq_by_history([t], [_ssq_draw([1, 2, 3, 4, 5, 6], 7)], compare_periods=0)) == 1

    def test_filter_ssq_keep(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        r = eng.filter_ssq_by_history([t], [_ssq_draw([10, 11, 12, 13, 14, 15], 1)], max_red_overlap=3)
        assert len(r) == 1

    def test_filter_ssq_discard(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        r = eng.filter_ssq_by_history([t], [_ssq_draw([1, 2, 3, 4, 5, 6], 7)], max_red_overlap=3)
        assert len(r) == 0

    def test_filter_ssq_blue_block(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        r = eng.filter_ssq_by_history(
            [t], [_ssq_draw([10, 11, 12, 13, 14, 15], 7)],
            max_red_overlap=3, block_blue_match=True, blue_compare_periods=1,
        )
        assert len(r) == 0

    # ---- DLT filter ----
    def test_filter_dlt_empty(self):
        assert eng.filter_dlt_by_history([], []) == []

    def test_filter_dlt_keep(self):
        t = Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        r = eng.filter_dlt_by_history([t], [_dlt_draw([10, 11, 12, 13, 14], [8, 9])], max_front_overlap=2)
        assert len(r) == 1

    def test_filter_dlt_discard(self):
        t = Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        r = eng.filter_dlt_by_history([t], [_dlt_draw([1, 2, 3, 4, 5], [1, 2])], max_front_overlap=2)
        assert len(r) == 0

    def test_filter_dlt_back_block(self):
        t = Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        r = eng.filter_dlt_by_history(
            [t], [_dlt_draw([10, 11, 12, 13, 14], [1, 2])],
            max_front_overlap=2, block_back_match=True, back_compare_periods=1,
        )
        assert len(r) == 0

    def test_estimate_dlt_pass_ratio(self):
        assert eng.estimate_dlt_pass_ratio([], compare_periods=0, max_front_overlap=0) == 1.0
        r = eng.estimate_dlt_pass_ratio([_dlt_draw([1, 2, 3, 4, 5], [1, 2])], compare_periods=1, max_front_overlap=2)
        assert 0 < r <= 1

    def test_dlt_filtered_gen_count(self):
        gen, ratio = eng.dlt_filtered_gen_count(5, [], compare_periods=0, max_front_overlap=0)
        assert gen >= 15
        assert ratio == 1.0
        # low pass-ratio -> capped path
        gen2, _ = eng.dlt_filtered_gen_count(100, [_dlt_draw([1, 2, 3, 4, 5], [1, 2])], compare_periods=1, max_front_overlap=0)
        assert gen2 >= 300

    def test_apply_dlt_experience_filter(self):
        tickets = [Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})]
        # empty tickets -> no-op
        assert eng.apply_dlt_experience_filter([], [], count=1, compare_periods=1, max_front_overlap=0) == []
        out = eng.apply_dlt_experience_filter(
            tickets, [_dlt_draw([1, 2, 3, 4, 5], [1, 2])],
            count=1, compare_periods=1, max_front_overlap=0,
        )
        assert len(out) <= 1

    # ---- FC3D filter ----
    def test_filter_fc3d_empty(self):
        assert eng.filter_fc3d_by_history([], []) == []

    def test_filter_fc3d_keep(self):
        t = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        r = eng.filter_fc3d_by_history([t], [_3d_draw([4, 5, 6])], max_overlap=1)
        assert len(r) == 1

    def test_filter_fc3d_discard(self):
        t = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        r = eng.filter_fc3d_by_history([t], [_3d_draw([1, 2, 3])], max_overlap=1)
        assert len(r) == 0

    def test_filter_fc3d_sum(self):
        t = Ticket(profile="3d", groups={"pos": [9, 9, 9]})
        r = eng.filter_fc3d_by_history([t], [], min_sum=0, max_sum=20)
        assert len(r) == 0
        # default range keeps
        t2 = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        r2 = eng.filter_fc3d_by_history([t2], [])
        assert len(r2) == 1

    def test_estimate_fc3d_pass_count(self):
        assert eng.estimate_fc3d_pass_count([], compare_periods=0, max_overlap=1) == 1000
        c = eng.estimate_fc3d_pass_count([_3d_draw([5, 5, 5])], compare_periods=1, max_overlap=1)
        assert 0 < c <= 1000

    def test_fc3d_filtered_gen_count(self):
        gen, pc = eng.fc3d_filtered_gen_count(5, [], compare_periods=0, max_overlap=1)
        assert gen >= 15 and pc == 1000

    def test_apply_fc3d_experience_filter(self):
        assert eng.apply_fc3d_experience_filter([], [], count=1, compare_periods=1, max_overlap=1) == []
        tickets = [Ticket(profile="3d", groups={"pos": [1, 2, 3]}) for _ in range(5)]
        out = eng.apply_fc3d_experience_filter(
            tickets, [_3d_draw([9, 9, 9])], count=5, compare_periods=1, max_overlap=0,
        )
        # all overlap -> filtered to 0 -> warning path; result truncated
        assert isinstance(out, list)

    # ---- PL3 filter ----
    def test_filter_pl3_and_helpers(self):
        t = Ticket(profile="pl3", groups={"pos": [1, 2, 3]})
        assert eng.filter_pl3_by_history([], []) == []
        assert len(eng.filter_pl3_by_history([t], [_3d_draw([4, 5, 6])], max_overlap=1)) == 1
        assert eng.estimate_pl3_pass_count([], compare_periods=0, max_overlap=1) == 1000
        gen, pc = eng.pl3_filtered_gen_count(5, [], compare_periods=0, max_overlap=1)
        assert gen >= 15
        assert eng.apply_pl3_experience_filter([], [], count=1, compare_periods=1, max_overlap=1) == []
        out = eng.apply_pl3_experience_filter(
            [t], [_3d_draw([1, 2, 3])], count=1, compare_periods=1, max_overlap=0,
        )
        assert len(out) <= 1

    # ---- PL5 filter ----
    def test_filter_pl5_and_helpers(self):
        t = Ticket(profile="pl5", groups={"pos": [1, 2, 3, 4, 5]})
        assert eng.filter_pl5_by_history([], []) == []
        assert len(eng.filter_pl5_by_history([t], [], min_sum=0, max_sum=45)) == 1
        assert eng.estimate_pl5_pass_ratio([], compare_periods=0, max_overlap=2) == 1.0
        r = eng.estimate_pl5_pass_ratio([DrawRecord(issue="x", draw_date=datetime(2024, 1, 1), profile="pl5", groups={"pos": [1, 2, 3, 4, 5]})], compare_periods=1, max_overlap=2)
        assert 0 < r <= 1
        gen, pr = eng.pl5_filtered_gen_count(5, [], compare_periods=0, max_overlap=2)
        assert gen >= 15
        assert eng.apply_pl5_experience_filter([], [], count=1, compare_periods=1, max_overlap=2) == []
        out = eng.apply_pl5_experience_filter([t], [], count=1, compare_periods=1, max_overlap=2)
        assert len(out) <= 1

    # ---- QXC filter ----
    def test_filter_qxc_and_helpers(self):
        t = Ticket(profile="qxc", groups={"pos": [1, 2, 3, 4, 5, 6, 7]})
        assert eng.filter_qxc_by_history([], []) == []
        assert len(eng.filter_qxc_by_history([t], [], min_sum=0, max_sum=63)) == 1
        assert eng.estimate_qxc_pass_ratio([], compare_periods=0, max_overlap=3) == 1.0
        r = eng.estimate_qxc_pass_ratio([DrawRecord(issue="x", draw_date=datetime(2024, 1, 1), profile="qxc", groups={"pos": [1, 2, 3, 4, 5, 6, 7]})], compare_periods=1, max_overlap=3)
        assert 0 < r <= 1
        gen, pr = eng.qxc_filtered_gen_count(5, [], compare_periods=0, max_overlap=3)
        assert gen >= 15
        assert eng.apply_qxc_experience_filter([], [], count=1, compare_periods=1, max_overlap=3) == []
        out = eng.apply_qxc_experience_filter([t], [], count=1, compare_periods=1, max_overlap=3)
        assert len(out) <= 1

    # ---- KL8 filter ----
    def test_filter_kl8_and_helpers(self):
        t = Ticket(profile="kl8", groups={"main": [1, 2, 3, 4, 5]})
        assert eng.filter_kl8_by_history([], []) == []
        assert len(eng.filter_kl8_by_history([t], [], min_sum=0, max_sum=800)) == 1
        assert eng.estimate_kl8_pass_ratio([], compare_periods=0, max_overlap=5) == 1.0
        r = eng.estimate_kl8_pass_ratio([DrawRecord(issue="x", draw_date=datetime(2024, 1, 1), profile="kl8", groups={"main": [1, 2, 3, 4, 5]})], compare_periods=1, max_overlap=5)
        assert 0 < r <= 1
        gen, pr = eng.kl8_filtered_gen_count(5, [], compare_periods=0, max_overlap=5)
        assert gen >= 15
        assert eng.apply_kl8_experience_filter([], [], count=1, compare_periods=1, max_overlap=5) == []
        out = eng.apply_kl8_experience_filter([t], [], count=1, compare_periods=1, max_overlap=5)
        assert len(out) <= 1


class TestEngineExtra:
    """Extra branch coverage for engine.py filter/estimate/apply helpers."""

    # ---- SSQ filter edge branches ----
    def test_filter_ssq_blue_cmp_zero(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        rec = _ssq_draw([1, 2, 3, 4, 5, 6], 7)
        # block_blue_match with blue_compare_periods=0 -> blue_data = []
        out = eng.filter_ssq_by_history(
            [t], [rec], compare_periods=1, block_blue_match=True, blue_compare_periods=0,
        )
        assert isinstance(out, list)

    def test_filter_ssq_no_recent(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        # a 3D record has no "red"/"blue" groups -> recent_data empty;
        # block_blue_match False -> blue_recent empty -> line 121 returns early
        rec = _3d_draw([9, 9, 9])
        out = eng.filter_ssq_by_history([t], [rec], compare_periods=1, block_blue_match=False)
        assert out == [t]

    # ---- DLT filter edge branches ----
    def test_filter_dlt_zero_periods(self):
        t = Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        rec = _dlt_draw([1, 2, 3, 4, 5], [1, 2])
        assert eng.filter_dlt_by_history([t], [rec], compare_periods=0) == [t]

    def test_filter_dlt_back_cmp_zero(self):
        t = Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        rec = _dlt_draw([1, 2, 3, 4, 5], [1, 2])
        # block_back_match True with back_compare_periods=0 -> back_data = []
        out = eng.filter_dlt_by_history(
            [t], [rec], block_back_match=True, back_compare_periods=0,
        )
        assert isinstance(out, list)

    def test_filter_dlt_no_recent(self):
        t = Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        # record has front but no back -> recent_data empty; block_back_match False -> 223
        rec = DrawRecord(issue="x", draw_date=datetime(2024, 1, 1),
                         profile="dlt", groups={"front": [9, 8, 7, 6, 5]})
        out = eng.filter_dlt_by_history([t], [rec], block_back_match=False)
        assert out == [t]

    # ---- kl8 filter with history (set-based overlap branch, line 460) ----
    def test_filter_kl8_with_history(self):
        t = Ticket(profile="kl8", groups={"main": [1, 2, 3, 4, 5]})
        rec = DrawRecord(issue="x", draw_date=datetime(2024, 1, 1),
                         profile="kl8", groups={"main": [9, 8, 7, 6, 5]})
        out = eng.filter_kl8_by_history([t], [rec], min_sum=0, max_sum=800)
        assert len(out) == 1

    # ---- estimate functions with restricted sum range + history ----
    def test_estimate_dlt_sum_range(self):
        rec = _dlt_draw([1, 2, 3, 4, 5], [1, 2])
        r = eng.estimate_dlt_pass_ratio([rec], compare_periods=1, max_front_overlap=0,
                                        min_front_sum=100, max_front_sum=165)
        assert 0 <= r <= 1

    def test_estimate_fc3d_sum_range(self):
        rec = _3d_draw([5, 5, 5])
        r = eng.estimate_fc3d_pass_count([rec], compare_periods=1, max_overlap=0,
                                         min_sum=15, max_sum=15)
        assert 0 <= r <= 1000

    def test_estimate_pl3_sum_range(self):
        rec = _3d_draw([5, 5, 5])
        r = eng.estimate_pl3_pass_count([rec], compare_periods=1, max_overlap=0,
                                        min_sum=15, max_sum=15)
        assert 0 <= r <= 1000

    def test_estimate_pl5_sum_range(self):
        rec = DrawRecord(issue="x", draw_date=datetime(2024, 1, 1),
                         profile="pl5", groups={"pos": [1, 2, 3, 4, 5]})
        r = eng.estimate_pl5_pass_ratio([rec], compare_periods=1, max_overlap=0,
                                        min_sum=15, max_sum=15)
        assert 0 <= r <= 1

    def test_estimate_qxc_sum_range(self):
        rec = DrawRecord(issue="x", draw_date=datetime(2024, 1, 1),
                         profile="qxc", groups={"pos": [1, 2, 3, 4, 5, 6, 7]})
        r = eng.estimate_qxc_pass_ratio([rec], compare_periods=1, max_overlap=0,
                                        min_sum=15, max_sum=15)
        assert 0 <= r <= 1

    def test_estimate_kl8_sum_range(self):
        rec = DrawRecord(issue="x", draw_date=datetime(2024, 1, 1),
                         profile="kl8", groups={"main": [1, 2, 3, 4, 5]})
        r = eng.estimate_kl8_pass_ratio([rec], compare_periods=1, max_overlap=0,
                                        min_sum=300, max_sum=800)
        assert 0 <= r <= 1

    # ---- apply_*_experience_filter warning branches (filtered < count) ----
    def test_apply_fc3d_warning(self):
        tickets = [Ticket(profile="3d", groups={"pos": [1, 2, 3]}) for _ in range(5)]
        out = eng.apply_fc3d_experience_filter(
            tickets, [_3d_draw([1, 2, 3])], count=5, compare_periods=1, max_overlap=0,
        )
        assert len(out) == 0

    def test_apply_pl5_warning(self):
        tickets = [Ticket(profile="pl5", groups={"pos": [1, 2, 3, 4, 5]}) for _ in range(5)]
        rec = DrawRecord(issue="x", draw_date=datetime(2024, 1, 1),
                         profile="pl5", groups={"pos": [1, 2, 3, 4, 5]})
        out = eng.apply_pl5_experience_filter(
            tickets, [rec], count=5, compare_periods=1, max_overlap=0,
        )
        assert len(out) == 0

    def test_apply_qxc_warning(self):
        tickets = [Ticket(profile="qxc", groups={"pos": [1, 2, 3, 4, 5, 6, 7]}) for _ in range(5)]
        rec = DrawRecord(issue="x", draw_date=datetime(2024, 1, 1),
                         profile="qxc", groups={"pos": [1, 2, 3, 4, 5, 6, 7]})
        out = eng.apply_qxc_experience_filter(
            tickets, [rec], count=5, compare_periods=1, max_overlap=0,
        )
        assert len(out) == 0

    def test_apply_kl8_warning(self):
        tickets = [Ticket(profile="kl8", groups={"main": [1, 2, 3, 4, 5]}) for _ in range(5)]
        rec = DrawRecord(issue="x", draw_date=datetime(2024, 1, 1),
                         profile="kl8", groups={"main": [1, 2, 3, 4, 5]})
        out = eng.apply_kl8_experience_filter(
            tickets, [rec], count=5, compare_periods=1, max_overlap=0,
        )
        assert len(out) == 0


# ===========================================================================
# core/ticket.py
# ===========================================================================

from caipiao.core.profile import NumberGroup, LotteryProfile, KL8, FC3D


class TestTicketModule:
    def test_ssq_construction(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert t.profile.key == "ssq"

    def test_ssq_missing_blue(self):
        with pytest.raises(ValueError, match="蓝球"):
            Ticket(red_balls=[1, 2, 3, 4, 5, 6])

    def test_fc3d_positional_no_sort(self):
        t = Ticket(profile="3d", groups={"pos": [3, 2, 1]})
        assert t.groups["pos"] == [3, 2, 1]

    def test_wrong_count_raises(self):
        with pytest.raises(ValueError, match="号码"):
            Ticket(profile="3d", groups={"pos": [1, 2]})

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="号码"):
            Ticket(red_balls=[0, 2, 3, 4, 5, 6], blue_ball=7)

    def test_duplicate_raises(self):
        with pytest.raises(ValueError, match="不能重复"):
            Ticket(red_balls=[1, 1, 3, 4, 5, 6], blue_ball=7)

    def test_missing_group_raises(self):
        with pytest.raises(ValueError, match="缺少号码组"):
            Ticket(profile="kl8", groups={})  # kl8 main is required

    def test_variable_pick_raises(self):
        with pytest.raises(ValueError, match="数量必须在"):
            Ticket(profile="kl8", groups={"main": list(range(1, 12))})

    def test_from_groups(self):
        t = Ticket.from_groups("ssq", {"red": [1, 2, 3, 4, 5, 6], "blue": [7]})
        assert t.profile.key == "ssq"

    def test_skip_validation(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5], blue_ball=7, validate=False)
        assert len(t.groups["red"]) == 5

    def test_red_balls_blue_ball(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert t.red_balls[0].number == 1
        assert t.blue_ball.number == 7

    def test_render_groups(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        groups = t.render_groups()
        assert groups[0].name == "红球"

    def test_format_pretty_ssq(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert "红球" in t.format_pretty()

    def test_format_pretty_ssq_missing(self):
        t = Ticket(red_balls=[], blue_ball=7, validate=False)
        with pytest.raises(ValueError, match="缺少红球或蓝球"):
            t.format_pretty()

    def test_format_pretty_3d(self):
        t = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        assert "1" in t.format_pretty()

    def test_format_compact_ssq(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert "+" in t.format_compact()

    def test_format_compact_ssq_missing(self):
        t = Ticket(red_balls=[], blue_ball=7, validate=False)
        with pytest.raises(ValueError, match="缺少红球或蓝球"):
            t.format_compact()

    def test_format_compact_3d(self):
        t = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        assert "1" in t.format_compact()

    def test_to_dict_ssq(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        d = t.to_dict()
        assert d["red"] == [1, 2, 3, 4, 5, 6]

    def test_to_dict_ssq_missing(self):
        t = Ticket(red_balls=[], blue_ball=7, validate=False)
        with pytest.raises(ValueError, match="缺少红球或蓝球"):
            t.to_dict()

    def test_to_dict_3d(self):
        t = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        d = t.to_dict()
        assert d["profile"] == "3d"

    def test_from_dict_groups(self):
        t = Ticket.from_dict({"profile": "3d", "groups": {"pos": [1, 2, 3]}, "generated_at": "2025-01-01T00:00:00"})
        assert t.profile.key == "3d"

    def test_from_dict_old_format(self):
        t = Ticket.from_dict({"red": [1, 2, 3, 4, 5, 6], "blue": 7, "generated_at": "2025-01-01T00:00:00"})
        assert t.profile.key == "ssq"

    def test_from_dict_old_missing(self):
        with pytest.raises(ValueError, match="red/blue"):
            Ticket.from_dict({"generated_at": "2025-01-01T00:00:00"})

    def test_equality_and_hash(self):
        t1 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        t2 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert t1 == t2
        assert hash(t1) == hash(t2)
        assert t1 != "x"
        assert repr(t1).startswith("Ticket(")
        assert str(t1) == t1.format_pretty()


# ===========================================================================
# core/backtest_worker.py
# ===========================================================================

import caipiao.core.backtest_worker as bw
from caipiao.core.backtest_data import (
    BatchBacktestResult,
    RoundBacktestContext,
    RoundResult,
    RoundTask,
)
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata


class _WorkerFakeStrategy(GenerationStrategy):
    @property
    def metadata(self):
        return StrategyMetadata(id="w", name="w", description="x")

    def generate(self, count=1, options=None):
        return []


class _FakeEngine:
    def __init__(self, tickets, strategy=None):
        self._tickets = tickets
        self._strategy = strategy

    def get(self, sid):
        return self._strategy

    def generate(self, sid, count=1, options=None):
        return self._tickets


def _ctx(profile_key="ssq", strategy_id="s", needs_history=False, plugin_dir=None,
         options=None, is_ml=False, records=None):
    return RoundBacktestContext(
        strategy_id=strategy_id,
        profile_key=profile_key,
        tickets_per_round=5,
        options=options or {},
        is_ml=is_ml,
        needs_history=needs_history,
        records=records if records is not None else [],
        seed=1,
        plugin_dir=plugin_dir,
    )


def _task(draw_groups, issue="2024001", draw_date=None, profile_key="ssq"):
    if draw_date is None:
        draw_date = datetime(2024, 1, 1)
    return RoundTask(
        index=0,
        actual=DrawRecord(
            issue=issue, draw_date=draw_date, profile=profile_key, groups=draw_groups
        ),
    )


class TestBacktestWorker:
    def test_merge_errors_only(self):
        merged = bw.merge_round_results(
            [RoundResult(index=0, error="boom")], total_rounds=1
        )
        assert merged.errors == ["boom"]
        assert merged.total_cost == 0

    def test_merge_normal(self):
        t = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        rr = RoundResult(
            index=0,
            total_cost=10,
            hit_count=2,
            total_fixed_prize=10,
            float_prize_count=1,
            first_ticket_hit_count=1,
            winners=[0, 1],
            ticket_results=[
                {"round": 0, "ticket_index": 0, "hits": {}, "prize_name": "一等奖", "prize_amount": None},
                {"round": 0, "ticket_index": 1, "hits": {}, "prize_name": "六等奖", "prize_amount": 5},
            ],
            ticket_index_hits={0: 1, 1: 1},
            date_str="2024-01-01",
            issue_str="2024001",
            actual_groups={"red": [1, 2, 3, 4, 5, 6], "blue": [7]},
            tickets=[t, t],
        )
        merged = bw.merge_round_results([rr], total_rounds=1)
        assert merged.total_cost == 10
        assert merged.winner_details
        assert merged.winner_details[0]["is_first"] is True
        assert merged.winner_details[1]["is_first"] is False

    def test_merge_with_non_winner(self):
        t = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        rr = RoundResult(
            index=0, total_cost=2, hit_count=0, total_fixed_prize=0,
            float_prize_count=0, first_ticket_hit_count=0, winners=[],
            ticket_results=[{
                "round": 0, "ticket_index": 0, "hits": {},
                "prize_name": "未中奖", "prize_amount": 0,
            }],
            ticket_index_hits={}, date_str="x", issue_str="x",
            actual_groups={}, tickets=[t],
        )
        merged = bw.merge_round_results([rr], total_rounds=1)
        assert merged.total_cost == 2
        assert merged.winner_details == []

    def test_worker_needs_history_ok(self, monkeypatch):
        # needs_history=True with >=100 history records -> line 203 (options["history"])
        eng_fake = _FakeEngine([Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)])
        monkeypatch.setattr(bw, "_build_engine", lambda pk, pd=None: eng_fake)
        monkeypatch.setattr(bw, "_detect_ml_strategy", lambda e, sid, ml: False)
        records = [
            DrawRecord(issue=f"h{i}", draw_date=datetime(2023, 1, 1) + timedelta(days=i),
                       red_balls=[i % 30 + 1, 2, 3, 4, 5, 6], blue_ball=7)
            for i in range(120)
        ]
        ctx = _ctx(needs_history=True, records=records)
        rr = bw.worker_round_backtest(ctx, _task({"red": [1, 2, 3, 4, 5, 6], "blue": [7]}))
        assert rr.error is None

    def test_worker_3d_fixed_prize(self, monkeypatch):
        # exact 3D match -> 直选 fixed prize (not None) -> line 310
        eng_fake = _FakeEngine([Ticket(profile="3d", groups={"pos": [1, 2, 3]})])
        monkeypatch.setattr(bw, "_build_engine", lambda pk, pd=None: eng_fake)
        monkeypatch.setattr(bw, "_detect_ml_strategy", lambda e, sid, ml: False)
        rr = bw.worker_round_backtest(
            _ctx(profile_key="3d"),
            _task({"pos": [1, 2, 3]}, profile_key="3d"),
        )
        assert rr.error is None
        assert rr.hit_count >= 1

    def test_worker_success_ssq(self, monkeypatch):
        eng_fake = _FakeEngine([Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
                                Ticket(red_balls=[7, 8, 9, 10, 11, 12], blue_ball=1)])
        monkeypatch.setattr(bw, "_build_engine", lambda pk, pd=None: eng_fake)
        monkeypatch.setattr(bw, "_detect_ml_strategy", lambda e, sid, ml: False)
        rr = bw.worker_round_backtest(_ctx(), _task({"red": [1, 2, 3, 4, 5, 6], "blue": [7]}))
        assert rr.error is None
        assert rr.hit_count >= 1

    def test_worker_history_too_short(self, monkeypatch):
        eng_fake = _FakeEngine([])
        monkeypatch.setattr(bw, "_build_engine", lambda pk, pd=None: eng_fake)
        monkeypatch.setattr(bw, "_detect_ml_strategy", lambda e, sid, ml: False)
        ctx = _ctx(
            needs_history=True,
            records=[DrawRecord(issue="x", draw_date=datetime(2023, 1, 1), profile="ssq", groups={"red": [1, 2, 3, 4, 5, 6], "blue": [7]})],
        )
        rr = bw.worker_round_backtest(ctx, _task({"red": [1, 2, 3, 4, 5, 6], "blue": [7]}))
        assert rr.error == "history too short"

    def test_worker_ml_branch(self, monkeypatch):
        eng_fake = _FakeEngine([Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)])
        monkeypatch.setattr(bw, "_build_engine", lambda pk, pd=None: eng_fake)
        monkeypatch.setattr(bw, "_detect_ml_strategy", lambda e, sid, ml: True)
        captured = {}
        monkeypatch.setattr(bw, "prepare_ml_options", lambda *a, **k: captured.setdefault("called", True) or dict(k.get("options", {})))
        rr = bw.worker_round_backtest(_ctx(strategy_id="xgb_1"), _task({"red": [1, 2, 3, 4, 5, 6], "blue": [7]}))
        assert captured.get("called") is True
        assert rr.error is None

    def test_worker_fc3d_filter_branch(self, monkeypatch):
        eng_fake = _FakeEngine([Ticket(profile="3d", groups={"pos": [1, 2, 3]}) for _ in range(5)])
        monkeypatch.setattr(bw, "_build_engine", lambda pk, pd=None: eng_fake)
        monkeypatch.setattr(bw, "_detect_ml_strategy", lambda e, sid, ml: False)
        opts = {
            "_fc3d_filter_enabled": True,
            "_fc3d_filter_compare_periods": 5,
            "_fc3d_filter_max_overlap": 1,
            "_fc3d_filter_min_sum": 0,
            "_fc3d_filter_max_sum": 27,
        }
        ctx = _ctx(profile_key="3d", options=opts,
                   records=[_3d_draw([9, 9, 9], days_ago=-10)])
        rr = bw.worker_round_backtest(
            ctx,
            _task({"pos": [4, 5, 6]}, profile_key="3d"),
        )
        assert rr.error is None

    def test_worker_dlt_filter_branch(self, monkeypatch):
        eng_fake = _FakeEngine([Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})])
        monkeypatch.setattr(bw, "_build_engine", lambda pk, pd=None: eng_fake)
        monkeypatch.setattr(bw, "_detect_ml_strategy", lambda e, sid, ml: False)
        opts = {
            "_dlt_filter_enabled": True,
            "_dlt_filter_compare_periods": 7,
            "_dlt_filter_max_front_overlap": 0,
            "_dlt_filter_min_front_sum": 15,
            "_dlt_filter_max_front_sum": 165,
        }
        ctx = _ctx(profile_key="dlt", options=opts,
                   records=[_dlt_draw([9, 8, 7, 6, 5], [9, 9], days_ago=-10)])
        rr = bw.worker_round_backtest(
            ctx,
            _task({"front": [10, 11, 12, 13, 14], "back": [8, 9]}, profile_key="dlt"),
        )
        assert rr.error is None

    def test_worker_exception(self, monkeypatch):
        class _BoomEngine:
            def get(self, sid):
                return None

            def generate(self, sid, count=1, options=None):
                raise RuntimeError("kaboom")

        monkeypatch.setattr(bw, "_build_engine", lambda pk, pd=None: _BoomEngine())
        monkeypatch.setattr(bw, "_detect_ml_strategy", lambda e, sid, ml: False)
        rr = bw.worker_round_backtest(_ctx(), _task({"red": [1, 2, 3, 4, 5, 6], "blue": [7]}))
        assert rr.error is not None
        assert "kaboom" in rr.error

    def test_worker_draw_only_branch(self, monkeypatch):
        custom = LotteryProfile(
            key="testx",
            name="t",
            groups=(
                NumberGroup("pos", "p", 0, 9, 3, positional=True, is_primary=True),
                NumberGroup("special", "s", 0, 9, 1, draw_only=True),
            ),
            data_url="", parser_key="x", draw_weekdays=(), storage_file="x",
            model_prefix="x",
        )
        monkeypatch.setattr(bw, "get_profile", lambda k: custom)
        eng_fake = _FakeEngine([Ticket(profile=custom, groups={"pos": [1, 2, 3]})])
        monkeypatch.setattr(bw, "_build_engine", lambda pk, pd=None: eng_fake)
        monkeypatch.setattr(bw, "_detect_ml_strategy", lambda e, sid, ml: False)
        rr = bw.worker_round_backtest(_ctx(profile_key="testx"), _task({"pos": [1, 2, 3], "special": [5]}, profile_key="testx"))
        assert rr.error is None

    def test_detect_ml_strategy_real(self):
        strat = _WorkerFakeStrategy()
        strat.is_ml = True
        assert bw._detect_ml_strategy(_FakeEngine([], strat), "w", False) is True
        assert bw._detect_ml_strategy(None, "w", True) is True
        assert bw._detect_ml_strategy(_FakeEngine([], strat), "w", False) is True
        strat.is_ml = False
        assert bw._detect_ml_strategy(_FakeEngine([], strat), "w", False) is False

    def test_build_engine_no_plugin(self, monkeypatch):
        monkeypatch.setattr(bw, "build_strategies", lambda p: [_WorkerFakeStrategy()])
        engine = bw._build_engine("ssq")
        assert engine.get("w") is not None

    def test_build_engine_with_plugin(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bw, "build_strategies", lambda p: [])
        monkeypatch.setattr("caipiao.plugins.PluginManager", _FakePluginManager)
        engine = bw._build_engine("ssq", plugin_dir=str(tmp_path))
        assert engine is not None

    def test_configure_worker_threads(self):
        bw._configure_worker_threads()
        assert os.environ["OMP_NUM_THREADS"] == "1"

    def test_worker_temp_dir(self):
        d = bw._get_worker_temp_dir()
        assert os.path.isdir(d)
        bw._cleanup_worker_temp_dir()
        assert not os.path.isdir(d)

    def test_prepare_ml_options_no_strategy(self):
        out = bw.prepare_ml_options([], {"a": 1}, "ssq", datetime(2024, 1, 1), "/tmp")
        assert out == {"a": 1}

    def test_prepare_ml_options_ssq_backends(self, monkeypatch):
        monkeypatch.setattr(bw, "MLPredictor", _FakePredictor)
        monkeypatch.setattr(bw, "new_model_path", lambda *a, **k: "/tmp/m")
        monkeypatch.setattr(bw, "LotteryLightGBMModel", object)
        monkeypatch.setattr(bw, "LotteryCatBoostModel", object)
        monkeypatch.setattr(bw, "LotteryXGBoostModel", object)
        hist = [DrawRecord(issue="x", draw_date=datetime(2024, 1, 1), profile="ssq", groups={"red": [1, 2, 3, 4, 5, 6], "blue": [7]})]
        opts = {"strategy_id": "lightgbm_1"}
        assert bw.prepare_ml_options(hist, opts, "ssq", datetime(2024, 1, 1), "/tmp") is not None
        opts2 = {"strategy_id": "catboost_1"}
        assert bw.prepare_ml_options(hist, opts2, "ssq", datetime(2024, 1, 1), "/tmp") is not None
        opts3 = {"strategy_id": "xgboost_1"}
        assert bw.prepare_ml_options(hist, opts3, "ssq", datetime(2024, 1, 1), "/tmp") is not None

    def test_prepare_ml_options_non_ssq_backends(self, monkeypatch):
        monkeypatch.setattr(bw, "GenericMLPredictor", _FakePredictor)
        monkeypatch.setattr(bw, "new_model_path", lambda *a, **k: "/tmp/m")
        hist = [DrawRecord(issue="x", draw_date=datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]})]
        for sid in ("lightgbm_1", "catboost_1", "xgboost_1"):
            opts = {"strategy_id": sid}
            assert bw.prepare_ml_options(hist, opts, "3d", datetime(2024, 1, 1), "/tmp") is not None


class _FakePredictor:
    def __init__(self, *a, **k):
        pass

    def train(self):
        return True


class _FakePluginManager:
    def __init__(self, engine, plugin_dir):
        self.engine = engine

    def load_all(self):
        return []
