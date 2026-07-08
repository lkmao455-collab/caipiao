"""福彩3D智能冷热号策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseFC3DStrategy


class FC3DSmartHotColdStrategy(BaseFC3DStrategy):
    """智能冷热号。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="smart_hot_cold_3d",
            name="智能冷热号",
            description="结合历史数据中的按位热号频率与冷号遗漏值加权生成。",
            configurable=True,
        )
