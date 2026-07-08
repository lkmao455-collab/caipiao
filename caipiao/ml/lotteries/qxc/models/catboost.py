"""QXC CatBoost 模型（当前复用通用顺序生成模型）."""

from __future__ import annotations

from .....core.profile import QXC
from ....generic_model import LotteryGenericModel


class QXCCatBoostModel(LotteryGenericModel):
    """QXC 专用的 CatBoost 顺序生成模型."""

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        super().__init__(profile=QXC, lookback=lookback, backend="catboost", temp_dir=temp_dir)
