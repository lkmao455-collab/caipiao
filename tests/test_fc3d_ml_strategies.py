"""福彩3D ML 策略回归测试."""

import os
import random
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from caipiao.core.profile import FC3D
from caipiao.core.strategies import build_strategies, is_ml_strategy, needs_history
from caipiao.core.strategies.lotteries.fc3d.ml import (
    FC3DCatBoostStrategy,
    FC3DLightGBMStrategy,
    FC3DMLStrategy,
    FC3DXGBoostStrategy,
)
from caipiao.data.models import DrawRecord


@pytest.fixture
def model_dir(tmp_path):
    """将模型缓存隔离到临时目录，避免污染用户数据。"""
    d = tmp_path / "models"
    d.mkdir()
    with patch.dict(os.environ, {"CAIPIAO_MODEL_DIR": str(d)}):
        yield d


def make_fc3d_history(n=120):
    rng = random.Random(0)
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [rng.randint(0, 9) for _ in range(3)]},
        )
        for i in range(n)
    ]


@pytest.mark.parametrize(
    "cls, sid",
    [
        (FC3DMLStrategy, "ml_strategy"),
        (FC3DXGBoostStrategy, "xgboost_3d"),
        (FC3DLightGBMStrategy, "lightgbm_3d"),
        (FC3DCatBoostStrategy, "catboost_3d"),
    ],
)
def test_fc3d_ml_strategy_metadata(cls, sid):
    s = cls()
    assert s.metadata.id == sid
    assert s.metadata.name != ""
    assert is_ml_strategy(sid) is True


@pytest.mark.parametrize(
    "cls",
    [
        FC3DXGBoostStrategy,
        FC3DLightGBMStrategy,
        FC3DCatBoostStrategy,
    ],
)
def test_fc3d_tree_ml_strategy_generates_valid(cls, model_dir):
    s = cls()
    history = make_fc3d_history(120)
    tickets = s.generate(count=2, options={"history": history, "history_count": 100})
    assert len(tickets) == 2
    for t in tickets:
        assert t.profile.key == "3d"
        assert len(t.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in t.groups["pos"])


def test_build_strategies_includes_fc3d_ml(model_dir):
    strategies = build_strategies(FC3D)
    ids = {s.metadata.id for s in strategies}
    assert "xgboost_3d" in ids
    assert "lightgbm_3d" in ids
    assert "catboost_3d" in ids


def test_fc3d_ml_strategy_needs_history(model_dir):
    s = FC3DXGBoostStrategy()
    assert needs_history("xgboost_3d") is True
    with pytest.raises(ValueError):
        s.generate(count=1, options={"history": make_fc3d_history(50)})
