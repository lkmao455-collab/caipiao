"""福彩3D奇偶策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseFC3DStrategy


class FC3DOddEvenStrategy(BaseFC3DStrategy):
    """奇偶均衡。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="odd_even_3d",
            name="奇偶均衡",
            description="控制福彩3D号码中奇数与偶数的比例。",
            configurable=True,
        )
