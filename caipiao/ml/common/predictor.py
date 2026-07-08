"""通用机器学习预测器高层接口（按彩种档案驱动）.

镜像 ``caipiao.ml.predictor.MLPredictor`` 的接口，
但支持任意 ``LotteryProfile``。

本模块位于 ``caipiao.ml.common``，为各彩种专属预测器提供可复用的基类。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from ...core.profile import LotteryProfile, NumberGroup
from ...data.models import DrawRecord
from . import model_store
from .features import build_features, build_prediction_features
from .base import LotteryGenericModel

logger = logging.getLogger(__name__)


class BaseMLPredictor:
    """基于历史数据的通用机器学习号码推荐器."""

    def __init__(
        self,
        records: List[DrawRecord],
        profile: LotteryProfile,
        lookback: int = 50,
        model_path: Optional[Path] = None,
        backend: str = "xgboost",
        temp_dir: Optional[str] = None,
    ) -> None:
        self.profile = profile
        self.records = sorted(records, key=lambda r: r.draw_date)
        self.lookback = lookback
        self.model_path = model_path
        self.backend = backend
        self.model = LotteryGenericModel(profile, lookback=lookback, backend=backend, temp_dir=temp_dir)
        self._needs_training = True
        self._feature_count: Optional[int] = None

        if model_path and model_path.exists():
            if self._metadata_matches():
                try:
                    self.model.load(model_path)
                    self._needs_training = False
                    logger.info("已加载与当前数据匹配的 %s 缓存模型", profile.name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("加载模型失败: %s", exc)
            else:
                logger.info("本地缓存模型与当前数据不一致，将重新训练")

    # ------------------------------------------------------------------ #
    # 元数据/指纹（复用 model_store）
    # ------------------------------------------------------------------ #
    def _data_fingerprint(self) -> str:
        return model_store.data_fingerprint(self.records)

    def _metadata_path(self) -> Optional[Path]:
        if not self.model_path:
            return None
        return Path(str(self.model_path) + ".meta.json")

    def _metadata_matches(self) -> bool:
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
            X = build_prediction_features(self.records, self.profile, self.lookback)
            if X.size == 0:
                raise ValueError("历史数据不足，无法计算特征维度")
            self._feature_count = int(X.shape[1])
        return self._feature_count

    def _save_metadata(self) -> None:
        meta_path = self._metadata_path()
        if not meta_path:
            return
        meta = {
            "fingerprint": self._data_fingerprint(),
            "record_count": len(self.records),
            "lookback": self.lookback,
            "feature_count": self._expected_feature_count(),
            "profile": self.profile.key,
            "backend": self.backend,
        }
        if self.records:
            latest = self.records[-1]
            meta["last_issue"] = latest.issue
            meta["last_draw_date"] = latest.draw_date.isoformat()
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # 训练/预测
    # ------------------------------------------------------------------ #
    def train(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        X, y_dict = build_features(self.records, self.profile, self.lookback)
        if X.shape[0] == 0:
            raise ValueError("历史数据不足，无法训练模型")
        self.model.fit(X, y_dict, progress_callback=progress_callback)
        self._needs_training = False
        if self.model_path:
            self.model.save(self.model_path)
            self._save_metadata()
            logger.info("模型已保存，数据指纹：%s", self._data_fingerprint())

    def predict(self) -> Dict[str, np.ndarray]:
        if self._needs_training:
            self.train()
        X = build_prediction_features(self.records, self.profile, self.lookback)
        if X.size == 0:
            raise ValueError("历史数据不足，无法预测")
        return self.model.predict_proba(X)

    # ------------------------------------------------------------------ #
    # 推荐
    # ------------------------------------------------------------------ #
    def recommend(
        self,
        group_picks: Optional[Dict[str, int]] = None,
        diversity_boost: float = 0.3,
        rng: Optional[np.random.RandomState] = None,
    ) -> Dict[str, List[int]]:
        """推荐号码组合.

        Args:
            group_picks: 每个组要选多少个号码；None 则使用组的默认 pick 数量。
            diversity_boost: 多样性增强系数。
            rng: 随机数生成器。

        Returns:
            每个组的推荐号码列表。
        """
        if rng is None:
            rng = np.random.RandomState()

        proba = self.predict()
        X_pred = build_prediction_features(self.records, self.profile, self.lookback)
        if X_pred.size == 0:
            raise ValueError("历史数据不足，无法预测")
        result: Dict[str, List[int]] = {}
        for g in self.profile.pick_groups:
            pick = (
                group_picks[g.key]
                if group_picks and g.key in group_picks
                else getattr(g, "effective_pick_max", g.count)
            )
            if g.positional:
                result[g.key] = self._recommend_positional(g, proba[g.key], rng)
            elif not g.positional and g.count > 1:
                # 组合组使用顺序生成模型采样
                result[g.key] = sorted(self.model.sample_combination(X_pred, g, rng))
            else:
                result[g.key] = self._recommend_combination(g, proba[g.key], pick, diversity_boost, rng)
        return result

    def _recommend_combination(
        self,
        group: NumberGroup,
        proba: np.ndarray,
        pick: int,
        diversity_boost: float,
        rng: np.random.RandomState,
    ) -> List[int]:
        pick = min(pick, len(group.values))
        if pick <= 0:
            return []
        weights = proba + 0.05
        weights = weights / weights.sum()
        available = group.values[:]
        p = weights.copy()
        selected: List[int] = []
        while len(selected) < pick:
            if selected and diversity_boost > 0:
                for s in selected:
                    for neighbor in range(max(group.lo, s - 1), min(group.hi, s + 2) + 1):
                        if neighbor in available:
                            idx = available.index(neighbor)
                            p[idx] *= (1 - diversity_boost * 0.5)
                p = p / p.sum()
            idx = rng.choice(len(available), p=p)
            n = available[idx]
            selected.append(n)
            available.pop(idx)
            p = np.delete(p, idx)
        return sorted(selected)

    def _recommend_positional(
        self,
        group: NumberGroup,
        proba: np.ndarray,
        rng: np.random.RandomState,
    ) -> List[int]:
        """按位组：每位按概率取最高或加权采样。"""
        if proba.ndim != 2 or proba.shape != (group.count, group.size):
            raise ValueError("按位概率矩阵形状与组定义不匹配")
        result = []
        for pos in range(group.count):
            weights = proba[pos] + 0.05
            weights = weights / weights.sum()
            digit = rng.choice(group.values, p=weights)
            result.append(int(digit))
        return result

    def is_ready(self) -> bool:
        return self.model.is_trained


# 向后兼容旧导入路径的别名
GenericMLPredictor = BaseMLPredictor
