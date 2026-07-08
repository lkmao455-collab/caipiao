"""机器学习预测器高层接口."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np

from ..data.models import DrawRecord
from .common.model_store import data_fingerprint
from .features import build_features, build_prediction_features
from .model import LotteryXGBoostModel

logger = logging.getLogger(__name__)


class MLPredictor:
    """基于历史数据的机器学习号码推荐器."""

    def __init__(
        self,
        records: List[DrawRecord],
        lookback: int = 50,
        model_path: Optional[Path] = None,
        model_class: type = LotteryXGBoostModel,
        temp_dir: Optional[str] = None,
    ) -> None:
        self.records = sorted(records, key=lambda r: r.draw_date)
        self.lookback = lookback
        self.model = model_class(lookback=lookback, temp_dir=temp_dir)
        self.model_path = model_path
        self._needs_training = True
        self._feature_count: Optional[int] = None

        if model_path and model_path.exists():
            if self._metadata_matches():
                try:
                    self.model.load(model_path)
                    self._needs_training = False
                    logger.info("已加载与当前数据匹配的缓存模型")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("加载模型失败: %s", exc)
            else:
                logger.info("本地缓存模型与当前数据不一致，将重新训练")

    def _data_fingerprint(self) -> str:
        """基于记录数量和最新一期生成数据指纹."""
        return data_fingerprint(self.records)

    def _metadata_path(self) -> Optional[Path]:
        if not self.model_path:
            return None
        return self.model_path.with_suffix(self.model_path.suffix + ".meta.json")

    def _metadata_matches(self) -> bool:
        """检查缓存模型元数据是否与当前数据一致."""
        meta_path = self._metadata_path()
        if not meta_path or not meta_path.exists():
            return False
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("fingerprint") != self._data_fingerprint():
                return False
            # 旧模型没有 feature_count 字段，按不一致处理（避免特征维度不匹配报错）
            if "feature_count" not in meta:
                return False
            return meta.get("feature_count") == self._expected_feature_count()
        except Exception:  # noqa: BLE001
            return False

    def _expected_feature_count(self) -> int:
        """当前特征工程期望的特征维度（缓存）。"""
        if self._feature_count is None:
            X = build_prediction_features(self.records, self.lookback)
            if X.size == 0:
                raise ValueError("历史数据不足，无法计算特征维度")
            self._feature_count = int(X.shape[1])
        return self._feature_count

    def _save_metadata(self) -> None:
        """保存模型元数据."""
        meta_path = self._metadata_path()
        if not meta_path:
            return
        meta = {
            "fingerprint": self._data_fingerprint(),
            "record_count": len(self.records),
            "lookback": self.lookback,
            "feature_count": self._expected_feature_count(),
        }
        if self.records:
            latest = self.records[-1]
            meta["last_issue"] = latest.issue
            meta["last_draw_date"] = latest.draw_date.isoformat()
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def train(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """使用全部历史数据训练模型.

        Args:
            progress_callback: 可选进度回调 ``callback(current, total)``，
                透传给底层模型用于界面进度展示。
        """
        X, y_red, y_blue = build_features(self.records, self.lookback)
        if X.shape[0] == 0:
            raise ValueError("历史数据不足，无法训练模型")
        self.model.fit(X, y_red, y_blue, progress_callback=progress_callback)
        self._needs_training = False
        if self.model_path:
            self.model.save(self.model_path)
            self._save_metadata()
            logger.info("模型已保存，数据指纹：%s", self._data_fingerprint())

    def predict(self) -> Tuple[np.ndarray, np.ndarray]:
        """预测下一期各号码出现概率.

        Returns:
            red_proba: 33 个红球概率
            blue_proba: 16 个蓝球概率
        """
        if self._needs_training:
            self.train()
        X = build_prediction_features(self.records, self.lookback)
        if X.size == 0:
            raise ValueError("历史数据不足，无法预测")
        return self.model.predict_proba(X)

    def recommend(
        self,
        red_count: int = 6,
        blue_count: int = 1,
        diversity_boost: float = 0.3,
        rng: Optional[np.random.RandomState] = None,
    ) -> Tuple[List[int], List[int]]:
        """推荐号码组合.

        红球使用顺序生成模型不放回采样；蓝球使用预测概率加权采样。
        """
        if rng is None:
            rng = np.random.RandomState()

        if not 1 <= red_count <= 33:
            raise ValueError("red_count 必须在 1..33 之间")
        if not 0 <= blue_count <= 16:
            raise ValueError("blue_count 必须在 0..16 之间")

        red_proba, blue_proba = self.predict()
        X_pred = build_prediction_features(self.records, self.lookback)
        if X_pred.size == 0:
            raise ValueError("历史数据不足，无法预测")

        selected_reds = sorted(self.model.sample_reds(X_pred, red_count, rng))

        blue_weights = blue_proba + 0.05
        blue_weights = blue_weights / blue_weights.sum()
        selected_blues: List[int] = []
        if blue_count > 0:
            selected_blues = rng.choice(
                range(1, 17), size=blue_count, replace=False, p=blue_weights
            ).tolist()

        return selected_reds, selected_blues

    def is_ready(self) -> bool:
        """模型是否已准备好."""
        return self.model.is_trained or not self._needs_training
