"""双色球 LightGBM 策略占位。"""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .._base import BaseSSQStrategy


class SSQLightGBMStrategy(BaseSSQStrategy):
    """LightGBM 智能分析。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ml_lightgbm",
            name="LightGBM 智能分析",
            description="基于 LightGBM 模型分析历史数据并生成号码。",
            configurable=True,
        )
