from collections import Counter
from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import get_profile
from caipiao.core.strategies.lotteries.fc3d import (
    FC3DRandomStrategy,
    FC3DOddEvenStrategy,
    FC3DHotColdStrategy,
    FC3DSmartHotColdStrategy,
    FC3DMissingNumberStrategy,
    FC3DBalancedStrategy,
    FC3DXGBoostStrategy,
    FC3DLightGBMStrategy,
    FC3DCatBoostStrategy,
)
from caipiao.core.strategies import build_strategies, needs_history, is_ml_strategy
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


def _max_digit_concentration(tickets):
    """返回所有 ticket 中按位数字出现频率的最大值。"""
    counts = Counter()
    for t in tickets:
        counts.update(t.groups["pos"])
    total = sum(counts.values())
    return max(counts.values()) / total if total else 0.0


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


def test_random_3d_preserves_order():
    strategy = FC3DRandomStrategy()
    tickets = strategy.generate(count=50)
    assert any(t.groups["pos"] != sorted(t.groups["pos"]) for t in tickets)


def test_odd_even_3d_respects_overall_count():
    strategy = FC3DOddEvenStrategy()
    tickets = strategy.generate(count=5, options={"odd_count": 2})
    for t in tickets:
        odd = sum(1 for n in t.groups["pos"] if n % 2 == 1)
        assert odd == 2  # 仅校验奇数个数，不校验位置顺序


def test_odd_even_3d_overall_preserves_random_order():
    strategy = FC3DOddEvenStrategy()
    # 不同种子应产生不同顺序；未指定种子时策略已改为基于内容确定性输出
    tickets1 = strategy.generate(count=20, options={"odd_count": 2, "seed": 1})
    tickets2 = strategy.generate(count=20, options={"odd_count": 2, "seed": 2})
    assert any(t1.groups["pos"] != t2.groups["pos"] for t1, t2 in zip(tickets1, tickets2))


def test_odd_even_3d_positional_mode():
    strategy = FC3DOddEvenStrategy()
    tickets = strategy.generate(count=5, options={"positional": [1, 0, 1]})
    for t in tickets:
        assert t.groups["pos"][0] % 2 == 1
        assert t.groups["pos"][1] % 2 == 0
        assert t.groups["pos"][2] % 2 == 1


def test_exclude_include_3d_positional():
    pytest.skip("exclude_include_3d 策略已从福彩3D移除")


# def test_exclude_include_3d_positional():
#     strategy = FC3DExcludeIncludeStrategy()
#     tickets = strategy.generate(
#         count=5,
#         options={
#             "include_pos": [[1], [], [5]],
#             "exclude_pos": [[], [2, 3], []],
#         },
#     )
#     for t in tickets:
#         assert t.groups["pos"][0] == 1
#         assert t.groups["pos"][1] not in (2, 3)
#         assert t.groups["pos"][2] == 5


def test_exclude_include_3d_no_sort():
    pytest.skip("exclude_include_3d 策略已从福彩3D移除")


# def test_exclude_include_3d_no_sort():
#     strategy = FC3DExcludeIncludeStrategy()
#     ticket = strategy.generate(
#         count=1,
#         options={"include_pos": [[9], [1], [0]]},
#     )[0]
#     assert ticket.groups["pos"] == [9, 1, 0]


def test_exclude_include_3d_empty_pool_raises():
    pytest.skip("exclude_include_3d 策略已从福彩3D移除")


# def test_exclude_include_3d_empty_pool_raises():
#     strategy = FC3DExcludeIncludeStrategy()
#     options = {
#         "include_pos": [[], [], []],
#         "exclude_pos": [[], [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], []],
#     }
#     with pytest.raises(ValueError, match=r"第2位排除后没有可用号码"):
#         strategy.validate_options(options)


def test_exclude_include_3d_empty_include_with_exclude():
    pytest.skip("exclude_include_3d 策略已从福彩3D移除")


# def test_exclude_include_3d_empty_include_with_exclude():
#     """Regression: empty include_pos but non-empty exclude_pos must choose from available pool."""
#     strategy = FC3DExcludeIncludeStrategy()
#     tickets = strategy.generate(
#         count=20,
#         options={
#             "include_pos": [[], [], []],
#             "exclude_pos": [[0, 1, 2], [3, 4], [5, 6, 7, 8]],
#             "seed": 123,
#         },
#     )
#     assert len(tickets) == 20
#     for t in tickets:
#         assert t.groups["pos"][0] not in (0, 1, 2)
#         assert t.groups["pos"][1] not in (3, 4)
#         assert t.groups["pos"][2] not in (5, 6, 7, 8)


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
        for i in range(30)
    ]
    ticket = strategy.generate(
        count=1,
        options={"history": history, "lookback": 30, "seed": 1, "use_enumeration": True},
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


def test_balanced_3d_uses_positional_weights():
    """当某位数字出现频率显著更高时，均衡策略倾向于选中该数字。"""
    strategy = FC3DBalancedStrategy()
    history = [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [7, (i % 10), ((i + 1) % 10)]},
        )
        for i in range(30)
    ]
    first_positions = [
        strategy.generate(
            count=1,
            options={"history": history, "lookback": 30, "use_enumeration": False, "seed": s},
        )[0].groups["pos"][0]
        for s in range(100)
    ]
    assert first_positions.count(7) > 50


def test_balanced_3d_span_and_tail_influence():
    """均衡策略会参考历史跨度和和尾，生成与之相近的结果。"""
    strategy = FC3DBalancedStrategy()
    history = [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [1, 2, 8]},
        )
        for i in range(30)
    ]
    ticket = strategy.generate(
        count=1,
        options={"history": history, "lookback": 30, "use_enumeration": True},
    )[0]
    pos = ticket.groups["pos"]
    span = max(pos) - min(pos)
    tail = sum(pos) % 10
    assert 5 <= span <= 9
    assert tail in {0, 1, 2}


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
    from caipiao.core.strategies.lotteries.fc3d import FC3DBalancedStrategy
    assert isinstance(strategies["balanced_3d"], FC3DBalancedStrategy)


def test_needs_history_and_is_ml_3d_unchanged():
    assert needs_history("balanced_3d")
    assert needs_history("xgboost_3d")
    assert is_ml_strategy("xgboost_3d")
    assert is_ml_strategy("lightgbm_3d")
    assert is_ml_strategy("catboost_3d")
    assert not needs_history("random_3d")


def test_all_3d_strategies_respect_count():
    profile = get_profile("3d")
    from caipiao.core.strategies import build_strategies

    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    history = make_history(120)
    for sid, strategy in strategies.items():
        if getattr(strategy, "_placeholder", False):
            continue
        options = {}
        if needs_history(sid):
            options["history"] = history
        tickets = strategy.generate(count=5, options=options)
        assert len(tickets) == 5, sid
        for t in tickets:
            assert len(t.groups["pos"]) == 3, sid
            assert all(0 <= n <= 9 for n in t.groups["pos"]), sid


def test_balanced_3d_no_history_raises():
    strategy = FC3DBalancedStrategy()
    with pytest.raises(ValueError):
        strategy.generate(count=1, options={"history": []})


def _make_biased_history(n=50):
    """生成有偏历史：前两位分别固定为高频数字 5 和 9."""
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [5, 9, (i % 10)]},
        )
        for i in range(n)
    ]


def test_hot_cold_3d_temperature_changes_concentration():
    strategy = FC3DHotColdStrategy()
    history = _make_biased_history(50)
    # 使用更大的样本量降低随机波动，避免小样本下高低温浓度偶尔倒挂
    low_t = strategy.generate(count=200, options={"mode": "hot", "history": history, "lookback": 30, "temperature": 5})
    high_t = strategy.generate(count=200, options={"mode": "hot", "history": history, "lookback": 30, "temperature": 50})
    # 低温度下应更集中在高频数字
    assert _max_digit_concentration(low_t) > _max_digit_concentration(high_t)


def test_smart_hot_cold_3d_temperature_changes_concentration():
    strategy = FC3DSmartHotColdStrategy()
    history = _make_biased_history(50)
    low_t = strategy.generate(count=50, options={"history": history, "lookback": 30, "temperature": 5})
    high_t = strategy.generate(count=50, options={"history": history, "lookback": 30, "temperature": 50})
    assert _max_digit_concentration(low_t) > _max_digit_concentration(high_t)


def test_all_3d_strategies_deterministic_without_user_seed():
    """未提供用户 seed 时，基于历史的策略仍应基于历史内容可复现。"""
    profile = get_profile("3d")
    from caipiao.core.strategies import build_strategies
    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    history = make_history(120)
    for sid, strategy in strategies.items():
        if not needs_history(sid):
            continue
        if getattr(strategy, "_placeholder", False):
            continue
        options = {}
        if needs_history(sid):
            options["history"] = history
            if is_ml_strategy(sid):
                options["history_count"] = 100
        t1 = strategy.generate(count=1, options=options)[0].groups["pos"]
        t2 = strategy.generate(count=1, options=options)[0].groups["pos"]
        assert t1 == t2, sid


def test_ml_3d_insufficient_history_raises():
    strategy = FC3DXGBoostStrategy()
    with pytest.raises(ValueError):
        strategy.generate(count=1, options={"history": make_history(50)})


@pytest.mark.parametrize(
    "strategy_id",
    [
        "random_3d",
        "odd_even_3d",
        "hot_cold_3d",
        "smart_hot_cold_3d",
        "missing_number_3d",
        "balanced_3d",
        "xgboost_3d",
        "lightgbm_3d",
        "catboost_3d",
    ],
)
def test_all_3d_strategies_seed_reproducible(strategy_id):
    profile = get_profile("3d")
    from caipiao.core.strategies import build_strategies

    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    strategy = strategies[strategy_id]
    options = {"seed": 123}
    if needs_history(strategy_id):
        options["history"] = make_history(120)
        if is_ml_strategy(strategy_id):
            options["history_count"] = 100
    t1 = strategy.generate(count=1, options=options)[0].groups["pos"]
    t2 = strategy.generate(count=1, options=options)[0].groups["pos"]
    assert t1 == t2, strategy_id
