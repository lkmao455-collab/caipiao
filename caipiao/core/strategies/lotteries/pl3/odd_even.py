"""排列3奇偶均衡策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.rng import make_rng
from ._base import PROFILE, _add_pick_count_schema, _get_pick_count, _make_ticket


class PL3OddEvenStrategy(GenerationStrategy):
    """控制主号码组中奇偶比例."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="odd_even_pl3",
            name="奇偶均衡",
            description="控制排列3号码中奇数和偶数的比例，默认接近均衡。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        primary = PROFILE.primary_group
        pick = primary.effective_pick_max
        schema: Dict[str, Any] = {
            "odd_count": {
                "type": "int",
                "label": "奇数个数",
                "default": pick // 2,
                "min": 0,
                "max": pick,
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema, label=f"{primary.name}投注个数")
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        primary = PROFILE.primary_group
        pick = _get_pick_count(options)
        odd_count = options.get("odd_count", pick // 2)
        if not isinstance(odd_count, int) or not (0 <= odd_count <= pick):
            raise ValueError(f"奇数个数必须是 0-{pick} 的整数")
        if primary.variable_pick:
            pc = options.get("pick_count")
            if pc is not None:
                pc = int(pc)
                if not (primary.effective_pick_min <= pc <= primary.effective_pick_max):
                    raise ValueError(
                        f"投注个数必须在 {primary.effective_pick_min}-{primary.effective_pick_max} 之间"
                    )

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        primary = PROFILE.primary_group
        pick = _get_pick_count(options)
        odd_count = int(options.get("odd_count", pick // 2))
        even_count = pick - odd_count
        rng = make_rng(options)

        odd_pool = [n for n in primary.values if n % 2 == 1]
        even_pool = [n for n in primary.values if n % 2 == 0]
        if odd_count > len(odd_pool) or even_count > len(even_pool):
            raise ValueError("奇偶数量超出可选范围")

        basis = f"奇偶均衡策略：{primary.name}中强制包含 {odd_count} 个奇数、{even_count} 个偶数。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            if primary.positional:
                groups[primary.key] = [rng.randint(primary.lo, primary.hi) for _ in range(primary.count)]
            else:
                groups[primary.key] = sorted(rng.sample(odd_pool, odd_count) + rng.sample(even_pool, even_count))
            self._fill_other_groups(groups, rng)
            tickets.append(_make_ticket(groups, strategy_name=self.metadata.name, basis=basis))
        return tickets

    def _fill_other_groups(self, groups: Dict[str, List[int]], rng: random.Random) -> None:
        for g in PROFILE.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))
