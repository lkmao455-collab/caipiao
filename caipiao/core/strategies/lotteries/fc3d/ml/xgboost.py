"""福彩3D XGBoost 策略占位。"""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .._base import BaseFC3DStrategy


class FC3DXGBoostStrategy(BaseFC3DStrategy):
    """XGBoost 智能分析。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="xgboost_3d",
            name="XGBoost 智能分析",
            description="基于 XGBoost 模型分析历史数据并生成号码。",
            configurable=True,
        )
