"""双色球 LightGBM 策略."""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .base import _SSQMLStrategyBase


class SSQLightGBMStrategy(_SSQMLStrategyBase):
    """LightGBM 智能分析。"""

    _backend = "lightgbm"
    _label = "LightGBM"
    _id = "ml_lightgbm"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ml_lightgbm",
            name="LightGBM 智能分析",
            description="基于 LightGBM 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
