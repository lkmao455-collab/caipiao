"""机器学习预测器高层接口."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from ..data.models import DrawRecord
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
    ) -> None:
        self.records = sorted(records, key=lambda r: r.draw_date)
        self.lookback = lookback
        self.model = LotteryXGBoostModel(lookback=lookback)
        self.model_path = model_path
        self._needs_training = True

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
        if not self.records:
            return "empty"
        latest = self.records[-1]
        return f"{len(self.records)}|{latest.issue}|{latest.draw_date.isoformat()}"

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
            return meta.get("fingerprint") == self._data_fingerprint()
        except Exception:  # noqa: BLE001
            return False

    def _save_metadata(self) -> None:
        """保存模型元数据."""
        meta_path = self._metadata_path()
        if not meta_path:
            return
        meta = {
            "fingerprint": self._data_fingerprint(),
            "record_count": len(self.records),
            "lookback": self.lookback,
        }
        if self.records:
            latest = self.records[-1]
            meta["last_issue"] = latest.issue
            meta["last_draw_date"] = latest.draw_date.isoformat()
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def train(self) -> None:
        """使用全部历史数据训练模型."""
        X, y_red, y_blue = build_features(self.records, self.lookback)
        if X.shape[0] == 0:
            raise ValueError("历史数据不足，无法训练模型")
        self.model.fit(X, y_red, y_blue)
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

        Args:
            red_count: 推荐红球个数。
            blue_count: 推荐蓝球个数。
            diversity_boost: 多样性增强系数，避免总是选相似号码。
            rng: 随机数生成器，用于多样化采样。

        Returns:
            reds: 推荐红球列表
            blues: 推荐蓝球列表
        """
        if rng is None:
            rng = np.random.RandomState()

        red_proba, blue_proba = self.predict()

        # 对概率进行加权随机采样，既尊重模型预测又保证多样性
        # 加入少量噪声，避免每次结果完全相同
        red_weights = red_proba + 0.05
        red_weights = red_weights / red_weights.sum()
        blue_weights = blue_proba + 0.05
        blue_weights = blue_weights / blue_weights.sum()

        selected_reds: List[int] = []
        available_reds = list(range(1, 34))
        red_p = red_weights.copy()

        while len(selected_reds) < red_count:
            # 多样性惩罚：与已选号码相邻的概率降低
            if selected_reds and diversity_boost > 0:
                for s in selected_reds:
                    for neighbor in range(max(1, s - 1), min(34, s + 2)):
                        if neighbor in available_reds:
                            idx_in_available = available_reds.index(neighbor)
                            red_p[idx_in_available] *= (1 - diversity_boost * 0.5)
                red_p = red_p / red_p.sum()

            idx = rng.choice(len(available_reds), p=red_p)
            n = available_reds[idx]
            selected_reds.append(n)
            available_reds.pop(idx)
            red_p = np.delete(red_p, idx)

        selected_blues = rng.choice(
            range(1, 17), size=blue_count, replace=False, p=blue_weights
        ).tolist()

        return sorted(selected_reds), selected_blues

    def is_ready(self) -> bool:
        """模型是否已准备好."""
        return self.model.is_trained or not self._needs_training
