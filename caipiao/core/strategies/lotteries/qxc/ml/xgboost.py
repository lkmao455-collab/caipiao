"""7星彩 XGBoost 策略."""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .base import _QXCMLStrategyBase


class QXCXGBoostStrategy(_QXCMLStrategyBase):
    _backend = "xgboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="xgboost_qxc",
            name="XGBoost 智能分析",
            description="基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
