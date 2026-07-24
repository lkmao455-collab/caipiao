"""性能优化模块测试."""

import numpy as np
import pytest

from caipiao.ml.optimization import (
    BatchProcessor,
    FeatureCache,
    MemoryOptimizer,
    OptimizedFeatureExtractor,
    PerformanceMonitor,
    timer,
)


class TestOptimizedFeatureExtractor:
    """优化的特征提取器测试."""

    def test_initialization(self):
        extractor = OptimizedFeatureExtractor(window_size=50)
        assert extractor.window_size == 50

    def test_extract_features(self):
        extractor = OptimizedFeatureExtractor(window_size=10)
        red_balls = np.random.randint(1, 34, size=(10, 6))
        blue_balls = np.random.randint(1, 17, size=(10,))
        features = extractor.extract_features_vectorized(red_balls, blue_balls)
        assert features.shape[0] > 0
        assert features.dtype == np.float32


class TestFeatureCache:
    """特征缓存测试."""

    def test_initialization(self):
        cache = FeatureCache(max_size=100)
        assert cache.size == 0

    def test_set_get(self):
        cache = FeatureCache()
        features = np.random.rand(10)
        cache.set("key1", features)
        assert cache.size == 1
        result = cache.get("key1")
        assert result is not None
        np.testing.assert_array_equal(result, features)

    def test_get_miss(self):
        cache = FeatureCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_lru_eviction(self):
        cache = FeatureCache(max_size=2)
        cache.set("key1", np.array([1]))
        cache.set("key2", np.array([2]))
        cache.set("key3", np.array([3]))  # 应该淘汰 key1
        assert cache.size == 2
        assert cache.get("key1") is None

    def test_clear(self):
        cache = FeatureCache()
        cache.set("key1", np.array([1]))
        cache.clear()
        assert cache.size == 0


class TestBatchProcessor:
    """批量处理器测试."""

    def test_initialization(self):
        processor = BatchProcessor(batch_size=10)
        assert processor.batch_size == 10

    def test_process_in_batches(self):
        processor = BatchProcessor(batch_size=5)
        data = np.random.rand(12, 10)
        result = processor.process_in_batches(data, lambda x: x * 2)
        assert result.shape == (12, 10)
        np.testing.assert_array_almost_equal(result, data * 2)


class TestMemoryOptimizer:
    """内存优化器测试."""

    def test_optimize_array(self):
        arr = np.random.rand(10).astype(np.float64)
        optimized = MemoryOptimizer.optimize_array(arr, np.float32)
        assert optimized.dtype == np.float32

    def test_compress_sparse(self):
        features = np.random.rand(10, 20)
        features[:, 5] = 0  # 使第 5 列方差为 0
        compressed, indices = MemoryOptimizer.compress_sparse(features, threshold=0.01)
        assert compressed.shape[1] < 20

    def test_estimate_memory(self):
        arr = np.random.rand(1000, 100)
        memory = MemoryOptimizer.estimate_memory_usage(arr)
        assert memory > 0


class TestPerformanceMonitor:
    """性能监控器测试."""

    def test_initialization(self):
        monitor = PerformanceMonitor()
        assert len(monitor.metrics) == 0

    def test_record(self):
        monitor = PerformanceMonitor()
        monitor.record("test", 0.1)
        monitor.record("test", 0.2)
        assert len(monitor.metrics["test"]) == 2

    def test_get_stats(self):
        monitor = PerformanceMonitor()
        monitor.record("test", 0.1)
        monitor.record("test", 0.2)
        stats = monitor.get_stats("test")
        assert stats["count"] == 2
        assert abs(stats["mean"] - 0.15) < 1e-10

    def test_summary(self):
        monitor = PerformanceMonitor()
        monitor.record("test", 0.1)
        summary = monitor.summary()
        assert "性能统计" in summary


class TestTimerDecorator:
    """计时装饰器测试."""

    def test_timer(self):
        @timer
        def slow_function():
            return sum(range(1000))

        result = slow_function()
        assert result == 499500
