"""持久化设置测试."""

import pytest

from caipiao.persistence.settings import AppSettings


class TestAppSettings:
    """AppSettings 测试."""

    def test_initialization(self):
        settings = AppSettings()
        assert settings is not None

    def test_default_count(self):
        settings = AppSettings()
        assert settings.default_count >= 1

    def test_set_default_count(self):
        settings = AppSettings()
        settings.default_count = 10
        assert settings.default_count == 10

    def test_default_count_bounds(self):
        settings = AppSettings()
        settings.default_count = 0
        assert settings.default_count == 1
        settings.default_count = 2000
        assert settings.default_count == 1000

    def test_last_strategy_id(self):
        settings = AppSettings()
        settings.last_strategy_id = "test_strategy"
        assert settings.last_strategy_id == "test_strategy"

    def test_dark_theme(self):
        settings = AppSettings()
        settings.dark_theme = True
        assert settings.dark_theme is True

    def test_plugin_dir(self):
        settings = AppSettings()
        settings.plugin_dir = "/test/path"
        assert settings.plugin_dir == "/test/path"

    def test_auto_update_on_start(self):
        settings = AppSettings()
        settings.auto_update_on_start = False
        assert settings.auto_update_on_start is False

    def test_auto_update_interval_days(self):
        settings = AppSettings()
        settings.auto_update_interval_days = 7
        assert settings.auto_update_interval_days == 7

    def test_auto_update_interval_bounds(self):
        settings = AppSettings()
        settings.auto_update_interval_days = 0
        assert settings.auto_update_interval_days == 1
        settings.auto_update_interval_days = 50
        assert settings.auto_update_interval_days == 30

    def test_boss_key(self):
        settings = AppSettings()
        settings.boss_key = "Ctrl+Shift+B"
        assert settings.boss_key == "Ctrl+Shift+B"

    def test_ssq_filter_compare_periods(self):
        settings = AppSettings()
        settings.ssq_filter_compare_periods = 10
        assert settings.ssq_filter_compare_periods == 10

    def test_ssq_filter_max_red_overlap(self):
        settings = AppSettings()
        settings.ssq_filter_max_red_overlap = 2
        assert settings.ssq_filter_max_red_overlap == 2

    def test_ssq_filter_block_blue(self):
        settings = AppSettings()
        settings.ssq_filter_block_blue = False
        assert settings.ssq_filter_block_blue is False

    def test_fc3d_filter_enabled(self):
        settings = AppSettings()
        settings.fc3d_filter_enabled = True
        assert settings.fc3d_filter_enabled is True

    def test_fc3d_filter_compare_periods(self):
        settings = AppSettings()
        settings.fc3d_filter_compare_periods = 10
        assert settings.fc3d_filter_compare_periods == 10

    def test_fc3d_filter_max_overlap(self):
        settings = AppSettings()
        settings.fc3d_filter_max_overlap = 2
        assert settings.fc3d_filter_max_overlap == 2

    def test_fc3d_filter_min_sum(self):
        settings = AppSettings()
        settings.fc3d_filter_min_sum = 5
        assert settings.fc3d_filter_min_sum == 5

    def test_fc3d_filter_max_sum(self):
        settings = AppSettings()
        settings.fc3d_filter_max_sum = 20
        assert settings.fc3d_filter_max_sum == 20

    def test_sync(self):
        settings = AppSettings()
        settings.sync()  # 应该不抛异常
