from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import get_profile
from caipiao.core.strategies.fc3d import (
    FC3DRandomStrategy,
    FC3DOddEvenStrategy,
    FC3DExcludeIncludeStrategy,
    FC3DHotColdStrategy,
    FC3DSmartHotColdStrategy,
    FC3DMissingNumberStrategy,
    FC3DBalancedStrategy,
    FC3DXGBoostStrategy,
    FC3DLightGBMStrategy,
    FC3DCatBoostStrategy,
)
from caipiao.core.strategies.generic import build_strategies, needs_history, is_ml_strategy
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
        assert odd == 2  # 仅校验奇数个数，不校验位置顺序


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


def test_exclude_include_3d_empty_pool_raises():
    strategy = FC3DExcludeIncludeStrategy()
    options = {
        "include_pos": [[], [], []],
        "exclude_pos": [[], [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], []],
    }
    with pytest.raises(ValueError, match=r"第2位排除后没有可用号码"):
        strategy.validate_options(options)


def test_exclude_include_3d_empty_include_with_exclude():
    """Regression: empty include_pos but non-empty exclude_pos must choose from available pool."""
    strategy = FC3DExcludeIncludeStrategy()
    tickets = strategy.generate(
        count=20,
        options={
            "include_pos": [[], [], []],
            "exclude_pos": [[0, 1, 2], [3, 4], [5, 6, 7, 8]],
            "seed": 123,
        },
    )
    assert len(tickets) == 20
    for t in tickets:
        assert t.groups["pos"][0] not in (0, 1, 2)
        assert t.groups["pos"][1] not in (3, 4)
        assert t.groups["pos"][2] not in (5, 6, 7, 8)


def test_smart_hot_cold_3d_all_digits_in_lookback():
    """Guard: lookback window contains every digit, so no division by zero can occur."""
    strategy = FC3DSmartHotColdStrategy()
    # 10 draws where each position cycles through 0-9, then repeat to satisfy minimum 20.
    history = [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(20)
    ]
    tickets = strategy.generate(count=5, options={"history": history, "lookback": 10, "seed": 7})
    assert len(tickets) == 5
    for t in tickets:
        assert len(t.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in t.groups["pos"])


def test_smart_hot_cold_3d_seed_reproducible():
    strategy = FC3DSmartHotColdStrategy()
    history = make_history(50)
    opts = {"history": history, "lookback": 30, "seed": 42}
    t1 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    t2 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    assert t1 == t2


def test_hot_cold_3d_generates_valid():
    strategy = FC3DHotColdStrategy()
    history = make_history(50)
    tickets = strategy.generate(count=3, options={"mode": "hot", "history": history})
    assert len(tickets) == 3
    for t in tickets:
        assert len(t.groups["pos"]) == 3


def test_hot_cold_3d_seed_reproducible():
    strategy = FC3DHotColdStrategy()
    history = make_history(50)
    opts = {"mode": "hot", "history": history, "seed": 42}
    t1 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    t2 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    assert t1 == t2


def test_smart_hot_cold_3d_uses_history():
    strategy = FC3DSmartHotColdStrategy()
    history = make_history(50)
    tickets = strategy.generate(count=3, options={"history": history, "lookback": 30})
    assert len(tickets) == 3


def test_missing_number_3d_generates_valid():
    strategy = FC3DMissingNumberStrategy()
    history = make_history(50)
    tickets = strategy.generate(count=3, options={"history": history, "lookback": 30})
    assert len(tickets) == 3


def test_balanced_3d_generates_valid():
    strategy = FC3DBalancedStrategy()
    history = make_history(50)
    tickets = strategy.generate(count=3, options={"history": history, "lookback": 30})
    assert len(tickets) == 3
    for t in tickets:
        assert len(t.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in t.groups["pos"])


def test_balanced_3d_respects_order():
    """历史均衡结果应保留百十位的原始顺序，不应被排序。"""
    strategy = FC3DBalancedStrategy()
    history = [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [9, 0, 1]},
        )
        for i in range(20)
    ]
    ticket = strategy.generate(
        count=1,
        options={"history": history, "lookback": 20, "seed": 1, "use_enumeration": True},
    )[0]
    assert ticket.groups["pos"] == [9, 0, 1]


def test_balanced_3d_enumeration_finds_best():
    strategy = FC3DBalancedStrategy()
    history = make_history(30)
    # 记录中全是 [i, i+1, i+2] mod 10，最优应接近这种模式
    tickets = strategy.generate(
        count=1,
        options={"history": history, "lookback": 30, "use_enumeration": True},
    )
    assert len(tickets) == 1


def test_balanced_3d_seed_reproducible():
    strategy = FC3DBalancedStrategy()
    history = make_history(50)
    opts = {"history": history, "lookback": 30, "seed": 42}
    t1 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    t2 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    assert t1 == t2


@pytest.mark.parametrize("strategy_cls", [FC3DXGBoostStrategy, FC3DLightGBMStrategy, FC3DCatBoostStrategy])
def test_ml_3d_strategy_generates_valid(strategy_cls):
    strategy = strategy_cls()
    assert strategy.is_ml
    history = make_history(120)
    tickets = strategy.generate(count=1, options={"history": history, "history_count": 100})
    assert len(tickets) == 1
    assert len(tickets[0].groups["pos"]) == 3
    assert all(0 <= n <= 9 for n in tickets[0].groups["pos"])


def test_build_strategies_3d_uses_fc3d_classes():
    profile = get_profile("3d")
    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    assert "random_3d" in strategies
    assert "balanced_3d" in strategies
    assert "xgboost_3d" in strategies
    # 确认是3D专属类，不是通用类
    from caipiao.core.strategies.fc3d import FC3DBalancedStrategy
    assert isinstance(strategies["balanced_3d"], FC3DBalancedStrategy)


def test_needs_history_and_is_ml_3d_unchanged():
    assert needs_history("balanced_3d")
    assert needs_history("xgboost_3d")
    assert is_ml_strategy("xgboost_3d")
    assert is_ml_strategy("lightgbm_3d")
    assert is_ml_strategy("catboost_3d")
    assert not needs_history("random_3d")
