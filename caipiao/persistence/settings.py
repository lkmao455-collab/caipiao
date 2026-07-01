"""应用设置."""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings


class AppSettings:
    """封装 QSettings，提供类型安全的配置读写."""

    def __init__(self, organization: str = "CaipiaoApp", app: str = "Generator") -> None:
        self._settings = QSettings(organization, app)

    def get(self, key: str, default=None):
        """读取设置项."""
        return self._settings.value(key, default)

    def set(self, key: str, value) -> None:
        """写入设置项."""
        self._settings.setValue(key, value)

    @property
    def default_count(self) -> int:
        return int(self.get("default_count", 5))

    @default_count.setter
    def default_count(self, value: int) -> None:
        self.set("default_count", max(1, min(100, int(value))))

    @property
    def last_strategy_id(self) -> str:
        return self.get("last_strategy_id", "random")

    @last_strategy_id.setter
    def last_strategy_id(self, value: str) -> None:
        self.set("last_strategy_id", value)

    @property
    def dark_theme(self) -> bool:
        return self.get("dark_theme", False) in (True, "true", "True", 1, "1")

    @dark_theme.setter
    def dark_theme(self, value: bool) -> None:
        self.set("dark_theme", bool(value))

    @property
    def plugin_dir(self) -> str:
        return self.get("plugin_dir", "")

    @plugin_dir.setter
    def plugin_dir(self, value: str) -> None:
        self.set("plugin_dir", value)

    @property
    def auto_update_on_start(self) -> bool:
        return self.get("auto_update_on_start", True) in (True, "true", "True", 1, "1")

    @auto_update_on_start.setter
    def auto_update_on_start(self, value: bool) -> None:
        self.set("auto_update_on_start", bool(value))

    @property
    def auto_update_interval_days(self) -> int:
        return int(self.get("auto_update_interval_days", 1))

    @auto_update_interval_days.setter
    def auto_update_interval_days(self, value: int) -> None:
        self.set("auto_update_interval_days", max(1, min(30, int(value))))

    @property
    def last_data_update(self) -> str:
        return self.get("last_data_update", "")

    @last_data_update.setter
    def last_data_update(self, value: str) -> None:
        self.set("last_data_update", value)

    @property
    def last_strategy_options(self) -> dict:
        """上次生成时使用的策略参数（JSON 字符串）。"""
        raw = self.get("last_strategy_options", "")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    @last_strategy_options.setter
    def last_strategy_options(self, value: dict) -> None:
        self.set("last_strategy_options", json.dumps(value or {}, ensure_ascii=False))

    def sync(self) -> None:
        """同步写入磁盘."""
        self._settings.sync()
