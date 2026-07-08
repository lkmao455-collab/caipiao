"""双色球历史均衡策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQBalancedStrategy(BaseSSQStrategy):
    """历史均衡。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="balanced",
            name="历史均衡",
            description="根据历史数据统计生成相对均衡的号码组合。",
            configurable=True,
        )
