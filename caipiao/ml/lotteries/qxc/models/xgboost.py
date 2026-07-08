"""QXC XGBoost 模型（当前复用通用顺序生成模型）."""

from __future__ import annotations

from .....core.profile import QXC
from ....common.base import LotteryGenericModel


class QXCXGBoostModel(LotteryGenericModel):
    """QXC 专用的 XGBoost 顺序生成模型."""

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        super().__init__(profile=QXC, lookback=lookback, backend="xgboost", temp_dir=temp_dir)
