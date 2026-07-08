"""KL8 XGBoost 模型占位实现."""

from __future__ import annotations

from typing import Any


class KL8XGBoostModel:
    """KL8 XGBoost 模型占位.

    由于 KL8 玩家选号数量 1-10 个可变，当前顺序生成模型无法直接支持，
    因此该类暂不提供实现。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "KL8 XGBoost 模型尚未实现：可变选号数量与当前顺序生成模型不兼容。"
        )
