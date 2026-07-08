"""双色球集成策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQEnsembleStrategy(BaseSSQStrategy):
    """集成投票。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ensemble",
            name="集成投票",
            description="融合多种策略结果进行投票生成号码。",
            configurable=True,
        )
