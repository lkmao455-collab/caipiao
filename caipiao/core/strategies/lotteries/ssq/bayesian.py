"""双色球贝叶斯策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQBayesianStrategy(BaseSSQStrategy):
    """贝叶斯分析。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="bayesian",
            name="贝叶斯分析",
            description="基于贝叶斯推断评估号码出现概率。",
            configurable=True,
        )
