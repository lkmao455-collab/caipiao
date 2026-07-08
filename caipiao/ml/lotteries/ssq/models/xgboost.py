"""SSQ XGBoost 模型（当前复用通用顺序生成模型）."""

from __future__ import annotations

from .....core.profile import SSQ
from ....common.base import LotteryGenericModel


class SSQXGBoostModel(LotteryGenericModel):
    """SSQ 专用的 XGBoost 顺序生成模型.

    当前直接继承 ``LotteryGenericModel`` 并固定彩种为 SSQ；
    后续若需 SSQ 专属特征或采样策略，可在此扩展。
    """

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        super().__init__(profile=SSQ, lookback=lookback, backend="xgboost", temp_dir=temp_dir)
