"""特征工程自动化管道.

提供自动化的特征工程流程，包括：
- 特征构建与组合
- 特征选择与降维
- 特征重要性分析
- 特征缓存与管理
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from ..data.models import DrawRecord
from .features import (
    RED_COUNT,
    BLUE_COUNT,
    _extract_window_features,
    _number_features,
    _window_stats,
    _correlation_features,
    _zone_distribution,
    _ac_value_features,
    _sum_distribution,
)

logger = logging.getLogger(__name__)


@dataclass
class FeatureConfig:
    """特征配置."""

    lookback: int = 50
    use_number_features: bool = True
    use_window_stats: bool = True
    use_correlation_features: bool = True
    use_zone_distribution: bool = True
    use_ac_value_features: bool = True
    use_sum_distribution: bool = True
    use_time_features: bool = True
    use_lag_features: bool = False
    use_rolling_features: bool = False
    lag_periods: List[int] = field(default_factory=lambda: [1, 2, 3])
    rolling_windows: List[int] = field(default_factory=lambda: [5, 10, 20])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lookback": self.lookback,
            "use_number_features": self.use_number_features,
            "use_window_stats": self.use_window_stats,
            "use_correlation_features": self.use_correlation_features,
            "use_zone_distribution": self.use_zone_distribution,
            "use_ac_value_features": self.use_ac_value_features,
            "use_sum_distribution": self.use_sum_distribution,
            "use_time_features": self.use_time_features,
            "use_lag_features": self.use_lag_features,
            "use_rolling_features": self.use_rolling_features,
            "lag_periods": self.lag_periods,
            "rolling_windows": self.rolling_windows,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FeatureConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class FeatureMetadata:
    """特征元数据."""

    feature_names: List[str] = field(default_factory=list)
    feature_count: int = 0
    config: FeatureConfig = field(default_factory=FeatureConfig)
    data_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_names": self.feature_names,
            "feature_count": self.feature_count,
            "config": self.config.to_dict(),
            "data_hash": self.data_hash,
        }


class FeaturePipeline:
    """特征工程自动化管道."""

    def __init__(
        self,
        config: Optional[FeatureConfig] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.config = config or FeatureConfig()
        self.cache_dir = cache_dir
        self._feature_extractors: List[Callable] = []
        self._setup_extractors()

    def _setup_extractors(self) -> None:
        """设置特征提取器."""
        self._feature_extractors = []

        if self.config.use_number_features:
            self._feature_extractors.append(("number", self._extract_number_features))

        if self.config.use_window_stats:
            self._feature_extractors.append(("window_stats", self._extract_window_stats))

        if self.config.use_correlation_features:
            self._feature_extractors.append(("correlation", self._extract_correlation_features))

        if self.config.use_zone_distribution:
            self._feature_extractors.append(("zone", self._extract_zone_distribution))

        if self.config.use_ac_value_features:
            self._feature_extractors.append(("ac_value", self._extract_ac_value_features))

        if self.config.use_sum_distribution:
            self._feature_extractors.append(("sum_dist", self._extract_sum_distribution))

        if self.config.use_time_features:
            self._feature_extractors.append(("time", self._extract_time_features))

        if self.config.use_lag_features:
            self._feature_extractors.append(("lag", self._extract_lag_features))

        if self.config.use_rolling_features:
            self._feature_extractors.append(("rolling", self._extract_rolling_features))

    def _extract_number_features(
        self, window: List[DrawRecord], records: List[DrawRecord], idx: int
    ) -> List[float]:
        """提取号码特征."""
        features = []
        for n in range(1, RED_COUNT + 1):
            features.extend(_number_features(window, n, is_red=True))
        for n in range(1, BLUE_COUNT + 1):
            features.extend(_number_features(window, n, is_red=False))
        return features

    def _extract_window_stats(
        self, window: List[DrawRecord], records: List[DrawRecord], idx: int
    ) -> List[float]:
        """提取窗口统计特征."""
        return _window_stats(window)

    def _extract_correlation_features(
        self, window: List[DrawRecord], records: List[DrawRecord], idx: int
    ) -> List[float]:
        """提取关联性特征."""
        return _correlation_features(window)

    def _extract_zone_distribution(
        self, window: List[DrawRecord], records: List[DrawRecord], idx: int
    ) -> List[float]:
        """提取区间分布特征."""
        return _zone_distribution(window)

    def _extract_ac_value_features(
        self, window: List[DrawRecord], records: List[DrawRecord], idx: int
    ) -> List[float]:
        """提取 AC 值特征."""
        return _ac_value_features(window)

    def _extract_sum_distribution(
        self, window: List[DrawRecord], records: List[DrawRecord], idx: int
    ) -> List[float]:
        """提取和值分布特征."""
        return _sum_distribution(window)

    def _extract_time_features(
        self, window: List[DrawRecord], records: List[DrawRecord], idx: int
    ) -> List[float]:
        """提取时间特征."""
        last = window[-1]
        return [
            last.draw_date.month / 12.0,
            last.draw_date.day / 31.0,
            last.draw_date.weekday() / 7.0,
        ]

    def _extract_lag_features(
        self, window: List[DrawRecord], records: List[DrawRecord], idx: int
    ) -> List[float]:
        """提取滞后特征."""
        features = []
        for lag in self.config.lag_periods:
            if idx - lag >= 0:
                lag_record = records[idx - lag]
                # 红球总和
                features.append(sum(lag_record.red_balls) / 200.0)
                # 蓝球
                features.append((lag_record.blue_ball or 0) / 16.0)
            else:
                features.extend([0.0, 0.0])
        return features

    def _extract_rolling_features(
        self, window: List[DrawRecord], records: List[DrawRecord], idx: int
    ) -> List[float]:
        """提取滚动统计特征."""
        features = []
        for w in self.config.rolling_windows:
            if idx >= w:
                recent = records[idx - w: idx]
                sums = [sum(r.red_balls) for r in recent]
                features.extend([
                    np.mean(sums) / 200.0,
                    np.std(sums) / 50.0 if len(sums) > 1 else 0.0,
                ])
            else:
                features.extend([0.0, 0.0])
        return features

    def _compute_data_hash(self, records: List[DrawRecord]) -> str:
        """计算数据哈希用于缓存."""
        if not records:
            return "empty"
        data_str = f"{len(records)}_{records[-1].issue}_{records[-1].draw_date}"
        return hashlib.md5(data_str.encode()).hexdigest()[:16]

    def build_features(
        self, records: List[DrawRecord]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """构建训练特征和标签."""
        if any(r.profile.key != "ssq" for r in records):
            raise ValueError("feature_pipeline 仅支持双色球记录")
        if self.config.lookback <= 0:
            raise ValueError("lookback 必须大于 0")
        if len(records) <= self.config.lookback:
            return np.array([]), np.array([]), np.array([])

        samples = len(records) - self.config.lookback
        X = []
        y_red = []
        y_blue = []

        for i in range(self.config.lookback, len(records)):
            window = records[i - self.config.lookback: i]
            next_record = records[i]

            # 提取所有特征
            features = []
            for name, extractor in self._feature_extractors:
                features.extend(extractor(window, records, i))

            X.append(features)

            # 标签
            red_label = np.zeros(RED_COUNT, dtype=np.int32)
            for n in next_record.red_balls:
                if 1 <= n <= RED_COUNT:
                    red_label[n - 1] = 1
            y_red.append(red_label)

            blue_label = np.zeros(BLUE_COUNT, dtype=np.int32)
            blue = next_record.blue_ball
            if blue is not None and 1 <= blue <= BLUE_COUNT:
                blue_label[blue - 1] = 1
            y_blue.append(blue_label)

        return np.array(X), np.array(y_red), np.array(y_blue)

    def build_prediction_features(
        self, records: List[DrawRecord]
    ) -> np.ndarray:
        """为最新一期构建预测特征."""
        if any(r.profile.key != "ssq" for r in records):
            raise ValueError("feature_pipeline 仅支持双色球记录")
        if self.config.lookback <= 0:
            raise ValueError("lookback 必须大于 0")
        if len(records) < self.config.lookback:
            return np.array([])

        window = records[-self.config.lookback:]
        idx = len(records) - 1

        features = []
        for name, extractor in self._feature_extractors:
            features.extend(extractor(window, records, idx))

        return np.array(features).reshape(1, -1)

    def get_feature_names(self) -> List[str]:
        """获取特征名称列表."""
        names = []

        if self.config.use_number_features:
            for n in range(1, RED_COUNT + 1):
                names.extend([
                    f"red_{n}_count", f"red_{n}_last_dist", f"red_{n}_freq",
                    f"red_{n}_gap_mean", f"red_{n}_gap_std",
                    f"red_{n}_gap_max", f"red_{n}_gap_min",
                    f"red_{n}_streak", f"red_{n}_max_hit",
                ])
            for n in range(1, BLUE_COUNT + 1):
                names.extend([
                    f"blue_{n}_count", f"blue_{n}_last_dist", f"blue_{n}_freq",
                    f"blue_{n}_gap_mean", f"blue_{n}_gap_std",
                    f"blue_{n}_gap_max", f"blue_{n}_gap_min",
                    f"blue_{n}_streak", f"blue_{n}_max_hit",
                ])

        if self.config.use_window_stats:
            names.extend(["w_mean_sum", "w_std_sum", "w_mean_odd", "w_mean_high", "w_mean_blue"])

        if self.config.use_correlation_features:
            names.extend(["adj_freq", "adj_possible", "avg_cooccur"])

        if self.config.use_zone_distribution:
            names.extend(["zone1", "zone2", "zone3", "zone_std"])

        if self.config.use_ac_value_features:
            names.extend(["ac_mean", "ac_std", "ac_min"])

        if self.config.use_sum_distribution:
            names.extend(["sum_z1", "sum_z2", "sum_z3", "sum_z4"])

        if self.config.use_time_features:
            names.extend(["month", "day", "weekday"])

        if self.config.use_lag_features:
            for lag in self.config.lag_periods:
                names.extend([f"lag_{lag}_sum", f"lag_{lag}_blue"])

        if self.config.use_rolling_features:
            for w in self.config.rolling_windows:
                names.extend([f"roll_{w}_mean", f"roll_{w}_std"])

        return names

    def analyze_feature_importance(
        self,
        X: np.ndarray,
        y: np.ndarray,
        top_n: int = 20,
    ) -> List[Tuple[str, float]]:
        """分析特征重要性（基于方差）。"""
        if X.shape[0] == 0 or X.shape[1] == 0:
            return []

        # 计算每个特征与目标的相关性
        correlations = []
        for i in range(X.shape[1]):
            if np.std(X[:, i]) > 0:
                corr = abs(np.corrcoef(X[:, i], y)[0, 1])
                correlations.append((i, corr))
            else:
                correlations.append((i, 0.0))

        # 按相关性排序
        correlations.sort(key=lambda x: x[1], reverse=True)

        # 获取特征名称
        feature_names = self.get_feature_names()

        result = []
        for idx, corr in correlations[:top_n]:
            name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
            result.append((name, corr))

        return result

    def select_features(
        self,
        X: np.ndarray,
        y: np.ndarray,
        threshold: float = 0.01,
    ) -> Tuple[np.ndarray, List[int]]:
        """选择重要特征。"""
        if X.shape[0] == 0 or X.shape[1] == 0:
            return X, []

        # 计算特征方差
        variances = np.var(X, axis=0)

        # 选择方差大于阈值的特征
        selected_indices = np.where(variances > threshold)[0]

        return X[:, selected_indices], selected_indices.tolist()

    def get_metadata(self, records: List[DrawRecord]) -> FeatureMetadata:
        """获取特征元数据."""
        return FeatureMetadata(
            feature_names=self.get_feature_names(),
            feature_count=len(self.get_feature_names()),
            config=self.config,
            data_hash=self._compute_data_hash(records),
        )

    def save_config(self, path: Path) -> None:
        """保存特征配置."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info("特征配置已保存到 %s", path)

    def load_config(self, path: Path) -> None:
        """加载特征配置."""
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.config = FeatureConfig.from_dict(data)
        self._setup_extractors()
        logger.info("特征配置已从 %s 加载", path)
