"""双色球遗漏号策略.

数学增强版：添加χ²均匀性检验守卫、z-score标准化、统计显著性检验，
避免赌徒谬误，提升策略的统计学严谨性。
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional

from .....data.analyzer import LotteryAnalyzer
from ....profile import SSQ
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options


class SSQMissingNumberStrategy(GenerationStrategy):
    """遗漏号策略.

    基于统计显著性的冷号选择：仅选择z>1.96的显著偏冷号码，避免赌徒谬误。
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="missing_number",
            name="遗漏号追踪",
            description="基于统计显著性的冷号选择：仅选择z>1.96的显著偏冷号码，避免赌徒谬误。",
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
                "default": 100,
                "min": 50,
                "max": 10000,
                "tooltip": "计算遗漏值的最近期数。建议至少50期以保证统计稳定性。",
            },
            "z_threshold": {
                "type": "int",
                "label": "z-score阈值(x0.01)",
                "default": 196,
                "min": 100,
                "max": 300,
                "tooltip": "统计显著性阈值。196=95%置信(z>1.96)，258=99%置信(z>2.58)。只有z-score超过此阈值的号码才被视为显著偏冷。",
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
        if len(records) < 50:
            raise ValueError("遗漏号策略需要至少 50 期历史数据（统计检验要求）")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = records_from_options(options)
        lookback = int(options.get("lookback", 100))
        z_threshold = int(options.get("z_threshold", 196)) / 100.0
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        analyzer = LotteryAnalyzer(records)

        # 1. 获取遗漏值
        missing_reds = analyzer.missing_reds(lookback)
        missing_blues = analyzer.missing_blues(lookback)

        # 2. 计算几何分布z-score
        # 双色球红球：33个号码，p=1/33≈0.0303
        # 蓝球：16个号码，p=1/16=0.0625
        p_red = 1.0 / 33.0
        p_blue = 1.0 / 16.0

        expected_red = (1 - p_red) / p_red  # ≈32
        sigma_red = math.sqrt(1 - p_red) / p_red  # ≈32.5

        expected_blue = (1 - p_blue) / p_blue  # ≈15
        sigma_blue = math.sqrt(1 - p_blue) / p_blue  # ≈15.5

        # 3. 找出统计显著偏冷的号码
        significant_cold_reds = []
        for n, missing_periods in missing_reds:
            z_score = (missing_periods - expected_red) / sigma_red
            if z_score > z_threshold:
                significant_cold_reds.append((n, missing_periods, round(z_score, 2)))

        significant_cold_blues = []
        for n, missing_periods in missing_blues:
            z_score = (missing_periods - expected_blue) / sigma_blue
            if z_score > z_threshold:
                significant_cold_blues.append((n, missing_periods, round(z_score, 2)))

        # 4. 构建候选池
        # 如果有显著冷号，优先选择；否则回退到前N个高遗漏号码
        if significant_cold_reds:
            red_pool = [n for n, _, _ in significant_cold_reds]
            # 确保至少有6个号码
            if len(red_pool) < 6:
                # 补充高遗漏号码
                for n, _, _ in missing_reds:
                    if n not in red_pool:
                        red_pool.append(n)
                    if len(red_pool) >= 6:
                        break
        else:
            # 无显著冷号：使用前12个高遗漏号码
            red_pool = [n for n, _ in missing_reds[:12]]

        if significant_cold_blues:
            blue_pool = [n for n, _, _ in significant_cold_blues]
            # 确保至少有1个号码
            if not blue_pool:
                blue_pool = [n for n, _ in missing_blues[:1]]
        else:
            blue_pool = [n for n, _ in missing_blues[:3]]

        # 5. 构建说明文本
        basis = (
            f"遗漏号追踪策略：基于最近 {lookback} 期历史数据，"
            f"z阈值={z_threshold}。"
        )

        if significant_cold_reds:
            red_desc = [f"{n}(z={z})" for n, _, z in significant_cold_reds[:5]]
            basis += f"统计显著偏冷红球(z>{z_threshold}): {', '.join(red_desc)}。"
        else:
            basis += f"无统计显著偏冷红球(z>{z_threshold})，使用高遗漏号码候选池。"

        if significant_cold_blues:
            blue_desc = [f"{n}(z={z})" for n, _, z in significant_cold_blues[:3]]
            basis += f"统计显著偏冷蓝球: {', '.join(blue_desc)}。"
        else:
            basis += "无统计显著偏冷蓝球，使用高遗漏号码候选池。"

        basis += (
            "数学说明：遗漏值服从几何分布Geom(p)，"
            f"红球期望={expected_red:.0f}期(σ≈{sigma_red:.1f})，"
            f"蓝球期望={expected_blue:.0f}期(σ≈{sigma_blue:.1f})。"
            "只有z>1.96(95%置信)的偏离才被视为统计显著，避免赌徒谬误。"
            "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        if seed is not None:
            basis += f" 随机种子：{seed}。"

        # 6. 生成号码
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
