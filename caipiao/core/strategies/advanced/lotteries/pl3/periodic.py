"""排列3周期性分析高级策略占位。"""

from __future__ import annotations

from ._base import PL3AdvancedStrategy


class PL3PeriodicStrategy(PL3AdvancedStrategy):
    """周期性分析（排列3占位）。"""

    _id = "periodic_pl3"
    _name = "周期性分析（排列3）"
    _description = "分析号码出现的周/月/季度周期性规律，多周期融合推荐。（当前为占位实现）"
    is_ml = False
