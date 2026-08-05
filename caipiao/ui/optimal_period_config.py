"""一键找最优期数的参数配置."""

from __future__ import annotations

import itertools
from typing import Any

OPTIMAL_PERIOD_RANGES: dict[str, list[int]] = {
    "lookback": [20, 50, 80, 100, 150, 200, 300],
    "history_count": [100, 200, 300, 500, 800, 1000, -1],
}


# 向后兼容：旧代码仍可通过 strategy_id 前缀获取单一参数名
STRATEGY_PARAM_MAP: dict[str, str] = {
    "smart_hot_cold": "lookback",
    "missing_number": "lookback",
    "balanced": "lookback",
    "xgboost": "history_count",
    "lightgbm": "history_count",
    "catboost": "history_count",
}


# 新增：多参数网格扫描配置
STRATEGY_PARAM_GRID: dict[str, dict[str, list]] = {
    "smart_hot_cold_3d": {
        "lookback": [30, 50, 80, 100, 150],
        "hot_weight": [30, 50, 70, 90],
        "cold_weight": [10, 30, 50, 70],
        "temperature": [5, 10, 20],  # 内部除以 10
    },
    "missing_number_3d": {
        "lookback": [30, 50, 80, 100],
        "pool_size": [3, 5, 7],
        "temperature": [5, 10, 20],
    },
    "balanced_3d": {
        "lookback": [50, 80, 100, 150],
        "max_attempts": [500, 1000, 2000],
    },
    "hot_cold_3d": {
        "mode": ["hot", "cold", "mixed"],
        "lookback": [50, 100, 150],
        "temperature": [5, 10, 20],
    },
    "xgboost_3d": {"history_count": [100, 200, 300, 500, -1]},
    "lightgbm_3d": {"history_count": [100, 200, 300, 500, -1]},
    "catboost_3d": {"history_count": [100, 200, 300, 500, -1]},
}


def resolve_optimal_param(strategy_id: str) -> tuple[str, list[int]] | None:
    """根据策略 id 返回要优化的参数名及其扫描范围（向后兼容）."""
    for prefix, param_name in STRATEGY_PARAM_MAP.items():
        if strategy_id.startswith(prefix):
            return param_name, OPTIMAL_PERIOD_RANGES[param_name]
    return None


def resolve_optimal_param_grid(strategy_id: str) -> dict[str, list]:
    """根据策略 id 返回多参数扫描网格。

    返回 dict[param_name, list[values]]。若该策略无网格配置，返回空 dict。
    """
    return STRATEGY_PARAM_GRID.get(strategy_id, {}).copy()


def build_param_combinations(
    grid: dict[str, list], locked: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """根据网格和已锁定参数生成未锁定参数的组合列表。"""
    locked = locked or {}
    free_grid = {k: v for k, v in grid.items() if k not in locked}
    if not free_grid:
        return [{}]
    keys = list(free_grid.keys())
    values = [free_grid[k] for k in keys]
    combos = []
    for combo in itertools.product(*values):
        params = dict(zip(keys, combo))
        params.update(locked)
        combos.append(params)
    return combos
