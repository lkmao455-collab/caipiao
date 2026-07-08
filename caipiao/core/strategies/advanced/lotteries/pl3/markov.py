"""排列3马尔可夫链分析高级策略占位。"""

from __future__ import annotations

from ._base import PL3AdvancedStrategy


class PL3MarkovStrategy(PL3AdvancedStrategy):
    """马尔可夫链分析（排列3占位）。"""

    _id = "markov_pl3"
    _name = "马尔可夫链分析（排列3）"
    _description = "基于状态转移矩阵分析号码出现的转移规律。（当前为占位实现）"
    is_ml = False
