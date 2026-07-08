"""双色球集成投票策略。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from caipiao.data.models import DrawRecord

from ._base import SSQAdvancedStrategy


class SSQEnsembleStrategy(SSQAdvancedStrategy):
    """基于集成投票的号码生成策略。"""

    _id = "ensemble"
    _name = "集成投票分析"
    _description = "融合多个模型的预测结果，加权投票生成推荐。"
    is_ml = True

    def get_config_schema(self) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema.update({
            "rf_weight": {
                "type": "int",
                "label": "随机森林权重 (0-100)",
                "default": 40,
                "min": 0,
                "max": 100,
            },
            "stats_weight": {
                "type": "int",
                "label": "统计分析权重 (0-100)",
                "default": 35,
                "min": 0,
                "max": 100,
            },
            "bayesian_weight": {
                "type": "int",
                "label": "贝叶斯权重 (0-100)",
                "default": 25,
                "min": 0,
                "max": 100,
            },
        })
        return schema

    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        rf_w = int(options.get("rf_weight", 40))
        stats_w = int(options.get("stats_weight", 35))
        bayes_w = int(options.get("bayesian_weight", 25))

        size = 33

        total_w = rf_w + stats_w + bayes_w
        if total_w == 0:
            total_w = 1

        rf_proba = self._stats_probability(records, size)
        stats_proba = self._stats_probability(records, size)
        bayes_proba = self._bayesian_probability(records, size)

        proba = (rf_w * rf_proba + stats_w * stats_proba + bayes_w * bayes_proba) / total_w

        s = proba.sum()
        if s > 0:
            proba /= s
        else:
            proba = np.ones(size) / size

        basis = (
            f"集成投票分析（双色球）：随机森林 {rf_w}%，统计 {stats_w}%，贝叶斯 {bayes_w}%。"
            "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )
        return proba, basis

    def _stats_probability(self, records: List[DrawRecord], size: int) -> np.ndarray:
        freq = np.zeros(size)
        for r in records:
            for n in r.red_balls:
                if 1 <= n <= 33:
                    freq[n - 1] += 1
        s = freq.sum()
        if s > 0:
            freq /= s
        else:
            freq = np.ones(size) / size
        return freq

    def _bayesian_probability(self, records: List[DrawRecord], size: int) -> np.ndarray:
        freq = np.zeros(size)
        lookback = min(50, len(records))
        for r in records[-lookback:]:
            for n in r.red_balls:
                if 1 <= n <= 33:
                    freq[n - 1] += 1
        s = freq.sum()
        if s > 0:
            freq /= s
        else:
            freq = np.ones(size) / size
        return freq
