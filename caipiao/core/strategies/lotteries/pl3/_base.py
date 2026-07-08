"""排列3策略共享工具."""

from __future__ import annotations

import random
from typing import Any, Dict, List

from ....profile import PL3
from ....ticket import Ticket


PROFILE = PL3


def _get_pick_count(options: Dict[str, Any]) -> int:
    """返回本次生成主号码组应选几个号码。"""
    primary = PROFILE.primary_group
    if not primary.variable_pick:
        return primary.count
    pick = options.get("pick_count")
    if pick is None:
        return primary.effective_pick_max
    try:
        pick = int(pick)
    except (TypeError, ValueError):
        return primary.effective_pick_max
    return max(primary.effective_pick_min, min(pick, primary.effective_pick_max))


def _add_pick_count_schema(schema: Dict[str, Any], label: str = "投注个数") -> None:
    """为可变 pick 彩种在策略参数里加入‘选几’配置。"""
    primary = PROFILE.primary_group
    if not primary.variable_pick:
        return
    schema["pick_count"] = {
        "type": "choice",
        "label": label,
        "choices": list(range(primary.effective_pick_min, primary.effective_pick_max + 1)),
        "default": primary.effective_pick_max,
        "tooltip": f"选择投注 {primary.name} 的号码个数。",
    }


def _make_ticket(groups: Dict[str, List[int]], **kwargs) -> Ticket:
    return Ticket(profile=PROFILE, groups=groups, **kwargs)
