"""SSQ ML 策略回归测试."""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from caipiao.core.profile import SSQ
from caipiao.core.strategies import build_strategies, is_ml_strategy
from caipiao.core.strategies.lotteries.ssq.ml import (
    SSQCatBoostStrategy,
    SSQHybridStrategy,
    SSQLightGBMStrategy,
    SSQLSTMStrategy,
    SSQXGBoostStrategy,
)
from caipiao.data.models import DrawRecord


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture
def model_dir(tmp_path):
    """将模型缓存隔离到临时目录，避免污染用户数据。"""
    d = tmp_path / "models"
    d.mkdir()
    with patch.dict(os.environ, {"CAIPIAO_MODEL_DIR": str(d)}):
        yield d


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


@pytest.mark.parametrize(
    "cls, sid",
    [
        (SSQXGBoostStrategy, "ml_xgboost"),
        (SSQLightGBMStrategy, "ml_lightgbm"),
        (SSQCatBoostStrategy, "ml_catboost"),
        (SSQLSTMStrategy, "ml_lstm"),
        (SSQHybridStrategy, "ml_hybrid"),
    ],
)
def test_ssq_ml_strategy_metadata(cls, sid):
    s = cls()
    assert s.metadata.id == sid
    assert s.metadata.name != ""
    assert is_ml_strategy(sid) is True


@pytest.mark.parametrize(
    "cls",
    [
        SSQXGBoostStrategy,
        SSQLightGBMStrategy,
        SSQCatBoostStrategy,
    ],
)
def test_ssq_tree_ml_strategy_generates_valid(cls, model_dir):
    s = cls()
    history = make_ssq_history(120)
    tickets = s.generate(count=2, options={"history": history})
    assert len(tickets) == 2
    for t in tickets:
        assert t.profile.key == "ssq"
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1
        assert all(1 <= n <= 33 for n in t.groups["red"])
        assert 1 <= t.groups["blue"][0] <= 16


@pytest.mark.skipif(not _torch_available(), reason="PyTorch 未安装")
@pytest.mark.parametrize(
    "cls",
    [
        SSQLSTMStrategy,
        SSQHybridStrategy,
    ],
)
def test_ssq_lstm_hybrid_generates_valid(cls, model_dir):
    s = cls()
    history = make_ssq_history(120)
    tickets = s.generate(count=2, options={"history": history})
    assert len(tickets) == 2
    for t in tickets:
        assert t.profile.key == "ssq"
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1
        assert all(1 <= n <= 33 for n in t.groups["red"])
        assert 1 <= t.groups["blue"][0] <= 16


def test_build_strategies_includes_ssq_ml(model_dir):
    strategies = build_strategies(SSQ)
    ids = {s.metadata.id for s in strategies}
    assert "ml_xgboost" in ids
    assert "ml_lightgbm" in ids
    assert "ml_catboost" in ids
    assert "ml_lstm" in ids
    assert "ml_hybrid" in ids


def test_ssq_ml_strategy_needs_history(model_dir):
    s = SSQXGBoostStrategy()
    with pytest.raises(ValueError):
        s.generate(count=1, options={"history": make_ssq_history(50)})
