"""相关性挖掘策略 - 支持双色球和福彩3D."""

from __future__ import annotations

import logging
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.models import DrawRecord
from ...profile import LotteryProfile, SSQ
from .base import _AdvancedBase

logger = logging.getLogger(__name__)


class CorrelationMiningStrategy(_AdvancedBase):
    """基于相关性挖掘的号码生成策略."""

    _id_base = "correlation"
    _name_base = "相关性挖掘"
    _description = "挖掘号码间的共现相关性和条件概率，发现隐藏的关联模式。"

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        super().__init__(profile)

    def get_config_schema(self) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema.update({
            "min_support": {
                "type": "int",
                "label": "最小支持度 (0-100)",
                "default": 5,
                "min": 1,
                "max": 20,
            },
            "correlation_weight": {
                "type": "int",
                "label": "相关性权重 (0-100)",
                "default": 60,
                "min": 0,
                "max": 100,
            },
        })
        return schema

    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        min_support = int(options.get("min_support", 5)) / 100.0
        corr_weight = int(options.get("correlation_weight", 60)) / 100.0

        group = self._profile.primary_group
        size = group.hi - group.lo + 1
        pick = group.count

        # 基础频率
        freq = np.zeros(size)
        for r in records:
            for n in r.groups.get(group.key, []):
                if group.lo <= n <= group.hi:
                    freq[n - group.lo] += 1
        total = len(records) or 1
        freq /= total

        # 共现矩阵
        cooccur = np.zeros((size, size))
        for r in records:
            nums = [n - group.lo for n in r.groups.get(group.key, [])
                    if group.lo <= n <= group.hi]
            for a, b in combinations(nums, 2):
                if 0 <= a < size and 0 <= b < size:
                    cooccur[a][b] += 1
                    cooccur[b][a] += 1

        max_cooccur = cooccur.max() if cooccur.max() > 0 else 1
        cooccur /= max_cooccur

        # 相关性得分
        corr_scores = np.zeros(size)
        for i in range(size):
            support_count = sum(1 for j in range(size) if j != i and cooccur[i][j] >= min_support)
            if support_count > 0:
                corr_scores[i] = np.mean([cooccur[j][i] for j in range(size)
                                          if j != i and cooccur[i][j] >= min_support])

        if corr_scores.max() > 0:
            corr_scores /= corr_scores.max()

        proba = (1 - corr_weight) * freq + corr_weight * corr_scores
        s = proba.sum()
        if s > 0:
            proba /= s
        else:
            proba = np.ones(size) / size

        if group.positional:
            proba = np.tile(proba, (pick, 1))

        basis = f"相关性挖掘（{self._profile.name}）：最小支持度 {int(min_support*100)}%，相关性权重 {int(corr_weight*100)}%。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        return proba, basis
