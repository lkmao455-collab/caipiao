"""特征工程自动化管道测试."""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord
from caipiao.ml.feature_pipeline import FeatureConfig, FeatureMetadata, FeaturePipeline


class TestFeatureConfig:
    """FeatureConfig 测试."""

    def test_default_config(self):
        config = FeatureConfig()
        assert config.lookback == 50
        assert config.use_number_features is True
        assert config.use_window_stats is True

    def test_to_dict(self):
        config = FeatureConfig(lookback=30)
        d = config.to_dict()
        assert d["lookback"] == 30
        assert "use_number_features" in d

    def test_from_dict(self):
        d = {"lookback": 30, "use_number_features": False}
        config = FeatureConfig.from_dict(d)
        assert config.lookback == 30
        assert config.use_number_features is False


class TestFeatureMetadata:
    """FeatureMetadata 测试."""

    def test_initial_state(self):
        meta = FeatureMetadata()
        assert meta.feature_count == 0

    def test_to_dict(self):
        meta = FeatureMetadata(
            feature_names=["f1", "f2"],
            feature_count=2,
            data_hash="abc123",
        )
        d = meta.to_dict()
        assert d["feature_count"] == 2
        assert d["data_hash"] == "abc123"


class TestFeaturePipeline:
    """FeaturePipeline 测试."""

    def test_initialization(self):
        pipeline = FeaturePipeline()
        assert pipeline.config.lookback == 50

    def test_custom_config(self):
        config = FeatureConfig(lookback=30, use_time_features=False)
        pipeline = FeaturePipeline(config=config)
        assert pipeline.config.lookback == 30
        assert pipeline.config.use_time_features is False

    def test_build_features_empty(self):
        pipeline = FeaturePipeline(FeatureConfig(lookback=10))
        X, y_red, y_blue = pipeline.build_features([])
        assert X.shape == (0,)
        assert y_red.shape == (0,)
        assert y_blue.shape == (0,)

    def test_build_features_insufficient(self):
        pipeline = FeaturePipeline(FeatureConfig(lookback=100))
        records = _make_ssq_records(50)
        X, y_red, y_blue = pipeline.build_features(records)
        assert X.shape == (0,)

    def test_build_features(self):
        pipeline = FeaturePipeline(FeatureConfig(lookback=10))
        records = _make_ssq_records(50)
        X, y_red, y_blue = pipeline.build_features(records)
        assert X.shape[0] == 40  # 50 - 10
        assert y_red.shape[0] == 40
        assert y_blue.shape[0] == 40

    def test_build_prediction_features(self):
        pipeline = FeaturePipeline(FeatureConfig(lookback=10))
        records = _make_ssq_records(50)
        X = pipeline.build_prediction_features(records)
        assert X.shape[0] == 1
        assert X.shape[1] > 0

    def test_build_prediction_features_insufficient(self):
        pipeline = FeaturePipeline(FeatureConfig(lookback=100))
        records = _make_ssq_records(50)
        X = pipeline.build_prediction_features(records)
        assert X.shape == (0,)

    def test_get_feature_names(self):
        pipeline = FeaturePipeline(FeatureConfig(lookback=10))
        names = pipeline.get_feature_names()
        assert len(names) > 0
        assert "month" in names

    def test_analyze_feature_importance(self):
        pipeline = FeaturePipeline(FeatureConfig(lookback=10))
        records = _make_ssq_records(50)
        X, y_red, y_blue = pipeline.build_features(records)
        importance = pipeline.analyze_feature_importance(X, y_red[:, 0], top_n=10)
        assert len(importance) == 10
        assert all(isinstance(name, str) for name, _ in importance)

    def test_select_features(self):
        pipeline = FeaturePipeline(FeatureConfig(lookback=10))
        records = _make_ssq_records(50)
        X, y_red, y_blue = pipeline.build_features(records)
        X_selected, indices = pipeline.select_features(X, y_red[:, 0])
        assert X_selected.shape[0] == X.shape[0]
        assert len(indices) > 0

    def test_get_metadata(self):
        pipeline = FeaturePipeline(FeatureConfig(lookback=10))
        records = _make_ssq_records(50)
        meta = pipeline.get_metadata(records)
        assert meta.feature_count > 0
        assert meta.data_hash != ""

    def test_save_load_config(self, tmp_path):
        config = FeatureConfig(lookback=30)
        pipeline = FeaturePipeline(config=config)
        path = tmp_path / "config.json"
        pipeline.save_config(path)

        new_pipeline = FeaturePipeline()
        new_pipeline.load_config(path)
        assert new_pipeline.config.lookback == 30


class TestFeaturePipelineConfigurations:
    """不同配置的特征管道测试."""

    def test_minimal_config(self):
        config = FeatureConfig(
            lookback=10,
            use_number_features=False,
            use_window_stats=False,
            use_correlation_features=False,
            use_zone_distribution=False,
            use_ac_value_features=False,
            use_sum_distribution=False,
            use_time_features=True,
        )
        pipeline = FeaturePipeline(config)
        records = _make_ssq_records(50)
        X, y_red, y_blue = pipeline.build_features(records)
        assert X.shape[0] == 40
        # 只有时间特征
        assert X.shape[1] == 3

    def test_full_config(self):
        config = FeatureConfig(
            lookback=10,
            use_number_features=True,
            use_window_stats=True,
            use_correlation_features=True,
            use_zone_distribution=True,
            use_ac_value_features=True,
            use_sum_distribution=True,
            use_time_features=True,
            use_lag_features=True,
            use_rolling_features=True,
        )
        pipeline = FeaturePipeline(config)
        records = _make_ssq_records(50)
        X, y_red, y_blue = pipeline.build_features(records)
        assert X.shape[0] == 40
        # 特征数量应该很多
        assert X.shape[1] > 100


def _make_ssq_records(count: int = 50) -> list:
    """创建测试用的双色球记录."""
    records = []
    for i in range(count):
        reds = sorted([(i + j) % 33 + 1 for j in range(6)])
        blue = (i % 16) + 1
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=reds,
            blue_ball=blue,
        ))
    return records
