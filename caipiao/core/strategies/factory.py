"""策略工厂入口。"""

from __future__ import annotations

from typing import List

from ..profile import LotteryProfile
from .registry import STRATEGY_REGISTRY
from ..strategy import GenerationStrategy


def build_strategies(profile: LotteryProfile) -> List[GenerationStrategy]:
    """为指定彩种生成全部策略实例。"""
    classes = STRATEGY_REGISTRY.get(profile.key)
    if classes is None:
        raise ValueError(f"未注册彩种 {profile.key} 的策略")
    return [cls() for cls in classes]


def needs_history(strategy_id: str) -> bool:
    """判断策略是否需要历史开奖数据。"""
    for key in (
        "hot_cold", "smart_hot_cold", "missing_number", "balanced",
        "stats", "xgboost", "lightgbm", "catboost", "ml_",
        "lstm", "hybrid", "random_forest", "bayesian", "markov",
        "trend", "periodic", "ensemble", "correlation", "transformer",
    ):
        if strategy_id.startswith(key):
            return True
    return False


def is_ml_strategy(strategy_id: str) -> bool:
    """判断策略是否为机器学习策略。"""
    return (
        strategy_id.startswith("xgboost_")
        or strategy_id.startswith("lightgbm_")
        or strategy_id.startswith("catboost_")
        or strategy_id.startswith("ml_")
        or strategy_id.startswith("random_forest")
        or strategy_id.startswith("ensemble")
        or strategy_id.startswith("lstm")
        or strategy_id.startswith("hybrid")
        or strategy_id.startswith("transformer")
    )
