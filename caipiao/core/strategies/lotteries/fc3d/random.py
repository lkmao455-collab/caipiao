"""福彩3D随机策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseFC3DStrategy


class FC3DRandomStrategy(BaseFC3DStrategy):
    """完全随机。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random_3d",
            name="完全随机",
            description="在百、十、个位上分别独立随机生成 0-9 数字。",
            configurable=True,
        )
