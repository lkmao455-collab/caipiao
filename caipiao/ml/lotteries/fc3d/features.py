"""FC3D 特征工程（当前委托通用实现，保留隔离边界）."""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

import numpy as np

from ....core.profile import FC3D
from ...generic_features import build_features as _build_features
from ...generic_features import build_prediction_features as _build_prediction_features

if TYPE_CHECKING:
    from ....core.profile import LotteryProfile
    from ....data.models import DrawRecord


def build_features(
    records: list[DrawRecord],
    profile: LotteryProfile | None = None,
    lookback: int = 50,
) -> Tuple[np.ndarray, dict[str, np.ndarray]]:
    """构建 FC3D 训练特征与标签.

    Args:
        records: 按时间排序的 FC3D 开奖记录。
        profile: 为兼容通用接口保留，忽略（始终使用 FC3D）。
        lookback: 回看期数。

    Returns:
        X: 特征矩阵。
        y_dict: 按号码组分组的标签字典。
    """
    return _build_features(records, profile=FC3D, lookback=lookback)


def build_prediction_features(
    records: list[DrawRecord],
    profile: LotteryProfile | None = None,
    lookback: int = 50,
) -> np.ndarray:
    """为最新一期构建 FC3D 预测特征.

    Args:
        records: 按时间排序的 FC3D 开奖记录。
        profile: 为兼容通用接口保留，忽略（始终使用 FC3D）。
        lookback: 回看期数。
    """
    return _build_prediction_features(records, profile=FC3D, lookback=lookback)
