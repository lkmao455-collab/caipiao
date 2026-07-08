"""QLC/KL8/DLT/PL3/PL5/QXC 彩种 ML 策略回归测试."""

import os
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from caipiao.core.profile import DLT, KL8, PL3, PL5, QLC, QXC
from caipiao.core.strategies import build_strategies, is_ml_strategy, needs_history
from caipiao.core.strategies.lotteries.dlt.ml import (
    DLTCatBoostStrategy,
    DLTLightGBMStrategy,
    DLTXGBoostStrategy,
)
from caipiao.core.strategies.lotteries.kl8.ml import (
    KL8CatBoostStrategy,
    KL8LightGBMStrategy,
    KL8XGBoostStrategy,
)
from caipiao.core.strategies.lotteries.pl3.ml import (
    PL3CatBoostStrategy,
    PL3LightGBMStrategy,
    PL3XGBoostStrategy,
)
from caipiao.core.strategies.lotteries.pl5.ml import (
    PL5CatBoostStrategy,
    PL5LightGBMStrategy,
    PL5XGBoostStrategy,
)
from caipiao.core.strategies.lotteries.qlc.ml import (
    QLCCatBoostStrategy,
    QLCLightGBMStrategy,
    QLCXGBoostStrategy,
)
from caipiao.core.strategies.lotteries.qxc.ml import (
    QXCCatBoostStrategy,
    QXCLightGBMStrategy,
    QXCXGBoostStrategy,
)
from caipiao.data.models import DrawRecord


@pytest.fixture
def model_dir(tmp_path):
    """将模型缓存隔离到临时目录，避免污染用户数据。"""
    d = tmp_path / "models"
    d.mkdir()
    with patch.dict(os.environ, {"CAIPIAO_MODEL_DIR": str(d)}):
        yield d


def _draw_groups_for_profile(profile, rng: random.Random) -> Dict[str, List[int]]:
    """为指定彩种生成一期合理的开奖号码组。"""
    groups: Dict[str, List[int]] = {}
    for g in profile.groups:
        if g.positional:
            groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
        elif g.key in ("basic", "front"):
            groups[g.key] = sorted(rng.sample(range(g.lo, g.hi + 1), g.count))
        elif g.key in ("special", "back"):
            groups[g.key] = sorted(rng.sample(range(g.lo, g.hi + 1), g.count))
        elif g.key == "main":
            groups[g.key] = sorted(rng.sample(range(g.lo, g.hi + 1), g.count))
        else:
            groups[g.key] = sorted(rng.sample(range(g.lo, g.hi + 1), g.count))
    return groups


def make_history(profile, n: int = 120, seed: int = 0) -> List[DrawRecord]:
    """生成 n 期合成历史记录。"""
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


LOTTERY_CASES = [
    ("qlc", QLC, [QLCXGBoostStrategy, QLCLightGBMStrategy, QLCCatBoostStrategy]),
    ("kl8", KL8, [KL8XGBoostStrategy, KL8LightGBMStrategy, KL8CatBoostStrategy]),
    ("dlt", DLT, [DLTXGBoostStrategy, DLTLightGBMStrategy, DLTCatBoostStrategy]),
    ("pl3", PL3, [PL3XGBoostStrategy, PL3LightGBMStrategy, PL3CatBoostStrategy]),
    ("pl5", PL5, [PL5XGBoostStrategy, PL5LightGBMStrategy, PL5CatBoostStrategy]),
    ("qxc", QXC, [QXCXGBoostStrategy, QXCLightGBMStrategy, QXCCatBoostStrategy]),
]

LOTTERY_IDS = {
    "qlc": ["xgboost_qlc", "lightgbm_qlc", "catboost_qlc"],
    "kl8": ["xgboost_kl8", "lightgbm_kl8", "catboost_kl8"],
    "dlt": ["xgboost_dlt", "lightgbm_dlt", "catboost_dlt"],
    "pl3": ["xgboost_pl3", "lightgbm_pl3", "catboost_pl3"],
    "pl5": ["xgboost_pl5", "lightgbm_pl5", "catboost_pl5"],
    "qxc": ["xgboost_qxc", "lightgbm_qxc", "catboost_qxc"],
}


@pytest.mark.parametrize("key, profile, classes", LOTTERY_CASES)
@pytest.mark.parametrize("cls_index", [0, 1, 2])
def test_ml_strategy_metadata(key, profile, classes, cls_index):
    cls = classes[cls_index]
    expected_id = LOTTERY_IDS[key][cls_index]
    s = cls()
    assert s.metadata.id == expected_id
    assert s.metadata.name != ""
    assert is_ml_strategy(expected_id) is True
    assert needs_history(expected_id) is True


@pytest.mark.parametrize("key, profile, classes", LOTTERY_CASES)
def test_build_strategies_includes_ml(key, profile, classes, model_dir):
    strategies = build_strategies(profile)
    ids = {s.metadata.id for s in strategies}
    for expected_id in LOTTERY_IDS[key]:
        assert expected_id in ids


@pytest.mark.parametrize("key, profile, classes", LOTTERY_CASES)
def test_real_ml_strategy_generates_valid(key, profile, classes, model_dir):
    """非占位 ML 策略在 120 期合成历史上应生成合法投注单。"""
    if key == "kl8":
        pytest.skip("KL8 ML 策略当前为占位实现")
    history = make_history(profile, n=120)
    for cls in classes:
        s = cls()
        tickets = s.generate(count=2, options={"history": history})
        assert len(tickets) == 2
        for t in tickets:
            assert t.profile.key == profile.key
            for g in profile.pick_groups:
                assert g.key in t.groups
                assert g.effective_pick_min <= len(t.groups[g.key]) <= g.effective_pick_max
                for n in t.groups[g.key]:
                    assert g.lo <= n <= g.hi


@pytest.mark.parametrize("cls", [KL8XGBoostStrategy, KL8LightGBMStrategy, KL8CatBoostStrategy])
def test_kl8_ml_strategy_placeholder(cls, model_dir):
    """KL8 ML 策略占位实现应抛出清晰的 NotImplementedError。"""
    s = cls()
    history = make_history(KL8, n=120)
    with pytest.raises(NotImplementedError):
        s.generate(count=1, options={"history": history})


@pytest.mark.parametrize("key, profile, classes", LOTTERY_CASES)
def test_ml_strategy_needs_sufficient_history(key, profile, classes, model_dir):
    """历史记录不足 100 期时应抛出 ValueError。"""
    if key == "kl8":
        pytest.skip("KL8 ML 策略当前为占位实现，由独立占位测试覆盖")
    s = classes[0]()
    with pytest.raises(ValueError):
        s.generate(count=1, options={"history": make_history(profile, n=50)})
