"""7星彩马尔可夫链分析高级策略占位。"""

from __future__ import annotations

from ._base import QXCAdvancedStrategy


class QXCMarkovStrategy(QXCAdvancedStrategy):
    """马尔可夫链分析（7星彩占位）。"""

    _id = "markov_qxc"
    _name = "马尔可夫链分析（7星彩）"
    _description = "基于状态转移矩阵分析号码出现的转移规律。（当前为占位实现）"
    is_ml = False
