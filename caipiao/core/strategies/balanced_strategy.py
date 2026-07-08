"""均衡策略.

基于历史统计，生成奇偶、大小、和值更接近历史平均水平的号码。
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ...data.analyzer import LotteryAnalyzer
from ...data.models import DrawRecord
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket


class BalancedStrategy(GenerationStrategy):
    """历史均衡策略.

    控制红球的奇偶比、大小比和和值范围，使其接近历史统计规律。
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="balanced",
            name="历史均衡",
            description="根据历史数据的奇偶比、大小比和和值分布生成均衡号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {
                "type": "history",
                "label": "历史记录",
                "default": [],
                "tooltip": "用于统计历史分布规律的开奖记录。",
            },
            "lookback": {
                "type": "int",
                "label": "统计期数",
                "default": 100,
                "min": 10,
                "max": 10000,
                "tooltip": "统计历史奇偶比、大小比、和值的最近期数。",
            },
            "max_attempts": {
                "type": "int",
                "label": "最大尝试次数",
                "default": 1000,
                "min": 100,
                "max": 10000,
                "tooltip": "为找到均衡组合最多尝试的随机次数。次数越多，结果越接近历史平均。",
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
        history = options.get("history", [])
        if not history:
            raise ValueError("历史均衡策略需要历史开奖数据，请先更新数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        history = options.get("history", [])
        lookback = int(options.get("lookback", 100))
        max_attempts = int(options.get("max_attempts", 1000))
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        records = [
            r if isinstance(r, DrawRecord) else DrawRecord(
                issue="",
                draw_date=r.generated_at,
                profile=r.profile.key,
                groups=r.groups,
            )
            for r in history
        ]
        analyzer = LotteryAnalyzer(records)

        odd_ratio, even_ratio = analyzer.odd_even_ratio(lookback)
        high_ratio, low_ratio = analyzer.high_low_ratio(lookback)
        sum_stats = analyzer.sum_statistics(lookback)
        avg_sum = sum_stats["avg"]
        std_sum = (sum_stats["max"] - sum_stats["min"]) / 6  # rough std
        sum_min = max(avg_sum - 1.5 * std_sum, sum_stats["min"])
        sum_max = min(avg_sum + 1.5 * std_sum, sum_stats["max"])

        target_odd = round(6 * odd_ratio)
        target_high = round(6 * high_ratio)

        # Use weighted selection from hot numbers
        freq = analyzer.red_frequency(lookback)
        max_freq = max(freq.values()) if freq else 1
        weights = [max(0.1, freq.get(n, 0) / max_freq + 0.2) for n in range(1, 34)]
        reds = list(range(1, 34))

        blue_freq = analyzer.blue_frequency(lookback)
        max_blue_freq = max(blue_freq.values()) if blue_freq else 1
        blue_weights = [max(0.1, blue_freq.get(n, 0) / max_blue_freq + 0.2) for n in range(1, 17)]
        blues = list(range(1, 17))

        basis = (
            f"历史均衡策略：基于最近 {lookback} 期历史数据，"
            f"使奇偶比、大小比、和值接近历史平均水平（目标奇数 {target_odd} 个、大号约 {target_high} 个）。"
            f"注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            best_candidate: Optional[Ticket] = None
            best_score = float("inf")

            for _ in range(max_attempts):
                candidate = sorted(rng.choices(reds, weights=weights, k=6))
                if len(set(candidate)) < 6:
                    continue
                odd_count = sum(1 for n in candidate if n % 2 == 1)
                high_count = sum(1 for n in candidate if n >= 17)
                total = sum(candidate)

                # Score: lower is better (closer to historical average)
                score = (
                    abs(odd_count - target_odd)
                    + abs(high_count - target_high)
                    + abs(total - avg_sum) / 10
                )

                if score < best_score:
                    best_score = score
                    best_candidate = Ticket(
                        red_balls=candidate,
                        blue_ball=rng.choices(blues, weights=blue_weights, k=1)[0],
                        strategy_name=self.metadata.name,
                        basis=basis,
                    )

                if best_score <= 0.5:
                    break

            if best_candidate is None:
                # Fallback: ensure at least one valid ticket
                candidate = sorted(rng.sample(reds, 6))
                best_candidate = Ticket(
                    red_balls=candidate,
                    blue_ball=rng.choices(blues, weights=blue_weights, k=1)[0],
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            tickets.append(best_candidate)

        return tickets
