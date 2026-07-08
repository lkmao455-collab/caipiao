"""SSQ ML 底层隔离测试."""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pytest

from caipiao.core.profile import SSQ
from caipiao.data.models import DrawRecord
from caipiao.ml.lotteries.ssq import (
    SSQPredictor,
    build_features,
    build_prediction_features,
)
from caipiao.ml.lotteries.ssq.models.catboost import SSQCatBoostModel
from caipiao.ml.lotteries.ssq.models.lightgbm import SSQLightGBMModel
from caipiao.ml.lotteries.ssq.models.xgboost import SSQXGBoostModel


def make_ssq_history(n=120):
    rng = __import__("random").Random(0)
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=sorted(rng.sample(range(1, 34), 6)),
            blue_ball=rng.randint(1, 16),
        )
        for i in range(n)
    ]


def test_build_features_returns_x_and_y_dict():
    records = make_ssq_history(120)
    X, y_dict = build_features(records, lookback=50)
    assert X.ndim == 2
    assert X.shape[0] == len(records) - 50
    assert "red" in y_dict and "blue" in y_dict
    assert y_dict["red"].shape == (X.shape[0], 33)
    assert y_dict["blue"].shape == (X.shape[0], 16)


def test_build_prediction_features_shape():
    records = make_ssq_history(120)
    X_pred = build_prediction_features(records, lookback=50)
    assert X_pred.ndim == 2
    assert X_pred.shape[0] == 1
    # 与训练特征维度一致
    X, _ = build_features(records, lookback=50)
    assert X_pred.shape[1] == X.shape[1]


def test_ssq_predictor_interface_matches_legacy_mlpredictor():
    """SSQPredictor 应提供与旧 MLPredictor 兼容的接口."""
    records = make_ssq_history(120)
    predictor = SSQPredictor(records, lookback=50, backend="xgboost")

    red_proba, blue_proba = predictor.predict()
    assert red_proba.shape == (33,)
    assert blue_proba.shape == (16,)
    assert np.isclose(red_proba.sum(), 1.0, atol=1e-3)
    assert np.all((blue_proba >= 0) & (blue_proba <= 1))

    reds, blues = predictor.recommend(red_count=6, blue_count=1)
    assert len(reds) == 6
    assert len(set(reds)) == 6
    assert all(1 <= n <= 33 for n in reds)
    assert len(blues) == 1
    assert all(1 <= n <= 16 for n in blues)


@pytest.mark.parametrize("backend", ["xgboost", "lightgbm", "catboost"])
def test_ssq_predictor_all_tree_backends(backend, tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    with patch.dict(os.environ, {"CAIPIAO_MODEL_DIR": str(d)}):
        records = make_ssq_history(120)
        predictor = SSQPredictor(records, lookback=50, backend=backend)
        reds, blues = predictor.recommend(red_count=6, blue_count=1)
        assert len(reds) == 6
        assert len(blues) == 1
        assert predictor.is_ready()


def test_ssq_predictor_model_save_and_load(tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    model_path = d / "ssq_test.pkl"

    records = make_ssq_history(120)
    predictor = SSQPredictor(records, lookback=50, backend="xgboost", model_path=model_path)
    predictor.train()
    assert model_path.exists()

    loaded = SSQPredictor(records, lookback=50, backend="xgboost", model_path=model_path)
    assert loaded.is_ready()
    reds, blues = loaded.recommend(red_count=6, blue_count=1)
    assert len(reds) == 6 and len(blues) == 1


def test_ssq_model_classes_pin_profile():
    assert SSQXGBoostModel().profile.key == "ssq"
    assert SSQLightGBMModel().profile.key == "ssq"
    assert SSQCatBoostModel().profile.key == "ssq"


def test_ssq_predictor_uses_ssq_profile():
    predictor = SSQPredictor(make_ssq_history(120), lookback=50)
    assert predictor.profile.key == "ssq"
