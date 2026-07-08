"""PL5 LightGBM 模型（当前复用通用顺序生成模型）."""

from __future__ import annotations

from .....core.profile import PL5
from ....generic_model import LotteryGenericModel


class PL5LightGBMModel(LotteryGenericModel):
    """PL5 专用的 LightGBM 顺序生成模型."""

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        super().__init__(profile=PL5, lookback=lookback, backend="lightgbm", temp_dir=temp_dir)
