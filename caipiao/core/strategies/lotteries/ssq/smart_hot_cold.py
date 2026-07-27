"""双色球智能冷热号策略（增强版）.

移植福彩3D的数学框架到双色球：
- 拉普拉斯平滑频率（热号信号）
- 几何分布 z-score 遗漏检验（冷号信号，避免赌徒谬误）
- χ² 均匀性检验守卫（判断冷热信号是否有统计学意义）
- z-score 标准化 + 温度控制 softmax（概率融合）
- Gumbel-max 无放回采样（保持分布形状的高效去重）
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....profile import SSQ
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options
from .stability import (
    RED_POOL,
    BLUE_POOL,
    chi_square_uniform_test,
    deterministic_seed,
    geometric_blue_missing_zscore,
    geometric_missing_zscore,
    raw_blue_missing_periods,
    raw_missing_periods,
    stable_blue_frequency,
    stable_blue_scores,
    stable_frequency,
    stable_scores,
    weighted_sample_reds,
)


class SSQSmartHotColdStrategy(GenerationStrategy):
    """双色球智能冷热号（增强版）.

    数学原理：
    1. 热号信号：拉普拉斯平滑后的出现频率概率
    2. 冷号信号：原始遗漏期数 → 几何分布 z-score
       在均匀假设(p=1/33)下 E[X]=32, σ≈5.63
       z > 1.96 才算 95% 置信的统计显著偏冷，避免赌徒谬误
    3. χ² 均匀性检验：判断红球/蓝球频率是否显著偏离均匀分布
       若均匀，冷热信号较弱（频率波动在噪声范围内）
    4. z-score 标准化 + 温度控制 softmax 融合热分和冷分
    5. Gumbel-max 无放回采样选取 6 个红球，保持概率分布形状
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
                "default": 200,
                "min": 1,
                "max": 10000,
                "tooltip": "用于统计冷热号的最近期数。期数过少容易受噪声影响，过多则反应迟缓。",
            },
            "temperature": {
                "type": "int",
                "label": "温度(x0.1)",
                "default": 10,
                "min": 1,
                "max": 50,
                "tooltip": "控制号码集中程度。10=标准平衡，1=高度集中（强烈偏向热/冷号），50=接近随机均匀分布。",
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
        if len(records) < 20:
            raise ValueError("智能冷热号策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = records_from_options(options)
        lookback = int(options.get("lookback", 200))
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        temperature = int(options.get("temperature", 10)) / 10.0
        seed = options.get("seed")
        rng = random.Random(deterministic_seed(options, records, lookback, self.metadata.id))

        # === 红球分析 ===

        # 热号信号: 拉普拉斯平滑后的频率概率
        red_freq = stable_frequency(records, lookback)

        # 冷号信号: 原始遗漏期数 → 几何分布 z-score
        red_raw_missing = raw_missing_periods(records, lookback)
        red_geo_z = geometric_missing_zscore(red_raw_missing)

        # χ² 均匀性检验
        red_counter = {n: 0 for n in RED_POOL}
        for r in records[-lookback:]:
            for n in r.groups.get("red", []):
                if n in red_counter:
                    red_counter[n] += 1
        red_counts = [red_counter[n] for n in RED_POOL]
        red_chi2, red_is_uniform = chi_square_uniform_test(red_counts)

        # 融合热分和冷分 → softmax 概率分布
        red_probs = stable_scores(
            red_freq, red_geo_z, hot_weight, cold_weight, temperature
        )

        # === 蓝球分析 ===

        blue_freq = stable_blue_frequency(records, lookback)
        blue_raw_missing = raw_blue_missing_periods(records, lookback)
        blue_geo_z = geometric_blue_missing_zscore(blue_raw_missing)

        blue_counter = {n: 0 for n in BLUE_POOL}
        for r in records[-lookback:]:
            for n in r.groups.get("blue", []):
                if n in blue_counter:
                    blue_counter[n] += 1
        blue_counts = [blue_counter[n] for n in BLUE_POOL]
        blue_chi2, blue_is_uniform = chi_square_uniform_test(blue_counts)

        blue_probs = stable_blue_scores(
            blue_freq, blue_geo_z, hot_weight, cold_weight, temperature
        )

        # === 构建说明文本 ===
        basis = (
            f"智能冷热号策略：lookback={lookback}，热权重={hot_weight}，"
            f"冷权重={cold_weight}，温度={temperature}。"
        )
        if red_is_uniform and blue_is_uniform:
            basis += (
                "χ²检验显示红球/蓝球接近均匀分布（频率波动在统计噪声范围内），"
                "冷热信号较弱。"
            )
        else:
            parts = []
            if not red_is_uniform:
                parts.append("红球")
            if not blue_is_uniform:
                parts.append("蓝球")
            basis += f"χ²检验显示{'/'.join(parts)}显著偏离均匀分布，冷热信号有效。"
        basis += "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        details: Dict[str, Any] = {
            "red_chi_square": round(red_chi2, 2),
            "red_is_uniform": red_is_uniform,
            "blue_chi_square": round(blue_chi2, 2),
            "blue_is_uniform": blue_is_uniform,
            "cold_signal": "geometric_zscore",
        }

        # === 生成号码 ===
        tickets: List[Ticket] = []
        for _ in range(count):
            reds = weighted_sample_reds(red_probs, 6, rng)
            blue = rng.choices(BLUE_POOL, weights=blue_probs, k=1)[0]
            tickets.append(
                Ticket(
                    profile=SSQ,
                    groups={"red": reds, "blue": [blue]},
                    strategy_name=self.metadata.name,
                    basis=basis,
                    details=details.copy(),
                )
            )
        return tickets
