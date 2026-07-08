"""排列5马尔可夫链分析高级策略占位。"""

from __future__ import annotations

from ._base import PL5AdvancedStrategy


class PL5MarkovStrategy(PL5AdvancedStrategy):
    """马尔可夫链分析（排列5占位）。"""

    _id = "markov_pl5"
    _name = "马尔可夫链分析（排列5）"
    _description = "基于状态转移矩阵分析号码出现的转移规律。（当前为占位实现）"
    is_ml = False
