"""福彩3D LightGBM 策略占位。"""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .._base import BaseFC3DStrategy


class FC3DLightGBMStrategy(BaseFC3DStrategy):
    """LightGBM 智能分析。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="lightgbm_3d",
            name="LightGBM 智能分析",
            description="基于 LightGBM 模型分析历史数据并生成号码。",
            configurable=True,
        )
