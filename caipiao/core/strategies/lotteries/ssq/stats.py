"""双色球统计策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQStatsStrategy(BaseSSQStrategy):
    """统计特征。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="stats",
            name="统计特征",
            description="基于历史数据统计特征生成号码。",
            configurable=True,
        )
