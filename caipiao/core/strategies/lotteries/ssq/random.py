"""双色球随机策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQRandomStrategy(BaseSSQStrategy):
    """完全随机。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random",
            name="完全随机",
            description="从红球 1-33 中随机抽取 6 个，蓝球 1-16 中随机抽取 1 个。",
            configurable=True,
        )
