"""福彩3D 直选/组选投注方式分配与判定测试。"""

from __future__ import annotations

from typing import List, Optional

from caipiao.core.engine import GenerationEngine
from caipiao.core.strategies.lotteries.fc3d.utils import assign_fc3d_bet_modes
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata
from caipiao.core.ticket import Ticket


def _ticket(nums: List[int]) -> Ticket:
    return Ticket(profile="3d", groups={"pos": nums})


def _modes(tickets: List[Ticket]) -> List[str]:
    return [t.details["bet_mode"] for t in tickets]


class TestAssignFc3dBetModes:
    def test_even_split(self):
        tickets = [_ticket([1, 2, 3]) for _ in range(10)]
        assign_fc3d_bet_modes(tickets)
        assert _modes(tickets) == ["组选"] * 5 + ["直选"] * 5

    def test_odd_split_group_has_one_more(self):
        tickets = [_ticket([1, 2, 3]) for _ in range(3)]
        assign_fc3d_bet_modes(tickets)
        assert _modes(tickets) == ["组选", "组选", "直选"]

    def test_single_ticket_is_group(self):
        tickets = [_ticket([1, 2, 3])]
        assign_fc3d_bet_modes(tickets)
        assert _modes(tickets) == ["组选"]

    def test_leopard_in_group_zone_becomes_zhixuan(self):
        # N=3：前 2 张为组选区；第 1 张是豹子号 → 转直选，不补位
        tickets = [_ticket([6, 6, 6]), _ticket([1, 2, 3]), _ticket([4, 5, 6])]
        assign_fc3d_bet_modes(tickets)
        assert _modes(tickets) == ["直选", "组选", "直选"]

    def test_empty_list(self):
        assert assign_fc3d_bet_modes([]) == []


class _Dummy3dStrategy(GenerationStrategy):
    def __init__(self, tickets: List[Ticket]) -> None:
        self._tickets = tickets

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(id="dummy-3d", name="dummy", description="")

    def generate(self, count: int = 1, options: Optional[dict] = None) -> List[Ticket]:
        return self._tickets


class TestEngineHook:
    def test_engine_assigns_bet_modes_for_3d(self):
        engine = GenerationEngine()
        engine.register(_Dummy3dStrategy([_ticket([1, 2, 3]) for _ in range(4)]))
        tickets = engine.generate("dummy-3d", count=4)
        assert _modes(tickets) == ["组选", "组选", "直选", "直选"]

    def test_engine_leaves_ssq_untouched(self):
        engine = GenerationEngine()
        ssq = [Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7) for _ in range(2)]
        engine.register(_Dummy3dStrategy(ssq))
        tickets = engine.generate("dummy-3d", count=2)
        assert all("bet_mode" not in t.details for t in tickets)


from caipiao.core.prize import calculate_prize


def _prize(ticket_nums, actual_nums, bet_mode=None):
    details = {"bet_mode": bet_mode} if bet_mode else None
    return calculate_prize(
        "3d",
        {"pos": 0},
        {"pos": ticket_nums},
        {"pos": actual_nums},
        details=details,
    )


class TestFc3dPrizeByBetMode:
    def test_zhixuan_exact_match(self):
        assert _prize([1, 2, 3], [1, 2, 3], "直选") == ("直选", 1040)

    def test_zhixuan_wrong_order_no_prize(self):
        # 直选票顺序不同 → 不中（旧逻辑会发组选6奖金）
        assert _prize([1, 2, 3], [3, 2, 1], "直选") == ("未中奖", 0)

    def test_zuxuan_unordered_match_group6(self):
        assert _prize([1, 2, 3], [3, 2, 1], "组选") == ("组选6", 173)

    def test_zuxuan_unordered_match_group3(self):
        assert _prize([1, 1, 2], [1, 2, 1], "组选") == ("组选3", 346)

    def test_zuxuan_exact_order_still_group_prize(self):
        # 组选票即使位置全对，也只发组选奖金
        assert _prize([1, 2, 3], [1, 2, 3], "组选") == ("组选6", 173)

    def test_zuxuan_mismatch(self):
        assert _prize([1, 2, 3], [4, 5, 6], "组选") == ("未中奖", 0)

    def test_zuxuan_leopard_fallback_zhixuan(self):
        # 豹子号标组选属异常数据，兜底按直选规则
        assert _prize([6, 6, 6], [6, 6, 6], "组选") == ("直选", 1040)

    def test_legacy_without_bet_mode_unchanged(self):
        # 无 bet_mode：保持旧行为（有序全对发直选，无序相同发组选）
        assert _prize([1, 2, 3], [1, 2, 3]) == ("直选", 1040)
        assert _prize([1, 2, 3], [3, 2, 1]) == ("组选6", 173)
        assert _prize([1, 2, 3], [4, 5, 6]) == ("未中奖", 0)
