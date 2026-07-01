"""核心模块单元测试."""

import pytest

from caipiao.core.ball import Ball, BallColor
from caipiao.core.engine import GenerationEngine
from caipiao.core.strategies import (
    ExcludeIncludeStrategy,
    HotColdStrategy,
    OddEvenStrategy,
    RandomStrategy,
)
from caipiao.core.ticket import Ticket


def test_ball_validation():
    Ball.red(1)
    Ball.red(33)
    Ball.blue(1)
    Ball.blue(16)

    with pytest.raises(ValueError):
        Ball.red(0)
    with pytest.raises(ValueError):
        Ball.red(34)
    with pytest.raises(ValueError):
        Ball.blue(17)


def test_ticket_validation():
    Ticket([1, 2, 3, 4, 5, 6], 7)

    with pytest.raises(ValueError):
        Ticket([1, 2, 3, 4, 5], 7)
    with pytest.raises(ValueError):
        Ticket([1, 2, 3, 4, 5, 5], 7)
    with pytest.raises(ValueError):
        Ticket([1, 2, 3, 4, 5, 6], 17)


def test_random_strategy():
    strategy = RandomStrategy()
    tickets = strategy.generate(count=10)
    assert len(tickets) == 10
    for t in tickets:
        assert len(t.red_balls) == 6
        assert 1 <= t.blue_ball.number <= 16


def test_odd_even_strategy():
    strategy = OddEvenStrategy()
    tickets = strategy.generate(count=5, options={"odd_count": 4})
    for t in tickets:
        odd_count = sum(1 for b in t.red_balls if b.number % 2 == 1)
        assert odd_count == 4


def test_exclude_include_strategy():
    strategy = ExcludeIncludeStrategy()
    tickets = strategy.generate(
        count=3,
        options={"include_red": [1, 2], "exclude_red": [33], "exclude_blue": [16]},
    )
    for t in tickets:
        reds = {b.number for b in t.red_balls}
        assert 1 in reds
        assert 2 in reds
        assert 33 not in reds
        assert t.blue_ball.number != 16


def test_engine():
    engine = GenerationEngine()
    engine.register(RandomStrategy())
    tickets = engine.generate("random", count=2)
    assert len(tickets) == 2


def test_hot_cold_strategy_with_history():
    strategy = HotColdStrategy()
    history = [Ticket([1, 2, 3, 4, 5, 6], 1) for _ in range(5)]
    tickets = strategy.generate(count=2, options={"mode": "hot", "history": history})
    assert len(tickets) == 2
