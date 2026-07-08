"""FC3D 与其他彩种 ML 底层隔离测试."""

import os
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import patch

import numpy as np
import pytest

from caipiao.core.profile import DLT, FC3D, KL8, PL3, PL5, QLC, QXC, LotteryProfile
from caipiao.data.models import DrawRecord
from caipiao.ml.lotteries.dlt import DLTPredictor
from caipiao.ml.lotteries.dlt import build_features as dlt_build_features
from caipiao.ml.lotteries.dlt import build_prediction_features as dlt_build_prediction_features
from caipiao.ml.lotteries.dlt.models.catboost import DLTCatBoostModel
from caipiao.ml.lotteries.dlt.models.lightgbm import DLTLightGBMModel
from caipiao.ml.lotteries.dlt.models.xgboost import DLTXGBoostModel
from caipiao.ml.lotteries.fc3d import FC3DPredictor
from caipiao.ml.lotteries.fc3d import build_features as fc3d_build_features
from caipiao.ml.lotteries.fc3d import build_prediction_features as fc3d_build_prediction_features
from caipiao.ml.lotteries.fc3d.models.catboost import FC3DCatBoostModel
from caipiao.ml.lotteries.fc3d.models.lightgbm import FC3DLightGBMModel
from caipiao.ml.lotteries.fc3d.models.xgboost import FC3DXGBoostModel
from caipiao.ml.lotteries.kl8 import KL8Predictor
from caipiao.ml.lotteries.kl8.models.catboost import KL8CatBoostModel
from caipiao.ml.lotteries.kl8.models.lightgbm import KL8LightGBMModel
from caipiao.ml.lotteries.kl8.models.xgboost import KL8XGBoostModel
from caipiao.ml.lotteries.pl3 import PL3Predictor
from caipiao.ml.lotteries.pl3 import build_features as pl3_build_features
from caipiao.ml.lotteries.pl3 import build_prediction_features as pl3_build_prediction_features
from caipiao.ml.lotteries.pl3.models.catboost import PL3CatBoostModel
from caipiao.ml.lotteries.pl3.models.lightgbm import PL3LightGBMModel
from caipiao.ml.lotteries.pl3.models.xgboost import PL3XGBoostModel
from caipiao.ml.lotteries.pl5 import PL5Predictor
from caipiao.ml.lotteries.pl5 import build_features as pl5_build_features
from caipiao.ml.lotteries.pl5 import build_prediction_features as pl5_build_prediction_features
from caipiao.ml.lotteries.pl5.models.catboost import PL5CatBoostModel
from caipiao.ml.lotteries.pl5.models.lightgbm import PL5LightGBMModel
from caipiao.ml.lotteries.pl5.models.xgboost import PL5XGBoostModel
from caipiao.ml.lotteries.qlc import QLCPredictor
from caipiao.ml.lotteries.qlc import build_features as qlc_build_features
from caipiao.ml.lotteries.qlc import build_prediction_features as qlc_build_prediction_features
from caipiao.ml.lotteries.qlc.models.catboost import QLCCatBoostModel
from caipiao.ml.lotteries.qlc.models.lightgbm import QLCLightGBMModel
from caipiao.ml.lotteries.qlc.models.xgboost import QLCXGBoostModel
from caipiao.ml.lotteries.qxc import QXCPredictor
from caipiao.ml.lotteries.qxc import build_features as qxc_build_features
from caipiao.ml.lotteries.qxc import build_prediction_features as qxc_build_prediction_features
from caipiao.ml.lotteries.qxc.models.catboost import QXCCatBoostModel
from caipiao.ml.lotteries.qxc.models.lightgbm import QXCLightGBMModel
from caipiao.ml.lotteries.qxc.models.xgboost import QXCXGBoostModel


def _draw_groups_for_profile(profile: LotteryProfile, rng: random.Random) -> Dict[str, List[int]]:
    """为指定彩种生成一期合理的开奖号码组."""
    groups: Dict[str, List[int]] = {}
    for g in profile.groups:
        if g.positional:
            groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
        else:
            groups[g.key] = sorted(rng.sample(range(g.lo, g.hi + 1), g.count))
    return groups


def make_history(profile: LotteryProfile, n: int = 120, seed: int = 0) -> List[DrawRecord]:
    """生成 n 期合成历史记录."""
    rng = random.Random(seed)
    history = []
    for i in range(n):
        groups = _draw_groups_for_profile(profile, rng)
        history.append(
            DrawRecord(
                f"2024{i:03d}",
                datetime(2024, 1, 1) + timedelta(days=i),
                profile=profile.key,
                groups=groups,
            )
        )
    return history


@pytest.fixture
def model_dir(tmp_path):
    """将模型缓存隔离到临时目录，避免污染用户数据."""
    d = tmp_path / "models"
    d.mkdir()
    with patch.dict(os.environ, {"CAIPIAO_MODEL_DIR": str(d)}):
        yield d


# --------------------------------------------------------------------------- #
# 特征工程
# --------------------------------------------------------------------------- #
LOOKBACK = 50


@pytest.mark.parametrize(
    "profile, build_features",
    [
        (FC3D, fc3d_build_features),
        (QLC, qlc_build_features),
        (DLT, dlt_build_features),
        (PL3, pl3_build_features),
        (PL5, pl5_build_features),
        (QXC, qxc_build_features),
    ],
)
def test_build_features_returns_x_and_y_dict(profile, build_features):
    records = make_history(profile, n=120)
    X, y_dict = build_features(records, lookback=LOOKBACK)
    assert X.ndim == 2
    assert X.shape[0] == len(records) - LOOKBACK
    for g in profile.groups:
        assert g.key in y_dict
        assert y_dict[g.key].shape[0] == X.shape[0]


@pytest.mark.parametrize(
    "profile, build_features, build_prediction_features",
    [
        (FC3D, fc3d_build_features, fc3d_build_prediction_features),
        (QLC, qlc_build_features, qlc_build_prediction_features),
        (DLT, dlt_build_features, dlt_build_prediction_features),
        (PL3, pl3_build_features, pl3_build_prediction_features),
        (PL5, pl5_build_features, pl5_build_prediction_features),
        (QXC, qxc_build_features, qxc_build_prediction_features),
    ],
)
def test_build_prediction_features_shape(profile, build_features, build_prediction_features):
    records = make_history(profile, n=120)
    X_pred = build_prediction_features(records, lookback=LOOKBACK)
    assert X_pred.ndim == 2
    assert X_pred.shape[0] == 1
    X, _ = build_features(records, lookback=LOOKBACK)
    assert X_pred.shape[1] == X.shape[1]


# --------------------------------------------------------------------------- #
# 预测器接口
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "profile, predictor_cls",
    [
        (FC3D, FC3DPredictor),
        (QLC, QLCPredictor),
        (DLT, DLTPredictor),
        (PL3, PL3Predictor),
        (PL5, PL5Predictor),
        (QXC, QXCPredictor),
    ],
)
def test_predictor_predict_and_recommend(profile, predictor_cls, model_dir):
    records = make_history(profile, n=120)
    predictor = predictor_cls(records, lookback=LOOKBACK, backend="xgboost")
    proba = predictor.predict()
    assert isinstance(proba, dict)
    for g in profile.groups:
        assert g.key in proba

    rec_groups = predictor.recommend(
        group_picks={g.key: g.effective_pick_max for g in profile.pick_groups},
        diversity_boost=0.3,
    )
    for g in profile.pick_groups:
        assert g.key in rec_groups
        assert g.effective_pick_min <= len(rec_groups[g.key]) <= g.effective_pick_max
        for n in rec_groups[g.key]:
            assert g.lo <= n <= g.hi


@pytest.mark.parametrize(
    "profile, predictor_cls",
    [
        (FC3D, FC3DPredictor),
        (QLC, QLCPredictor),
        (DLT, DLTPredictor),
        (PL3, PL3Predictor),
        (PL5, PL5Predictor),
        (QXC, QXCPredictor),
    ],
)
def test_predictor_pins_profile(profile, predictor_cls):
    predictor = predictor_cls(make_history(profile, n=120), lookback=LOOKBACK)
    assert predictor.profile.key == profile.key


@pytest.mark.parametrize(
    "profile, predictor_cls",
    [
        (FC3D, FC3DPredictor),
        (QLC, QLCPredictor),
        (DLT, DLTPredictor),
        (PL3, PL3Predictor),
        (PL5, PL5Predictor),
        (QXC, QXCPredictor),
    ],
)
@pytest.mark.parametrize("backend", ["xgboost", "lightgbm", "catboost"])
def test_predictor_all_tree_backends(profile, predictor_cls, backend, model_dir):
    records = make_history(profile, n=120)
    predictor = predictor_cls(records, lookback=LOOKBACK, backend=backend)
    rec_groups = predictor.recommend(
        group_picks={g.key: g.effective_pick_max for g in profile.pick_groups},
    )
    for g in profile.pick_groups:
        assert g.key in rec_groups
    assert predictor.is_ready()


# --------------------------------------------------------------------------- #
# 模型类固定彩种
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "profile, model_classes",
    [
        (FC3D, [FC3DXGBoostModel, FC3DLightGBMModel, FC3DCatBoostModel]),
        (QLC, [QLCXGBoostModel, QLCLightGBMModel, QLCCatBoostModel]),
        (DLT, [DLTXGBoostModel, DLTLightGBMModel, DLTCatBoostModel]),
        (PL3, [PL3XGBoostModel, PL3LightGBMModel, PL3CatBoostModel]),
        (PL5, [PL5XGBoostModel, PL5LightGBMModel, PL5CatBoostModel]),
        (QXC, [QXCXGBoostModel, QXCLightGBMModel, QXCCatBoostModel]),
    ],
)
def test_model_classes_pin_profile(profile, model_classes):
    for cls in model_classes:
        model = cls()
        assert model.profile.key == profile.key


# --------------------------------------------------------------------------- #
# KL8 占位
# --------------------------------------------------------------------------- #
def test_kl8_predictor_placeholder():
    records = make_history(KL8, n=120)
    predictor = KL8Predictor(records, lookback=LOOKBACK)
    assert predictor.is_ready() is False
    with pytest.raises(NotImplementedError):
        predictor.train()
    with pytest.raises(NotImplementedError):
        predictor.predict()
    with pytest.raises(NotImplementedError):
        predictor.recommend()


@pytest.mark.parametrize("cls", [KL8XGBoostModel, KL8LightGBMModel, KL8CatBoostModel])
def test_kl8_model_classes_placeholder(cls):
    with pytest.raises(NotImplementedError):
        cls()
