"""七乐彩完全随机策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.rng import make_rng
from ._base import PROFILE, _add_pick_count_schema, _get_pick_count, _make_ticket


class QLCRandomStrategy(GenerationStrategy):
    """完全随机生成投注单."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random_qlc",
            name="完全随机",
            description="在七乐彩 1-30 号池中完全随机抽取 7 个基本号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        schema = {
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            }
        }
        _add_pick_count_schema(schema, label=f"{PROFILE.primary_group.name}投注个数")
        return schema

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = make_rng(options)
        pick = _get_pick_count(options)
        primary = PROFILE.primary_group
        basis = f"完全随机策略：在 {PROFILE.name} 号池中等概率随机抽取 {pick} 个{primary.name}。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            for g in PROFILE.pick_groups:
                current_pick = pick if g.is_primary else g.count
                if g.variable_pick and not g.is_primary:
                    current_pick = rng.randint(g.effective_pick_min, g.effective_pick_max)
                if g.positional:
                    groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
                elif g.allow_repeat:
                    groups[g.key] = sorted(rng.choices(g.values, k=current_pick))
                else:
                    groups[g.key] = sorted(rng.sample(g.values, current_pick))
            tickets.append(_make_ticket(groups, strategy_name=self.metadata.name, basis=basis))
        return tickets
