"""策略公共模块测试."""

import pytest

from caipiao.core.strategies.common.rng import make_rng
from caipiao.core.strategies.common.records import records_from_options
from caipiao.core.ticket import Ticket


class TestMakeRng:
    """make_rng 测试."""

    def test_same_seed_same_rng(self):
        rng1 = make_rng({"seed": 42})
        rng2 = make_rng({"seed": 42})
        # 相同种子应该产生相同的随机数序列
        assert rng1.random() == rng2.random()

    def test_different_seed_different_rng(self):
        rng1 = make_rng({"seed": 42})
        rng2 = make_rng({"seed": 43})
        # 不同种子应该产生不同的随机数序列
        assert rng1.random() != rng2.random()

    def test_no_seed(self):
        rng = make_rng({})
        # 没有种子应该创建 Random 实例
        assert rng is not None


class TestRecordsFromOptions:
    """records_from_options 测试."""

    def test_empty_options(self):
        result = records_from_options({})
        assert result == []

    def test_with_history(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        result = records_from_options({"history": [ticket]})
        assert len(result) == 1
