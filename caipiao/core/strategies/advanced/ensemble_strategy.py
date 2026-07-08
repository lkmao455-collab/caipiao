"""集成投票策略 - 支持双色球和福彩3D."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.models import DrawRecord
from ...profile import LotteryProfile, SSQ
from .base import _AdvancedBase

logger = logging.getLogger(__name__)


class EnsembleVotingStrategy(_AdvancedBase):
    """基于集成投票的号码生成策略."""

    _id_base = "ensemble"
    _name_base = "集成投票分析"
    _description = "融合多个模型的预测结果，加权投票生成推荐。"
    is_ml = True

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        super().__init__(profile)

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

        group = self._profile.primary_group
        size = group.hi - group.lo + 1
        pick = group.count

        total_w = rf_w + stats_w + bayes_w
        if total_w == 0:
            total_w = 1

        # 模型1: 随机森林
        rf_proba = self._rf_probability(records, group, size, pick)

        # 模型2: 统计频率
        stats_proba = self._stats_probability(records, group, size, pick)

        # 模型3: 贝叶斯
        bayes_proba = self._bayesian_probability(records, group, size, pick)

        proba = (rf_w * rf_proba + stats_w * stats_proba + bayes_w * bayes_proba) / total_w

        if group.positional and proba.ndim == 1:
            proba = np.tile(proba, (pick, 1))

        basis = f"集成投票分析（{self._profile.name}）：随机森林 {rf_w}%，统计 {stats_w}%，贝叶斯 {bayes_w}%。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        return proba, basis

    def _rf_probability(self, records, group, size, pick):
        """随机森林概率。"""
        try:
            from sklearn.ensemble import RandomForestClassifier

            lookback = min(30, len(records) - 1) if len(records) > 31 else 5
            X_list, y_list = [], []

            for i in range(lookback, len(records)):
                window = records[i - lookback:i]
                features = []
                for pos in range(pick):
                    freq = np.zeros(size)
                    for r in window:
                        nums = r.groups.get(group.key, [])
                        if pos < len(nums):
                            freq[nums[pos] - group.lo] += 1
                    freq /= max(len(window), 1)
                    features.extend(freq)
                X_list.append(features)
                current = records[i].groups.get(group.key, [])
                y_list.append([n - group.lo for n in current[:pick]])

            if not X_list:
                return np.ones(size) / size

            X = np.array(X_list)
            y = np.array(y_list)

            if group.positional:
                proba = np.zeros((pick, size))
                for pos in range(pick):
                    clf = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
                    clf.fit(X, y[:, pos])
                    # 预测
                    features = []
                    window = records[-lookback:]
                    for p2 in range(pick):
                        freq = np.zeros(size)
                        for r in window:
                            nums = r.groups.get(group.key, [])
                            if p2 < len(nums):
                                freq[nums[p2] - group.lo] += 1
                        freq /= max(len(window), 1)
                        features.extend(freq)
                    proba[pos] = clf.predict_proba(np.array([features]))[0]
                return proba
            else:
                # 简化：使用频率
                return self._stats_probability(records, group, size, pick)
        except Exception:
            return np.ones(size) / size

    def _stats_probability(self, records, group, size, pick):
        """统计频率概率。"""
        freq = np.zeros(size)
        for r in records:
            for n in r.groups.get(group.key, []):
                if group.lo <= n <= group.hi:
                    freq[n - group.lo] += 1
        s = freq.sum()
        if s > 0:
            freq /= s
        else:
            freq = np.ones(size) / size
        if group.positional:
            freq = np.tile(freq, (pick, 1))
        return freq

    def _bayesian_probability(self, records, group, size, pick):
        """贝叶斯概率。"""
        freq = np.zeros(size)
        lookback = min(50, len(records))
        for r in records[-lookback:]:
            for n in r.groups.get(group.key, []):
                if group.lo <= n <= group.hi:
                    freq[n - group.lo] += 1
        s = freq.sum()
        if s > 0:
            freq /= s
        else:
            freq = np.ones(size) / size
        if group.positional:
            freq = np.tile(freq, (pick, 1))
        return freq
