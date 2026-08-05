"""生成策略接口."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .ticket import Ticket


@dataclass
class StrategyMetadata:
    """策略元数据."""

    id: str
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    configurable: bool = False


class GenerationStrategy(ABC):
    """号码生成策略基类.

    所有自定义策略都必须继承此类，并实现 generate 方法。
    策略可通过插件机制动态加载。
    """

    #: 标记该策略是否为机器学习策略；批量回测 worker 会据此决定
    #: 是否在子进程中预先训练模型。插件 ML 策略也应置为 True。
    is_ml: bool = False

    @property
    @abstractmethod
    def metadata(self) -> StrategyMetadata:
        """返回策略元数据."""
        ...

    @abstractmethod
    def generate(
        self, count: int = 1, options: dict[str, Any] | None = None
    ) -> list[Ticket]:
        """生成指定数量的投注单.

        Args:
            count: 生成数量.
            options: 策略参数，由具体策略定义.

        Returns:
            生成的 Ticket 列表.
        """
        ...

    def get_config_schema(self) -> dict[str, Any] | None:
        """返回配置项定义，用于 UI 动态渲染参数面板.

        返回 JSON Schema 风格字典，例如：
        {
            "seed": {"type": "int", "label": "随机种子", "default": None},
            "min_odd": {"type": "int", "label": "最小奇数个数", "default": 2},
        }
        """
        return None

    def validate_options(self, options: dict[str, Any]) -> None:
        """校验策略参数，可在 generate 前调用."""

    def __str__(self) -> str:
        return f"{self.metadata.name} ({self.metadata.id})"
