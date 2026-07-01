"""生成引擎."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .strategy import GenerationStrategy
from .ticket import Ticket


class GenerationEngine:
    """号码生成引擎.

    负责管理所有可用策略，并根据选中的策略生成投注单。
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, GenerationStrategy] = {}

    def register(self, strategy: GenerationStrategy) -> None:
        """注册一个生成策略."""
        self._strategies[strategy.metadata.id] = strategy

    def unregister(self, strategy_id: str) -> None:
        """注销指定策略."""
        self._strategies.pop(strategy_id, None)

    def get(self, strategy_id: str) -> Optional[GenerationStrategy]:
        """获取指定策略."""
        return self._strategies.get(strategy_id)

    def list_strategies(self) -> List[GenerationStrategy]:
        """列出所有已注册策略."""
        return list(self._strategies.values())

    def generate(
        self,
        strategy_id: str,
        count: int = 1,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[Ticket]:
        """使用指定策略生成投注单."""
        strategy = self._strategies.get(strategy_id)
        if strategy is None:
            raise ValueError(f"未找到策略: {strategy_id}")
        options = options or {}
        strategy.validate_options(options)
        return strategy.generate(count=count, options=options)
