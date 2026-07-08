"""超级大乐透马尔可夫链分析高级策略占位。"""

from __future__ import annotations

from ._base import DLTAdvancedStrategy


class DLTMarkovStrategy(DLTAdvancedStrategy):
    """马尔可夫链分析（超级大乐透占位）。"""

    _id = "markov_dlt"
    _name = "马尔可夫链分析（超级大乐透）"
    _description = "基于状态转移矩阵分析号码出现的转移规律。（当前为占位实现）"
    is_ml = False
