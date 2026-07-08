"""双色球马尔可夫策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQMarkovStrategy(BaseSSQStrategy):
    """马尔可夫链。"""

    is_ml = False

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="markov",
            name="马尔可夫链",
            description="基于马尔可夫链建模号码转移概率。",
            configurable=True,
        )
