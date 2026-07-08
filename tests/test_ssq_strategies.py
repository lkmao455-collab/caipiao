import pytest

from caipiao.core.profile import SSQ
from caipiao.core.strategies import build_strategies
from caipiao.core.strategies.lotteries.ssq.odd_even import SSQOddEvenStrategy
from caipiao.core.strategies.lotteries.ssq.random import SSQRandomStrategy


def test_ssq_random_metadata():
    s = SSQRandomStrategy()
    assert s.metadata.id == "random"
    assert s.metadata.name == "完全随机"


def test_ssq_random_generates_valid_tickets():
    s = SSQRandomStrategy()
    tickets = s.generate(count=5)
    assert len(tickets) == 5
    for t in tickets:
        assert t.profile.key == "ssq"
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1
        assert all(1 <= n <= 33 for n in t.groups["red"])
        assert 1 <= t.groups["blue"][0] <= 16


def test_ssq_random_seed_reproducible():
    s = SSQRandomStrategy()
    t1 = s.generate(count=1, options={"seed": 42})[0]
    t2 = s.generate(count=1, options={"seed": 42})[0]
    assert t1.groups == t2.groups


def test_ssq_odd_even_metadata():
    s = SSQOddEvenStrategy()
    assert s.metadata.id == "odd_even"
    assert s.metadata.name == "奇偶均衡"


def test_ssq_odd_even_respects_count():
    s = SSQOddEvenStrategy()
    tickets = s.generate(count=5, options={"odd_count": 2})
    for t in tickets:
        odd = sum(1 for n in t.groups["red"] if n % 2 == 1)
        assert odd == 2


def test_build_strategies_includes_ssq():
    strategies = build_strategies(SSQ)
    ids = {s.metadata.id for s in strategies}
    assert "random" in ids
    assert "odd_even" in ids
