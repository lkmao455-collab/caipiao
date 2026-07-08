"""双色球 Transformer 策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQTransformerStrategy(BaseSSQStrategy):
    """Transformer 序列建模。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="transformer",
            name="Transformer 序列建模",
            description="基于 Transformer 模型学习历史开奖序列。",
            configurable=True,
        )
