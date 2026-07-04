"""XGBoost 模型训练与预测."""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
import xgboost as xgb
from sklearn.multioutput import MultiOutputClassifier

logger = logging.getLogger(__name__)


class LotteryXGBoostModel:
    """基于 XGBoost 的彩票号码分析模型.

    为每个红球和每个蓝球训练二分类器，输出下一期出现的概率。
    """

    def __init__(self, lookback: int = 50, temp_dir: Optional[str] = None) -> None:
        self.lookback = lookback
        self.temp_dir = temp_dir
        self.red_models: List[xgb.XGBClassifier] = []
        self.blue_model: Optional[MultiOutputClassifier] = None
        self.is_trained = False

    def _create_classifier(self) -> xgb.XGBClassifier:
        """创建 XGBoost 分类器."""
        return xgb.XGBClassifier(
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

    def fit(
        self,
        X: np.ndarray,
        y_red: np.ndarray,
        y_blue: np.ndarray,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """训练模型.

        Args:
            X: 特征矩阵 (samples, features)
            y_red: 红球标签 (samples, 33)
            y_blue: 蓝球标签 (samples, 16)
            progress_callback: 可选进度回调，签名为 ``callback(current, total)``，
                每训练完一个分类器调用一次，用于界面进度展示。
        """
        if X.shape[0] == 0:
            raise ValueError("训练数据为空")
        if y_red.ndim != 2 or y_blue.ndim != 2:
            raise ValueError("y_red/y_blue 必须是二维数组")

        # 总步数 = 33 个红球分类器 + 1 个蓝球多输出分类器
        total = int(y_red.shape[1]) + 1

        # 训练 33 个红球二分类器
        self.red_models = []
        for i in range(y_red.shape[1]):
            model = self._create_classifier()
            # 处理类别不平衡：正样本很少
            pos = int(y_red[:, i].sum())
            neg = y_red.shape[0] - pos
            scale = neg / max(pos, 1)
            model.set_params(scale_pos_weight=min(scale, 10.0))
            model.fit(X, y_red[:, i])
            self.red_models.append(model)
            if progress_callback is not None:
                progress_callback(i + 1, total)
            logger.debug("红球 %02d 模型训练完成", i + 1)

        # 训练蓝球多输出分类器
        blue_clf = self._create_classifier().set_params(scale_pos_weight=5.0)
        self.blue_model = MultiOutputClassifier(blue_clf, n_jobs=1)
        self.blue_model.fit(X, y_blue)
        if progress_callback is not None:
            progress_callback(total, total)

        self.is_trained = True
        logger.info("XGBoost 模型训练完成")

    def predict_proba(
        self, X: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """预测下一期各号码出现概率.

        Returns:
            red_proba: 红球概率 (33,)
            blue_proba: 蓝球概率 (16,)
        """
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        def _binary_proba(model):
            probs = model.predict_proba(X)[0]
            return probs[1] if probs.shape[0] > 1 else float(model.classes_[0] == 1)

        red_proba = np.array([_binary_proba(model) for model in self.red_models])
        blue_proba = np.array([_binary_proba(est) for est in self.blue_model.estimators_])
        return red_proba, blue_proba

    def save(self, path: Path | str) -> None:
        """保存模型到文件."""
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
        logger.info("模型已保存到 %s", path)

    def load(self, path: Path | str) -> None:
        """从文件加载模型."""
        path = Path(path)
        with path.open("rb") as f:
            data = pickle.load(f)
        self.red_models = data["red_models"]
        self.blue_model = data["blue_model"]
        self.lookback = data["lookback"]
        self.is_trained = data["is_trained"]
        logger.info("模型已从 %s 加载", path)
