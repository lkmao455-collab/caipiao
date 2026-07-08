"""福彩3D历史均衡策略."""

from __future__ import annotations

import itertools
import random
from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import FC3D_PROFILE, _records_from_options
from .stability import deterministic_seed
from .utils import (
    DIGIT_POOL,
    fc3d_bet_type,
    overall_high_low_ratio,
    overall_odd_even_ratio,
    positional_weights,
    road_012_statistics,
    shape_ratio,
    span_statistics,
    sum_statistics,
    sum_tail_statistics,
)


class FC3DBalancedStrategy(GenerationStrategy):
    """3D历史均衡：按位统计，保留顺序，支持枚举择优。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="balanced_3d",
            name="历史均衡",
            description="根据历史数据的按位频率、奇偶、大小、跨度、和尾、012路和形态生成均衡号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "max_attempts": {"type": "int", "label": "最大尝试次数", "default": 1000, "min": 100, "max": 10000},
            "use_enumeration": {
                "type": "bool",
                "label": "使用枚举择优",
                "default": True,
                "tooltip": "3D仅1000种组合，枚举可找到评分最高且确定性的结果。",
            },
            "dedup": {
                "type": "bool",
                "label": "号码去重",
                "default": True,
                "tooltip": "开启后去除号码集合重复，例如123和132视为相同号码。",
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        if len(options.get("history", [])) < 20:
            raise ValueError("历史均衡策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        max_attempts = int(options.get("max_attempts", 1000))
        use_enumeration = bool(options.get("use_enumeration", True))
        dedup = bool(options.get("dedup", True))

        det_seed = deterministic_seed(options, records, lookback, self.metadata.id)
        rng = random.Random(det_seed)

        odd_ratio, _ = overall_odd_even_ratio(records, lookback)
        high_ratio, _ = overall_high_low_ratio(records, lookback)
        sum_stats = sum_statistics(records, lookback)
        avg_sum = sum_stats["avg"]
        tail_avg = sum_tail_statistics(records, lookback)["avg"]
        span_avg = span_statistics(records, lookback)["avg"]
        shape = shape_ratio(records, lookback)
        road = road_012_statistics(records, lookback)
        target_odd = round(3 * odd_ratio)
        target_high = round(3 * high_ratio)
        weights = positional_weights(records, lookback, smoothing=1.0)

        basis = (
            f"历史均衡策略：基于最近 {lookback} 期，"
            f"使3D号码的按位频率、奇偶、大小、和值、跨度、和尾、012路和形态接近历史平均。"
        )
        user_seed = options.get("seed")
        if user_seed is not None:
            basis += f" 随机种子：{user_seed}。"

        max_weight = lookback * len(DIGIT_POOL)

        def score(candidate: List[int]) -> float:
            odd_count = sum(1 for n in candidate if n % 2 == 1)
            high_count = sum(1 for n in candidate if n >= 5)
            total = sum(candidate)
            tail = total % 10
            span = max(candidate) - min(candidate)
            shape_type = fc3d_bet_type(candidate)
            shape_score = 0.0
            if shape_type == "豹子号":
                shape_score = 1 - shape["leopard"]
            elif shape_type == "组选3":
                shape_score = 1 - shape["group3"]
            else:
                shape_score = 1 - shape["group6"]

            weight_score = -sum(weights[pos][candidate[pos]] for pos in range(3)) / (max_weight or 1)
            road_score = sum(
                1.0 - road[pos][candidate[pos] % 3] for pos in range(3)
            )

            return (
                abs(odd_count - target_odd)
                + abs(high_count - target_high)
                + abs(total - avg_sum) / 10.0
                + abs(tail - tail_avg) / 5.0
                + abs(span - span_avg) / 5.0
                + shape_score
                + weight_score
                + road_score
            )

        def sample_one() -> List[int]:
            return [rng.choices(range(10), weights=weights[pos], k=1)[0] for pos in range(3)]

        seen: set = set()
        tickets: List[Ticket] = []
        for _ in range(count):
            best_candidate: Optional[List[int]] = None
            best_score = float("inf")

            if use_enumeration:
                candidates = [list(c) for c in itertools.product(range(10), repeat=3)]
                if user_seed is not None:
                    rng.shuffle(candidates)
                for candidate in candidates:
                    key = tuple(sorted(candidate))
                    if dedup and key in seen:
                        continue
                    s = score(candidate)
                    if s < best_score:
                        best_score = s
                        best_candidate = candidate
            else:
                for _ in range(max_attempts):
                    candidate = sample_one()
                    key = tuple(sorted(candidate))
                    if dedup and key in seen:
                        continue
                    s = score(candidate)
                    if s < best_score:
                        best_score = s
                        best_candidate = candidate
                    if best_score <= 0.5:
                        break

            if best_candidate is None:
                best_candidate = sample_one()

            seen.add(tuple(sorted(best_candidate)))
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE,
                    groups={"pos": best_candidate},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
