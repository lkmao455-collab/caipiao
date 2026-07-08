"""FC3D CatBoost 模型（当前复用通用顺序生成模型）."""

from __future__ import annotations

from .....core.profile import FC3D
from ....generic_model import LotteryGenericModel


class FC3DCatBoostModel(LotteryGenericModel):
    """FC3D 专用的 CatBoost 顺序生成模型."""

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        super().__init__(profile=FC3D, lookback=lookback, backend="catboost", temp_dir=temp_dir)
