"""插件扩展系统：管理和加载自定义插件。"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import logging

logger = logging.getLogger(__name__)


@dataclass
class PluginMeta:
    """插件元数据。"""

    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    enabled: bool = True
    hooks: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plugin:
    """插件实例。"""

    meta: PluginMeta
    module: Any = None
    instance: Any = None
    hooks: dict[str, list[Callable]] = field(default_factory=dict)


class PluginManager:
    """插件管理器：加载、启用、禁用插件。"""

    def __init__(self, plugins_dir: str = ".caipiao/plugins"):
        self._plugins_dir = Path(plugins_dir)
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, Plugin] = {}
        self._hook_registry: dict[str, list[Callable]] = {}
        self._load_plugins()

    def _load_plugins(self):
        """从插件目录加载所有插件。"""
        for plugin_dir in self._plugins_dir.iterdir():
            if plugin_dir.is_dir():
                manifest_path = plugin_dir / "manifest.json"
                if manifest_path.exists():
                    try:
                        self._load_plugin(plugin_dir)
                    except Exception as e:
                        logger.error(f"Failed to load plugin {plugin_dir.name}: {e}")

    def _load_plugin(self, plugin_dir: Path):
        """加载单个插件。"""
        manifest_path = plugin_dir / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        meta = PluginMeta(
            id=manifest["id"],
            name=manifest["name"],
            version=manifest.get("version", "1.0.0"),
            description=manifest.get("description", ""),
            author=manifest.get("author", ""),
            enabled=manifest.get("enabled", True),
            hooks=manifest.get("hooks", []),
            config=manifest.get("config", {}),
        )

        # 加载插件模块
        module_name = f"caipiao_plugin_{meta.id}"
        plugin_py = plugin_dir / "plugin.py"
        if plugin_py.exists():
            spec = importlib.util.spec_from_file_location(module_name, plugin_py)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # 创建插件实例
                if hasattr(module, "PluginClass"):
                    instance = module.PluginClass(meta.config)
                else:
                    instance = None

                plugin = Plugin(meta=meta, module=module, instance=instance)

                # 注册钩子
                for hook_name in meta.hooks:
                    if hasattr(module, hook_name):
                        hook_func = getattr(module, hook_name)
                        plugin.hooks[hook_name] = [hook_func]
                        if hook_name not in self._hook_registry:
                            self._hook_registry[hook_name] = []
                        self._hook_registry[hook_name].append(hook_func)

                self._plugins[meta.id] = plugin
                logger.info(f"Loaded plugin: {meta.name} v{meta.version}")
        else:
            self._plugins[meta.id] = Plugin(meta=meta)

    def get_plugins(self) -> list[PluginMeta]:
        """获取所有插件列表。"""
        return [p.meta for p in self._plugins.values()]

    def get_plugin(self, plugin_id: str) -> PluginMeta | None:
        """获取插件元数据。"""
        plugin = self._plugins.get(plugin_id)
        return plugin.meta if plugin else None

    def enable_plugin(self, plugin_id: str) -> bool:
        """启用插件。"""
        plugin = self._plugins.get(plugin_id)
        if plugin:
            plugin.meta.enabled = True
            self._save_plugin_state(plugin_id, True)
            return True
        return False

    def disable_plugin(self, plugin_id: str) -> bool:
        """禁用插件。"""
        plugin = self._plugins.get(plugin_id)
        if plugin:
            plugin.meta.enabled = False
            self._save_plugin_state(plugin_id, False)
            return True
        return False

    def _save_plugin_state(self, plugin_id: str, enabled: bool):
        """保存插件状态。"""
        plugin = self._plugins.get(plugin_id)
        if plugin:
            manifest_path = self._plugins_dir / plugin_id / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                manifest["enabled"] = enabled
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)

    def execute_hook(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """执行钩子。"""
        results = []
        if hook_name in self._hook_registry:
            for hook_func in self._hook_registry[hook_name]:
                try:
                    result = hook_func(*args, **kwargs)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Hook {hook_name} execution failed: {e}")
        return results

    def install_plugin(self, plugin_dir: str) -> bool:
        """安装插件（从本地目录）。"""
        src = Path(plugin_dir)
        if not src.exists():
            return False

        manifest_path = src / "manifest.json"
        if not manifest_path.exists():
            return False

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        plugin_id = manifest.get("id")
        if not plugin_id:
            return False

        dest = self._plugins_dir / plugin_id
        if dest.exists():
            # 更新已有插件
            import shutil
            shutil.rmtree(dest)

        import shutil
        shutil.copytree(src, dest)

        # 重新加载
        self._load_plugin(dest)
        return True

    def uninstall_plugin(self, plugin_id: str) -> bool:
        """卸载插件。"""
        if plugin_id not in self._plugins:
            return False

        # 移除钩子
        plugin = self._plugins[plugin_id]
        for hook_name, hook_funcs in plugin.hooks.items():
            if hook_name in self._hook_registry:
                for hf in hook_funcs:
                    if hf in self._hook_registry[hook_name]:
                        self._hook_registry[hook_name].remove(hf)

        # 删除插件目录
        plugin_dir = self._plugins_dir / plugin_id
        if plugin_dir.exists():
            import shutil
            shutil.rmtree(plugin_dir)

        del self._plugins[plugin_id]
        return True


# 全局插件管理器
_plugin_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
