"""双色球 LSTM 策略.

复用原有通用 LSTMStrategy 逻辑，仅替换为 SSQ 专属的 ml_lstm ID。
"""

from __future__ import annotations

from .....strategy import StrategyMetadata
from ....lstm_strategy import LSTMStrategy


class SSQLSTMStrategy(LSTMStrategy):
    """LSTM 智能分析。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ml_lstm",
            name="LSTM 时序分析",
            description="基于 LSTM 神经网络捕捉号码时序规律，红球和蓝球分别建模。",
            configurable=True,
        )
