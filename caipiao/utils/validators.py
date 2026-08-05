"""输入校验工具."""

from __future__ import annotations


def parse_int_list(text: str, min_val: int = 1, max_val: int = 33) -> list[int]:
    """解析逗号/空格分隔的整数列表."""
    if min_val > max_val:
        raise ValueError(f"min_val ({min_val}) must not be greater than max_val ({max_val})")
    if text is None:
        raise TypeError("text must be a string")
    result: list[int] = []
    if not text.strip():
        return result
    for part in text.replace("，", ",").replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError as exc:
            raise ValueError(f"无法解析整数: {part!r}") from exc
        if not (min_val <= value <= max_val):
            raise ValueError(f"数值 {value} 不在 {min_val}-{max_val} 范围内")
        result.append(value)
    return result
