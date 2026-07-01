"""奇偶均衡策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket


class OddEvenStrategy(GenerationStrategy):
    """尽量保持红球奇偶比均衡（默认 3:3，可配置）."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="odd_even",
            name="奇偶均衡",
            description="控制红球中奇数和偶数的比例，默认 3:3。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "odd_count": {
                "type": "int",
                "label": "奇数个数",
                "default": 3,
                "min": 0,
                "max": 6,
                "tooltip": "指定红球中奇数的个数（0~6），偶数个数自动为 6 减该值。默认 3 个奇数符合历史统计规律。",
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
        odd_count = options.get("odd_count", 3)
        if not isinstance(odd_count, int) or not (0 <= odd_count <= 6):
            raise ValueError("奇数个数必须是 0-6 的整数")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        odd_count = int(options.get("odd_count", 3))
        even_count = 6 - odd_count
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        odd_reds = [i for i in range(1, 34) if i % 2 == 1]
        even_reds = [i for i in range(1, 34) if i % 2 == 0]
        basis = f"奇偶均衡策略：红球中强制包含 {odd_count} 个奇数、{even_count} 个偶数，其余号码随机补充。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            if odd_count > len(odd_reds) or even_count > len(even_reds):
                raise ValueError("奇偶数量超出可选范围")
            reds = sorted(rng.sample(odd_reds, odd_count) + rng.sample(even_reds, even_count))
            blue = rng.randint(1, 16)
            tickets.append(
                Ticket(
                    red_balls=reds,
                    blue_ball=blue,
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
