"""ML 特征工程测试."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord
from caipiao.ml.features import (
    build_features,
    build_incremental_features,
    build_prediction_features,
)


class TestBuildFeatures:
    """build_features 测试."""

    def test_empty_records(self):
        X, y_red, y_blue = build_features([], lookback=50)
        assert X.shape == (0,)
        assert y_red.shape == (0,)
        assert y_blue.shape == (0,)

    def test_insufficient_records(self):
        records = _make_ssq_records(30)
        X, y_red, y_blue = build_features(records, lookback=50)
        assert X.shape == (0,)

    def test_valid_records(self):
        records = _make_ssq_records(100)
        X, y_red, y_blue = build_features(records, lookback=50)
        assert X.shape[0] == 50
        assert y_red.shape[0] == 50
        assert y_blue.shape[0] == 50

    def test_invalid_lookback(self):
        records = _make_ssq_records(100)
        with pytest.raises(ValueError, match="lookback"):
            build_features(records, lookback=0)

    def test_non_ssq_records(self):
        records = _make_3d_records(100)
        with pytest.raises(ValueError, match="双色球"):
            build_features(records, lookback=50)


class TestBuildIncrementalFeatures:
    """build_incremental_features 测试."""

    def test_empty_records(self):
        X, y_red, y_blue = build_incremental_features([], lookback=50, new_count=1)
        assert X.shape == (0,)

    def test_valid_incremental(self):
        records = _make_ssq_records(100)
        X, y_red, y_blue = build_incremental_features(records, lookback=50, new_count=5)
        assert X.shape[0] == 5
        assert y_red.shape[0] == 5

    def test_new_count_exceeds(self):
        records = _make_ssq_records(100)
        X, y_red, y_blue = build_incremental_features(records, lookback=50, new_count=100)
        assert X.shape[0] == 50


class TestBuildPredictionFeatures:
    """build_prediction_features 测试."""

    def test_empty_records(self):
        X = build_prediction_features([], lookback=50)
        assert X.shape == (0,)

    def test_insufficient_records(self):
        records = _make_ssq_records(30)
        X = build_prediction_features(records, lookback=50)
        assert X.shape == (0,)

    def test_valid_prediction(self):
        records = _make_ssq_records(100)
        X = build_prediction_features(records, lookback=50)
        assert X.shape[0] == 1
        assert X.shape[1] > 0


def _make_ssq_records(count: int = 100) -> list:
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


def _make_3d_records(count: int = 100) -> list:
    """创建测试用的 3D 记录."""
    records = []
    for i in range(count):
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [i % 10, (i + 1) % 10, (i + 2) % 10]},
        ))
    return records
