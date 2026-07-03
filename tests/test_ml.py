"""机器学习模块测试."""

from datetime import datetime

import numpy as np

from caipiao.data.models import DrawRecord
from caipiao.ml import model_store
from caipiao.ml.features import build_features, build_prediction_features
from caipiao.ml.lgbm_model import LotteryLightGBMModel
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


def test_lightgbm_predictor_train_and_predict():
    records = make_records(120)
    predictor = MLPredictor(
        records, lookback=50, model_path=None, model_class=LotteryLightGBMModel
    )
    predictor.train()
    red_proba, blue_proba = predictor.predict()
    assert red_proba.shape == (33,)
    assert blue_proba.shape == (16,)
    assert np.all(red_proba >= 0) and np.all(red_proba <= 1)
    assert np.all(blue_proba >= 0) and np.all(blue_proba <= 1)


def test_lightgbm_predictor_recommend():
    records = make_records(120)
    predictor = MLPredictor(
        records, lookback=50, model_path=None, model_class=LotteryLightGBMModel
    )
    reds, blues = predictor.recommend(red_count=6, blue_count=1)
    assert len(reds) == 6
    assert len(blues) == 1
    assert all(1 <= n <= 33 for n in reds)
    assert 1 <= blues[0] <= 16


def test_lightgbm_model_save_load(tmp_path):
    records = make_records(120)
    X, y_red, y_blue = build_features(records, lookback=50)

    model = LotteryLightGBMModel(lookback=50)
    model.fit(X, y_red, y_blue)
    assert model.is_trained

    X_pred = build_prediction_features(records, lookback=50)
    red_before, blue_before = model.predict_proba(X_pred)

    path = tmp_path / "lightgbm_model.pkl"
    model.save(path)
    assert path.exists()

    loaded = LotteryLightGBMModel(lookback=1)
    loaded.load(path)
    assert loaded.is_trained
    assert loaded.lookback == 50

    red_after, blue_after = loaded.predict_proba(X_pred)
    assert np.allclose(red_before, red_after)
    assert np.allclose(blue_before, blue_after)


def test_lightgbm_freshness_detection_and_retrain(tmp_path):
    """LightGBM 应能检测模型是否与当前数据匹配，过期时触发重训."""
    records = make_records(120)
    lookback = 50
    path = model_store.new_model_path(records, lookback, directory=tmp_path, prefix="lightgbm")

    # 首次：无缓存模型 -> 需要训练
    p1 = MLPredictor(
        records, lookback=lookback, model_path=path, model_class=LotteryLightGBMModel
    )
    assert not p1.is_ready()
    p1.train()
    assert path.exists()

    # 数据未变：识别为最新，加载缓存而非重训
    assert model_store.is_model_current(
        records, lookback, directory=tmp_path, prefix="lightgbm"
    )
    found = model_store.find_current_model(
        records, lookback, directory=tmp_path, prefix="lightgbm"
    )
    assert found == path
    p2 = MLPredictor(
        records, lookback=lookback, model_path=found, model_class=LotteryLightGBMModel
    )
    assert p2.is_ready()  # 已加载缓存，无需重训

    # 数据变化：模型过期，检测为不最新（据此自动重训）
    records2 = make_records(121)
    assert not model_store.is_model_current(
        records2, lookback, directory=tmp_path, prefix="lightgbm"
    )
    assert (
        model_store.find_current_model(
            records2, lookback, directory=tmp_path, prefix="lightgbm"
        )
        is None
    )
