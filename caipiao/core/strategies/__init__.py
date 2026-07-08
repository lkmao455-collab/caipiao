"""策略包公共入口。"""

from .factory import build_strategies, is_ml_strategy, needs_history

__all__ = ["build_strategies", "needs_history", "is_ml_strategy"]
