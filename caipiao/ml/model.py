"""XGBoost 模型训练与预测（顺序组合生成版）.

为双色球红球建模为不放回顺序生成问题：
给定历史窗口特征和已选红球，预测下一个红球号码。
蓝球仍按 16 个二分类器建模（每期只开 1 个蓝球）。
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
import xgboost as xgb
from sklearn.multioutput import MultiOutputClassifier
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger(__name__)

RED_COUNT = 33
BLUE_COUNT = 16
RED_PICK = 6


class LotteryXGBoostModel:
    """基于 XGBoost 的彩票号码分析模型.

    红球：顺序生成模型，输入包含历史特征、已选红球 mask、当前步数。
    蓝球：为每个蓝球训练二分类器，输出下一期出现的概率。
    """

    def __init__(self, lookback: int = 50, temp_dir: Optional[str] = None) -> None:
        self.lookback = lookback
        self.temp_dir = temp_dir
        self.red_sequence_model: Optional[xgb.XGBClassifier] = None
        self.red_sequence_encoder: Optional[LabelEncoder] = None
        self.blue_model: Optional[MultiOutputClassifier] = None
        self._base_feature_dim: Optional[int] = None
        self.is_trained = False

    def _create_classifier(
        self, positional: bool = False, num_class: int = 0
    ) -> xgb.XGBClassifier:
        """创建 XGBoost 分类器."""
        clf = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="binary:logistic",
            eval_metric="logloss",
            use_label_encoder=False,
            n_jobs=1,
            nthread=1,
            random_state=42,
            verbosity=0,
        )
        if positional:
            if num_class <= 1:
                raise ValueError("多分类类别数必须大于 1")
            clf.set_params(objective="multi:softprob", num_class=num_class)
        return clf

    def _build_sequence_input(
        self, base_x: np.ndarray, mask: np.ndarray, step: int
    ) -> np.ndarray:
        """构造红球顺序生成模型的一个输入向量."""
        step_norm = step / max(RED_PICK - 1, 1)
        return np.concatenate([base_x.flatten(), mask, [step_norm]]).astype(np.float32)

    def _build_sequence_training_data(
        self, X: np.ndarray, y_red: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, LabelEncoder]:
        """从 one-hot 红球标签构造顺序生成训练数据."""
        X_seq: List[np.ndarray] = []
        y_seq: List[int] = []
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
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """训练模型."""
        if X.shape[0] == 0:
            raise ValueError("训练数据为空")
        if y_red.ndim != 2 or y_blue.ndim != 2:
            raise ValueError("y_red/y_blue 必须是二维数组")
        self._base_feature_dim = X.shape[1]

        total = 2  # 红球顺序模型 + 蓝球多输出模型

        # 训练红球顺序生成模型
        X_seq, y_seq, encoder = self._build_sequence_training_data(X, y_red)
        num_class = len(encoder.classes_)
        self.red_sequence_model = self._create_classifier(
            positional=True, num_class=num_class
        )
        self.red_sequence_model.fit(X_seq, y_seq)
        self.red_sequence_encoder = encoder
        if progress_callback is not None:
            progress_callback(1, total)
        logger.debug("红球顺序生成模型训练完成")

        # 训练蓝球多输出分类器
        blue_clf = self._create_classifier().set_params(scale_pos_weight=5.0)
        self.blue_model = MultiOutputClassifier(blue_clf, n_jobs=1)
        self.blue_model.fit(X, y_blue)
        if progress_callback is not None:
            progress_callback(total, total)

        self.is_trained = True
        logger.info("XGBoost 模型训练完成")

    def _predict_sequence_initial(self, X: np.ndarray) -> np.ndarray:
        """预测 step=0 时各红球概率，用于展示."""
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
    ) -> Tuple[np.ndarray, np.ndarray]:
        """预测下一期各号码出现概率.

        Returns:
            red_proba: 33 个红球初始概率（step=0）
            blue_proba: 16 个蓝球概率
        """
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
    ) -> List[int]:
        """使用顺序生成模型采样 count 个不重复红球."""
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")
        encoder = self.red_sequence_encoder
        selected: List[int] = []
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

    def save(self, path: Path | str) -> None:
        """保存模型到文件."""
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
        logger.info("模型已保存到 %s", path)

    def load(self, path: Path | str) -> None:
        """从文件加载模型."""
        path = Path(path)
        with path.open("rb") as f:
            data = pickle.load(f)
        self.red_sequence_model = data["red_sequence_model"]
        self.red_sequence_encoder = data["red_sequence_encoder"]
        self.blue_model = data["blue_model"]
        self.lookback = data["lookback"]
        self.is_trained = data["is_trained"]
        self._base_feature_dim = data.get("base_feature_dim")
        logger.info("模型已从 %s 加载", path)
