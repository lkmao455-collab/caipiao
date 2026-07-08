"""双色球 CatBoost 策略占位。"""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .._base import BaseSSQStrategy


class SSQCatBoostStrategy(BaseSSQStrategy):
    """CatBoost 智能分析。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ml_catboost",
            name="CatBoost 智能分析",
            description="基于 CatBoost 模型分析历史数据并生成号码。",
            configurable=True,
        )
