"""机器学习模块测试."""

from datetime import datetime

import numpy as np

from caipiao.data.models import DrawRecord
from caipiao.ml.features import build_features
from caipiao.ml.predictor import MLPredictor


def make_records(count: int = 120):
    records = []
    base = datetime(2024, 1, 1)
    for i in range(count):
        # Generate deterministic pseudo-random numbers
        nums = [(i * 7 + j * 13) % 33 + 1 for j in range(6)]
        blue = (i * 5 + 3) % 16 + 1
        records.append(
            DrawRecord(
                issue=f"2024{i+1:03d}",
                draw_date=base,
                red_balls=sorted(nums),
                blue_ball=blue,
            )
        )
    return records


def test_build_features_shape():
    records = make_records(120)
    X, y_red, y_blue = build_features(records, lookback=50)
    assert X.shape[0] == 70
    assert y_red.shape == (70, 33)
    assert y_blue.shape == (70, 16)


def test_predictor_train_and_predict():
    records = make_records(120)
    predictor = MLPredictor(records, lookback=50, model_path=None)
    predictor.train()
    red_proba, blue_proba = predictor.predict()
    assert red_proba.shape == (33,)
    assert blue_proba.shape == (16,)
    assert np.all(red_proba >= 0) and np.all(red_proba <= 1)
    assert np.all(blue_proba >= 0) and np.all(blue_proba <= 1)


def test_predictor_recommend():
    records = make_records(120)
    predictor = MLPredictor(records, lookback=50, model_path=None)
    reds, blues = predictor.recommend(red_count=6, blue_count=1)
    assert len(reds) == 6
    assert len(blues) == 1
    assert all(1 <= n <= 33 for n in reds)
    assert 1 <= blues[0] <= 16
