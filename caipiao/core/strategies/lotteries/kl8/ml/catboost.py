"""快乐8 CatBoost 策略（占位）."""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .base import _KL8MLStrategyBase


class KL8CatBoostStrategy(_KL8MLStrategyBase):
    _backend = "catboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="catboost_kl8",
            name="CatBoost 智能分析",
            description="基于 CatBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
