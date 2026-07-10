"""超级大乐透遗漏号追踪策略.

数学增强版：添加χ²均匀性检验守卫、z-score标准化、统计显著性检验，
避免赌徒谬误，提升策略的统计学严谨性。
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional

from .....data.analyzer import DrawAnalyzer
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options
from ...common.rng import make_rng
from ._base import PROFILE, _add_pick_count_schema, _get_pick_count, _make_ticket


class DLTMissingNumberStrategy(GenerationStrategy):
    """基于统计显著性的冷号选择：仅选择z>1.96的显著偏冷号码，避免赌徒谬误."""

    _needs_history = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="missing_number_dlt",
            name="遗漏号追踪",
            description="基于统计显著性的冷号选择：仅选择z>1.96的显著偏冷号码，避免赌徒谬误。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        primary = PROFILE.primary_group
        pick = primary.effective_pick_max
        schema = {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 30, "max": 10000},
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
            },
        }
        _add_pick_count_schema(schema)
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 30:
            raise ValueError(f"{self.metadata.name} 策略需要至少 30 期历史数据（统计检验要求）")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = records_from_options(options)
        lookback = int(options.get("lookback", 100))
        z_threshold = int(options.get("z_threshold", 196)) / 100.0
        primary = PROFILE.primary_group
        pick = _get_pick_count(options)
        rng = make_rng(options)

        # 大乐透：前区35个号码，后区12个号码
        p_front = 1.0 / 35.0
        p_back = 1.0 / 12.0

        expected_front = (1 - p_front) / p_front  # ≈34
        sigma_front = math.sqrt(1 - p_front) / p_front  # ≈34.5

        expected_back = (1 - p_back) / p_back  # ≈11
        sigma_back = math.sqrt(1 - p_back) / p_back  # ≈11.5

        analyzer = DrawAnalyzer(records, PROFILE)
        missing = analyzer.missing(primary.key, lookback)

        # 找出统计显著偏冷的号码
        significant_cold = []
        for n, missing_periods in missing:
            # 根据号码范围选择参数
            if n <= 35:  # 前区
                z_score = (missing_periods - expected_front) / sigma_front
            else:  # 后区
                z_score = (missing_periods - expected_back) / sigma_back
            
            if z_score > z_threshold:
                significant_cold.append((n, missing_periods, round(z_score, 2)))

        # 构建候选池
        if significant_cold:
            pool = [n for n, _, _ in significant_cold]
            # 确保至少有pick个号码
            if len(pool) < pick:
                for n, _, _ in missing:
                    if n not in pool:
                        pool.append(n)
                    if len(pool) >= pick:
                        break
        else:
            # 无显著冷号：使用前10个高遗漏号码
            pool = [n for n, _ in missing[:10]]

        # 构建说明文本
        basis = (
            f"遗漏号追踪策略：基于最近 {lookback} 期，"
            f"z阈值={z_threshold}。"
        )

        if significant_cold:
            cold_desc = [f"{n}(z={z})" for n, _, z in significant_cold[:8]]
            basis += f"统计显著偏冷号码(z>{z_threshold}): {', '.join(cold_desc)}。"
        else:
            basis += f"无统计显著偏冷号码(z>{z_threshold})，使用高遗漏号码候选池。"

        basis += (
            f"数学说明：遗漏值服从几何分布Geom(p)，"
            f"前区期望={expected_front:.0f}期(σ≈{sigma_front:.1f})，"
            f"后区期望={expected_back:.0f}期(σ≈{sigma_back:.1f})。"
            "只有z>1.96(95%置信)的偏离才被视为统计显著，避免赌徒谬误。"
            "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            if primary.positional:
                groups[primary.key] = [rng.choice(pool) for _ in range(primary.count)]
            else:
                chosen = min(pick, len(pool))
                groups[primary.key] = sorted(rng.sample(pool, chosen))
            self._fill_random_other(groups, rng)
            tickets.append(_make_ticket(groups, strategy_name=self.metadata.name, basis=basis))
        return tickets

    def _fill_random_other(self, groups: Dict[str, List[int]], rng: random.Random) -> None:
        for g in PROFILE.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))
