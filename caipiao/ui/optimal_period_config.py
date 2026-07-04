"""一键找最优期数的参数配置."""

from __future__ import annotations

from typing import List, Tuple


OPTIMAL_PERIOD_RANGES: dict[str, list[int]] = {
    "lookback": [20, 50, 80, 100, 150, 200, 300],
    "history_count": [100, 200, 300, 500, 800, 1000, -1],
}


STRATEGY_PARAM_MAP: dict[str, str] = {
    "smart_hot_cold": "lookback",
    "missing_number": "lookback",
    "balanced": "lookback",
    "xgboost": "history_count",
    "lightgbm": "history_count",
    "catboost": "history_count",
}


def resolve_optimal_param(strategy_id: str) -> Tuple[str, list[int]] | None:
    """根据策略 id 返回要优化的参数名及其扫描范围."""
    for prefix, param_name in STRATEGY_PARAM_MAP.items():
        if strategy_id.startswith(prefix):
            return param_name, OPTIMAL_PERIOD_RANGES[param_name]
    return None
