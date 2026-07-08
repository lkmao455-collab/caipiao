"""FC3D LightGBM 模型（当前复用通用顺序生成模型）."""

from __future__ import annotations

from .....core.profile import FC3D
from ....common.base import LotteryGenericModel


class FC3DLightGBMModel(LotteryGenericModel):
    """FC3D 专用的 LightGBM 顺序生成模型."""

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        super().__init__(profile=FC3D, lookback=lookback, backend="lightgbm", temp_dir=temp_dir)
