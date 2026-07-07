from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import get_profile
from caipiao.core.strategies.fc3d import (
    FC3DRandomStrategy,
    FC3DOddEvenStrategy,
    FC3DExcludeIncludeStrategy,
)
from caipiao.data.models import DrawRecord


def make_history(n=30):
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(n)
    ]


def test_random_3d_generates_three_digits():
    strategy = FC3DRandomStrategy()
    tickets = strategy.generate(count=5)
    assert len(tickets) == 5
    for t in tickets:
        assert len(t.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in t.groups["pos"])


def test_random_3d_seed_reproducible():
    strategy = FC3DRandomStrategy()
    t1 = strategy.generate(count=1, options={"seed": 42})[0].groups["pos"]
    t2 = strategy.generate(count=1, options={"seed": 42})[0].groups["pos"]
    assert t1 == t2


def test_odd_even_3d_respects_overall_count():
    strategy = FC3DOddEvenStrategy()
    tickets = strategy.generate(count=5, options={"odd_count": 2})
    for t in tickets:
        odd = sum(1 for n in t.groups["pos"] if n % 2 == 1)
        assert odd == 2


def test_odd_even_3d_positional_mode():
    strategy = FC3DOddEvenStrategy()
    tickets = strategy.generate(count=5, options={"positional": [1, 0, 1]})
    for t in tickets:
        assert t.groups["pos"][0] % 2 == 1
        assert t.groups["pos"][1] % 2 == 0
        assert t.groups["pos"][2] % 2 == 1


def test_exclude_include_3d_positional():
    strategy = FC3DExcludeIncludeStrategy()
    tickets = strategy.generate(
        count=5,
        options={
            "include_pos": [[1], [], [5]],
            "exclude_pos": [[], [2, 3], []],
        },
    )
    for t in tickets:
        assert t.groups["pos"][0] == 1
        assert t.groups["pos"][1] not in (2, 3)
        assert t.groups["pos"][2] == 5


def test_exclude_include_3d_no_sort():
    strategy = FC3DExcludeIncludeStrategy()
    ticket = strategy.generate(
        count=1,
        options={"include_pos": [[9], [1], [0]]},
    )[0]
    assert ticket.groups["pos"] == [9, 1, 0]
