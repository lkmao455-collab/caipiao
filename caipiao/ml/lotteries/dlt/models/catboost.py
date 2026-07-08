"""DLT CatBoost 模型（当前复用通用顺序生成模型）."""

from __future__ import annotations

from .....core.profile import DLT
from ....common.base import LotteryGenericModel


class DLTCatBoostModel(LotteryGenericModel):
    """DLT 专用的 CatBoost 顺序生成模型."""

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        super().__init__(profile=DLT, lookback=lookback, backend="catboost", temp_dir=temp_dir)
