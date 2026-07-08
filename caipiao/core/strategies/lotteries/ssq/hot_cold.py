"""双色球冷热号策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQHotColdStrategy(BaseSSQStrategy):
    """冷热号分析。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="hot_cold",
            name="冷热号分析",
            description="基于历史开奖数据统计号码出现频率。",
            configurable=True,
        )
