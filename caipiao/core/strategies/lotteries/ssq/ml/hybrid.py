"""双色球混合模型策略.

复用原有通用 HybridStrategy 逻辑，仅替换为 SSQ 专属的 ml_hybrid ID。
"""

from __future__ import annotations

from .....strategy import StrategyMetadata
from ....hybrid_strategy import HybridStrategy


class SSQHybridStrategy(HybridStrategy):
    """混合模型智能分析。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ml_hybrid",
            name="智能混合分析",
            description="红球用 XGBoost 概率建模，蓝球用 LSTM 时序建模，取两者优势。",
            configurable=True,
        )
