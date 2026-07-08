"""双色球排除/必含策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQExcludeIncludeStrategy(BaseSSQStrategy):
    """排除/必含。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="exclude_include",
            name="排除/必含",
            description="排除不想要的号码或强制包含幸运号码。",
            configurable=True,
        )
