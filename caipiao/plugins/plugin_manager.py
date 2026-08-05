"""插件管理器.

支持从指定目录动态加载 Python 文件作为策略插件。
每个插件文件应导出一个或多个 GenerationStrategy 子类，
或通过 register_strategies(engine) 函数注册。
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from ..core.engine import GenerationEngine
from ..core.strategy import GenerationStrategy

logger = logging.getLogger(__name__)


class PluginManager:
    """管理外部策略插件的加载与卸载."""

    def __init__(self, engine: GenerationEngine, plugin_dir: Path | str) -> None:
        self.engine = engine
        self.plugin_dir = Path(plugin_dir)
        self._loaded_plugins: list[ModuleType] = []
        self._plugin_strategy_ids: list[str] = []

    def discover(self) -> list[Path]:
        """发现插件文件."""
        if not self.plugin_dir.is_dir():
            return []
        files = [
            p
            for p in self.plugin_dir.iterdir()
            if p.is_file() and p.suffix == ".py" and not p.name.startswith("_")
        ]
        return sorted(files)

    def load_all(self) -> list[str]:
        """加载所有插件，返回加载的策略 ID 列表."""
        loaded_ids: list[str] = []
        for plugin_path in self.discover():
            try:
                ids = self.load(plugin_path)
                loaded_ids.extend(ids)
            except Exception as exc:  # noqa: BLE001
                logger.error("加载插件失败 %s: %s", plugin_path, exc)
        return loaded_ids

    def load(self, plugin_path: Path) -> list[str]:
        """加载单个插件文件."""
        before_ids = {
            s.metadata.id
            for s in self.engine.list_strategies()
            if getattr(s, "metadata", None) is not None
        }
        spec = importlib.util.spec_from_file_location(
            f"caipiao_plugin_{plugin_path.stem}", plugin_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载插件: {plugin_path}")

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise ImportError(f"无法执行插件: {plugin_path}") from exc
        self._loaded_plugins.append(module)

        loaded_ids: list[str] = []

        # 方式1：通过 register_strategies(engine) 函数注册
        register_func: Callable[[GenerationEngine], None] | None = getattr(
            module, "register_strategies", None
        )
        if callable(register_func):
            try:
                register_func(self.engine)
            except Exception as exc:  # noqa: BLE001
                logger.error("register_strategies 失败 %s: %s", plugin_path, exc)

        # 方式2：自动发现模块中的 GenerationStrategy 子类
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, GenerationStrategy)
                and obj is not GenerationStrategy
                and not inspect.isabstract(obj)
            ):
                try:
                    strategy = obj()
                    self.engine.register(strategy)
                    loaded_ids.append(strategy.metadata.id)
                except Exception as exc:  # noqa: BLE001
                    logger.error("实例化策略失败 %s: %s", obj.__name__, exc)

        # 记录本插件新增的策略 ID（方式1 通过前后对比补充）
        after_ids = {
            s.metadata.id
            for s in self.engine.list_strategies()
            if getattr(s, "metadata", None) is not None
        }
        new_ids = list(after_ids - before_ids)
        self._plugin_strategy_ids.extend(
            sid for sid in new_ids if sid not in self._plugin_strategy_ids
        )
        return list(dict.fromkeys(loaded_ids + new_ids))

    def unload_all(self) -> None:
        """卸载所有已加载插件（仅移除插件策略，保留内置策略）。"""
        for sid in self._plugin_strategy_ids:
            self.engine.unregister(sid)
        self._plugin_strategy_ids.clear()
        self._loaded_plugins.clear()
