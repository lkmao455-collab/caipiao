"""双色球关联挖掘策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQCorrelationStrategy(BaseSSQStrategy):
    """关联挖掘。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="correlation",
            name="关联挖掘",
            description="基于号码关联规则生成号码。",
            configurable=True,
        )
