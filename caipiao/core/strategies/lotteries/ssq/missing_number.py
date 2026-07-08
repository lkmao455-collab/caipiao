"""双色球遗漏号策略.

优先选择长时间未出现的号码，认为它们“快出了”。
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from .....data.analyzer import LotteryAnalyzer
from ....profile import SSQ
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options


class SSQMissingNumberStrategy(GenerationStrategy):
    """遗漏号策略.

    基于历史开奖数据，优先选择遗漏值较高的号码。
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="missing_number",
            name="遗漏号追踪",
            description="选择近期遗漏值较高的红球和蓝球，适合追冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {
                "type": "history",
                "label": "历史记录",
                "default": [],
                "tooltip": "用于计算遗漏值的历史开奖记录。",
            },
            "lookback": {
                "type": "int",
                "label": "统计期数",
                "default": 50,
                "min": 10,
                "max": 10000,
                "tooltip": "计算遗漏值的最近期数。遗漏值越大表示该号码越久未出现。",
            },
            "pool_size": {
                "type": "int",
                "label": "候选池大小",
                "default": 12,
                "min": 6,
                "max": 20,
                "tooltip": "从高遗漏号码中选取的候选池大小。池子越小，号码越“冷”。",
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
        records = records_from_options(options)
        if not records:
            raise ValueError("遗漏号策略需要历史开奖数据，请先更新数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = records_from_options(options)
        lookback = int(options.get("lookback", 50))
        pool_size = int(options.get("pool_size", 12))
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        analyzer = LotteryAnalyzer(records)

        # Red pool: top missing numbers
        missing_reds = analyzer.missing_reds(lookback)
        red_pool = [n for n, _ in missing_reds[:pool_size]]

        # Blue pool: top missing numbers
        missing_blues = analyzer.missing_blues(lookback)
        blue_pool = [n for n, _ in missing_blues[: min(8, pool_size // 2 + 2)]]

        basis = (
            f"遗漏号追踪策略：基于最近 {lookback} 期历史数据，"
            f"从高遗漏值红球候选池（前 {pool_size} 个）和蓝球候选池中随机抽取。"
            f"注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            reds = sorted(rng.sample(red_pool, 6))
            blue = rng.choice(blue_pool)
            tickets.append(
                Ticket(
                    profile=SSQ,
                    groups={"red": reds, "blue": [blue]},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
