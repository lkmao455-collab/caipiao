"""快乐8 LightGBM 策略（占位）."""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .base import _KL8MLStrategyBase


class KL8LightGBMStrategy(_KL8MLStrategyBase):
    _backend = "lightgbm"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="lightgbm_kl8",
            name="LightGBM 智能分析",
            description="基于 LightGBM 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
