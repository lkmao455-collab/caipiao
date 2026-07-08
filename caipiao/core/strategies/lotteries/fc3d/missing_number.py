"""福彩3D遗漏号策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseFC3DStrategy


class FC3DMissingNumberStrategy(BaseFC3DStrategy):
    """遗漏号追踪。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="missing_number_3d",
            name="遗漏号追踪",
            description="选择近期按位遗漏值较高的号码。",
            configurable=True,
        )
