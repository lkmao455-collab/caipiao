"""双色球趋势策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQTrendStrategy(BaseSSQStrategy):
    """趋势分析。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="trend",
            name="趋势分析",
            description="基于历史数据趋势生成号码。",
            configurable=True,
        )
