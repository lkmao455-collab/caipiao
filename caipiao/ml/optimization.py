"""性能优化模块.

提供特征工程和数据处理的优化版本，使用 NumPy 向量化操作
替代 Python 循环，显著提升性能。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def cached_property(func: Callable) -> property:
    """缓存属性装饰器."""
    attr_name = f"_cached_{func.__name__}"

    @property
    def wrapper(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, func(self))
        return getattr(self, attr_name)

    return wrapper


def timer(func: Callable) -> Callable:
    """计时装饰器."""
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.debug("%s 执行时间: %.4f 秒", func.__name__, elapsed)
        return result
    return wrapper


class OptimizedFeatureExtractor:
    """优化的特征提取器.

    使用 NumPy 向量化操作替代 Python 循环。
    """

    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self._number_cache: dict[int, np.ndarray] = {}

    @timer
    def extract_features_vectorized(
        self,
        red_balls_matrix: np.ndarray,
        blue_balls: np.ndarray,
    ) -> np.ndarray:
        """向量化特征提取.

        Args:
            red_balls_matrix: 形状 (window_size, 6) 的红球矩阵
            blue_balls: 形状 (window_size,) 的蓝球数组

        Returns:
            特征向量
        """
        features = []

        # 1. 红球统计特征（向量化）
        red_features = self._extract_red_features_vectorized(red_balls_matrix)
        features.extend(red_features)

        # 2. 蓝球统计特征
        blue_features = self._extract_blue_features_vectorized(blue_balls)
        features.extend(blue_features)

        # 3. 窗口统计特征（向量化）
        window_features = self._extract_window_features_vectorized(
            red_balls_matrix, blue_balls
        )
        features.extend(window_features)

        return np.array(features, dtype=np.float32)

    def _extract_red_features_vectorized(
        self, red_balls_matrix: np.ndarray
    ) -> list[float]:
        """向量化提取红球特征."""
        features = []

        # 每个号码的出现次数（向量化）
        for num in range(1, 34):
            # 检查号码是否在每期中出现
            appears = np.any(red_balls_matrix == num, axis=1)
            count = np.sum(appears)
            last_idx = np.max(np.where(appears)[0]) if count > 0 else -1
            last_distance = (len(appears) - 1 - last_idx) if count > 0 else len(appears)

            features.append(count / 10.0)
            features.append(last_distance / len(appears))
            features.append(count / len(appears))

        return features

    def _extract_blue_features_vectorized(
        self, blue_balls: np.ndarray
    ) -> list[float]:
        """向量化提取蓝球特征."""
        features = []

        for num in range(1, 17):
            appears = blue_balls == num
            count = np.sum(appears)
            last_idx = np.max(np.where(appears)[0]) if count > 0 else -1
            last_distance = (len(appears) - 1 - last_idx) if count > 0 else len(appears)

            features.append(count / 10.0)
            features.append(last_distance / len(appears))
            features.append(count / len(appears))

        return features

    def _extract_window_features_vectorized(
        self,
        red_balls_matrix: np.ndarray,
        blue_balls: np.ndarray,
    ) -> list[float]:
        """向量化提取窗口统计特征."""
        # 红球总和
        red_sums = np.sum(red_balls_matrix, axis=1)
        mean_sum = np.mean(red_sums) / 200.0
        std_sum = np.std(red_sums) / 50.0 if len(red_sums) > 1 else 0.0

        # 奇数个数
        odd_counts = np.sum(red_balls_matrix % 2 == 1, axis=1)
        mean_odd = np.mean(odd_counts) / 6.0

        # 大号个数 (>=17)
        high_counts = np.sum(red_balls_matrix >= 17, axis=1)
        mean_high = np.mean(high_counts) / 6.0

        # 蓝球均值
        mean_blue = np.mean(blue_balls) / 16.0 if len(blue_balls) > 0 else 0.0

        return [mean_sum, std_sum, mean_odd, mean_high, mean_blue]


class FeatureCache:
    """特征缓存."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: dict[str, tuple[np.ndarray, float]] = {}
        self._access_count: dict[str, int] = {}

    def get(self, key: str) -> np.ndarray | None:
        """获取缓存的特征."""
        if key in self._cache:
            self._access_count[key] = self._access_count.get(key, 0) + 1
            return self._cache[key][0]
        return None

    def set(self, key: str, features: np.ndarray) -> None:
        """设置缓存的特征."""
        if len(self._cache) >= self.max_size:
            # LRU 淘汰
            min_key = min(self._access_count, key=self._access_count.get)
            del self._cache[min_key]
            del self._access_count[min_key]

        self._cache[key] = (features, time.time())
        self._access_count[key] = 1

    def clear(self) -> None:
        """清空缓存."""
        self._cache.clear()
        self._access_count.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class BatchProcessor:
    """批量处理器."""

    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size

    def process_in_batches(
        self,
        data: np.ndarray,
        processor: Callable[[np.ndarray], np.ndarray],
    ) -> np.ndarray:
        """分批处理数据."""
        n_samples = data.shape[0]
        results = []

        for i in range(0, n_samples, self.batch_size):
            batch = data[i: i + self.batch_size]
            processed = processor(batch)
            results.append(processed)

        return np.vstack(results)

    def parallel_process(
        self,
        data: list[Any],
        processor: Callable[[Any], Any],
        n_workers: int = 4,
    ) -> list[Any]:
        """并行处理数据."""
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            results = list(executor.map(processor, data))

        return results


class MemoryOptimizer:
    """内存优化器."""

    @staticmethod
    def optimize_array(arr: np.ndarray, dtype: np.float32 = np.float32) -> np.ndarray:
        """优化数组内存使用."""
        if arr.dtype == dtype:
            return arr
        return arr.astype(dtype)

    @staticmethod
    def compress_sparse(features: np.ndarray, threshold: float = 0.01) -> tuple[np.ndarray, list[int]]:
        """压缩稀疏特征."""
        # 找出方差大于阈值的特征
        variances = np.var(features, axis=0)
        selected = np.where(variances > threshold)[0]
        return features[:, selected], selected.tolist()

    @staticmethod
    def estimate_memory_usage(arr: np.ndarray) -> float:
        """估算数组内存使用（MB）."""
        return arr.nbytes / (1024 * 1024)


def optimize_imports():
    """优化导入（延迟导入）."""


# 性能监控装饰器
class PerformanceMonitor:
    """性能监控器."""

    def __init__(self):
        self.metrics: dict[str, list[float]] = {}

    def record(self, name: str, duration: float):
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append(duration)

    def get_stats(self, name: str) -> dict[str, float]:
        if name not in self.metrics:
            return {}
        values = self.metrics[name]
        return {
            "count": len(values),
            "mean": np.mean(values),
            "std": np.std(values),
            "min": np.min(values),
            "max": np.max(values),
            "total": np.sum(values),
        }

    def summary(self) -> str:
        lines = ["性能统计:", "=" * 40]
        for name in self.metrics:
            stats = self.get_stats(name)
            lines.append(
                f"{name}: {stats['count']} 次, "
                f"平均 {stats['mean']:.4f}s, "
                f"总计 {stats['total']:.4f}s"
            )
        return "\n".join(lines)


# 全局性能监控器
perf_monitor = PerformanceMonitor()
