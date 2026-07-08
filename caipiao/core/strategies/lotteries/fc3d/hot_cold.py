"""福彩3D冷热号策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseFC3DStrategy


class FC3DHotColdStrategy(BaseFC3DStrategy):
    """冷热号分析。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="hot_cold_3d",
            name="冷热号分析",
            description="基于历史记录统计每位数字出现频率。",
            configurable=True,
        )
