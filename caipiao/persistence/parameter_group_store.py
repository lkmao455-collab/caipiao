"""参数组持久化存储.

按彩种分别存储为 JSON 文件：
    <data_dir>/param_groups/<profile_key>.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from ..core.parameter_group import (
    ParameterGroup,
    parameter_group_from_dict,
    parameter_group_to_dict,
)

logger = logging.getLogger(__name__)


class ParameterGroupStore:
    """参数组持久化存储."""

    def __init__(self, data_dir: Path) -> None:
        self._base_dir = data_dir / "param_groups"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, profile_key: str) -> Path:
        """返回指定彩种的存储文件路径."""
        return self._base_dir / f"{profile_key}.json"

    def load_all(self, profile_key: str) -> List[ParameterGroup]:
        """加载指定彩种的所有参数组."""
        path = self.path_for(profile_key)
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("参数组文件损坏或读取失败: %s, 错误: %s", path, exc)
            return []
        if not isinstance(data, list):
            return []
        return [parameter_group_from_dict(item) for item in data]

    def save(self, group: ParameterGroup) -> None:
        """保存参数组；若已存在则更新."""
        groups = self.load_all(group.profile_key)
        updated = [g for g in groups if g.id != group.id]
        updated.append(group)
        self._write(group.profile_key, updated)

    def delete(self, profile_key: str, group_id: str) -> bool:
        """删除指定参数组."""
        groups = self.load_all(profile_key)
        before = len(groups)
        remaining = [g for g in groups if g.id != group_id]
        if len(remaining) == before:
            return False
        self._write(profile_key, remaining)
        return True

    def rename(self, profile_key: str, group_id: str, new_name: str) -> bool:
        """重命名指定参数组."""
        groups = self.load_all(profile_key)
        for g in groups:
            if g.id == group_id:
                g.name = new_name
                self._write(profile_key, groups)
                return True
        return False

    def get(self, profile_key: str, group_id: str) -> ParameterGroup | None:
        """获取指定参数组."""
        for g in self.load_all(profile_key):
            if g.id == group_id:
                return g
        return None

    def _write(self, profile_key: str, groups: List[ParameterGroup]) -> None:
        """将参数组列表写入磁盘."""
        path = self.path_for(profile_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(
                [parameter_group_to_dict(g) for g in groups],
                f,
                ensure_ascii=False,
                indent=2,
            )
