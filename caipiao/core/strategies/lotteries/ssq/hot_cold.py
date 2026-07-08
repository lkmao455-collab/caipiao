"""双色球冷热号策略."""

from __future__ import annotations

import random
from collections import Counter
from typing import Any, Dict, List, Optional

from ....profile import SSQ
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options


class SSQHotColdStrategy(GenerationStrategy):
    """根据历史开奖记录统计冷热号，优先选择热号或冷号."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="hot_cold",
            name="冷热号分析",
            description="基于历史记录统计出现频率，优先选择热号或冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "mode": {
                "type": "choice",
                "label": "模式",
                "choices": ["hot", "cold", "mixed"],
                "default": "mixed",
                "tooltip": "hot=优先选择近期热号；cold=优先选择近期冷号；mixed=热号冷号混合。基于频率统计，不保证未来走势。",
            },
            "history": {
                "type": "history",
                "label": "历史记录",
                "default": [],
                "tooltip": "用于统计冷热号的历史开奖记录。数据越多，频率估计越稳定（大数定律）。",
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
        mode = options.get("mode", "mixed")
        if mode not in ("hot", "cold", "mixed"):
            raise ValueError("mode 必须是 hot、cold 或 mixed")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        mode = options.get("mode", "mixed")
        records = records_from_options(options)
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        red_counter: Counter = Counter()
        for record in records:
            red_counter.update(record.groups.get("red", []))

        all_reds = list(range(1, 34))
        if not red_counter:
            ranked_reds = all_reds[:]
            rng.shuffle(ranked_reds)
        else:
            ranked_reds = sorted(all_reds, key=lambda n: red_counter.get(n, 0), reverse=True)

        if mode == "hot":
            pool = ranked_reds[:16]
            mode_text = "优先选择近期热号"
        elif mode == "cold":
            pool = ranked_reds[-16:]
            mode_text = "优先选择近期冷号"
        else:
            pool = ranked_reds[:8] + ranked_reds[-8:]
            mode_text = "热号与冷号混合"

        basis = f"冷热号分析策略：{mode_text}，基于历史记录统计频率后选取候选池。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            reds = sorted(rng.sample(pool, 6))
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
