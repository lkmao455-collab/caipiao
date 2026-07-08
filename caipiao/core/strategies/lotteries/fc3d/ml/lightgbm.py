"""福彩3D LightGBM 策略."""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .base import _FC3DMLStrategyBase


class FC3DLightGBMStrategy(_FC3DMLStrategyBase):
    _backend = "lightgbm"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="lightgbm_3d",
            name="LightGBM 智能分析",
            description="基于 LightGBM 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
