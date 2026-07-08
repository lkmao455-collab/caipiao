"""福彩3D排除/必含策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseFC3DStrategy


class FC3DExcludeIncludeStrategy(BaseFC3DStrategy):
    """排除/必含。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="exclude_include_3d",
            name="排除/必含",
            description="排除不想要的号码或强制包含幸运号码。",
            configurable=True,
        )
