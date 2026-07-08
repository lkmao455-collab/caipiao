"""福彩3D CatBoost 策略占位。"""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .._base import BaseFC3DStrategy


class FC3DCatBoostStrategy(BaseFC3DStrategy):
    """CatBoost 智能分析。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="catboost_3d",
            name="CatBoost 智能分析",
            description="基于 CatBoost 模型分析历史数据并生成号码。",
            configurable=True,
        )
