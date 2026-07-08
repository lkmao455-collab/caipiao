"""双色球混合模型策略占位。"""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .._base import BaseSSQStrategy


class SSQHybridStrategy(BaseSSQStrategy):
    """混合模型智能分析。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ml_hybrid",
            name="混合模型智能分析",
            description="基于混合模型分析历史数据并生成号码。",
            configurable=True,
        )
