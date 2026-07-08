"""福彩3D历史均衡策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseFC3DStrategy


class FC3DBalancedStrategy(BaseFC3DStrategy):
    """历史均衡。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="balanced_3d",
            name="历史均衡",
            description="根据历史数据的按位频率、奇偶、大小等生成均衡号码。",
            configurable=True,
        )
