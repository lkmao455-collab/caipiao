"""随机森林模型训练与预测."""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier

logger = logging.getLogger(__name__)


class LotteryRandomForestModel:
    """基于随机森林的彩票号码分析模型."""

    def __init__(self, lookback: int = 50, temp_dir: Optional[str] = None) -> None:
        self.lookback = lookback
        self.temp_dir = temp_dir
        self.red_models: List[RandomForestClassifier] = []
        self.blue_model: Optional[MultiOutputClassifier] = None
        self.is_trained = False

    def _create_classifier(self) -> RandomForestClassifier:
        return RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features="sqrt",
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
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
        total = int(y_red.shape[1]) + 1

        self.red_models = []
        for i in range(y_red.shape[1]):
            model = self._create_classifier()
            model.fit(X, y_red[:, i])
            self.red_models.append(model)
            if progress_callback is not None:
                progress_callback(i + 1, total)
            logger.debug("红球 %02d 随机森林模型训练完成", i + 1)

        blue_clf = self._create_classifier()
        self.blue_model = MultiOutputClassifier(blue_clf, n_jobs=1)
        self.blue_model.fit(X, y_blue)
        if progress_callback is not None:
            progress_callback(total, total)

        self.is_trained = True
        logger.info("随机森林模型训练完成")

    def predict_proba(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        def _binary_proba(model):
            probs = model.predict_proba(X)[0]
            return probs[1] if probs.shape[0] > 1 else float(model.classes_[0] == 1)

        red_proba = np.array([_binary_proba(model) for model in self.red_models])
        blue_proba = np.array([_binary_proba(est) for est in self.blue_model.estimators_])
        return red_proba, blue_proba

    def feature_importance(self) -> Tuple[np.ndarray, np.ndarray]:
        """返回特征重要性（红球模型平均）。"""
        if not self.is_trained:
            return np.array([]), np.array([])
        red_imp = np.mean([m.feature_importances_ for m in self.red_models], axis=0)
        blue_imp = np.mean([est.feature_importances_ for est in self.blue_model.estimators_], axis=0)
        return red_imp, blue_imp

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
        logger.info("随机森林模型已保存到 %s", path)

    def load(self, path: Path | str) -> None:
        path = Path(path)
        with path.open("rb") as f:
            data = pickle.load(f)
        self.red_models = data["red_models"]
        self.blue_model = data["blue_model"]
        self.lookback = data["lookback"]
        self.is_trained = data["is_trained"]
        logger.info("随机森林模型已从 %s 加载", path)
