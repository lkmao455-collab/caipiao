"""智能冷热号策略.

综合考虑号码出现频率和遗漏值，给每个号码打分后加权随机选取。
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ...data.analyzer import LotteryAnalyzer
from ...data.models import DrawRecord
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket


class SmartHotColdStrategy(GenerationStrategy):
    """智能冷热分析策略.

    基于历史开奖数据，综合热号频率和冷号遗漏值生成号码。
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="smart_hot_cold",
            name="智能冷热号",
            description="结合历史数据中的热号频率与冷号遗漏值加权生成号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {
                "type": "history",
                "label": "历史记录",
                "default": [],
                "tooltip": "用于训练/分析的历史开奖记录。",
            },
            "hot_weight": {
                "type": "int",
                "label": "热号权重",
                "default": 60,
                "min": 0,
                "max": 100,
                "tooltip": "热号（高频出现）在评分中的权重。权重越大，越倾向选择近期常出的号码。",
            },
            "cold_weight": {
                "type": "int",
                "label": "冷号权重",
                "default": 40,
                "min": 0,
                "max": 100,
                "tooltip": "冷号（高遗漏值）在评分中的权重。权重越大，越倾向选择长期未出的号码。",
            },
            "lookback": {
                "type": "int",
                "label": "统计期数",
                "default": 100,
                "min": 10,
                "max": 10000,
                "tooltip": "用于统计冷热号的最近期数。期数过少容易受噪声影响，过多则反应迟缓。",
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
            raise ValueError("智能冷热号策略需要历史开奖数据，请先更新数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        history = options.get("history", [])
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        lookback = int(options.get("lookback", 100))
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

        # Build red scores
        red_scores: Dict[int, float] = {n: 0.0 for n in range(1, 34)}

        # Hot score based on frequency
        freq = analyzer.red_frequency(lookback)
        max_freq = max(freq.values()) if freq else 1
        for n, f in freq.items():
            red_scores[n] += hot_weight * (f / max_freq)

        # Cold score based on missing value (higher missing = higher score)
        missing = dict(analyzer.missing_reds(lookback))
        max_missing = max(missing.values()) if missing else 1
        for n, m in missing.items():
            red_scores[n] += cold_weight * (m / max_missing)

        # Normalize to weights
        min_score = min(red_scores.values())
        weights = [max(0.1, red_scores[n] - min_score + 1.0) for n in range(1, 34)]

        # Build blue scores similarly
        blue_scores: Dict[int, float] = {n: 0.0 for n in range(1, 17)}
        blue_freq = analyzer.blue_frequency(lookback)
        max_blue_freq = max(blue_freq.values()) if blue_freq else 1
        for n, f in blue_freq.items():
            blue_scores[n] += hot_weight * (f / max_blue_freq)

        blue_missing = dict(analyzer.missing_blues(lookback))
        max_blue_missing = max(blue_missing.values()) if blue_missing else 1
        for n, m in blue_missing.items():
            blue_scores[n] += cold_weight * (m / max_blue_missing)

        min_blue_score = min(blue_scores.values())
        blue_weights = [max(0.1, blue_scores[n] - min_blue_score + 1.0) for n in range(1, 17)]

        basis = (
            f"智能冷热号策略：综合最近 {lookback} 期热号频率（权重 {hot_weight}）"
            f"与冷号遗漏值（权重 {cold_weight}）加权评分后随机抽取。"
            f"注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        reds = list(range(1, 34))
        blues = list(range(1, 17))
        for _ in range(count):
            selected = sorted(rng.choices(reds, weights=weights, k=6))
            # Ensure no duplicates; if any, re-sample
            while len(set(selected)) < 6:
                selected = sorted(rng.choices(reds, weights=weights, k=6))
            blue = rng.choices(blues, weights=blue_weights, k=1)[0]
            tickets.append(
                Ticket(
                    red_balls=selected,
                    blue_ball=blue,
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
