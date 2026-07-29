"""奖金计算模块测试."""

import pytest

from caipiao.core.prize import (
    calculate_prize,
    fc3d_bet_type,
    _ssq_prize,
    _fc3d_prize,
    _kl8_prize,
    _dlt_prize,
    _pl3_prize,
    _pl5_prize,
)


class TestSSQPrize:
    """双色球奖金测试."""

    def test_first_prize(self):
        hits = {"red": 6, "blue": 1}
        level, amount = _ssq_prize(hits)
        assert level == "一等奖"
        assert amount is None

    def test_second_prize(self):
        hits = {"red": 6, "blue": 0}
        level, amount = _ssq_prize(hits)
        assert level == "二等奖"
        assert amount is None

    def test_third_prize(self):
        hits = {"red": 5, "blue": 1}
        level, amount = _ssq_prize(hits)
        assert level == "三等奖"
        assert amount == 3000

    def test_fourth_prize(self):
        hits = {"red": 5, "blue": 0}
        level, amount = _ssq_prize(hits)
        assert level == "四等奖"
        assert amount == 200

    def test_fifth_prize(self):
        hits = {"red": 4, "blue": 0}
        level, amount = _ssq_prize(hits)
        assert level == "五等奖"
        assert amount == 10

    def test_sixth_prize(self):
        hits = {"red": 0, "blue": 1}
        level, amount = _ssq_prize(hits)
        assert level == "六等奖"
        assert amount == 5

    def test_no_prize(self):
        hits = {"red": 0, "blue": 0}
        level, amount = _ssq_prize(hits)
        assert level == "未中奖"
        assert amount == 0


class TestFC3DPrize:
    """福彩3D奖金测试."""

    def test_zhixuan(self):
        hits = {}
        ticket_groups = {"pos": [1, 2, 3]}
        actual_groups = {"pos": [1, 2, 3]}
        level, amount = _fc3d_prize(hits, ticket_groups, actual_groups)
        assert level == "直选"
        assert amount == 1040

    def test_zuxuan6(self):
        hits = {}
        ticket_groups = {"pos": [1, 2, 3]}
        actual_groups = {"pos": [3, 2, 1]}
        level, amount = _fc3d_prize(hits, ticket_groups, actual_groups)
        assert level == "组选6"
        assert amount == 173

    def test_zuxuan3(self):
        hits = {}
        ticket_groups = {"pos": [1, 1, 2]}
        actual_groups = {"pos": [2, 1, 1]}
        level, amount = _fc3d_prize(hits, ticket_groups, actual_groups)
        assert level == "组选3"
        assert amount == 346

    def test_no_prize(self):
        hits = {}
        ticket_groups = {"pos": [1, 2, 3]}
        actual_groups = {"pos": [4, 5, 6]}
        level, amount = _fc3d_prize(hits, ticket_groups, actual_groups)
        assert level == "未中奖"
        assert amount == 0

    def test_no_actual_groups(self):
        hits = {}
        ticket_groups = {"pos": [1, 2, 3]}
        level, amount = _fc3d_prize(hits, ticket_groups, None)
        assert level == "未中奖"
        assert amount == 0


class TestKL8Prize:
    """快乐8奖金测试."""

    def test_select_one(self):
        hits = {"main": 1}
        groups = {"main": [1]}
        level, amount = _kl8_prize(hits, groups)
        assert level == "选一中一"
        assert amount == 4

    def test_select_five(self):
        hits = {"main": 5}
        groups = {"main": [1, 2, 3, 4, 5]}
        level, amount = _kl8_prize(hits, groups)
        assert level == "选五中五"
        assert amount == 1000

    def test_no_prize(self):
        hits = {"main": 0}
        groups = {"main": [1, 2, 3, 4, 5]}
        level, amount = _kl8_prize(hits, groups)
        assert level == "未中奖"
        assert amount == 0


class TestDLTPrize:
    """超级大乐透奖金测试."""

    def test_first_prize(self):
        hits = {"front": 5, "back": 2}
        level, amount = _dlt_prize(hits)
        assert level == "一等奖"
        assert amount is None

    def test_second_prize(self):
        hits = {"front": 5, "back": 1}
        level, amount = _dlt_prize(hits)
        assert level == "二等奖"
        assert amount is None

    def test_third_prize(self):
        hits = {"front": 5, "back": 0}
        level, amount = _dlt_prize(hits)
        assert level == "三等奖"
        assert amount == 10000

    def test_no_prize(self):
        hits = {"front": 0, "back": 0}
        level, amount = _dlt_prize(hits)
        assert level == "未中奖"
        assert amount == 0


class TestPL3Prize:
    """排列3奖金测试."""

    def test_zhixuan(self):
        hits = {}
        ticket_groups = {"pos": [1, 2, 3]}
        actual_groups = {"pos": [1, 2, 3]}
        level, amount = _pl3_prize(hits, ticket_groups, actual_groups)
        assert level == "直选"
        assert amount == 1040

    def test_no_prize(self):
        hits = {}
        ticket_groups = {"pos": [1, 2, 3]}
        actual_groups = {"pos": [4, 5, 6]}
        level, amount = _pl3_prize(hits, ticket_groups, actual_groups)
        assert level == "未中奖"
        assert amount == 0


class TestPL5Prize:
    """排列5奖金测试."""

    def test_zhixuan(self):
        hits = {"pos": 5}
        level, amount = _pl5_prize(hits)
        assert level == "直选"
        assert amount == 100000

    def test_no_prize(self):
        hits = {"pos": 0}
        level, amount = _pl5_prize(hits)
        assert level == "未中奖"
        assert amount == 0


class TestCalculatePrize:
    """calculate_prize 函数测试."""

    def test_ssq(self):
        hits = {"red": 6, "blue": 1}
        level, amount = calculate_prize("ssq", hits, {})
        assert level == "一等奖"

    def test_3d(self):
        hits = {}
        ticket_groups = {"pos": [1, 2, 3]}
        actual_groups = {"pos": [1, 2, 3]}
        level, amount = calculate_prize("3d", hits, ticket_groups, actual_groups)
        assert level == "直选"

    def test_unknown_lottery(self):
        hits = {}
        level, amount = calculate_prize("unknown", hits, {})
        assert level == "未知彩种"
        assert amount == 0


class TestFC3DBetType:
    """福彩3D投注方式测试."""

    def test_zu6(self):
        assert fc3d_bet_type([1, 2, 3]) == "组选6"

    def test_zu3(self):
        assert fc3d_bet_type([1, 1, 2]) == "组选3"

    def test_baozi(self):
        assert fc3d_bet_type([1, 1, 1]) == "豹子号（直选）"

    def test_unknown(self):
        assert fc3d_bet_type([1, 2]) == "未知"
