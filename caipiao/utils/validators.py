"""输入校验工具."""

from __future__ import annotations

from typing import List


def parse_int_list(text: str, min_val: int = 1, max_val: int = 33) -> List[int]:
    """解析逗号/空格分隔的整数列表."""
    result: List[int] = []
    if not text.strip():
        return result
    for part in text.replace("，", ",").replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        if not (min_val <= value <= max_val):
            raise ValueError(f"数值 {value} 不在 {min_val}-{max_val} 范围内")
        result.append(value)
    return result
