"""参数组数据模型.

参数组用于保存「一键找最优策略和参数」扫描结果中的多个策略及其参数，
方便用户日后快速复用。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class StrategyParameterItem:
    """参数组中的单个策略参数条目."""

    strategy_id: str
    strategy_name: str
    param_name: str | None
    param_value: int | None
    enabled: bool = True
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParameterGroup:
    """由多个策略参数条目组成的参数组."""

    id: str
    name: str
    profile_key: str
    created_at: str
    items: List[StrategyParameterItem]
    scan_context: Dict[str, Any] = field(default_factory=dict)


def parameter_group_to_dict(group: ParameterGroup) -> dict:
    """将参数组序列化为字典."""
    return asdict(group)


def parameter_group_from_dict(data: dict) -> ParameterGroup:
    """从字典反序列化参数组，兼容缺少字段的旧数据."""
    items = [
        StrategyParameterItem(
            strategy_id=item.get("strategy_id", ""),
            strategy_name=item.get("strategy_name", ""),
            param_name=item.get("param_name"),
            param_value=item.get("param_value"),
            enabled=item.get("enabled", True),
            metrics=item.get("metrics", {}),
        )
        for item in data.get("items", [])
    ]
    return ParameterGroup(
        id=data.get("id", ""),
        name=data.get("name", ""),
        profile_key=data.get("profile_key", ""),
        created_at=data.get("created_at", ""),
        items=items,
        scan_context=data.get("scan_context", {}),
    )
