"""双色球智能冷热号策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQSmartHotColdStrategy(BaseSSQStrategy):
    """智能冷热号。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="smart_hot_cold",
            name="智能冷热号",
            description="结合热号频率与冷号遗漏值加权生成。",
            configurable=True,
        )
