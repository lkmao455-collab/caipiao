"""福彩3D分散随机策略测试."""

from __future__ import annotations

import pytest

from caipiao.core.strategies.lotteries.fc3d.dispersed_random import (
    FC3DDispersedRandomStrategy,
)


def test_dispersed_random_strategy_exists():
    strategy = FC3DDispersedRandomStrategy()
    assert strategy.metadata.id == "dispersed_random_3d"
    tickets = strategy.generate(count=5, options={})
    assert len(tickets) == 5


@pytest.fixture
def strategy():
    return FC3DDispersedRandomStrategy()


def test_metadata(strategy):
    assert strategy.metadata.id == "dispersed_random_3d"
    assert strategy.metadata.name == "分散随机"


def test_generate_without_history(strategy):
    tickets = strategy.generate(count=20, options={})
    assert len(tickets) == 20
    for t in tickets:
        assert len(t.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in t.groups["pos"])


def test_dedup_removes_group_duplicates(strategy):
    tickets = strategy.generate(count=50, options={"dedup": True, "seed": 1})
    keys = {tuple(sorted(t.groups["pos"])) for t in tickets}
    assert len(keys) == len(tickets)


def test_dedup_allows_more_than_220_raises(strategy):
    with pytest.raises(ValueError):
        strategy.generate(count=300, options={"dedup": True})


def test_seed_deterministic(strategy):
    t1 = strategy.generate(count=20, options={"seed": 42})
    t2 = strategy.generate(count=20, options={"seed": 42})
    assert [t.groups["pos"] for t in t1] == [t.groups["pos"] for t in t2]


def test_dispersion_positive(strategy):
    tickets = strategy.generate(count=20, options={"seed": 123})
    nums = [tuple(t.groups["pos"]) for t in tickets]
    min_dist = float("inf")
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            d = FC3DDispersedRandomStrategy._euclidean_distance(nums[i], nums[j])
            if d < min_dist:
                min_dist = d
    assert min_dist > 0


def test_no_history_required(strategy):
    # 明确不传 history 也能工作
    tickets = strategy.generate(count=5, options={})
    assert len(tickets) == 5
