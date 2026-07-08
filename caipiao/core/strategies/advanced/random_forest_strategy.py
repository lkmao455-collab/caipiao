"""随机森林策略 - 支持双色球和福彩3D."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.models import DrawRecord
from ....ml.random_forest_model import LotteryRandomForestModel
from ...profile import LotteryProfile, SSQ
from .base import _AdvancedBase

logger = logging.getLogger(__name__)


class RandomForestStrategy(_AdvancedBase):
    """基于随机森林集成学习的号码生成策略."""

    _id_base = "random_forest"
    _name_base = "随机森林分析"
    _description = "基于随机森林集成学习，通过多棵决策树投票预测号码概率。"
    is_ml = True

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        super().__init__(profile)

    def get_config_schema(self) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema.update({
            "n_estimators": {
                "type": "int",
                "label": "决策树数量",
                "default": 200,
                "min": 50,
                "max": 500,
            },
            "max_depth": {
                "type": "int",
                "label": "最大深度",
                "default": 8,
                "min": 3,
                "max": 15,
            },
        })
        return schema

    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        n_estimators = int(options.get("n_estimators", 200))
        max_depth = int(options.get("max_depth", 8))

        if self._is_ssq():
            return self._compute_ssq(records, n_estimators, max_depth)
        elif self._is_3d():
            return self._compute_3d(records, n_estimators, max_depth)
        else:
            return self._compute_generic(records, n_estimators, max_depth)

    def _compute_ssq(self, records, n_estimators, max_depth):
        from ....ml.features import build_features, build_prediction_features

        lookback = min(50, len(records) - 1) if len(records) > 51 else 10
        X, y_red, y_blue = build_features(records, lookback)
        if X.shape[0] == 0:
            raise ValueError("历史数据不足")

        model = LotteryRandomForestModel(lookback=lookback)
        model.fit(X, y_red, y_blue)
        X_pred = build_prediction_features(records, lookback)
        red_proba, blue_proba = model.predict_proba(X_pred)

        basis = f"随机森林分析（SSQ）：基于 {len(records)} 期数据，特征回看 {lookback} 期。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        # 返回红球概率，蓝球单独处理
        return red_proba, basis

    def _compute_3d(self, records, n_estimators, max_depth):
        from sklearn.ensemble import RandomForestClassifier

        group = self._profile.primary_group
        size = group.hi - group.lo + 1  # 10 (0-9)
        pick = group.count  # 3

        # 构建特征：每期3位的历史频率
        lookback = min(30, len(records) - 1) if len(records) > 31 else 5

        X_list = []
        y_list = []

        for i in range(lookback, len(records)):
            window = records[i - lookback:i]
            # 特征：每位的频率分布
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

            # 标签：当前期的号码
            current = records[i].groups.get(group.key, [])
            y_list.append([n - group.lo for n in current[:pick]])

        if not X_list:
            # 数据不足，返回均匀概率
            proba = np.ones((pick, size)) / size
            basis = f"随机森林分析（福彩3D）：数据不足，使用均匀概率。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
            return proba, basis

        X = np.array(X_list)
        y = np.array(y_list)

        # 为每位训练一个分类器
        classifiers = []
        for pos in range(pick):
            clf = RandomForestClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                random_state=42,
            )
            clf.fit(X, y[:, pos])
            classifiers.append(clf)

        # 预测
        features = []
        window = records[-lookback:] if len(records) >= lookback else records
        for pos in range(pick):
            freq = np.zeros(size)
            for r in window:
                nums = r.groups.get(group.key, [])
                if pos < len(nums):
                    freq[nums[pos] - group.lo] += 1
            freq /= max(len(window), 1)
            features.extend(freq)

        X_pred = np.array([features])
        proba = np.zeros((pick, size))
        for pos in range(pick):
            proba[pos] = classifiers[pos].predict_proba(X_pred)[0]

        basis = f"随机森林分析（福彩3D）：基于 {len(records)} 期数据，每位独立建模。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        return proba, basis

    def _compute_generic(self, records, n_estimators, max_depth):
        """通用彩种的随机森林预测。"""
        from sklearn.ensemble import RandomForestClassifier

        group = self._profile.primary_group
        size = group.hi - group.lo + 1
        pick = group.count
        lookback = min(30, len(records) - 1) if len(records) > 31 else 5

        X_list = []
        y_list = []

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
            proba = np.ones((pick, size)) / size
            basis = f"随机森林分析：数据不足，使用均匀概率。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
            return proba, basis

        X = np.array(X_list)
        y = np.array(y_list)

        classifiers = []
        for pos in range(pick):
            clf = RandomForestClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                random_state=42,
            )
            clf.fit(X, y[:, pos])
            classifiers.append(clf)

        features = []
        window = records[-lookback:] if len(records) >= lookback else records
        for pos in range(pick):
            freq = np.zeros(size)
            for r in window:
                nums = r.groups.get(group.key, [])
                if pos < len(nums):
                    freq[nums[pos] - group.lo] += 1
            freq /= max(len(window), 1)
            features.extend(freq)

        X_pred = np.array([features])
        proba = np.zeros((pick, size))
        for pos in range(pick):
            proba[pos] = classifiers[pos].predict_proba(X_pred)[0]

        basis = f"随机森林分析：基于 {len(records)} 期数据，每位独立建模。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        return proba, basis
