"""双色球 CatBoost 策略."""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .base import _SSQMLStrategyBase


class SSQCatBoostStrategy(_SSQMLStrategyBase):
    """CatBoost 智能分析。"""

    _backend = "catboost"
    _label = "CatBoost"
    _id = "ml_catboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ml_catboost",
            name="CatBoost 智能分析",
            description="基于 CatBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
