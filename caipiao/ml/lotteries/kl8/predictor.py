"""KL8 专属 ML 预测器占位实现."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class KL8Predictor:
    """KL8 机器学习预测器占位.

    由于当前 ``GenericMLPredictor`` 训练目标为开奖 20 码，而玩家选号范围为
    1-10 个，计数不匹配，因此暂不提供实现。
    """

    def __init__(
        self,
        records: list[Any],
        lookback: int = 50,
        model_path: Optional[Any] = None,
        backend: str = "xgboost",
        temp_dir: Optional[str] = None,
    ) -> None:
        self.records = records
        self.lookback = lookback
        self.model_path = model_path
        self.backend = backend
        self.temp_dir = temp_dir

    def train(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "KL8 的 ML 预测器尚未实现：GenericMLPredictor 的组合组采样固定返回 "
            "20 个号码，与 KL8 投注单 1-10 个号码的约束不匹配。"
        )

    def predict(self) -> Dict[str, np.ndarray]:
        raise NotImplementedError(
            "KL8 的 ML 预测器尚未实现：GenericMLPredictor 的组合组采样固定返回 "
            "20 个号码，与 KL8 投注单 1-10 个号码的约束不匹配。"
        )

    def recommend(
        self,
        group_picks: Optional[Dict[str, int]] = None,
        diversity_boost: float = 0.3,
        rng: Optional[np.random.RandomState] = None,
    ) -> Dict[str, List[int]]:
        raise NotImplementedError(
            "KL8 的 ML 预测器尚未实现：GenericMLPredictor 的组合组采样固定返回 "
            "20 个号码，与 KL8 投注单 1-10 个号码的约束不匹配。"
        )

    def is_ready(self) -> bool:
        return False
