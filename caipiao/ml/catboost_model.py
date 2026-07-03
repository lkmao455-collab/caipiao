"""CatBoost 模型训练与预测.

结构与 :class:`caipiao.ml.model.LotteryXGBoostModel` 保持一致：
为每个红球训练一个二分类器，蓝球用多输出分类器统一训练，
输出下一期各号码出现的概率。
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import numpy as np
from sklearn.multioutput import MultiOutputClassifier

logger = logging.getLogger(__name__)


try:
    from catboost import CatBoostClassifier
except ImportError as exc:  # pragma: no cover
    CatBoostClassifier = None  # type: ignore
    logging.getLogger(__name__).warning("catboost 未安装，CatBoost 模型不可用: %s", exc)


class LotteryCatBoostModel:
    """基于 CatBoost 的彩票号码分析模型."""

    def __init__(self, lookback: int = 50) -> None:
        self.lookback = lookback
        self.red_models: List[Any] = []
        self.blue_model: Optional[MultiOutputClassifier] = None
        self.is_trained = False

    def _create_classifier(self) -> Any:
        if CatBoostClassifier is None:
            raise RuntimeError("catboost 未安装，无法创建 CatBoost 分类器")
        return CatBoostClassifier(
            iterations=100,
            depth=4,
            learning_rate=0.1,
            loss_function="Logloss",
            random_seed=42,
            verbose=False,
            thread_count=1,
        )

    def fit(
        self,
        X: np.ndarray,
        y_red: np.ndarray,
        y_blue: np.ndarray,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        if X.shape[0] == 0:
            raise ValueError("训练数据为空")
        if y_red.ndim != 2 or y_blue.ndim != 2:
            raise ValueError("y_red/y_blue 必须是二维数组")

        total = int(y_red.shape[1]) + 1

        self.red_models = []
        for i in range(y_red.shape[1]):
            model = self._create_classifier()
            pos = int(y_red[:, i].sum())
            neg = y_red.shape[0] - pos
            scale = neg / max(pos, 1)
            # CatBoost 使用 scale_pos_weight 处理类别不平衡
            model.set_params(scale_pos_weight=min(scale, 10.0))
            model.fit(X, y_red[:, i])
            self.red_models.append(model)
            if progress_callback is not None:
                progress_callback(i + 1, total)
            logger.debug("红球 %02d CatBoost 模型训练完成", i + 1)

        blue_clf = self._create_classifier().set_params(scale_pos_weight=5.0)
        self.blue_model = MultiOutputClassifier(blue_clf, n_jobs=1)
        self.blue_model.fit(X, y_blue)
        if progress_callback is not None:
            progress_callback(total, total)

        self.is_trained = True
        logger.info("CatBoost 模型训练完成")

    def predict_proba(
        self, X: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        def _binary_proba(model):
            probs = model.predict_proba(X)[0]
            return probs[1] if probs.shape[0] > 1 else float(model.classes_[0] == 1)

        red_proba = np.array([_binary_proba(model) for model in self.red_models])
        blue_proba = np.array([_binary_proba(est) for est in self.blue_model.estimators_])
        return red_proba, blue_proba

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(
                {
                    "red_models": self.red_models,
                    "blue_model": self.blue_model,
                    "lookback": self.lookback,
                    "is_trained": self.is_trained,
                },
                f,
            )
        logger.info("CatBoost 模型已保存到 %s", path)

    def load(self, path: Path | str) -> None:
        path = Path(path)
        with path.open("rb") as f:
            data = pickle.load(f)
        self.red_models = data["red_models"]
        self.blue_model = data["blue_model"]
        self.lookback = data["lookback"]
        self.is_trained = data["is_trained"]
        logger.info("CatBoost 模型已从 %s 加载", path)
