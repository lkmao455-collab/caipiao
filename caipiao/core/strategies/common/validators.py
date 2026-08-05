"""通用参数校验辅助."""

from __future__ import annotations

from typing import Any


def validate_odd_count(options: dict[str, Any], pick: int) -> None:
    """校验奇数个数参数。"""
    odd_count = options.get("odd_count", pick // 2)
    if not isinstance(odd_count, int) or not (0 <= odd_count <= pick):
        raise ValueError(f"奇数个数必须是 0-{pick} 的整数")
