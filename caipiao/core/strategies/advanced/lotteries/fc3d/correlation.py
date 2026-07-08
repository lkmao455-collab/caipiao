"""福彩3D相关性挖掘高级策略占位。"""

from __future__ import annotations

from ._base import FC3DAdvancedStrategy


class FC3DCorrelationStrategy(FC3DAdvancedStrategy):
    """相关性挖掘（福彩3D占位）。"""

    _id = "correlation_3d"
    _name = "相关性挖掘（福彩3D）"
    _description = "挖掘号码间的共现相关性和条件概率，发现隐藏的关联模式。（当前为占位实现）"
    is_ml = False
