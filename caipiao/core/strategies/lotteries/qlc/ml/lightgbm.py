"""七乐彩 LightGBM 策略."""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .base import _QLCMLStrategyBase


class QLCLightGBMStrategy(_QLCMLStrategyBase):
    _backend = "lightgbm"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="lightgbm_qlc",
            name="LightGBM 智能分析",
            description="基于 LightGBM 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
