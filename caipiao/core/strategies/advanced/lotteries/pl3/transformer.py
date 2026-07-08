"""排列3Transformer 时序预测高级策略占位。"""

from __future__ import annotations

from ._base import PL3AdvancedStrategy


class PL3TransformerStrategy(PL3AdvancedStrategy):
    """Transformer 时序预测（排列3占位）。"""

    _id = "transformer_pl3"
    _name = "Transformer 时序预测（排列3）"
    _description = "基于可训练 Transformer Encoder 学习历史 one-hot 序列规律，输出下一期号码概率。（当前为占位实现）"
    is_ml = True
