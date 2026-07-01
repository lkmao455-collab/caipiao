"""自定义策略插件示例.

将此文件放在 plugins/ 目录下，程序启动或点击“重新加载插件”时会自动加载。
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from caipiao.core.strategy import GenerationStrategy, StrategyMetadata
from caipiao.core.ticket import Ticket


class LuckyNumberStrategy(GenerationStrategy):
    """幸运号码策略：蓝球优先选择 6、8、16 等吉利数字."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="lucky_number",
            name="幸运号码",
            description="红球随机，蓝球优先选择 6、8、16 等吉利号码。",
            version="1.0.0",
            author="Plugin Author",
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "lucky_blues": {
                "type": "list_int",
                "label": "幸运蓝球",
                "default": [6, 8, 16],
                "min": 1,
                "max": 16,
            }
        }

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        lucky_blues = options.get("lucky_blues", [6, 8, 16]) or [6, 8, 16]
        if not lucky_blues:
            lucky_blues = list(range(1, 17))

        tickets: List[Ticket] = []
        for _ in range(count):
            reds = sorted(random.sample(range(1, 34), 6))
            blue = random.choice(lucky_blues)
            tickets.append(
                Ticket(
                    red_balls=reds,
                    blue_ball=blue,
                    strategy_name=self.metadata.name,
                )
            )
        return tickets


def register_strategies(engine):
    """可选：通过函数方式注册策略."""
    engine.register(LuckyNumberStrategy())
