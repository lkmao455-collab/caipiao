"""福彩3D遗漏号追踪策略.

数学增强版：添加χ²均匀性检验守卫、z-score标准化、统计显著性检验，
避免赌徒谬误，提升策略的统计学严谨性。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import (
    FC3D_PROFILE,
    _make_rng,
    _records_from_options,
    _weighted_sample_without_replacement,
)
from .stability import (
    chi_square_uniform_test,
    geometric_missing_zscore,
    raw_missing_periods,
    sample_weighted,
    softmax_scores,
)
from .utils import positional_frequency, DIGIT_POOL


class FC3DMissingNumberStrategy(GenerationStrategy):
    """3D遗漏号追踪：基于统计显著性的冷号选择策略.

    改进点：
    1. 添加χ²均匀性检验守卫：数据接近均匀时退化为随机
    2. 使用几何分布z-score替代归一化遗漏值：避免赌徒谬误
    3. 添加统计显著性检验：z>1.96才认为偏冷
    4. 改进softmax输入：使用z-score作为logits
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="missing_number_3d",
            name="遗漏号追踪",
            description="基于统计显著性的冷号选择：仅选择z>1.96的显著偏冷号码，避免赌徒谬误。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
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
            "temperature": {
                "type": "int",
                "label": "温度(x0.1)",
                "default": 5,
                "min": 1,
                "max": 20,
                "tooltip": "控制号码集中程度。5=较集中，1=高度集中，20=接近随机。",
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
        if len(options.get("history", [])) < 30:
            raise ValueError("遗漏号追踪策略需要至少 30 期历史数据（统计检验要求）")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        z_threshold = int(options.get("z_threshold", 196)) / 100.0
        temperature = int(options.get("temperature", 5)) / 10.0
        dedup = bool(options.get("dedup", True))
        rng = _make_rng(options, records, lookback, self.metadata.id)

        # 1. χ²均匀性检验守卫
        pos_freq_counts = positional_frequency(records, lookback)
        chi2_values: List[float] = []
        uniform_flags: List[bool] = []
        for pos in range(3):
            counts = [pos_freq_counts[pos].get(d, 0) for d in range(10)]
            chi2, is_uniform = chi_square_uniform_test(counts)
            chi2_values.append(round(chi2, 2))
            uniform_flags.append(is_uniform)

        # 2. 原始遗漏期数 → 几何分布 z-score
        raw_missing = raw_missing_periods(records, lookback)
        geo_z = geometric_missing_zscore(raw_missing)

        # 3. 按位计算概率
        pos_probs: List[List[float]] = []
        significant_cold: List[List[int]] = []  # 统计显著偏冷的号码

        for pos in range(3):
            # 找出z-score超过阈值的显著偏冷号码
            # 只有当χ²检验显示数据不均匀时，才认为有显著冷号
            # 这样可以减少假阳性率
            if uniform_flags[pos]:
                # 数据均匀：无显著冷号
                cold_digits = []
            else:
                # 数据不均匀：找出z-score超过阈值的显著偏冷号码
                cold_digits = [
                    d for d in DIGIT_POOL
                    if geo_z[pos][d] > z_threshold
                ]
            significant_cold.append(cold_digits)

            if not cold_digits:
                # 无显著冷号：退化为均匀分布
                probs = [1.0 / 10.0] * 10
            else:
                # 有显著冷号：基于z-score加权
                # 使用z-score作为softmax logits（无界实数）
                logits = [geo_z[pos][d] for d in DIGIT_POOL]
                probs = softmax_scores(logits, temperature)
            pos_probs.append(probs)

        # 4. 构建说明文本
        all_uniform = all(uniform_flags)
        total_significant = sum(len(cold) for cold in significant_cold)

        basis = (
            f"遗漏号追踪策略：lookback={lookback}，z阈值={z_threshold}，"
            f"温度={temperature}。"
        )

        if all_uniform:
            basis += (
                "χ²检验显示各位置接近均匀分布（频率波动在统计噪声范围内），"
                "冷号信号较弱，退化为均匀随机。"
            )
        else:
            deviating = [p + 1 for p, u in enumerate(uniform_flags) if not u]
            basis += f"χ²检验显示第{deviating}位显著偏离均匀分布。"

        if total_significant > 0:
            cold_desc = []
            for pos, cold in enumerate(significant_cold):
                if cold:
                    cold_desc.append(f"第{pos+1}位: {cold}")
            basis += f"统计显著偏冷号码(z>{z_threshold}): {'; '.join(cold_desc)}。"
        else:
            basis += "无统计显著偏冷号码。"

        basis += (
            "数学说明：遗漏值服从几何分布Geom(p=0.1)，期望=9期，σ≈9.49期。"
            "只有z>1.96(95%置信)的偏离才被视为统计显著，避免赌徒谬误。"
            "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        details: Dict[str, Any] = {
            "pos_probabilities": pos_probs,
            "chi_square": chi2_values,
            "is_uniform": uniform_flags,
            "significant_cold": significant_cold,
            "z_scores": [{d: round(geo_z[pos][d], 3) for d in DIGIT_POOL} for pos in range(3)],
            "z_threshold": z_threshold,
        }

        # 5. 采样
        if dedup:
            results = _weighted_sample_without_replacement(pos_probs, count, rng)
        else:
            results = [
                [sample_weighted(rng, list(range(10)), pos_probs[pos]) for pos in range(3)]
                for _ in range(count)
            ]

        tickets: List[Ticket] = []
        for result in results:
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE,
                    groups={"pos": result},
                    strategy_name=self.metadata.name,
                    basis=basis,
                    details=details.copy(),
                )
            )
        return tickets
