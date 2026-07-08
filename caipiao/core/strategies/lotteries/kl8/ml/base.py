"""快乐8 ML 策略公共逻辑（文件私有）.

当前 ``GenericMLPredictor`` 训练目标为开奖 20 码，而玩家选号范围为 1-10 个，
计数不匹配，因此暂以占位基类实现；待后端支持可变选号后再替换。
"""

from __future__ import annotations

from ....common.ml import make_placeholder_ml_base
from .....profile import KL8

_KL8MLStrategyBase = make_placeholder_ml_base(
    KL8,
    reason="GenericMLPredictor 的组合组采样固定返回 20 个号码，与 KL8 投注单 1-10 个号码的约束不匹配。",
)
