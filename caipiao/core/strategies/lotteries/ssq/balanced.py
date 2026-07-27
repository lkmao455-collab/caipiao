"""双色球均衡策略.

基于历史统计，生成奇偶、大小、和值更接近历史平均水平的号码。
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Any, Dict, List, Optional, Tuple

from .....data.analyzer import LotteryAnalyzer
from ....profile import SSQ
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options


def _weighted_sample_without_replacement(
    rng: random.Random, values: List[int], weights: List[float], k: int
) -> List[int]:
    """无放回加权采样（Gumbel-max trick）。

    等价于从概率分布中无放回采样 k 个号码，保持概率分布形状。
    """
    log_weights = []
    for w in weights:
        if w > 0:
            log_weights.append(-math.log(rng.random()) / w)
        else:
            log_weights.append(float("inf"))
    indexed = list(zip(values, log_weights))
    indexed.sort(key=lambda x: x[1], reverse=True)
    return sorted(v for v, _ in indexed[:k])


class SSQBalancedStrategy(GenerationStrategy):
    """历史均衡策略.

    控制红球的奇偶比、大小比、和值范围、连号模式和三区分布，使其接近历史统计规律。
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
                "default": 200,
                "min": 1,
                "max": 10000,
                "tooltip": "统计历史奇偶比、大小比、和值、连号、区间分布的最近期数。",
            },
            "max_attempts": {
                "type": "int",
                "label": "最大尝试次数",
                "default": 1000,
                "min": 100,
                "max": 10000,
                "tooltip": "为找到均衡组合最多尝试的随机次数。次数越多，结果越接近历史平均。",
            },
            "consecutive_weight": {
                "type": "int",
                "label": "连号权重",
                "default": 1,
                "min": 0,
                "max": 5,
                "tooltip": "连号模式在评分中的权重。0=忽略连号约束，越大越倾向匹配历史连号频率。",
            },
            "zone_weight": {
                "type": "int",
                "label": "区间分布权重",
                "default": 1,
                "min": 0,
                "max": 5,
                "tooltip": "三区分布在评分中的权重。0=忽略区间约束，越大越倾向匹配历史区间比例。",
            },
            "blue_use_missing": {
                "type": "bool",
                "label": "蓝球使用遗漏值加权",
                "default": True,
                "tooltip": "结合蓝球频率和遗漏值z-score进行加权选择，而非仅用频率。",
            },
            "blue_odd_even": {
                "type": "int",
                "label": "蓝球奇偶控制 (0=不控制)",
                "default": 0,
                "min": 0,
                "max": 1,
                "tooltip": "0=不控制，1=强制奇数，2=强制偶数。留空则使用历史比例。",
            },
            "blue_size": {
                "type": "int",
                "label": "蓝球大小控制 (0=不控制)",
                "default": 0,
                "min": 0,
                "max": 1,
                "tooltip": "0=不控制，1=强制小号(1-8)，2=强制大号(9-16)。留空则使用历史比例。",
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
            raise ValueError("历史均衡策略需要历史开奖数据，请先更新数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = records_from_options(options)
        lookback = int(options.get("lookback", 200))
        max_attempts = int(options.get("max_attempts", 1000))
        consecutive_weight = int(options.get("consecutive_weight", 1))
        zone_weight = int(options.get("zone_weight", 1))
        blue_use_missing = bool(options.get("blue_use_missing", True))
        blue_odd_even = int(options.get("blue_odd_even", 0))
        blue_size = int(options.get("blue_size", 0))
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        analyzer = LotteryAnalyzer(records)

        odd_ratio, even_ratio = analyzer.odd_even_ratio(lookback)
        high_ratio, low_ratio = analyzer.high_low_ratio(lookback)
        sum_stats = analyzer.sum_statistics(lookback)
        avg_sum = sum_stats["avg"]
        # 计算真正标准差而非极差/6
        sliced = analyzer.records[-lookback:] if lookback and lookback < len(analyzer.records) else analyzer.records
        all_sums = [sum(r.groups.get("red", [])) for r in sliced]
        std_sum = statistics.stdev(all_sums) if len(all_sums) > 1 else 10.0
        sum_min = max(avg_sum - 1.5 * std_sum, sum_stats["min"])
        sum_max = min(avg_sum + 1.5 * std_sum, sum_stats["max"])

        target_odd = round(6 * odd_ratio)
        target_high = round(6 * high_ratio)

        # 连号统计：历史平均连号对数
        consec_dist = analyzer.consecutive_count_distribution(lookback)
        target_consecutive = max(consec_dist.items(), key=lambda x: x[1])[0] if consec_dist else 1

        # 三区分布统计
        zone_dist = analyzer.zone_distribution(lookback)
        target_zone1 = round(6 * zone_dist["zone1"])
        target_zone2 = round(6 * zone_dist["zone2"])
        target_zone3 = round(6 * zone_dist["zone3"])

        # Use weighted selection from hot numbers
        freq = analyzer.red_frequency(lookback)
        max_freq = max(freq.values()) if freq else 1
        weights = [max(0.1, freq.get(n, 0) / max_freq + 0.2) for n in range(1, 34)]
        reds = list(range(1, 34))

        blue_freq = analyzer.blue_frequency(lookback)
        max_blue_freq = max(blue_freq.values()) if blue_freq else 1

        # 蓝球候选池构建：结合频率和遗漏值
        if blue_use_missing:
            missing_blues = analyzer.missing_blues(lookback)
            # 几何分布z-score: p=1/16, E[X]=15, sigma≈3.84
            p_blue = 1.0 / 16.0
            expected_blue = (1 - p_blue) / p_blue
            sigma_blue = math.sqrt(1 - p_blue) / p_blue
            blue_scores = {}
            for n in range(1, 17):
                freq_score = blue_freq.get(n, 0) / max_blue_freq if max_blue_freq else 0
                miss_periods = next((m for num, m in missing_blues if num == n), 0)
                z_score = max(0, (miss_periods - expected_blue) / sigma_blue)
                # 频率分 + 遗漏z-score分（遗漏越高越倾向被选）
                blue_scores[n] = freq_score + 0.3 * z_score
            max_blue_score = max(blue_scores.values()) if blue_scores else 1
            blue_weights = [max(0.1, blue_scores.get(n, 0) / max_blue_score + 0.2) for n in range(1, 17)]
        else:
            blue_weights = [max(0.1, blue_freq.get(n, 0) / max_blue_freq + 0.2) for n in range(1, 17)]
        blues = list(range(1, 17))

        # 蓝球奇偶/大小控制
        if blue_odd_even == 1:
            blues = [n for n in blues if n % 2 == 1]
            blue_weights = [blue_weights[n - 1] for n in blues]
        elif blue_odd_even == 2:
            blues = [n for n in blues if n % 2 == 0]
            blue_weights = [blue_weights[n - 1] for n in blues]
        if blue_size == 1:
            blues = [n for n in blues if n <= 8]
            blue_weights = [blue_weights[blues.index(n)] for n in blues]
        elif blue_size == 2:
            blues = [n for n in blues if n >= 9]
            blue_weights = [blue_weights[blues.index(n)] for n in blues]

        basis = (
            f"历史均衡策略：基于最近 {lookback} 期历史数据，"
            f"使奇偶比、大小比、和值、连号、区间分布接近历史平均水平"
            f"（目标奇数 {target_odd} 个、大号约 {target_high} 个、连号 {target_consecutive} 对、"
            f"三区分布 {target_zone1}:{target_zone2}:{target_zone3}）。"
        )
        if blue_use_missing:
            basis += "蓝球结合频率与遗漏值z-score加权。"
        basis += "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            best_candidate: Optional[Ticket] = None
            best_score = float("inf")

            for _ in range(max_attempts):
                candidate = _weighted_sample_without_replacement(rng, reds, weights, 6)
                if len(set(candidate)) < 6:
                    continue
                odd_count = sum(1 for n in candidate if n % 2 == 1)
                high_count = sum(1 for n in candidate if n >= 17)
                total = sum(candidate)

                # 连号对数
                consec = sum(1 for i in range(len(candidate) - 1) if candidate[i] + 1 == candidate[i + 1])

                # 三区分布
                z1 = sum(1 for n in candidate if 1 <= n <= 11)
                z2 = sum(1 for n in candidate if 12 <= n <= 22)
                z3 = sum(1 for n in candidate if 23 <= n <= 33)

                # Score: lower is better (closer to historical average)
                score = (
                    abs(odd_count - target_odd)
                    + abs(high_count - target_high)
                    + abs(total - avg_sum) / 10
                    + consecutive_weight * abs(consec - target_consecutive)
                    + zone_weight * abs(z1 - target_zone1)
                    + zone_weight * abs(z2 - target_zone2)
                    + zone_weight * abs(z3 - target_zone3)
                )

                if score < best_score:
                    best_score = score
                    blue_num = _weighted_sample_without_replacement(rng, blues, blue_weights, 1)[0]
                    best_candidate = Ticket(
                        profile=SSQ,
                        groups={"red": candidate, "blue": [blue_num]},
                        strategy_name=self.metadata.name,
                        basis=basis,
                    )

                if best_score <= 0.5:
                    break

            if best_candidate is None:
                # Fallback: ensure at least one valid ticket
                candidate = sorted(rng.sample(reds, 6))
                blue_num = _weighted_sample_without_replacement(rng, blues, blue_weights, 1)[0]
                best_candidate = Ticket(
                    profile=SSQ,
                    groups={"red": candidate, "blue": [blue_num]},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            tickets.append(best_candidate)

        return tickets
