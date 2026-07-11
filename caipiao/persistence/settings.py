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
    def draw_analysis_max_gap(self) -> int:
        return int(self.get("draw_analysis_max_gap", 1))

    @draw_analysis_max_gap.setter
    def draw_analysis_max_gap(self, value: int) -> None:
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 1
        self.set("draw_analysis_max_gap", max(0, min(50, value)))

    @property
    def draw_analysis_filter_threshold(self) -> int:
        return int(self.get("draw_analysis_filter_threshold", 1))

    @draw_analysis_filter_threshold.setter
    def draw_analysis_filter_threshold(self, value: int) -> None:
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 1
        self.set("draw_analysis_filter_threshold", max(0, min(10, value)))

    # ------------------------------------------------------------------ #
    # 开奖记录分析 - 按彩种分开存储
    # ------------------------------------------------------------------ #

    def get_draw_analysis_max_gap(self, profile_key: str) -> int:
        """获取指定彩种的最大间隔期数，默认1."""
        try:
            return int(self.get(f"draw_analysis_{profile_key}_max_gap", 1))
        except (ValueError, TypeError):
            return 1

    def set_draw_analysis_max_gap(self, profile_key: str, value: int) -> None:
        """设置指定彩种的最大间隔期数."""
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 1
        self.set(f"draw_analysis_{profile_key}_max_gap", max(0, min(50, value)))

    def get_draw_analysis_filter_threshold(self, profile_key: str) -> int:
        """获取指定彩种的过滤阈值，默认1."""
        try:
            return int(self.get(f"draw_analysis_{profile_key}_filter_threshold", 1))
        except (ValueError, TypeError):
            return 1

    def set_draw_analysis_filter_threshold(self, profile_key: str, value: int) -> None:
        """设置指定彩种的过滤阈值."""
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 1
        self.set(f"draw_analysis_{profile_key}_filter_threshold", max(0, min(10, value)))

    def get_draw_analysis_group_mode(self, profile_key: str) -> str:
        """获取指定彩种的分组模式，默认'all'."""
        return str(self.get(f"draw_analysis_{profile_key}_group_mode", "all"))

    def set_draw_analysis_group_mode(self, profile_key: str, value: str) -> None:
        """设置指定彩种的分组模式."""
        self.set(f"draw_analysis_{profile_key}_group_mode", str(value))

    # ------------------------------------------------------------------ #
    # 批量回测参数
    # ------------------------------------------------------------------ #

    def get_batch_backtest_count(self, profile_key: str) -> int:
        """获取指定彩种的批量回测每期注数，默认5."""
        try:
            return int(self.get(f"batch_backtest_{profile_key}_count", 5))
        except (ValueError, TypeError):
            return 5

    def set_batch_backtest_count(self, profile_key: str, value: int) -> None:
        """设置指定彩种的批量回测每期注数."""
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 5
        self.set(f"batch_backtest_{profile_key}_count", max(1, min(1000, value)))

    def get_batch_backtest_filter_threshold(self, profile_key: str) -> int:
        """获取指定彩种的批量回测过滤阈值，默认1."""
        try:
            return int(self.get(f"batch_backtest_{profile_key}_filter_threshold", 1))
        except (ValueError, TypeError):
            return 1

    def set_batch_backtest_filter_threshold(self, profile_key: str, value: int) -> None:
        """设置指定彩种的批量回测过滤阈值."""
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 1
        self.set(f"batch_backtest_{profile_key}_filter_threshold", max(0, min(10, value)))

    def get_batch_backtest_filter_periods(self, profile_key: str) -> int:
        """获取指定彩种的批量回测比较期数，默认7."""
        try:
            return int(self.get(f"batch_backtest_{profile_key}_filter_periods", 7))
        except (ValueError, TypeError):
            return 7

    def set_batch_backtest_filter_periods(self, profile_key: str, value: int) -> None:
        """设置指定彩种的批量回测比较期数."""
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 7
        self.set(f"batch_backtest_{profile_key}_filter_periods", max(1, min(50, value)))

    # ------------------------------------------------------------------ #
    # 双色球过滤参数
    # ------------------------------------------------------------------ #

    @property
    def ssq_filter_compare_periods(self) -> int:
        """SSQ过滤：对比的历史期数，默认 7。"""
        try:
            return int(self.get("ssq_filter_compare_periods", 7))
        except (ValueError, TypeError):
            return 7

    @ssq_filter_compare_periods.setter
    def ssq_filter_compare_periods(self, value: int) -> None:
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 7
        self.set("ssq_filter_compare_periods", max(0, min(50, value)))

    @property
    def ssq_filter_max_red_overlap(self) -> int:
        """SSQ过滤：允许的红球最大重合数，默认 3。"""
        try:
            return int(self.get("ssq_filter_max_red_overlap", 3))
        except (ValueError, TypeError):
            return 3

    @ssq_filter_max_red_overlap.setter
    def ssq_filter_max_red_overlap(self, value: int) -> None:
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 3
        self.set("ssq_filter_max_red_overlap", max(0, min(6, value)))

    @property
    def ssq_filter_block_blue(self) -> bool:
        """SSQ过滤：是否禁止蓝球与历史相同，默认 False。"""
        raw = self.get("ssq_filter_block_blue", False)
        if isinstance(raw, str):
            return raw.strip().lower() in {"true", "1", "yes", "on"}
        return bool(raw)

    @ssq_filter_block_blue.setter
    def ssq_filter_block_blue(self, value: bool) -> None:
        self.set("ssq_filter_block_blue", bool(value))

    # ------------------------------------------------------------------ #
    # 福彩3D 经验策略过滤参数
    # ------------------------------------------------------------------ #

    @property
    def fc3d_filter_enabled(self) -> bool:
        """3D经验策略过滤：是否启用，默认 False（保持原有无过滤行为）。"""
        raw = self.get("fc3d_filter_enabled", False)
        if isinstance(raw, str):
            return raw.strip().lower() in {"true", "1", "yes", "on"}
        return bool(raw)

    @fc3d_filter_enabled.setter
    def fc3d_filter_enabled(self, value: bool) -> None:
        self.set("fc3d_filter_enabled", bool(value))

    @property
    def fc3d_filter_compare_periods(self) -> int:
        """3D经验策略过滤：向前比较的历史期数，默认 5。"""
        try:
            return int(self.get("fc3d_filter_compare_periods", 5))
        except (ValueError, TypeError):
            return 5

    @fc3d_filter_compare_periods.setter
    def fc3d_filter_compare_periods(self, value: int) -> None:
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 5
        self.set("fc3d_filter_compare_periods", max(0, min(50, value)))

    @property
    def fc3d_filter_max_overlap(self) -> int:
        """3D经验策略过滤：允许的相同号码最大个数，默认 1（超过则淘汰）。"""
        try:
            return int(self.get("fc3d_filter_max_overlap", 1))
        except (ValueError, TypeError):
            return 1

    @fc3d_filter_max_overlap.setter
    def fc3d_filter_max_overlap(self, value: int) -> None:
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 1
        self.set("fc3d_filter_max_overlap", max(0, min(3, value)))

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
