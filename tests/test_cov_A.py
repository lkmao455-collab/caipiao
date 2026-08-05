"""Coverage tests for assigned core modules."""
from __future__ import annotations

import random
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

import pytest

from caipiao.utils.validators import parse_int_list
from caipiao.utils import encoding_utils
from caipiao.utils.encoding_utils import (
    _detect_encoding_from_bytes,
    detect_file_encoding,
    read_text_file,
    read_text_file_with_info,
)
import caipiao.utils as utils_pkg
from caipiao.utils import app_data_dir

from caipiao.core.ball import Ball, BallColor
from caipiao.core import prize
from caipiao.core.strategies.common.validators import validate_odd_count
from caipiao.core.strategies.common.records import records_from_options
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata
from caipiao.core.strategies.factory import build_strategies, is_ml_strategy, needs_history
from caipiao.core.profile import (
    DLT, FC3D, GD36X7, KL8, NumberGroup, PL3, PL5, PROFILES, QXC, SSQ,
    LotteryProfile, category_label, get_profile, list_profiles,
    list_profiles_by_category, profile_keys,
)
from caipiao.core.strategies.lotteries.pl3._base import (
    _add_pick_count_schema as pl3_add_schema,
    _get_pick_count as pl3_get_pick,
    _make_ticket as pl3_make_ticket,
)
from caipiao.core.strategies.lotteries.pl5._base import (
    _add_pick_count_schema as pl5_add_schema,
    _get_pick_count as pl5_get_pick,
    _make_ticket as pl5_make_ticket,
)
from caipiao.core.strategies.lotteries.qxc._base import (
    _add_pick_count_schema as qxc_add_schema,
    _get_pick_count as qxc_get_pick,
    _make_ticket as qxc_make_ticket,
)
from caipiao.core.strategies.lotteries.kl8._base import (
    _add_pick_count_schema as kl8_add_schema,
    _get_pick_count as kl8_get_pick,
    _make_ticket as kl8_make_ticket,
)
import caipiao.core.strategies.lotteries.pl3._base as pl3_mod
import caipiao.core.strategies.lotteries.pl5._base as pl5_mod
import caipiao.core.strategies.lotteries.qxc._base as qxc_mod
import caipiao.core.strategies.lotteries.dlt._base as dlt_mod
import caipiao.core.strategies.lotteries.kl8._base as kl8_mod
from caipiao.core.strategies.lotteries.dlt._base import (
    _add_pick_count_schema as dlt_add_schema,
    _get_pick_count as dlt_get_pick,
    _make_ticket as dlt_make_ticket,
)
from caipiao.core.strategies.lotteries.fc3d._base import (
    _make_rng, _records_from_options, _sample_with_dedup,
    _weighted_sample_without_replacement,
)
from caipiao.data.models import DrawRecord


class TestParseIntList:
    def test_min_gt_max(self):
        with pytest.raises(ValueError):
            parse_int_list("1,2", min_val=10, max_val=5)

    def test_none_text(self):
        with pytest.raises(TypeError):
            parse_int_list(None)

    def test_empty(self):
        assert parse_int_list("   ") == []
        assert parse_int_list("") == []

    def test_comma(self):
        assert parse_int_list("1,2,3") == [1, 2, 3]

    def test_space(self):
        assert parse_int_list("1 2 3") == [1, 2, 3]

    def test_chinese_comma(self):
        assert parse_int_list("1，2，3") == [1, 2, 3]

    def test_mixed_and_whitespace(self):
        assert parse_int_list(" 1 , 2 ，3 4 ") == [1, 2, 3, 4]

    def test_out_of_range(self):
        with pytest.raises(ValueError):
            parse_int_list("99", min_val=1, max_val=33)
        with pytest.raises(ValueError):
            parse_int_list("0", min_val=1, max_val=33)

    def test_non_integer(self):
        with pytest.raises(ValueError):
            parse_int_list("1,abc,3")

    def test_custom_range(self):
        assert parse_int_list("5,6,7", min_val=5, max_val=7) == [5, 6, 7]


class TestDetectEncodingFromBytes:
    def test_empty(self):
        assert _detect_encoding_from_bytes(b"") == "utf-8"

    def test_utf8(self):
        with mock.patch.object(encoding_utils, "chardet", None):
            assert _detect_encoding_from_bytes(b"hello world") == "utf-8"

    def test_bom_utf8sig(self):
        assert _detect_encoding_from_bytes("hi".encode("utf-8-sig")) == "utf-8-sig"

    def test_bom_utf16_le(self):
        assert _detect_encoding_from_bytes(b"\xff\xfe" + b"abcd") == "utf-16"

    def test_bom_utf16_be(self):
        assert _detect_encoding_from_bytes(b"\xfe\xff" + b"abcd") == "utf-16"

    def test_chardet_ascii(self):
        # 非 UTF-8 字节才能进入 chardet 分支；ascii 会被规范化为 utf-8 但解码仍失败 -> latin-1
        c = mock.Mock()
        c.detect.return_value = {"encoding": "ascii", "confidence": 0.9}
        with mock.patch.object(encoding_utils, "chardet", c):
            assert _detect_encoding_from_bytes(b"\xff") == "latin-1"

    def test_chardet_gb2312(self):
        # 0xd6 0xd0 是 GBK 的 "中"，非 UTF-8，chardet 判为 gb2312 -> gb18030
        c = mock.Mock()
        c.detect.return_value = {"encoding": "gb2312", "confidence": 0.9}
        with mock.patch.object(encoding_utils, "chardet", c):
            assert _detect_encoding_from_bytes(b"\xd6\xd0") == "gb18030"

    def test_chardet_utf8(self):
        c = mock.Mock()
        c.detect.return_value = {"encoding": "utf-8", "confidence": 0.9}
        with mock.patch.object(encoding_utils, "chardet", c):
            assert _detect_encoding_from_bytes(b"\xd6\xd0") == "gb18030"

    def test_chardet_latin1(self):
        c = mock.Mock()
        c.detect.return_value = {"encoding": "latin-1", "confidence": 0.9}
        with mock.patch.object(encoding_utils, "chardet", c):
            assert _detect_encoding_from_bytes(b"\xff") == "latin-1"

    def test_chardet_low_confidence_falls_to_gbk(self):
        c = mock.Mock()
        c.detect.return_value = {"encoding": "ascii", "confidence": 0.3}
        with mock.patch.object(encoding_utils, "chardet", c):
            assert _detect_encoding_from_bytes(b"\xd6\xd0") == "gb18030"

    def test_chardet_decode_fails_then_latin1(self):
        c = mock.Mock()
        c.detect.return_value = {"encoding": "ascii", "confidence": 0.9}
        with mock.patch.object(encoding_utils, "chardet", c):
            assert _detect_encoding_from_bytes(b"\xff\xff") == "latin-1"


class TestEncodingFileIO:
    def test_detect_file_encoding_utf8(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_bytes("hello".encode("utf-8"))
        assert detect_file_encoding(str(p)) == "utf-8"

    def test_detect_file_encoding_bom(self, tmp_path):
        p = tmp_path / "b.txt"
        p.write_bytes("hi".encode("utf-8-sig"))
        assert detect_file_encoding(str(p)) == "utf-8-sig"

    def test_read_text_file(self, tmp_path):
        p = tmp_path / "c.txt"
        p.write_bytes("neirong".encode("utf-8"))
        assert read_text_file(str(p)) == "neirong"

    def test_read_with_info_crlf(self, tmp_path):
        p = tmp_path / "d.txt"
        p.write_bytes("a\r\nb".encode("utf-8"))
        text, enc, ending = read_text_file_with_info(str(p))
        assert text == "a\r\nb"
        assert enc == "UTF-8"
        assert ending == "CRLF"

    def test_read_with_info_lf(self, tmp_path):
        p = tmp_path / "e.txt"
        p.write_bytes("a\nb".encode("utf-8"))
        _, enc, ending = read_text_file_with_info(str(p))
        assert enc == "UTF-8"
        assert ending == "LF"

    def test_read_with_info_cr(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_bytes(b"a\rb")
        _, enc, ending = read_text_file_with_info(str(p))
        assert ending == "CR"

    def test_read_with_info_no_newline(self, tmp_path):
        p = tmp_path / "g.txt"
        p.write_bytes(b"abc")
        _, enc, ending = read_text_file_with_info(str(p))
        assert ending == "LF"

    def test_read_with_info_latin1_fallback(self, tmp_path):
        p = tmp_path / "h.txt"
        p.write_bytes(b"\x81")
        with mock.patch.object(encoding_utils, "chardet", None):
            text, enc, ending = read_text_file_with_info(str(p))
        assert enc == "LATIN-1"
        assert text == "\x81"
        assert ending == "LF"


class TestAppDataDir:
    def test_source_run(self, tmp_path):
        main = tmp_path / "app" / "main.py"
        main.parent.mkdir(parents=True, exist_ok=True)
        fake = SimpleNamespace(argv=[str(main)])
        with mock.patch.object(utils_pkg, "sys", fake):
            d = app_data_dir()
        assert d == tmp_path / "app" / ".caipiao"
        assert d.is_dir()

    def test_frozen_meipass(self, tmp_path):
        fake = SimpleNamespace(frozen=True, _MEIPASS=str(tmp_path / "frozen"))
        with mock.patch.object(utils_pkg, "sys", fake):
            d = app_data_dir()
        assert d == tmp_path / "frozen" / ".caipiao"
        assert d.is_dir()

    def test_frozen_executable(self, tmp_path):
        exe = tmp_path / "exe" / "app.exe"
        fake = SimpleNamespace(frozen=True, executable=str(exe))
        with mock.patch.object(utils_pkg, "sys", fake):
            d = app_data_dir()
        assert d == tmp_path / "exe" / ".caipiao"
        assert d.is_dir()


class TestBall:
    def test_red_blue(self):
        r = Ball.red(10)
        assert isinstance(r, Ball)
        assert r.color == BallColor.RED
        assert r.number == 10
        assert Ball.blue(1).color == BallColor.BLUE

    def test_int_conversion(self):
        assert Ball.red(5.0).number == 5

    def test_repr_str(self):
        b = Ball.red(7)
        assert repr(b) == "Ball(7, RED)"
        assert str(b) == "07"

    def test_eq(self):
        assert Ball.red(1) == Ball.red(1)
        assert Ball.red(1) != Ball.blue(1)
        assert Ball.red(1) != Ball.red(2)
        assert Ball.red(1).__eq__("notaball") is NotImplemented

    def test_hash(self):
        assert hash(Ball.red(1)) == hash(Ball.red(1))

    def test_red_out_of_range(self):
        with pytest.raises(ValueError):
            Ball.red(0)
        with pytest.raises(ValueError):
            Ball.red(34)

    def test_blue_out_of_range(self):
        with pytest.raises(ValueError):
            Ball.blue(0)
        with pytest.raises(ValueError):
            Ball.blue(17)


class TestSsqPrize:
    def test_first(self):
        assert prize._ssq_prize({"red": 6, "blue": 1}) == ("一等奖", None)

    def test_second(self):
        assert prize._ssq_prize({"red": 6, "blue": 0}) == ("二等奖", None)

    def test_third(self):
        assert prize._ssq_prize({"red": 5, "blue": 1}) == ("三等奖", 3000)

    def test_fourth(self):
        assert prize._ssq_prize({"red": 5, "blue": 0}) == ("四等奖", 200)
        assert prize._ssq_prize({"red": 4, "blue": 1}) == ("四等奖", 200)

    def test_fifth(self):
        assert prize._ssq_prize({"red": 4, "blue": 0}) == ("五等奖", 10)
        assert prize._ssq_prize({"red": 3, "blue": 1}) == ("五等奖", 10)

    def test_sixth(self):
        assert prize._ssq_prize({"red": 0, "blue": 1}) == ("六等奖", 5)

    def test_none(self):
        assert prize._ssq_prize({"red": 0, "blue": 0}) == ("未中奖", 0)


class TestFc3dPrize:
    def test_no_actual(self):
        assert prize._fc3d_prize({}, {"pos": [1, 2, 3]}) == ("未中奖", 0)

    def test_len_mismatch(self):
        assert prize._fc3d_prize({}, {"pos": [1, 2, 3]}, {"pos": [1, 2]}) == ("未中奖", 0)

    def test_bet_mode_zuxuan_leopard_forced_zhixuan(self):
        assert prize._fc3d_prize(
            {}, {"pos": [1, 1, 1]}, {"pos": [1, 1, 1]}, {"bet_mode": "组选"}
        )[0] == "直选"

    def test_zhixuan_match(self):
        assert prize._fc3d_prize(
            {}, {"pos": [1, 2, 3]}, {"pos": [1, 2, 3]}, {"bet_mode": "直选"}
        ) == ("直选", 1040)

    def test_zhixuan_mismatch(self):
        assert prize._fc3d_prize(
            {}, {"pos": [1, 2, 3]}, {"pos": [9, 9, 9]}, {"bet_mode": "直选"}
        ) == ("未中奖", 0)

    def test_zuxuan6(self):
        assert prize._fc3d_prize(
            {}, {"pos": [3, 2, 1]}, {"pos": [1, 2, 3]}, {"bet_mode": "组选"}
        ) == ("组选6", 173)

    def test_zuxuan3(self):
        assert prize._fc3d_prize(
            {}, {"pos": [2, 1, 1]}, {"pos": [1, 1, 2]}, {"bet_mode": "组选"}
        ) == ("组选3", 346)

    def test_zuxuan_mismatch(self):
        assert prize._fc3d_prize(
            {}, {"pos": [1, 2, 3]}, {"pos": [9, 9, 9]}, {"bet_mode": "组选"}
        ) == ("未中奖", 0)

    def test_no_bet_mode_zhixuan(self):
        assert prize._fc3d_prize({}, {"pos": [1, 2, 3]}, {"pos": [1, 2, 3]}) == ("直选", 1040)

    def test_no_bet_mode_zuxuan6(self):
        assert prize._fc3d_prize({}, {"pos": [3, 2, 1]}, {"pos": [1, 2, 3]}) == ("组选6", 173)

    def test_no_bet_mode_zuxuan3(self):
        assert prize._fc3d_prize({}, {"pos": [2, 1, 1]}, {"pos": [1, 1, 2]}) == ("组选3", 346)

    def test_no_bet_mode_mismatch(self):
        assert prize._fc3d_prize({}, {"pos": [1, 2, 3]}, {"pos": [9, 9, 9]}) == ("未中奖", 0)


class TestKl8Prize:
    def test_pick1_hit1(self):
        assert prize._kl8_prize({"main": 1}, {"main": [1]}) == ("选一中一", 4)

    def test_pick10_hit10(self):
        assert prize._kl8_prize({"main": 10}, {"main": list(range(10))}) == ("选十中十", None)

    def test_pick10_hit5(self):
        assert prize._kl8_prize({"main": 5}, {"main": list(range(10))}) == ("选十中五", 3)

    def test_pick7_hit0(self):
        assert prize._kl8_prize({"main": 0}, {"main": list(range(7))}) == ("选七全不中", 2)

    def test_pick2_hit2(self):
        assert prize._kl8_prize({"main": 2}, {"main": [1, 2]}) == ("选二中二", 19)

    def test_pick3_hit1_miss(self):
        assert prize._kl8_prize({"main": 1}, {"main": [1, 2, 3]}) == ("未中奖", 0)

    def test_pick_unregistered(self):
        assert prize._kl8_prize({"main": 0}, {"main": list(range(11))}) == ("未中奖", 0)


class TestDltPrize:
    def test_cases(self):
        assert prize._dlt_prize({"front": 5, "back": 2}) == ("一等奖", None)
        assert prize._dlt_prize({"front": 5, "back": 1}) == ("二等奖", None)
        assert prize._dlt_prize({"front": 5, "back": 0}) == ("三等奖", 10000)
        assert prize._dlt_prize({"front": 4, "back": 2}) == ("四等奖", 3000)
        assert prize._dlt_prize({"front": 4, "back": 1}) == ("五等奖", 300)
        assert prize._dlt_prize({"front": 3, "back": 2}) == ("六等奖", 200)
        assert prize._dlt_prize({"front": 4, "back": 0}) == ("七等奖", 100)
        assert prize._dlt_prize({"front": 3, "back": 1}) == ("八等奖", 15)
        assert prize._dlt_prize({"front": 2, "back": 2}) == ("八等奖", 15)
        assert prize._dlt_prize({"front": 3, "back": 0}) == ("九等奖", 5)
        assert prize._dlt_prize({"front": 1, "back": 2}) == ("九等奖", 5)
        assert prize._dlt_prize({"front": 2, "back": 1}) == ("九等奖", 5)
        assert prize._dlt_prize({"front": 0, "back": 2}) == ("九等奖", 5)
        assert prize._dlt_prize({"front": 0, "back": 0}) == ("未中奖", 0)


class TestPl3Prize:
    def test_no_actual(self):
        assert prize._pl3_prize({}, {"pos": [1, 2, 3]}) == ("未中奖", 0)

    def test_len_mismatch(self):
        assert prize._pl3_prize({}, {"pos": [1, 2, 3]}, {"pos": [1, 2]}) == ("未中奖", 0)

    def test_zhixuan(self):
        assert prize._pl3_prize({}, {"pos": [1, 2, 3]}, {"pos": [1, 2, 3]}) == ("直选", 1040)

    def test_zuxuan6(self):
        assert prize._pl3_prize({}, {"pos": [3, 2, 1]}, {"pos": [1, 2, 3]}) == ("组选6", 173)

    def test_zuxuan3(self):
        assert prize._pl3_prize({}, {"pos": [2, 1, 1]}, {"pos": [1, 1, 2]}) == ("组选3", 346)

    def test_mismatch(self):
        assert prize._pl3_prize({}, {"pos": [1, 2, 3]}, {"pos": [9, 9, 9]}) == ("未中奖", 0)


class TestPl5Prize:
    def test_hit(self):
        assert prize._pl5_prize({"pos": 5}) == ("直选", 100000)

    def test_miss(self):
        assert prize._pl5_prize({"pos": 4}) == ("未中奖", 0)


class TestQxcPrize:
    def _actual(self):
        return {"pos": [0, 1, 2, 3, 4, 5, 6]}

    def test_no_actual(self):
        assert prize._qxc_prize({}, {"pos": [0, 1, 2, 3, 4, 5, 6]}) == ("未中奖", 0)

    def test_len_mismatch(self):
        assert prize._qxc_prize({}, {"pos": [1, 2, 3]}, {"pos": [1, 2, 3]}) == ("未中奖", 0)

    def test_first(self):
        assert prize._qxc_prize({}, {"pos": [0, 1, 2, 3, 4, 5, 6]}, self._actual()) == ("一等奖", None)

    def test_second(self):
        assert prize._qxc_prize(
            {}, {"pos": [9, 1, 2, 3, 4, 5, 6]}, self._actual()
        ) == ("二等奖", None)

    def test_third(self):
        assert prize._qxc_prize(
            {}, {"pos": [9, 9, 2, 3, 4, 5, 6]}, self._actual()
        ) == ("三等奖", 3000)

    def test_fourth(self):
        assert prize._qxc_prize(
            {}, {"pos": [9, 9, 9, 3, 4, 5, 6]}, self._actual()
        ) == ("四等奖", 500)

    def test_fifth(self):
        assert prize._qxc_prize(
            {}, {"pos": [9, 9, 9, 9, 4, 5, 6]}, self._actual()
        ) == ("五等奖", 30)

    def test_sixth(self):
        assert prize._qxc_prize(
            {}, {"pos": [9, 9, 9, 9, 9, 5, 6]}, self._actual()
        ) == ("六等奖", 5)

    def test_none(self):
        assert prize._qxc_prize(
            {}, {"pos": [9, 9, 9, 9, 9, 9, 9]}, self._actual()
        ) == ("未中奖", 0)


class TestGd36x7Prize:
    def test_cases(self):
        assert prize._gd36x7_prize({"basic": 7}) == ("一等奖", None)
        assert prize._gd36x7_prize({"basic": 6, "special": 1}) == ("二等奖", None)
        assert prize._gd36x7_prize({"basic": 6}) == ("三等奖", None)
        assert prize._gd36x7_prize({"basic": 5, "special": 1}) == ("四等奖", 200)
        assert prize._gd36x7_prize({"basic": 5}) == ("五等奖", 50)
        assert prize._gd36x7_prize({"basic": 4, "special": 1}) == ("六等奖", 10)
        assert prize._gd36x7_prize({"basic": 4}) == ("七等奖", 5)
        assert prize._gd36x7_prize({"basic": 0, "special": 0}) == ("未中奖", 0)


class TestFc3dBetType:
    def test_unknown_len(self):
        assert prize.fc3d_bet_type([1, 2]) == "未知"

    def test_group6(self):
        assert prize.fc3d_bet_type([1, 2, 3]) == "组选6"

    def test_group3(self):
        assert prize.fc3d_bet_type([1, 1, 2]) == "组选3"

    def test_leopard(self):
        assert prize.fc3d_bet_type([1, 1, 1]) == "豹子号（直选）"


class TestCalculatePrizeDispatch:
    def test_ssq(self):
        assert prize.calculate_prize("ssq", {"red": 6, "blue": 1}, {})[0] == "一等奖"

    def test_3d(self):
        r = prize.calculate_prize(
            "3d", {"pos": 3}, {"pos": [1, 2, 3]}, {"pos": [1, 2, 3]}, {"bet_mode": "直选"}
        )
        assert r == ("直选", 1040)

    def test_kl8(self):
        assert prize.calculate_prize("kl8", {"main": 1}, {"main": [1]})[0] == "选一中一"

    def test_dlt(self):
        assert prize.calculate_prize("dlt", {"front": 5, "back": 2}, {})[0] == "一等奖"

    def test_pl3(self):
        assert prize.calculate_prize("pl3", {"pos": 3}, {"pos": [1, 2, 3]}, {"pos": [1, 2, 3]})[0] == "直选"

    def test_pl5(self):
        assert prize.calculate_prize("pl5", {"pos": 5}, {})[0] == "直选"

    def test_qxc(self):
        assert prize.calculate_prize(
            "qxc", {"pos": 7}, {"pos": [0, 1, 2, 3, 4, 5, 6]}, {"pos": [0, 1, 2, 3, 4, 5, 6]}
        )[0] == "一等奖"

    def test_gd36x7(self):
        assert prize.calculate_prize("gd36x7", {"basic": 7}, {})[0] == "一等奖"

    def test_unknown(self):
        assert prize.calculate_prize("nope", {}, {}) == ("未知彩种", 0)


class TestValidateOddCount:
    def test_default(self):
        validate_odd_count({}, pick=6)

    def test_valid(self):
        validate_odd_count({"odd_count": 2}, pick=6)

    def test_invalid_type(self):
        with pytest.raises(ValueError):
            validate_odd_count({"odd_count": "x"}, pick=6)

    def test_negative(self):
        with pytest.raises(ValueError):
            validate_odd_count({"odd_count": -1}, pick=6)

    def test_too_large(self):
        with pytest.raises(ValueError):
            validate_odd_count({"odd_count": 7}, pick=6)


class TestRecordsFromOptions:
    def test_empty(self):
        assert records_from_options({}) == []
        assert records_from_options({"history": None}) == []

    def test_draw_record(self):
        rec = DrawRecord(issue="1", draw_date=datetime(2024, 1, 1), groups={"pos": [1, 2, 3]})
        out = records_from_options({"history": [rec]})
        assert out == [rec]

    def test_dict_str_date(self):
        out = records_from_options(
            {"history": [{"issue": "2", "draw_date": "2024-02-02", "groups": {"pos": [1, 2, 3]}}]}
        )
        assert out[0].issue == "2"
        assert out[0].draw_date.year == 2024

    def test_dict_datetime_date(self):
        dt = datetime(2024, 3, 3)
        out = records_from_options(
            {"history": [{"issue": "3", "draw_date": dt, "groups": {"pos": [1, 2, 3]}}]}
        )
        assert out[0].draw_date == dt

    def test_dict_default_date(self):
        out = records_from_options(
            {"history": [{"issue": "4", "groups": {"pos": [1, 2, 3]}}]}
        )
        assert out[0].issue == "4"
        assert isinstance(out[0].draw_date, datetime)

    def test_object(self):
        obj = SimpleNamespace(
            issue="5", draw_date=datetime(2024, 4, 4), profile="3d", groups={"pos": [1, 2, 3]}
        )
        out = records_from_options({"history": [obj]})
        assert out[0].issue == "5"


class _DummyStrategy(GenerationStrategy):
    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(id="dummy", name="Dummy", description="desc")

    def generate(self, count: int = 1, options=None):
        return []


class TestStrategy:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            GenerationStrategy()

    def test_metadata_dataclass(self):
        m = StrategyMetadata(id="x", name="X", description="d", version="2.0.0")
        assert m.version == "2.0.0"

    def test_concrete(self):
        s = _DummyStrategy()
        assert s.is_ml is False
        assert str(s) == "Dummy (dummy)"
        assert s.get_config_schema() is None
        s.validate_options({})
        assert s.generate() == []


class TestFactory:
    def test_build_strategies(self):
        strategies = build_strategies(SSQ)
        assert len(strategies) == 3

    def test_build_unknown(self):
        prof = LotteryProfile(
            key="unknown123", name="U", groups=(NumberGroup("g", "G", 1, 10, 2),),
            data_url="", parser_key="", draw_weekdays=(), storage_file="x.json", model_prefix="u",
        )
        with pytest.raises(ValueError):
            build_strategies(prof)

    def test_needs_history(self):
        assert needs_history("smart_hot_cold_xyz") is True
        assert needs_history("balanced_xyz") is True
        assert needs_history("other") is False

    def test_is_ml_strategy(self):
        assert is_ml_strategy("anything") is False


def _minimal_group(key="g"):
    return NumberGroup(key, "G", 1, 10, 2)


class TestNumberGroup:
    def test_size_values(self):
        g = SSQ.group("red")
        assert g.size == 33
        assert g.values == list(range(1, 34))

    def test_effective_pick(self):
        assert SSQ.group("red").effective_pick_min == 6
        assert SSQ.group("red").effective_pick_max == 6
        assert KL8.group("main").effective_pick_min == 1
        assert KL8.group("main").effective_pick_max == 10

    def test_variable_pick(self):
        assert SSQ.group("red").variable_pick is False
        assert KL8.group("main").variable_pick is True

    def test_high_low_border(self):
        assert SSQ.group("red").high_low_border == 17
        assert FC3D.group("pos").high_low_border == 5

    def test_validate_ok(self):
        SSQ.group("red").validate_numbers([1, 2, 3, 4, 5, 6])

    def test_validate_range(self):
        with pytest.raises(ValueError):
            SSQ.group("red").validate_numbers([1, 2, 3, 4, 5, 99])

    def test_validate_repeat(self):
        with pytest.raises(ValueError):
            SSQ.group("red").validate_numbers([1, 1, 2, 3, 4, 5])

    def test_validate_allow_repeat(self):
        FC3D.group("pos").validate_numbers([1, 1, 2])


class TestLotteryProfile:
    def test_group_found(self):
        assert SSQ.group("red").key == "red"

    def test_group_keyerror(self):
        with pytest.raises(KeyError):
            SSQ.group("nope")

    def test_group_keys(self):
        assert SSQ.group_keys == ["red", "blue"]

    def test_pick_groups_excludes_draw_only(self):
        assert [g.key for g in GD36X7.pick_groups] == ["basic"]

    def test_primary_group(self):
        assert SSQ.primary_group.key == "red"

    def test_primary_group_fallback(self):
        prof = LotteryProfile(
            key="fb", name="F", groups=(_minimal_group(),),
            data_url="", parser_key="", draw_weekdays=(), storage_file="f.json", model_prefix="f",
        )
        assert prof.primary_group.key == "g"

    def test_primary_group_no_groups(self):
        prof = LotteryProfile(
            key="ng", name="N", groups=(),
            data_url="", parser_key="", draw_weekdays=(), storage_file="n.json", model_prefix="n",
        )
        with pytest.raises(ValueError):
            _ = prof.primary_group

    def test_is_daily(self):
        assert SSQ.is_daily is False
        assert FC3D.is_daily is True

    def test_prefixes_ssq(self):
        assert SSQ.xgboost_prefix() == "xgboost"
        assert SSQ.lightgbm_prefix() == "lightgbm"
        assert SSQ.catboost_prefix() == "catboost"

    def test_prefixes_non_ssq(self):
        assert KL8.xgboost_prefix() == "kl8_xgboost"
        assert KL8.lightgbm_prefix() == "kl8_lightgbm"
        assert KL8.catboost_prefix() == "kl8_catboost"


class TestProfileFunctions:
    def test_profile_keys(self):
        assert set(profile_keys()) == set(PROFILES.keys())

    def test_get_profile(self):
        assert get_profile("ssq") is SSQ
        assert get_profile("unknown_key") is SSQ

    def test_list_profiles(self):
        keys = [p.key for p in list_profiles()]
        assert keys == ["ssq", "3d", "kl8", "dlt", "pl3", "pl5", "qxc"]

    def test_list_profiles_by_category(self):
        by_cat = list_profiles_by_category()
        assert set(by_cat.keys()) >= {"welfare", "sports"}
        assert SSQ in by_cat["welfare"]
        assert DLT in by_cat["sports"]

    def test_category_label(self):
        assert category_label("welfare") == "福利彩票"
        assert category_label("sports") == "体育彩票"
        assert category_label("other") == "other"


def _var_profile(key, group_key, count, pmin, pmax, lo=0, hi=9):
    g = NumberGroup(
        group_key, "G", lo, hi, count,
        positional=True, allow_repeat=True, pick_min=pmin, pick_max=pmax, is_primary=True,
    )
    return LotteryProfile(
        key=key, name="F", groups=(g,),
        data_url="", parser_key="", draw_weekdays=(), storage_file="f.json", model_prefix="f",
    )


def _nonvar_profile(key, group_key, count, lo=0, hi=9):
    g = NumberGroup(
        group_key, "G", lo, hi, count, positional=True, allow_repeat=True, is_primary=True,
    )
    return LotteryProfile(
        key=key, name="F", groups=(g,),
        data_url="", parser_key="", draw_weekdays=(), storage_file="f.json", model_prefix="f",
    )


class TestPl3Base:
    def test_get_pick_non_variable(self):
        assert pl3_get_pick({}) == 3

    def test_add_schema_non_variable(self):
        schema = {}
        pl3_add_schema(schema)
        assert "pick_count" not in schema

    def test_make_ticket(self):
        t = pl3_make_ticket(groups={"pos": [1, 2, 3]})
        assert t.profile.key == "pl3"

    def test_get_pick_variable_branch(self, monkeypatch):
        fp = _var_profile("pl3", "pos", 3, 1, 5)
        monkeypatch.setattr(pl3_mod, "PROFILE", fp)
        assert pl3_get_pick({}) == 5
        assert pl3_get_pick({"pick_count": 3}) == 3
        assert pl3_get_pick({"pick_count": "x"}) == 5
        assert pl3_get_pick({"pick_count": 10}) == 5
        assert pl3_get_pick({"pick_count": 0}) == 1

    def test_add_schema_variable_branch(self, monkeypatch):
        fp = _var_profile("pl3", "pos", 3, 1, 5)
        monkeypatch.setattr(pl3_mod, "PROFILE", fp)
        schema = {}
        pl3_add_schema(schema)
        assert schema["pick_count"]["default"] == 5


class TestPl5Base:
    def test_get_pick_non_variable(self):
        assert pl5_get_pick({}) == 5

    def test_add_schema_non_variable(self):
        schema = {}
        pl5_add_schema(schema)
        assert "pick_count" not in schema

    def test_make_ticket(self):
        t = pl5_make_ticket(groups={"pos": [1, 2, 3, 4, 5]})
        assert t.profile.key == "pl5"

    def test_get_pick_variable_branch(self, monkeypatch):
        fp = _var_profile("pl5", "pos", 5, 1, 7)
        monkeypatch.setattr(pl5_mod, "PROFILE", fp)
        assert pl5_get_pick({}) == 7
        assert pl5_get_pick({"pick_count": 4}) == 4
        assert pl5_get_pick({"pick_count": "x"}) == 7
        assert pl5_get_pick({"pick_count": 20}) == 7
        assert pl5_get_pick({"pick_count": 0}) == 1

    def test_add_schema_variable_branch(self, monkeypatch):
        fp = _var_profile("pl5", "pos", 5, 1, 7)
        monkeypatch.setattr(pl5_mod, "PROFILE", fp)
        schema = {}
        pl5_add_schema(schema)
        assert schema["pick_count"]["default"] == 7


class TestQxcBase:
    def test_get_pick_non_variable(self):
        assert qxc_get_pick({}) == 7

    def test_add_schema_non_variable(self):
        schema = {}
        qxc_add_schema(schema)
        assert "pick_count" not in schema

    def test_make_ticket(self):
        t = qxc_make_ticket(groups={"pos": [1, 2, 3, 4, 5, 6, 7]})
        assert t.profile.key == "qxc"

    def test_get_pick_variable_branch(self, monkeypatch):
        fp = _var_profile("qxc", "pos", 7, 1, 9)
        monkeypatch.setattr(qxc_mod, "PROFILE", fp)
        assert qxc_get_pick({}) == 9
        assert qxc_get_pick({"pick_count": 5}) == 5
        assert qxc_get_pick({"pick_count": "x"}) == 9
        assert qxc_get_pick({"pick_count": 20}) == 9
        assert qxc_get_pick({"pick_count": 0}) == 1

    def test_add_schema_variable_branch(self, monkeypatch):
        fp = _var_profile("qxc", "pos", 7, 1, 9)
        monkeypatch.setattr(qxc_mod, "PROFILE", fp)
        schema = {}
        qxc_add_schema(schema)
        assert schema["pick_count"]["default"] == 9


class TestDltBase:
    def test_get_pick_non_variable(self):
        assert dlt_get_pick({}) == 5

    def test_add_schema_non_variable(self):
        schema = {}
        dlt_add_schema(schema)
        assert "pick_count" not in schema

    def test_make_ticket(self):
        t = dlt_make_ticket(groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        assert t.profile.key == "dlt"

    def test_get_pick_variable_branch(self, monkeypatch):
        fp = _var_profile("dlt", "front", 5, 1, 8, lo=1, hi=35)
        monkeypatch.setattr(dlt_mod, "PROFILE", fp)
        assert dlt_get_pick({}) == 8
        assert dlt_get_pick({"pick_count": 5}) == 5
        assert dlt_get_pick({"pick_count": "x"}) == 8
        assert dlt_get_pick({"pick_count": 20}) == 8
        assert dlt_get_pick({"pick_count": 0}) == 1

    def test_add_schema_variable_branch(self, monkeypatch):
        fp = _var_profile("dlt", "front", 5, 1, 8, lo=1, hi=35)
        monkeypatch.setattr(dlt_mod, "PROFILE", fp)
        schema = {}
        dlt_add_schema(schema)
        assert schema["pick_count"]["default"] == 8


class TestKl8Base:
    def test_get_pick_none(self):
        assert kl8_get_pick({}) == 10

    def test_get_pick_valid(self):
        assert kl8_get_pick({"pick_count": 5}) == 5

    def test_get_pick_invalid(self):
        assert kl8_get_pick({"pick_count": "abc"}) == 10

    def test_get_pick_over_max(self):
        assert kl8_get_pick({"pick_count": 20}) == 10

    def test_get_pick_under_min(self):
        assert kl8_get_pick({"pick_count": 0}) == 1

    def test_get_pick_default_param(self):
        assert kl8_get_pick({}, default_pick=7) == 7

    def test_get_pick_default_param_none(self):
        assert kl8_get_pick({}, default_pick=None) == 10

    def test_get_pick_invalid_default_param(self):
        assert kl8_get_pick({"pick_count": "x"}, default_pick=3) == 3

    def test_add_schema(self):
        schema = {}
        kl8_add_schema(schema)
        assert schema["pick_count"]["default"] == 10
        assert schema["pick_count"]["choices"] == list(range(1, 11))

    def test_add_schema_default_pick(self):
        schema = {}
        kl8_add_schema(schema, default_pick=5)
        assert schema["pick_count"]["default"] == 5

    def test_add_schema_default_pick_clamped(self):
        schema = {}
        kl8_add_schema(schema, default_pick=99)
        assert schema["pick_count"]["default"] == 10

    def test_make_ticket(self):
        t = kl8_make_ticket(groups={"main": [1, 2, 3]})
        assert t.profile.key == "kl8"

    def test_get_pick_nonvariable_branch(self, monkeypatch):
        fp = _nonvar_profile("kl8", "main", 10, lo=1, hi=80)
        monkeypatch.setattr(kl8_mod, "PROFILE", fp)
        assert kl8_get_pick({}) == 10

    def test_add_schema_nonvariable_branch(self, monkeypatch):
        fp = _nonvar_profile("kl8", "main", 10, lo=1, hi=80)
        monkeypatch.setattr(kl8_mod, "PROFILE", fp)
        schema = {}
        kl8_add_schema(schema)
        assert "pick_count" not in schema


class _Obj:
    def __init__(self):
        self.issue = "o"
        self.draw_date = datetime(2024, 1, 1)
        self.profile = "3d"
        self.groups = {"pos": [1, 2, 3]}


class TestFc3dBase:
    def test_records_empty(self):
        assert _records_from_options({}) == []

    def test_records_draw_record(self):
        rec = DrawRecord(issue="1", draw_date=datetime(2024, 1, 1), groups={"pos": [1, 2, 3]})
        out = _records_from_options({"history": [rec]})
        assert out == [rec]

    def test_records_dict_str(self):
        out = _records_from_options(
            {"history": [{"issue": "2", "draw_date": "2024-02-02", "groups": {"pos": [1, 2, 3]}}]}
        )
        assert out[0].issue == "2"

    def test_records_dict_datetime(self):
        dt = datetime(2024, 3, 3)
        out = _records_from_options(
            {"history": [{"issue": "3", "draw_date": dt, "groups": {"pos": [1, 2, 3]}}]}
        )
        assert out[0].draw_date == dt

    def test_records_dict_default_date(self):
        out = _records_from_options({"history": [{"issue": "4", "groups": {"pos": [1, 2, 3]}}]})
        assert isinstance(out[0].draw_date, datetime)

    def test_records_object(self):
        out = _records_from_options({"history": [_Obj()]})
        assert out[0].issue == "o"

    def test_make_rng_no_seed_no_history(self):
        rng = _make_rng({})
        assert isinstance(rng, random.Random)

    def test_make_rng_with_seed(self):
        rng = _make_rng({"seed": 7})
        assert isinstance(rng, random.Random)
        assert rng.random() == random.Random(7).random()

    def test_make_rng_with_history(self):
        recs = [DrawRecord(issue="1", draw_date=datetime(2024, 1, 1), groups={"pos": [1, 2, 3]})]
        rng = _make_rng({}, history=recs)
        assert isinstance(rng, random.Random)

    def test_sample_with_dedup_false(self):
        out = _sample_with_dedup(lambda: [1, 2, 3], count=2, dedup=False)
        assert out == [[1, 2, 3], [1, 2, 3]]

    def test_sample_with_dedup_true_distinct(self):
        out = _sample_with_dedup(lambda: [1, 2, 3], count=1, dedup=True)
        assert out == [[1, 2, 3]]

    def test_sample_with_dedup_true_repeat(self):
        out = _sample_with_dedup(lambda: [1, 2, 3], count=3, dedup=True)
        assert len(out) == 3

    def test_weighted_normal(self):
        pos_probs = [[0.1] * 10 for _ in range(3)]
        out = _weighted_sample_without_replacement(pos_probs, count=2, rng=random.Random(0))
        assert len(out) == 2
        for combo in out:
            assert len(combo) == 3

    def test_weighted_shape_weights(self):
        pos_probs = [[0.1] * 10 for _ in range(3)]
        out = _weighted_sample_without_replacement(
            pos_probs, count=2, rng=random.Random(0),
            shape_weights={"leopard": 2.0, "group3": 1.0, "group6": 1.0},
        )
        assert len(out) == 2

    def test_weighted_total_zero(self):
        pos_probs = [[0.0] * 10 for _ in range(3)]
        out = _weighted_sample_without_replacement(pos_probs, count=2, rng=random.Random(0))
        assert out == []
