"""快乐8策略共享工具."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....profile import KL8
from ....ticket import Ticket


PROFILE = KL8


def _get_pick_count(
    options: Dict[str, Any], default_pick: Optional[int] = None
) -> int:
    """返回本次生成主号码组应选几个号码。

    Args:
        default_pick: 当 options 未指定 pick_count 时的默认值。
            None（默认）表示回退到彩种 effective_pick_max，保持旧行为。
    """
    primary = PROFILE.primary_group
    if not primary.variable_pick:
        return primary.count
    pick = options.get("pick_count")
    if pick is None:
        fallback = primary.effective_pick_max if default_pick is None else default_pick
        return max(primary.effective_pick_min, min(fallback, primary.effective_pick_max))
    try:
        pick = int(pick)
    except (TypeError, ValueError):
        fallback = primary.effective_pick_max if default_pick is None else default_pick
        return max(primary.effective_pick_min, min(fallback, primary.effective_pick_max))
    return max(primary.effective_pick_min, min(pick, primary.effective_pick_max))


def _add_pick_count_schema(
    schema: Dict[str, Any], label: str = "投注个数", default_pick: Optional[int] = None
) -> None:
    """为可变 pick 彩种在策略参数里加入‘选几’配置。

    Args:
        default_pick: schema 默认值。None（默认）表示用彩种 effective_pick_max。
    """
    primary = PROFILE.primary_group
    if not primary.variable_pick:
        return
    default_value = primary.effective_pick_max if default_pick is None else default_pick
    default_value = max(
        primary.effective_pick_min, min(default_value, primary.effective_pick_max)
    )
    schema["pick_count"] = {
        "type": "choice",
        "label": label,
        "choices": list(range(primary.effective_pick_min, primary.effective_pick_max + 1)),
        "default": default_value,
        "tooltip": f"选择投注 {primary.name} 的号码个数。",
    }


def _make_ticket(groups: Dict[str, List[int]], **kwargs) -> Ticket:
    return Ticket(profile=PROFILE, groups=groups, **kwargs)
