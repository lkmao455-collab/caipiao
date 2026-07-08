"""双色球完全随机策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....profile import SSQ
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket


class SSQRandomStrategy(GenerationStrategy):
    """完全随机生成投注单."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random",
            name="完全随机",
            description="从 33 个红球和 16 个蓝球中完全随机抽取。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
                "tooltip": "固定随机种子可使每次生成的号码相同，便于重复实验。留空则完全随机。",
            }
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        seed = options.get("seed")
        if seed is not None and not isinstance(seed, int):
            raise ValueError("随机种子必须是整数")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        basis = "完全随机策略：从 33 个红球和 16 个蓝球中等概率随机抽取。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            reds = sorted(rng.sample(range(1, 34), 6))
            blue = rng.randint(1, 16)
            tickets.append(
                Ticket(
                    profile=SSQ,
                    groups={"red": reds, "blue": [blue]},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
