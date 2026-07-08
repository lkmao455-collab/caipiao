"""快乐8马尔可夫链分析高级策略占位。"""

from __future__ import annotations

from ._base import KL8AdvancedStrategy


class KL8MarkovStrategy(KL8AdvancedStrategy):
    """马尔可夫链分析（快乐8占位）。"""

    _id = "markov_kl8"
    _name = "马尔可夫链分析（快乐8）"
    _description = "基于状态转移矩阵分析号码出现的转移规律。（当前为占位实现）"
    is_ml = False
