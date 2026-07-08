"""排列5相关性挖掘高级策略占位。"""

from __future__ import annotations

from ._base import PL5AdvancedStrategy


class PL5CorrelationStrategy(PL5AdvancedStrategy):
    """相关性挖掘（排列5占位）。"""

    _id = "correlation_pl5"
    _name = "相关性挖掘（排列5）"
    _description = "挖掘号码间的共现相关性和条件概率，发现隐藏的关联模式。（当前为占位实现）"
    is_ml = False
