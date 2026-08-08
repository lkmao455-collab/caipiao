"""测试插件管理器。"""

import json
import tempfile
from pathlib import Path

import pytest

from caipiao.web.plugin_manager import PluginManager


@pytest.fixture
def plugin_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_plugin(plugin_dir):
    plugin_path = plugin_dir / "test_plugin"
    plugin_path.mkdir()
    manifest = {
        "id": "test_plugin",
        "name": "Test Plugin",
        "version": "1.0.0",
        "description": "A test plugin",
        "author": "Test",
        "enabled": True,
        "hooks": [],
    }
    with open(plugin_path / "manifest.json", "w") as f:
        json.dump(manifest, f)
    return plugin_path


def test_plugin_manager_init(plugin_dir):
    pm = PluginManager(str(plugin_dir))
    assert pm.get_plugins() == []


def test_load_plugin(plugin_dir, sample_plugin):
    pm = PluginManager(str(plugin_dir))
    plugins = pm.get_plugins()
    assert len(plugins) == 1
    assert plugins[0].id == "test_plugin"
    assert plugins[0].name == "Test Plugin"


def test_enable_disable_plugin(plugin_dir, sample_plugin):
    pm = PluginManager(str(plugin_dir))
    assert pm.disable_plugin("test_plugin")
    assert pm.get_plugin("test_plugin").enabled is False
    assert pm.enable_plugin("test_plugin")
    assert pm.get_plugin("test_plugin").enabled is True


def test_nonexistent_plugin(plugin_dir):
    pm = PluginManager(str(plugin_dir))
    assert pm.get_plugin("nonexistent") is None
    assert pm.enable_plugin("nonexistent") is False
    assert pm.disable_plugin("nonexistent") is False


def test_uninstall_plugin(plugin_dir, sample_plugin):
    pm = PluginManager(str(plugin_dir))
    assert pm.uninstall_plugin("test_plugin")
    assert pm.get_plugin("test_plugin") is None
    assert not sample_plugin.exists()
