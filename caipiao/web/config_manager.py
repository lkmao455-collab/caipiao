"""配置管理系统：动态配置中心和配置版本管理。"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class ConfigItem:
    key: str
    value: Any
    value_type: str = "string"  # string, number, boolean, json, list
    description: str = ""
    category: str = "general"
    is_secret: bool = False
    is_readonly: bool = False
    default_value: Any = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    updated_by: str = ""


@dataclass
class ConfigVersion:
    version: int
    items: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    created_by: str = ""
    description: str = ""


class ConfigManager:
    """配置管理器：动态配置、版本管理、配置监听。"""

    def __init__(self, data_dir: str = ".caipiao/config"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._configs: dict[str, ConfigItem] = {}
        self._versions: list[ConfigVersion] = []
        self._listeners: dict[str, list[callable]] = {}
        self._current_version = 0
        self._load_configs()

    def _load_configs(self):
        file_path = self._data_dir / "configs.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, item_data in data.items():
                self._configs[key] = ConfigItem(**item_data)

    def _save_configs(self):
        file_path = self._data_dir / "configs.json"
        data = {
            key: {
                "key": item.key,
                "value": item.value,
                "value_type": item.value_type,
                "description": item.description,
                "category": item.category,
                "is_secret": item.is_secret,
                "is_readonly": item.is_readonly,
                "default_value": item.default_value,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "updated_by": item.updated_by,
            }
            for key, item in self._configs.items()
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        item = self._configs.get(key)
        if item:
            return item.value
        return default

    def set(
        self,
        key: str,
        value: Any,
        value_type: str = "string",
        description: str = "",
        category: str = "general",
        is_secret: bool = False,
        updated_by: str = "",
    ):
        if key in self._configs and self._configs[key].is_readonly:
            raise ValueError(f"Config {key} is readonly")

        old_value = self._configs.get(key).value if key in self._configs else None

        self._configs[key] = ConfigItem(
            key=key,
            value=value,
            value_type=value_type,
            description=description,
            category=category,
            is_secret=is_secret,
            default_value=self._configs.get(key).default_value if key in self._configs else value,
            updated_at=time.time(),
            updated_by=updated_by,
        )

        self._save_configs()
        self._notify_listeners(key, old_value, value)

    def delete(self, key: str) -> bool:
        if key in self._configs and not self._configs[key].is_readonly:
            del self._configs[key]
            self._save_configs()
            return True
        return False

    def get_by_category(self, category: str) -> list[ConfigItem]:
        return [item for item in self._configs.values() if item.category == category]

    def get_all(self, include_secrets: bool = False) -> list[ConfigItem]:
        if include_secrets:
            return list(self._configs.values())
        return [item for item in self._configs.values() if not item.is_secret]

    def watch(self, key: str, callback: callable):
        if key not in self._listeners:
            self._listeners[key] = []
        self._listeners[key].append(callback)

    def _notify_listeners(self, key: str, old_value: Any, new_value: Any):
        for callback in self._listeners.get(key, []):
            try:
                callback(key, old_value, new_value)
            except Exception as e:
                logger.error(f"Config listener error: {e}")

    # 版本管理
    def create_version(self, description: str = "", created_by: str = "") -> ConfigVersion:
        self._current_version += 1
        version = ConfigVersion(
            version=self._current_version,
            items={key: item.value for key, item in self._configs.items()},
            description=description,
            created_by=created_by,
        )
        self._versions.append(version)
        return version

    def get_versions(self) -> list[ConfigVersion]:
        return self._versions

    def rollback(self, version: int) -> bool:
        target = next((v for v in self._versions if v.version == version), None)
        if not target:
            return False

        for key, value in target.items.items():
            if key in self._configs:
                self._configs[key].value = value
                self._configs[key].updated_at = time.time()

        self._save_configs()
        return True

    # 批量操作
    def update_many(self, configs: dict[str, Any], updated_by: str = ""):
        for key, value in configs.items():
            self.set(key, value, updated_by=updated_by)

    def export_configs(self) -> dict[str, Any]:
        return {key: item.value for key, item in self._configs.items()}

    def import_configs(self, data: dict[str, Any], updated_by: str = ""):
        for key, value in data.items():
            self.set(key, value, updated_by=updated_by)


# 全局配置管理器
_config_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
