"""贝叶斯推断策略 - 支持双色球和福彩3D."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.analyzer import DrawAnalyzer
from ....data.models import DrawRecord
from ...profile import LotteryProfile, SSQ
from .base import _AdvancedBase

logger = logging.getLogger(__name__)


class BayesianStrategy(_AdvancedBase):
    """基于贝叶斯推断的号码生成策略."""

    _id_base = "bayesian"
    _name_base = "贝叶斯推断"
    _description = "基于贝叶斯定理融合历史先验与近期观测，提供概率推断。"

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        super().__init__(profile)

    def get_config_schema(self) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema.update({
            "prior_weight": {
                "type": "int",
                "label": "先验权重 (0-100)",
                "default": 60,
                "min": 10,
                "max": 90,
            },
            "lookback": {
                "type": "int",
                "label": "观测窗口期数",
                "default": 50,
                "min": 10,
                "max": 500,
            },
            "alpha": {
                "type": "int",
                "label": "先验强度 (alpha)",
                "default": 2,
                "min": 1,
                "max": 10,
            },
        })
        return schema

    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        prior_weight = int(options.get("prior_weight", 60)) / 100.0
        lookback = int(options.get("lookback", 50))
        alpha = int(options.get("alpha", 2))

        group = self._profile.primary_group
        size = group.hi - group.lo + 1
        pick = group.count

        analyzer = DrawAnalyzer(records, self._profile)

        if group.positional:
            # 按位：每位独立推断
            proba = np.zeros((pick, size))
            for pos in range(pick):
                proba[pos] = self._bayesian_inference(
                    analyzer, group.key, size, lookback, prior_weight, alpha, pos
                )
            basis = f"贝叶斯推断（{self._profile.name}）：先验权重 {int(prior_weight*100)}%，观测窗口 {lookback} 期。"
        else:
            # 组合：整体推断
            proba = self._bayesian_inference(
                analyzer, group.key, size, lookback, prior_weight, alpha
            )
            basis = f"贝叶斯推断（{self._profile.name}）：先验权重 {int(prior_weight*100)}%，观测窗口 {lookback} 期。"

        return proba, basis

    def _bayesian_inference(
        self,
        analyzer: DrawAnalyzer,
        group_key: str,
        size: int,
        lookback: int,
        prior_weight: float,
        alpha: float,
        position: int | None = None,
    ) -> np.ndarray:
        """贝叶斯推断。"""
        # 先验
        freq_all = analyzer.frequency(group_key)
        total_all = sum(freq_all.values()) or 1

        # 似然
        freq_recent = analyzer.frequency(group_key, last_n=lookback)
        total_recent = sum(freq_recent.values()) or 1

        posterior = np.zeros(size, dtype=np.float64)
        for n in range(size):
            a_prior = alpha + freq_all.get(n + 1, 0) * alpha / max(total_all, 1)
            b_prior = alpha + (total_all - freq_all.get(n + 1, 0)) * alpha / max(total_all, 1)
            k = freq_recent.get(n + 1, 0)
            a_post = a_prior + k
            b_post = b_prior + total_recent - k
            posterior[n] = a_post / (a_post + b_post)

        prior = np.array([freq_all.get(n + 1, 0) / max(total_all, 1) for n in range(size)])
        result = prior_weight * prior + (1 - prior_weight) * posterior

        s = result.sum()
        if s > 0:
            result /= s
        else:
            result = np.ones(size) / size

        return result
