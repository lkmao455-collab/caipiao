"""FC3D XGBoost 模型（当前复用通用顺序生成模型）."""

from __future__ import annotations

from .....core.profile import FC3D
from ....generic_model import LotteryGenericModel


class FC3DXGBoostModel(LotteryGenericModel):
    """FC3D 专用的 XGBoost 顺序生成模型.

    当前直接继承 ``LotteryGenericModel`` 并固定彩种为 FC3D；
    后续若需 FC3D 专属特征或采样策略，可在此扩展。
    """

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        super().__init__(profile=FC3D, lookback=lookback, backend="xgboost", temp_dir=temp_dir)
