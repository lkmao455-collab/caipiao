"""双色球奇偶策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQOddEvenStrategy(BaseSSQStrategy):
    """奇偶均衡。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="odd_even",
            name="奇偶均衡",
            description="控制红球中奇数与偶数的比例。",
            configurable=True,
        )
