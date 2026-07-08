"""双色球随机森林高级策略。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from caipiao.data.models import DrawRecord
from caipiao.ml.features import build_features, build_prediction_features
from caipiao.ml.random_forest_model import LotteryRandomForestModel

from ._base import SSQAdvancedStrategy


class SSQRandomForestStrategy(SSQAdvancedStrategy):
    """基于随机森林集成学习的号码生成策略。"""

    _id = "random_forest"
    _name = "随机森林分析"
    _description = "基于随机森林集成学习，通过多棵决策树投票预测号码概率。"
    is_ml = True

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

        lookback = min(50, len(records) - 1) if len(records) > 51 else 10
        X, y_red, y_blue = build_features(records, lookback)
        if X.shape[0] == 0:
            raise ValueError("历史数据不足")

        model = LotteryRandomForestModel(lookback=lookback)
        model.fit(X, y_red, y_blue)
        X_pred = build_prediction_features(records, lookback)
        red_proba, _ = model.predict_proba(X_pred)

        basis = (
            f"随机森林分析（SSQ）：基于 {len(records)} 期数据，特征回看 {lookback} 期，"
            f"决策树 {n_estimators} 棵，最大深度 {max_depth}。"
            "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )
        return red_proba, basis
