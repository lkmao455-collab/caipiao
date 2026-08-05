"""KL8 专属 ML 预测器."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ....core.profile import KL8
from ....data.models import DrawRecord
from ...common.predictor import BaseMLPredictor


class KL8Predictor(BaseMLPredictor):
    """基于历史数据的 KL8 专属机器学习号码推荐器.

    使用 ``BaseMLPredictor`` 的通用训练/推理能力，
    但在推荐阶段根据用户选号个数（1-10）进行加权采样。
    """

    def __init__(
        self,
        records: list[DrawRecord],
        lookback: int = 50,
        model_path: Path | None = None,
        backend: str = "xgboost",
        temp_dir: str | None = None,
    ) -> None:
        super().__init__(
            records=records,
            profile=KL8,
            lookback=lookback,
            model_path=model_path,
            backend=backend,
            temp_dir=temp_dir,
        )

    def predict(self) -> np.ndarray:
        """预测下一期各号码出现概率.

        Returns:
            80 个号码的 step-0 初始概率（ndarray, shape=(80,)）。
        """
        proba = super().predict()
        return proba["main"]

    def recommend(
        self,
        pick: int = 4,
        diversity_boost: float = 0.3,
        rng: np.random.RandomState | None = None,
    ) -> list[int]:
        """推荐号码组合.

        Args:
            pick: 要选多少个号码（1-10）。
            diversity_boost: 多样性增强系数。
            rng: 随机数生成器。

        Returns:
            推荐号码列表（已排序）。
        """
        if rng is None:
            rng = np.random.RandomState()
        proba = self.predict()
        main_group = self.profile.primary_group
        return self._recommend_combination(main_group, proba, pick, diversity_boost, rng)
