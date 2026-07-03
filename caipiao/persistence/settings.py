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
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 5
        self.set("default_count", max(1, min(1000, value)))

    @property
    def last_strategy_id(self) -> str:
        return self.get("last_strategy_id", "random")

    @last_strategy_id.setter
    def last_strategy_id(self, value: str) -> None:
        self.set("last_strategy_id", value)

    @property
    def dark_theme(self) -> bool:
        raw = self.get("dark_theme", False)
        if isinstance(raw, str):
            return raw.strip().lower() in {"true", "1", "yes", "on"}
        return bool(raw)

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
        raw = self.get("auto_update_on_start", True)
        if isinstance(raw, str):
            return raw.strip().lower() in {"true", "1", "yes", "on"}
        return bool(raw)

    @auto_update_on_start.setter
    def auto_update_on_start(self, value: bool) -> None:
        self.set("auto_update_on_start", bool(value))

    @property
    def auto_update_interval_days(self) -> int:
        return int(self.get("auto_update_interval_days", 1))

    @auto_update_interval_days.setter
    def auto_update_interval_days(self, value: int) -> None:
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 1
        self.set("auto_update_interval_days", max(1, min(30, value)))

    @property
    def last_data_update(self) -> str:
        return self.get("last_data_update", "")

    @last_data_update.setter
    def last_data_update(self, value: str) -> None:
        self.set("last_data_update", value)

    @property
    def boss_key(self) -> str:
        return self.get("boss_key", "")

    @boss_key.setter
    def boss_key(self, value: str) -> None:
        self.set("boss_key", value.strip() if value else "")

    @property
    def last_history_count(self) -> int:
        """ML/历史策略上次使用的历史记录期数；-1 表示使用全部。"""
        try:
            return int(self.get("last_history_count", -1))
        except (ValueError, TypeError):
            return -1

    @last_history_count.setter
    def last_history_count(self, value: int) -> None:
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = -1
        self.set("last_history_count", value)

    @property
    def last_backtest_options(self) -> dict:
        """历史回测对话框上次使用的参数."""
        raw = self.get("last_backtest_options", "")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    @last_backtest_options.setter
    def last_backtest_options(self, value: dict) -> None:
        try:
            self.set("last_backtest_options", json.dumps(value or {}, ensure_ascii=False))
        except TypeError:
            self.set("last_backtest_options", "{}")

    @property
    def last_backtest_date(self) -> str:
        return self.get("last_backtest_date", "")

    @last_backtest_date.setter
    def last_backtest_date(self, value: str) -> None:
        self.set("last_backtest_date", value)

    @property
    def last_backtest_count(self) -> int:
        try:
            return int(self.get("last_backtest_count", 5))
        except (ValueError, TypeError):
            return 5

    @last_backtest_count.setter
    def last_backtest_count(self, value: int) -> None:
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 5
        self.set("last_backtest_count", max(1, min(1000, value)))

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
        try:
            self.set("last_strategy_options", json.dumps(value or {}, ensure_ascii=False))
        except TypeError:
            self.set("last_strategy_options", "{}")

    def sync(self) -> None:
        """同步写入磁盘."""
        self._settings.sync()
