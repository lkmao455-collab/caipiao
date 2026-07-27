"""快乐8生成策略."""

from .balanced import KL8BalancedStrategy
from .smart_hot_cold import KL8SmartHotColdStrategy

__all__ = [
    "KL8SmartHotColdStrategy",
    "KL8BalancedStrategy",
]
