"""插件管理器.

支持从指定目录动态加载 Python 文件作为策略插件。
每个插件文件应导出一个或多个 GenerationStrategy 子类，
或通过 register_strategies(engine) 函数注册。
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path
from types import ModuleType
from typing import Callable, List

from ..core.engine import GenerationEngine
from ..core.strategy import GenerationStrategy

logger = logging.getLogger(__name__)


class PluginManager:
    """管理外部策略插件的加载与卸载."""

    def __init__(self, engine: GenerationEngine, plugin_dir: Path | str) -> None:
        self.engine = engine
        self.plugin_dir = Path(plugin_dir)
        self._loaded_plugins: List[ModuleType] = []

    def discover(self) -> List[Path]:
        """发现插件文件."""
        if not self.plugin_dir.exists():
            return []
        files = [
            p
            for p in self.plugin_dir.iterdir()
            if p.is_file() and p.suffix == ".py" and not p.name.startswith("_")
        ]
        return sorted(files)

    def load_all(self) -> List[str]:
        """加载所有插件，返回加载的策略 ID 列表."""
        loaded_ids: List[str] = []
        for plugin_path in self.discover():
            try:
                ids = self.load(plugin_path)
                loaded_ids.extend(ids)
            except Exception as exc:  # noqa: BLE001
                logger.error("加载插件失败 %s: %s", plugin_path, exc)
        return loaded_ids

    def load(self, plugin_path: Path) -> List[str]:
        """加载单个插件文件."""
        spec = importlib.util.spec_from_file_location(
            f"caipiao_plugin_{plugin_path.stem}", plugin_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载插件: {plugin_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._loaded_plugins.append(module)

        loaded_ids: List[str] = []

        # 方式1：通过 register_strategies(engine) 函数注册
        register_func: Callable[[GenerationEngine], None] | None = getattr(
            module, "register_strategies", None
        )
        if callable(register_func):
            register_func(self.engine)
            # 无法直接知道注册了哪些，稍后通过 engine 反推

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

        return loaded_ids

    def unload_all(self) -> None:
        """卸载所有已加载插件（从引擎中移除相关策略）."""
        # 简单实现：直接清空引擎中所有策略
        self.engine._strategies.clear()
        self._loaded_plugins.clear()
