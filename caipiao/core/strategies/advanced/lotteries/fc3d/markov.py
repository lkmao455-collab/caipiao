"""福彩3D马尔可夫链分析高级策略占位。"""

from __future__ import annotations

from ._base import FC3DAdvancedStrategy


class FC3DMarkovStrategy(FC3DAdvancedStrategy):
    """马尔可夫链分析（福彩3D占位）。"""

    _id = "markov_3d"
    _name = "马尔可夫链分析（福彩3D）"
    _description = "基于状态转移矩阵分析号码出现的转移规律。（当前为占位实现）"
    is_ml = False
