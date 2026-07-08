"""排列3排除/必含策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.rng import make_rng
from ._base import PROFILE, _make_ticket


class PL3ExcludeIncludeStrategy(GenerationStrategy):
    """排除或强制包含某些号码."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="exclude_include_pl3",
            name="排除/必含",
            description="排除不想要的号码，或强制包含某些幸运号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        schema: Dict[str, Any] = {}
        for g in PROFILE.pick_groups:
            schema[f"include_{g.key}"] = {
                "type": "list_int",
                "label": f"必含 {g.name}",
                "default": [],
                "min": g.lo,
                "max": g.hi,
            }
            schema[f"exclude_{g.key}"] = {
                "type": "list_int",
                "label": f"排除 {g.name}",
                "default": [],
                "min": g.lo,
                "max": g.hi,
            }
        schema["seed"] = {
            "type": "int",
            "label": "随机种子（可选）",
            "default": None,
            "min": 0,
            "max": 999999999,
        }
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        for g in PROFILE.pick_groups:
            include = set(options.get(f"include_{g.key}", []))
            exclude = set(options.get(f"exclude_{g.key}", []))
            valid_range = set(g.values)
            if not (include <= valid_range):
                raise ValueError(f"必含 {g.name} 包含越界号码")
            if not (exclude <= valid_range):
                raise ValueError(f"排除 {g.name} 包含越界号码")
            if include & exclude:
                raise ValueError(f"{g.name} 中同一号码不能同时必含和排除")
            if len(include) > g.effective_pick_max:
                raise ValueError(f"必含 {g.name} 数量不能超过 {g.effective_pick_max}")
            available = valid_range - exclude
            if len(available) < g.effective_pick_min:
                raise ValueError(f"{g.name} 排除后剩余号码不足")
            if not (include <= available):
                raise ValueError(f"必含 {g.name} 不能出现在排除列表中")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        rng = make_rng(options)

        basis_parts = ["排除/必含策略："]
        for g in PROFILE.pick_groups:
            inc = set(options.get(f"include_{g.key}", []))
            exc = set(options.get(f"exclude_{g.key}", []))
            if inc:
                basis_parts.append(f"必含 {g.name} {sorted(inc)}；")
            if exc:
                basis_parts.append(f"排除 {g.name} {sorted(exc)}；")
        basis = " ".join(basis_parts) + "其余号码在可用范围内随机补充。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            for g in PROFILE.pick_groups:
                include = set(options.get(f"include_{g.key}", []))
                exclude = set(options.get(f"exclude_{g.key}", []))
                available = list(set(g.values) - exclude - include)
                if g.positional:
                    pos_chosen = []
                    pool = list(set(g.values) - exclude)
                    for _ in range(g.count):
                        pos_pool = list(include) if include and rng.random() < 0.5 else pool
                        if not pos_pool:
                            pos_pool = g.values[:]
                        pos_chosen.append(rng.choice(pos_pool))
                    groups[g.key] = pos_chosen
                else:
                    if g.variable_pick:
                        pick = rng.randint(g.effective_pick_min, g.effective_pick_max)
                        pick = max(pick, len(include))
                        pick = min(pick, g.effective_pick_max)
                    else:
                        pick = g.count
                    if len(include) >= pick:
                        groups[g.key] = sorted(include)[:pick]
                        continue
                    need = pick - len(include)
                    if len(available) < need:
                        raise ValueError(f"{g.name} 排除后可用号码不足 {need} 个")
                    chosen = sorted(set(rng.sample(available, need)) | include)
                    groups[g.key] = chosen
            tickets.append(_make_ticket(groups, strategy_name=self.metadata.name, basis=basis))
        return tickets
