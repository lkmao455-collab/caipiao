"""双色球相关性挖掘策略。"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Tuple

import numpy as np

from caipiao.data.models import DrawRecord

from ._base import SSQAdvancedStrategy


class SSQCorrelationStrategy(SSQAdvancedStrategy):
    """基于相关性挖掘的号码生成策略。"""

    _id = "correlation"
    _name = "相关性挖掘"
    _description = "挖掘号码间的共现相关性和条件概率，发现隐藏的关联模式。"

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

        size = 33

        freq = np.zeros(size)
        for r in records:
            for n in r.red_balls:
                if 1 <= n <= 33:
                    freq[n - 1] += 1
        total = len(records) or 1
        freq /= total

        cooccur = np.zeros((size, size))
        for r in records:
            nums = [n - 1 for n in r.red_balls if 1 <= n <= 33]
            for a, b in combinations(nums, 2):
                if 0 <= a < size and 0 <= b < size:
                    cooccur[a][b] += 1
                    cooccur[b][a] += 1

        max_cooccur = cooccur.max() if cooccur.max() > 0 else 1
        cooccur /= max_cooccur

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

        basis = (
            f"相关性挖掘（双色球）：最小支持度 {int(min_support * 100)}%，相关性权重 {int(corr_weight * 100)}%。"
            "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )
        return proba, basis
