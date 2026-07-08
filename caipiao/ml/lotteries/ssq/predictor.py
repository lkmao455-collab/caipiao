"""SSQ 专属 ML 预测器（当前委托通用实现，保留隔离边界）."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np

from ....core.profile import SSQ
from ....data.models import DrawRecord
from ...generic_predictor import GenericMLPredictor
from .features import build_prediction_features


class SSQPredictor(GenericMLPredictor):
    """基于历史数据的 SSQ 专属机器学习号码推荐器.

    当前实现直接复用 ``GenericMLPredictor`` 的通用训练/推理能力，
    同时提供与旧 ``caipiao.ml.predictor.MLPredictor`` 兼容的接口，
    使 SSQ ML 策略无需改动即可切换到底层。
    """

    def __init__(
        self,
        records: List[DrawRecord],
        lookback: int = 50,
        model_path: Optional[Path] = None,
        backend: str = "xgboost",
        temp_dir: Optional[str] = None,
    ) -> None:
        super().__init__(
            records=records,
            profile=SSQ,
            lookback=lookback,
            model_path=model_path,
            backend=backend,
            temp_dir=temp_dir,
        )

    def train(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """使用全部历史数据训练模型."""
        super().train(progress_callback=progress_callback)

    def predict(self) -> Tuple[np.ndarray, np.ndarray]:
        """预测下一期各号码出现概率.

        Returns:
            red_proba: 33 个红球概率。
            blue_proba: 16 个蓝球概率。
        """
        proba = super().predict()
        return proba["red"], proba["blue"]

    def recommend(
        self,
        red_count: int = 6,
        blue_count: int = 1,
        diversity_boost: float = 0.3,
        rng: Optional[np.random.RandomState] = None,
    ) -> Tuple[List[int], List[int]]:
        """推荐号码组合.

        Args:
            red_count: 红球个数。
            blue_count: 蓝球个数。
            diversity_boost: 多样性增强系数。
            rng: 随机数生成器。

        Returns:
            selected_reds: 推荐红球列表（已排序）。
            selected_blues: 推荐蓝球列表。
        """
        if rng is None:
            rng = np.random.RandomState()

        # 使用父类的 dict 接口获取概率，避免被自己覆盖的 tuple 接口干扰。
        proba = GenericMLPredictor.predict(self)
        X_pred = build_prediction_features(self.records, self.profile, self.lookback)
        if X_pred.size == 0:
            raise ValueError("历史数据不足，无法预测")

        red_group = self.profile.group("red")
        blue_group = self.profile.group("blue")

        reds = sorted(self.model.sample_combination(X_pred, red_group, rng))
        blues = self._recommend_combination(
            blue_group, proba["blue"], blue_count, diversity_boost, rng
        )
        return reds, blues
