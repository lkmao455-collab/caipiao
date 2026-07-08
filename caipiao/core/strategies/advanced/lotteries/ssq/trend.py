"""双色球趋势分析策略。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from caipiao.data.models import DrawRecord

from ._base import SSQAdvancedStrategy


class SSQTrendStrategy(SSQAdvancedStrategy):
    """基于趋势分析的号码生成策略。"""

    _id = "trend"
    _name = "趋势分析"
    _description = "基于滑动窗口分析号码频率变化趋势，识别上升/下降趋势。"

    def get_config_schema(self) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema.update({
            "window_size": {
                "type": "int",
                "label": "趋势窗口大小",
                "default": 10,
                "min": 5,
                "max": 30,
            },
            "trend_weight": {
                "type": "int",
                "label": "趋势权重 (0-100)",
                "default": 50,
                "min": 0,
                "max": 100,
            },
        })
        return schema

    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        window_size = int(options.get("window_size", 10))
        trend_weight = int(options.get("trend_weight", 50)) / 100.0

        size = 33

        if len(records) < window_size + 1:
            proba = np.ones(size) / size
            basis = "趋势分析（双色球）：数据不足，使用均匀概率。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
            return proba, basis

        freq_current = np.zeros(size)
        freq_prev = np.zeros(size)

        for r in records[-window_size:]:
            for n in r.red_balls:
                if 1 <= n <= 33:
                    freq_current[n - 1] += 1

        for r in records[-2 * window_size:-window_size]:
            for n in r.red_balls:
                if 1 <= n <= 33:
                    freq_prev[n - 1] += 1

        freq_current /= max(window_size, 1)
        freq_prev /= max(window_size, 1)

        trend_scores = freq_current - freq_prev
        if trend_scores.max() - trend_scores.min() > 0:
            trend_normalized = (trend_scores - trend_scores.min()) / (trend_scores.max() - trend_scores.min())
        else:
            trend_normalized = np.ones(size) * 0.5

        freq_normalized = freq_current / max(freq_current.sum(), 1e-10)
        proba = (1 - trend_weight) * freq_normalized + trend_weight * trend_normalized
        s = proba.sum()
        if s > 0:
            proba /= s
        else:
            proba = np.ones(size) / size

        basis = (
            f"趋势分析（双色球）：窗口 {window_size} 期，趋势权重 {int(trend_weight * 100)}%。"
            "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )
        return proba, basis
