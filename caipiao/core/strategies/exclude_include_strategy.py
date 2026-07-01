"""排除/必含策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Set

from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket


class ExcludeIncludeStrategy(GenerationStrategy):
    """支持排除特定号码、强制包含特定号码的生成策略."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="exclude_include",
            name="排除/必含",
            description="排除不想要的号码，或强制包含某些幸运号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "include_red": {
                "type": "list_int",
                "label": "必含红球（逗号分隔）",
                "default": [],
                "min": 1,
                "max": 33,
                "tooltip": "强制包含某些红球，其余号码随机补充。相当于在缩小的样本空间内抽样。",
            },
            "exclude_red": {
                "type": "list_int",
                "label": "排除红球（逗号分隔）",
                "default": [],
                "min": 1,
                "max": 33,
                "tooltip": "排除不想要的号码。注意：排除过多会导致可用号码不足。",
            },
            "exclude_blue": {
                "type": "list_int",
                "label": "排除蓝球（逗号分隔）",
                "default": [],
                "min": 1,
                "max": 16,
                "tooltip": "排除不想要的蓝球。",
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
                "tooltip": "固定随机种子可使每次生成的号码相同，便于重复实验。留空则完全随机。",
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        include = set(options.get("include_red", []))
        exclude = set(options.get("exclude_red", []))
        if include & exclude:
            raise ValueError("同一号码不能同时出现在必含和排除列表中")
        if len(include) > 6:
            raise ValueError("必含红球不能超过 6 个")
        available = set(range(1, 34)) - exclude
        if len(available) < 6:
            raise ValueError("排除后剩余红球不足 6 个")
        if not (set(options.get("include_red", [])) <= available):
            raise ValueError("必含红球不能出现在排除列表中")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        include_red: Set[int] = set(options.get("include_red", []))
        exclude_red: Set[int] = set(options.get("exclude_red", []))
        exclude_blue: Set[int] = set(options.get("exclude_blue", []))
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        available_reds = list(set(range(1, 34)) - exclude_red - include_red)
        available_blues = list(set(range(1, 17)) - exclude_blue)

        if not available_blues:
            raise ValueError("排除后没有可用蓝球")

        basis_parts = ["排除/必含策略："]
        if include_red:
            basis_parts.append(f"必含红球 {sorted(include_red)}；")
        else:
            basis_parts.append("无必含红球；")
        if exclude_red:
            basis_parts.append(f"排除红球 {sorted(exclude_red)}；")
        if exclude_blue:
            basis_parts.append(f"排除蓝球 {sorted(exclude_blue)}；")
        basis = " ".join(basis_parts) + "其余号码在可用范围内随机补充。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        need_pick = 6 - len(include_red)
        for _ in range(count):
            picked = sorted(rng.sample(available_reds, need_pick))
            reds = sorted(set(picked) | include_red)
            blue = rng.choice(available_blues)
            tickets.append(
                Ticket(
                    red_balls=reds,
                    blue_ball=blue,
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
