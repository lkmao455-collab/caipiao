"""双色球随机森林策略占位。"""

from __future__ import annotations

from ....strategy import StrategyMetadata
from ._base import BaseSSQStrategy


class SSQRandomForestStrategy(BaseSSQStrategy):
    """随机森林。"""

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random_forest",
            name="随机森林",
            description="基于随机森林模型分析历史数据并生成号码。",
            configurable=True,
        )
