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
