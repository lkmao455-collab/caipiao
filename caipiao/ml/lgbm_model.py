"""LightGBM 模型训练与预测."""

from __future__ import annotations

import logging
import pickle
import warnings
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import lightgbm as lgb
import numpy as np
from sklearn.multioutput import MultiOutputClassifier

logger = logging.getLogger(__name__)


class LotteryLightGBMModel:
    """基于 LightGBM 的彩票号码分析模型.

    结构与 :class:`caipiao.ml.model.LotteryXGBoostModel` 保持一致：
    为每个红球训练一个二分类器，蓝球用多输出分类器统一训练，
    输出下一期各号码出现的概率。
    """

    def __init__(self, lookback: int = 50, temp_dir: Optional[str] = None) -> None:
        self.lookback = lookback
        self.temp_dir = temp_dir
        self.red_models: List[lgb.LGBMClassifier] = []
        self.blue_model: Optional[MultiOutputClassifier] = None
        self.is_trained = False

    def _create_classifier(self) -> lgb.LGBMClassifier:
        """创建 LightGBM 分类器."""
        return lgb.LGBMClassifier(
            n_estimators=100,
            max_depth=4,
            num_leaves=15,
            learning_rate=0.1,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            objective="binary",
            n_jobs=1,
            num_threads=1,
            random_state=42,
            verbose=-1,
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
        logger.info("LightGBM 模型训练完成")

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

        # LightGBM 用 numpy 训练时会自造列名（Column_0..），而预测同样传 numpy
        # 数组（无列名），sklearn 因此发出"特征名不匹配"告警。列顺序与数量一致，
        # 预测结果不受影响，这里仅屏蔽这一条误报。
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names",
                category=UserWarning,
            )
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
