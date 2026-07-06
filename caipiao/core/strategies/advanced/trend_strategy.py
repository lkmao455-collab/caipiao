"""趋势分析策略 - 支持双色球和福彩3D."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.models import DrawRecord
from ...profile import LotteryProfile, SSQ
from .base import _AdvancedBase

logger = logging.getLogger(__name__)


class TrendAnalysisStrategy(_AdvancedBase):
    """基于趋势分析的号码生成策略."""

    _id_base = "trend"
    _name_base = "趋势分析"
    _description = "基于滑动窗口分析号码频率变化趋势，识别上升/下降趋势。"

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        super().__init__(profile)

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

        group = self._profile.primary_group
        size = group.hi - group.lo + 1
        pick = group.count

        if len(records) < window_size + 1:
            proba = np.ones(size) / size
            if group.positional:
                proba = np.tile(proba, (pick, 1))
            basis = f"趋势分析（{self._profile.name}）：数据不足，使用均匀概率。"
            return proba, basis

        # 计算频率
        freq_current = np.zeros(size)
        freq_prev = np.zeros(size)

        for r in records[-window_size:]:
            nums = r.groups.get(group.key, [])
            for n in nums:
                if group.lo <= n <= group.hi:
                    freq_current[n - group.lo] += 1

        for r in records[-2 * window_size:-window_size]:
            nums = r.groups.get(group.key, [])
            for n in nums:
                if group.lo <= n <= group.hi:
                    freq_prev[n - group.lo] += 1

        freq_current /= max(window_size, 1)
        freq_prev /= max(window_size, 1)

        # 趋势得分
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

        if group.positional:
            proba = np.tile(proba, (pick, 1))

        basis = f"趋势分析（{self._profile.name}）：窗口 {window_size} 期，趋势权重 {int(trend_weight*100)}%。"
        return proba, basis
