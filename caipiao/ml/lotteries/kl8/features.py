"""KL8 特征工程（当前委托通用实现，保留隔离边界）."""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

import numpy as np

from ....core.profile import KL8
from ...common.features import build_features as _build_features
from ...common.features import build_prediction_features as _build_prediction_features

if TYPE_CHECKING:
    from ....core.profile import LotteryProfile
    from ....data.models import DrawRecord


def build_features(
    records: list[DrawRecord],
    profile: LotteryProfile | None = None,
    lookback: int = 50,
) -> Tuple[np.ndarray, dict[str, np.ndarray]]:
    """构建 KL8 训练特征与标签（当前仅做特征工程，预测器暂不支持）."""
    return _build_features(records, profile=KL8, lookback=lookback)


def build_prediction_features(
    records: list[DrawRecord],
    profile: LotteryProfile | None = None,
    lookback: int = 50,
) -> np.ndarray:
    """为最新一期构建 KL8 预测特征（当前仅做特征工程，预测器暂不支持）."""
    return _build_prediction_features(records, profile=KL8, lookback=lookback)
