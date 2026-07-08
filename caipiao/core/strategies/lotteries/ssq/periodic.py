"""双色球周期策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQPeriodicStrategy(BaseSSQStrategy):
    """周期分析。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="periodic",
            name="周期分析",
            description="基于开奖周期特征生成号码。",
            configurable=True,
        )
