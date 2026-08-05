"""随机森林模型训练与预测（顺序组合生成版）.

为双色球红球建模为不放回顺序生成问题，蓝球按二分类建模。
"""

from __future__ import annotations

import logging
import pickle
from collections.abc import Callable
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger(__name__)

RED_COUNT = 33
BLUE_COUNT = 16
RED_PICK = 6


class LotteryRandomForestModel:
    """基于随机森林的彩票号码分析模型."""

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        self.lookback = lookback
        self.temp_dir = temp_dir
        self.red_sequence_model: RandomForestClassifier | None = None
        self.red_sequence_encoder: LabelEncoder | None = None
        self.blue_model: MultiOutputClassifier | None = None
        self._base_feature_dim: int | None = None
        self.is_trained = False

    def _create_classifier(
        self, positional: bool = False, num_class: int = 0
    ) -> RandomForestClassifier:
        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features="sqrt",
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
        )
        if positional:
            if num_class <= 1:
                raise ValueError("多分类类别数必须大于 1")
            clf.set_params(criterion="gini")
        return clf

    def _build_sequence_input(
        self, base_x: np.ndarray, mask: np.ndarray, step: int
    ) -> np.ndarray:
        step_norm = step / max(RED_PICK - 1, 1)
        return np.concatenate([base_x.flatten(), mask, [step_norm]]).astype(np.float32)

    def _build_sequence_training_data(
        self, X: np.ndarray, y_red: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, LabelEncoder]:
        X_seq: list[np.ndarray] = []
        y_seq: list[int] = []
        for i in range(X.shape[0]):
            nums = [idx for idx, val in enumerate(y_red[i]) if val]
            nums.sort()
            mask = np.zeros(RED_COUNT, dtype=np.float32)
            for step, num_idx in enumerate(nums):
                X_seq.append(self._build_sequence_input(X[i], mask, step))
                y_seq.append(num_idx)
                mask[num_idx] = 1.0
        encoder = LabelEncoder()
        y_enc = encoder.fit_transform(y_seq)
        return np.array(X_seq), y_enc, encoder

    def fit(
        self,
        X: np.ndarray,
        y_red: np.ndarray,
        y_blue: np.ndarray,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        if X.shape[0] == 0:
            raise ValueError("训练数据为空")
        self._base_feature_dim = X.shape[1]
        total = 2

        X_seq, y_seq, encoder = self._build_sequence_training_data(X, y_red)
        num_class = len(encoder.classes_)
        self.red_sequence_model = self._create_classifier(positional=True, num_class=num_class)
        self.red_sequence_model.fit(X_seq, y_seq)
        self.red_sequence_encoder = encoder
        if progress_callback is not None:
            progress_callback(1, total)
        logger.debug("红球顺序生成随机森林训练完成")

        blue_clf = self._create_classifier()
        self.blue_model = MultiOutputClassifier(blue_clf, n_jobs=1)
        self.blue_model.fit(X, y_blue)
        if progress_callback is not None:
            progress_callback(total, total)

        self.is_trained = True
        logger.info("随机森林模型训练完成")

    def _predict_sequence_initial(self, X: np.ndarray) -> np.ndarray:
        mask = np.zeros(RED_COUNT, dtype=np.float32)
        x = self._build_sequence_input(X, mask, 0).reshape(1, -1)
        pred = self.red_sequence_model.predict_proba(x)[0]
        encoder = self.red_sequence_encoder
        full = np.full(RED_COUNT, 0.05 / RED_COUNT, dtype=np.float32)
        for idx, cls in enumerate(encoder.classes_):
            full[int(cls)] = max(pred[idx], 0.0)
        full = full / full.sum()
        return full

    def predict_proba(
        self, X: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        red_proba = self._predict_sequence_initial(X)

        def _binary_proba(est):
            probs = est.predict_proba(X)[0]
            return probs[1] if probs.shape[0] > 1 else float(est.classes_[0] == 1)

        blue_proba = np.array([_binary_proba(est) for est in self.blue_model.estimators_])
        return red_proba, blue_proba

    def sample_reds(
        self,
        X_pred: np.ndarray,
        count: int,
        rng: np.random.RandomState,
    ) -> list[int]:
        """使用顺序生成模型采样 count 个不重复红球."""
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")
        encoder = self.red_sequence_encoder
        selected: list[int] = []
        mask = np.zeros(RED_COUNT, dtype=np.float32)
        for step in range(count):
            x = self._build_sequence_input(X_pred, mask, step).reshape(1, -1)
            pred = self.red_sequence_model.predict_proba(x)[0]
            full = np.full(RED_COUNT, 0.05 / RED_COUNT, dtype=np.float32)
            for idx, cls in enumerate(encoder.classes_):
                full[int(cls)] = max(pred[idx], 0.0)
            for idx in selected:
                full[idx] = 0.0
            s = full.sum()
            if s <= 0:
                remaining = [i for i in range(RED_COUNT) if i not in selected]
                full = np.zeros(RED_COUNT, dtype=np.float32)
                for i in remaining:
                    full[i] = 1.0 / max(len(remaining), 1)
            else:
                full = full / s
            next_idx = int(rng.choice(RED_COUNT, p=full))
            selected.append(next_idx)
            mask[next_idx] = 1.0
        return [idx + 1 for idx in selected]

    def feature_importance(self) -> tuple[np.ndarray, np.ndarray]:
        """返回特征重要性（红球模型平均）."""
        if not self.is_trained:
            return np.array([]), np.array([])
        red_imp = self.red_sequence_model.feature_importances_
        blue_imp = np.mean(
            [est.feature_importances_ for est in self.blue_model.estimators_], axis=0
        )
        return red_imp, blue_imp

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(
                {
                    "red_sequence_model": self.red_sequence_model,
                    "red_sequence_encoder": self.red_sequence_encoder,
                    "blue_model": self.blue_model,
                    "lookback": self.lookback,
                    "is_trained": self.is_trained,
                    "base_feature_dim": self._base_feature_dim,
                },
                f,
            )
        logger.info("随机森林模型已保存到 %s", path)

    def load(self, path: Path | str) -> None:
        path = Path(path)
        with path.open("rb") as f:
            data = pickle.load(f)
        self.red_sequence_model = data["red_sequence_model"]
        self.red_sequence_encoder = data["red_sequence_encoder"]
        self.blue_model = data["blue_model"]
        self.lookback = data["lookback"]
        self.is_trained = data["is_trained"]
        self._base_feature_dim = data.get("base_feature_dim")
        logger.info("随机森林模型已从 %s 加载", path)
