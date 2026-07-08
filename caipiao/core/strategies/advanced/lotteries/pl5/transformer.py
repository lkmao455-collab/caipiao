"""排列5Transformer 时序预测高级策略占位。"""

from __future__ import annotations

from ._base import PL5AdvancedStrategy


class PL5TransformerStrategy(PL5AdvancedStrategy):
    """Transformer 时序预测（排列5占位）。"""

    _id = "transformer_pl5"
    _name = "Transformer 时序预测（排列5）"
    _description = "基于可训练 Transformer Encoder 学习历史 one-hot 序列规律，输出下一期号码概率。（当前为占位实现）"
    is_ml = True
